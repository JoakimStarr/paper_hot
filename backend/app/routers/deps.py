"""共享依赖与工具函数（各 router 模块公用）。"""
import asyncio
import concurrent.futures
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import Header, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse  # noqa: F401

from app.config import settings
from app.ai_service import ai_trend_service
from app.schemas import PaperCardResponse

logger = logging.getLogger(__name__)

_shared_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)


async def verify_token(x_api_token: str = Header(default=None)):
    if settings.api_token and settings.api_token != "":
        if x_api_token is None or not hmac.compare_digest(x_api_token, settings.api_token):
            raise HTTPException(status_code=401, detail="Invalid or missing API token")
    return True


def _get_ai_client(provider: Optional[str] = None):
    """获取指定 provider 的 AI 客户端（均为 OpenAI 兼容客户端）；provider 为空时按默认优先级选择。"""
    try:
        return ai_trend_service.get_client(provider)
    except KeyError:
        if provider:
            raise HTTPException(status_code=503, detail=f"AI provider '{provider}' is not configured or initialized.")
        raise HTTPException(status_code=503, detail="No AI provider configured. Please set an API key in Settings.")


def _resolve_model_provider(model: Optional[str]):
    """将模型名解析为 (provider, bare_model)。兼容 'provider/model' 与裸模型名。"""
    if not model:
        return None, None
    return ai_trend_service._resolve_model(model)


def _get_default_model(provider: str) -> Optional[str]:
    """取该 provider 的默认模型。

    若设置了全局 default_model（'provider/model'）且属于该 provider，则优先返回它；
    否则回退到该 provider 优先级列表第一位。
    """
    global_default = getattr(settings, "default_model", None)
    if global_default:
        provider_part, _, bare = global_default.partition("/")
        if provider_part and provider_part == provider and bare:
            models = ai_trend_service.models.get(provider) or []
            if bare in models:
                return bare
    models = ai_trend_service.models.get(provider) or []
    return models[0] if models else None


def _stream_chat_response(client, provider: str, messages: list, model: Optional[str] = None,
                          meta_events: Optional[list[dict]] = None):
    """统一的 SSE 流式对话。所有 provider 均为 OpenAI 兼容接口，
    思考型模型的 reasoning_content 与正文 content 都会转发给前端。

    meta_events：正文流开始前先发射的结构化事件（如 Agent 工具调用轨迹 / 检索到的论文），
    前端经 streamChat 的 onMeta 回调接收。
    """
    if not model:
        model = _get_default_model(provider)

    async def event_generator():
        for ev in (meta_events or []):
            yield f"data: {json.dumps(ev)}\n\n"
        async for frame in _stream_llm_content(client, model, messages):
            yield frame

    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def _stream_llm_content(client, model: str, messages: list):
    """流式拉取 LLM 正文/reasoning 的异步生成器（SSE 帧），供各流式接口复用。"""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    timeout_seconds = 120

    def run_stream():
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                max_tokens=4096,
            )
            for chunk in response:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    content = getattr(delta, "content", None)
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning:
                        loop.call_soon_threadsafe(queue.put_nowait, ("reasoning", reasoning))
                    if content:
                        loop.call_soon_threadsafe(queue.put_nowait, ("content", content))
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", str(e)))
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

    future = _shared_executor.submit(run_stream)
    start_time = time.time()

    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    logger.warning(f"Stream timeout after {timeout_seconds}s")
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    break
                continue

            msg_type, msg_content = item
            if msg_type == "done":
                yield f"data: {json.dumps({'done': True})}\n\n"
                break
            elif msg_type == "error":
                yield f"data: {json.dumps({'content': f'[ERROR] {msg_content}'})}\n\n"
            elif msg_type == "reasoning":
                yield f"data: {json.dumps({'reasoning': msg_content})}\n\n"
            elif msg_type == "content":
                yield f"data: {json.dumps({'content': msg_content})}\n\n"
    finally:
        # 客户端断开（生成器被关闭）时取消后台拉流任务，避免继续消耗 LLM token
        future.cancel()


