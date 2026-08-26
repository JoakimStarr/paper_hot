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


def _stream_chat_response(client, provider: str, messages: list, model: Optional[str] = None):
    """统一的 SSE 流式对话。所有 provider 均为 OpenAI 兼容接口，
    思考型模型的 reasoning_content 与正文 content 都会转发给前端。"""
    if not model:
        model = _get_default_model(provider)

    async def event_generator():
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