def _stream_agent_chat_response(client, provider: str, messages: list, model: Optional[str] = None,
                                surface: str = "trend_chat",
                                agent_enabled: Optional[bool] = None):
    """追问 SSE：默认跑 Agent 工具循环（实时推送工具调用进度 → 工具轨迹 → 正文）；
    当 Agent 关闭时退化为普通对话——不调用任何工具，直接流式输出回答。

    agent_enabled：请求级覆盖（悬浮助手"检索数据库"开关）。为 None 时使用全局 settings.agent_enabled。
    """
    from app.agent import run_agent_chat

    if not model:
        model = _get_default_model(provider)

    enabled = agent_enabled if agent_enabled is not None else settings.agent_enabled

    async def event_generator():
        # Agent 开关关闭：普通追问，无检索、无工具轨迹/进度
        if not enabled:
            async for frame in _stream_llm_content(client, model, messages):
                yield frame
            return

        progress_q: asyncio.Queue = asyncio.Queue()
        box: dict = {"messages": messages, "trace": []}

        async def _run_agent():
            try:
                msgs, trace = await run_agent_chat(
                    messages, client, model, surface=surface,
                    on_progress=progress_q.put_nowait,
                )
                box["messages"] = msgs
                box["trace"] = trace
            except Exception as e:
                logger.warning(f"agent loop failed, fallback to plain chat: {e}")
            finally:
                # 结束哨兵（put_nowait：任务被取消时也能安全退出循环）
                progress_q.put_nowait(None)

        task = asyncio.create_task(_run_agent())
        try:
            while True:
                ev = await progress_q.get()
                if ev is None:
                    break
                yield f"data: {json.dumps({'tool_progress': ev})}\n\n"
            await task
        finally:
            if not task.done():
                task.cancel()

        if box["trace"]:
            yield f"data: {json.dumps({'tools': _compact_agent_trace(box['trace'])})}\n\n"
        async for frame in _stream_llm_content(client, model, box["messages"]):
            yield frame

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _clean_author_name(name: str) -> str:
    import re
    name = name.strip().rstrip(',').rstrip('，').strip()
    name = re.sub(r'[\w.+-]+@[\w.+-]+', '', name)
    name = re.sub(r'@\.com', '', name)
    name = re.sub(r'\s+', '', name)
    return name

def _parse_json_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean_author_name(str(v)) for v in value if v and str(v).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [_clean_author_name(str(v)) for v in parsed if v and str(v).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _compact_agent_trace(trace: list) -> list[dict]:
    """把 Agent 工具调用轨迹压缩成可发给前端展示的结构（工具名/参数/检索到的论文卡片）。"""
    out: list[dict] = []
    for t in trace or []:
        item: dict = {"tool": t.get("tool"), "args": t.get("args", {})}
        result = t.get("result")
        if isinstance(result, dict) and result.get("papers"):
            item["papers"] = [
                {
                    "n": p.get("n"),
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "url": p.get("url") or (f"/paper/{p.get('id')}" if p.get("id") else None),
                    "source": p.get("source"),
                    "published_at": p.get("published_at"),
                    "similarity": p.get("similarity"),
                }
                for p in result["papers"][:10]
            ]
        out.append(item)
    return out


def _isoformat_utc(dt: datetime) -> str:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _paper_to_card(paper) -> PaperCardResponse:
    return PaperCardResponse(
        id=paper.id,
        title=paper.title,
        abstract=paper.abstract,
        authors=_parse_json_list(paper.authors),
        url=paper.url,
        source=paper.source,
        venue=paper.venue,
        journal_name=paper.journal_name,
        journal_issue=paper.journal_issue,
        economics_subfield=paper.economics_subfield,
        cnki_subject=paper.cnki_subject,
        doi=paper.doi,
        keywords_cn=_parse_json_list(paper.keywords_cn),
        published_at=paper.published_at,
        topic=paper.features.topic if paper.features else None,
        recency_score=paper.scores.recency_score if paper.scores else 0.0,
        venue_score=paper.scores.venue_score if paper.scores else 0.0,
        trend_score=paper.scores.trend_score if paper.scores else 0.0,
        final_score=paper.scores.final_score if paper.scores else 0.0,
        created_at=paper.created_at
    )


def _compute_cache_key(prefix: str, total: int, page: int, page_size: int, **filters) -> str:
    # 筛选/排序参数必须参与 ETag，否则同一页数下不同筛选会错误命中 304 拿到旧数据
    filter_str = "&".join(f"{k}={v}" for k, v in sorted(filters.items()) if v is not None)
    return hashlib.md5(f"{prefix}:{total}:{page}:{page_size}:{filter_str}".encode()).hexdigest()




async def _safe_query(db, coro, default):
    """PERF_PLAN 1.2：容错查询统一 helper（P0 会话卫生）。

    异常时先回滚会话（防止 PendingRollbackError 使后续查询整请求 500），
    再降级返回 default，并以 warning 日志保留首因。
    """
    import logging
    try:
        return await coro
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        logging.getLogger(__name__).warning("_safe_query: query failed, rolled back", exc_info=True)
        return default
