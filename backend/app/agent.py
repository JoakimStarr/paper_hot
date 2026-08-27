"""简易 AI Agent（PAGE_REDESIGN §9）：OpenAI 兼容 function calling 工具循环。

设计约束：
- 混合策略：一次性产出（报告/单篇分析）保持预聚合；Agent 仅用于多轮追问/深挖。
- 每个工具独立 DB 会话（异常回滚不污染外层）；LIMIT 封顶；max_rounds 防死循环；
  模型不返回合法 tool_calls 时原样返回消息（降级为普通对话）。
"""
import asyncio
import json
import logging
from typing import Any

from sqlalchemy import select as sa_select, String as SAString, or_ as sa_or, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Paper, TopicTrend, PaperScore

logger = logging.getLogger(__name__)

MAX_TOOL_RESULTS_ITEMS = 8
MAX_ROUND_TRIPS = 6


# ---------------------------------------------------------------- 工具实现
# 每个工具拿到独立的只读会话；返回值必须是可 JSON 序列化的 dict。

async def _t_search_papers(db: AsyncSession, args: dict) -> dict:
    """按关键词/年份/期刊检索论文（热度排序）。"""
    kw = str(args.get("keyword") or "").strip()
    if not kw:
        return {"error": "keyword 参数必填"}
    year_from = args.get("year_from")
    year_to = args.get("year_to")
    journal = str(args.get("journal") or "").strip()
    limit = min(int(args.get("limit") or MAX_TOOL_RESULTS_ITEMS), MAX_TOOL_RESULTS_ITEMS)

    conds = [
        sa_or(
            Paper.keywords_cn.cast(SAString).ilike(f"%{kw}%"),
            Paper.title.ilike(f"%{kw}%"),
        )
    ]
    if year_from:
        conds.append(Paper.published_at >= f"{int(year_from)}-01-01")
    if year_to:
        conds.append(Paper.published_at <= f"{int(year_to)}-12-31")
    if journal:
        conds.append(Paper.journal_name.ilike(f"%{journal}%"))

    result = await db.execute(
        sa_select(
            Paper.id, Paper.title, Paper.journal_name, Paper.published_at,
            Paper.keywords_cn, PaperScore.final_score,
        )
        .outerjoin(PaperScore, PaperScore.paper_id == Paper.id)
        .where(*conds)
        .order_by(sa_func.coalesce(PaperScore.final_score, 0).desc(), Paper.published_at.desc())
        .limit(limit)
    )
    items = []
    for pid, title, journal_name, pub, kws, score in result.fetchall():
        items.append({
            "id": pid,
            "title": title,
            "journal": journal_name,
            "published_at": str(pub)[:10] if pub else None,
            "keywords": (kws or [])[:6],
            "score": round(float(score), 3) if score is not None else None,
        })
    return {"total_matched_shown": len(items), "papers": items}


async def _t_paper_trend(db: AsyncSession, args: dict) -> dict:
    """查询关键词的逐年发文计数。"""
    kw = str(args.get("keyword") or "").strip()
    if not kw:
        return {"error": "keyword 参数必填"}

    # 优先读趋势表（年度桶）
    rows = (await db.execute(
        sa_select(TopicTrend.week_start, TopicTrend.paper_count)
        .where(TopicTrend.topic == kw)
        .order_by(TopicTrend.week_start)
    )).fetchall()

    yearly: dict[str, int] = {}
    source = "topic_trends"
    for ws, c in rows:
        y = str(ws)[:4]
        yearly[y] = yearly.get(y, 0) + (c or 0)

    if not yearly:
        # 兜底：直接对 papers 表按年统计
        rows2 = (await db.execute(
            sa_select(
                sa_func.strftime("%Y", Paper.published_at),
                sa_func.count(Paper.id),
            )
            .where(Paper.keywords_cn.cast(SAString).ilike(f"%{kw}%"))
            .group_by(sa_func.strftime("%Y", Paper.published_at))
        )).fetchall()
        yearly = {y: c for y, c in rows2 if y}
        source = "papers_live"

    series = [{"year": y, "count": c} for y, c in sorted(yearly.items())]
    total = sum(yearly.values())
    return {"keyword": kw, "total": total, "source": source, "yearly": series}


async def _t_keyword_gaps(db: AsyncSession, args: dict) -> dict:
    """研究空白组合（共现异常稀疏的高频词对）。"""
    from app.stats import compute_keyword_gaps
    top_n = min(int(args.get("top_n") or 5), 10)
    gaps = await compute_keyword_gaps(db, limit=top_n)
    return {"gaps": gaps}


async def _t_subfield_distribution(db: AsyncSession, args: dict) -> dict:
    """子领域论文分布。"""
    rows = (await db.execute(
        sa_select(Paper.economics_subfield, sa_func.count(Paper.id))
        .where(Paper.economics_subfield.isnot(None))
        .where(Paper.economics_subfield != "")
        .group_by(Paper.economics_subfield)
        .order_by(sa_func.count(Paper.id).desc())
    )).fetchall()
    return {"distribution": [{"subfield": s or "未知", "count": c} for s, c in rows]}


async def _t_author_papers(db: AsyncSession, args: dict) -> dict:
    """按作者名查其论文列表。"""
    author = str(args.get("author") or "").strip()
    limit = min(int(args.get("limit") or MAX_TOOL_RESULTS_ITEMS), MAX_TOOL_RESULTS_ITEMS)
    if not author:
        return {"error": "author 参数必填"}
    rows = (await db.execute(
        sa_select(Paper.id, Paper.title, Paper.published_at, Paper.journal_name)
        .where(Paper.authors.cast(SAString).ilike(f"%{author}%"))
        .order_by(Paper.published_at.desc())
        .limit(limit)
    )).fetchall()
    return {
        "author": author,
        "shown": len(rows),
        "papers": [
            {"id": pid, "title": ti, "published_at": str(pub)[:10] if pub else None, "journal": j}
            for pid, ti, pub, j in rows
        ],
    }


async def _t_retrieve_context(db: AsyncSession, args: dict) -> dict:
    """语义召回：按查询词在论文库中找最相关的论文（含摘要），供回答引用。

    与 search_papers（SQL 关键词命中）互补：适合"该方向研究到哪了/有哪些结论"这类
    需要读论文内容的提问。返回按相似度降序的 top-k，每篇带 [n] 编号与摘要。
    """
    query = str(args.get("query") or "").strip()
    if not query:
        return {"error": "query 参数必填"}
    from app.routers.topic import _retrieve_similar_papers
    k = min(int(args.get("limit") or 6), 10)
    try:
        papers, mode = await _retrieve_similar_papers(db, query, k=k)
    except Exception as e:
        return {"error": f"retrieval failed: {type(e).__name__}"}
    items = []
    for i, p in enumerate(papers, start=1):
        items.append({
            "n": i,
            "id": p.get("id"),
            "title": p.get("title"),
            "abstract": (p.get("abstract") or "")[:600],
            "source": p.get("source"),
            "published_at": p.get("published_at"),
            "similarity": p.get("similarity"),
            "url": f"/paper/{p.get('id')}",
        })
    return {"mode": mode, "count": len(items), "papers": items}


# ---------------------------------------------------------------- 工具注册表

def _schema(name: str, description: str, props: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        },
    }


TOOL_HANDLERS = {
    "search_papers": _t_search_papers,
    "paper_trend": _t_paper_trend,
    "keyword_gaps": _t_keyword_gaps,
    "subfield_distribution": _t_subfield_distribution,
    "author_papers": _t_author_papers,
    "retrieve_context": _t_retrieve_context,
}

TOOL_SCHEMAS_BY_SURFACE: dict[str, list[dict]] = {
    # 全局悬浮助手（跨页面通用）：完整工具集，覆盖论文/趋势/空白/子领域/作者检索
    "assistant_chat": [
        _schema("search_papers", "按关键词/年份/期刊检索论文库中的论文",
                {"keyword": {"type": "string"}, "year_from": {"type": "integer"},
                 "year_to": {"type": "integer"}, "journal": {"type": "string"},
                 "limit": {"type": "integer"}}, ["keyword"]),
        _schema("retrieve_context", "语义召回最相关的论文（含摘要，带 [n] 编号），回答涉及论文内容/结论/方法时使用",
                {"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]),
        _schema("paper_trend", "查询某关键词的逐年发文量趋势",
                {"keyword": {"type": "string"}}, ["keyword"]),
        _schema("keyword_gaps", "获取研究空白组合（高频但共现稀疏的关键词对）",
                {"top_n": {"type": "integer"}}, []),
        _schema("subfield_distribution", "获取经济学子领域论文分布",
                {}, []),
        _schema("author_papers", "按作者名查询其论文列表",
                {"author": {"type": "string"}, "limit": {"type": "integer"}}, ["author"]),
    ],
    # 趋势追问（P0）
    "trend_chat": [
        _schema("search_papers", "按关键词/年份/期刊检索论文库中的论文",
                {"keyword": {"type": "string"}, "year_from": {"type": "integer"},
                 "year_to": {"type": "integer"}, "journal": {"type": "string"},
                 "limit": {"type": "integer"}}, ["keyword"]),
        _schema("retrieve_context", "语义召回最相关的论文（含摘要，带 [n] 编号），回答涉及论文内容/结论/方法时使用",
                {"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]),
        _schema("paper_trend", "查询某关键词的逐年发文量趋势",
                {"keyword": {"type": "string"}}, ["keyword"]),
        _schema("keyword_gaps", "获取研究空白组合（高频但共现稀疏的关键词对）",
                {"top_n": {"type": "integer"}}, []),
        _schema("subfield_distribution", "获取经济学子领域论文分布",
                {}, []),
        _schema("author_papers", "按作者名查询其论文列表",
                {"author": {"type": "string"}, "limit": {"type": "integer"}}, ["author"]),
    ],
    # 单篇论文追问（P0）：在论文自身内容之上，可跨库检索相关文献
    "paper_chat": [
        _schema("search_papers", "按关键词/年份/期刊检索论文库中的论文",
                {"keyword": {"type": "string"}, "year_from": {"type": "integer"},
                 "year_to": {"type": "integer"}, "journal": {"type": "string"},
                 "limit": {"type": "integer"}}, ["keyword"]),
        _schema("retrieve_context", "语义召回最相关的论文（含摘要，带 [n] 编号），回答涉及相关文献/结论/方法时使用",
                {"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]),
        _schema("paper_trend", "查询某关键词的逐年发文量趋势",
                {"keyword": {"type": "string"}}, ["keyword"]),
        _schema("author_papers", "按作者名查询其论文列表",
                {"author": {"type": "string"}, "limit": {"type": "integer"}}, ["author"]),
    ],
}

DEFAULT_MAX_RESULT_CHARS = 3000


def _clip(obj: Any) -> str:
    s = json.dumps(obj, ensure_ascii=False)
    return s[:DEFAULT_MAX_RESULT_CHARS]


# ---------------------------------------------------------------- 执行循环

async def run_agent_chat(
    messages: list[dict],
    client: Any,
    model: str,
    surface: str = "trend_chat",
    max_rounds: int = MAX_ROUND_TRIPS,
    outer_db: AsyncSession | None = None,
    on_progress: Any = None,
) -> tuple[list[dict], list[dict]]:
    """带工具调用循环的对话。

    返回 (messages, tool_trace)：messages 为补全了助手/工具轮次的完整消息，
    可直接交给流式接口做最终回答；tool_trace 供日志/调试。
    若模型未发起任何工具调用，messages 原样返回（普通对话降级）。

    on_progress：可选回调，每次执行工具前调用 on_progress({"tool": name, "args": args})，
    供上层实时推送工具调用进度（SSE 到前端）。
    """
    schemas = TOOL_SCHEMAS_BY_SURFACE.get(surface, [])
    convo = [dict(m) for m in messages]
    trace: list[dict] = []

    # 跨工具统一编号：所有返回论文的工具（含 search_papers/author_papers）都会被编号，
    # 保证回答中的 [n] 引用能映射到唯一论文，且一轮内多次工具调用不产生 n 冲突。
    next_paper_n = 1

    for _round in range(max_rounds):
        try:
            # 注意：client 是 sync OpenAI 客户端（deps.get_ai_client 返回值），
            # 直接 await 其 create() 会抛 TypeError 并被下面的 except 吞掉，
            # 导致 Agent 永远「降级为纯对话」。必须经 to_thread 下放线程池。
            try:
                resp = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=model,
                    messages=convo,
                    tools=schemas or None,
                )
            except Exception as e:
                # 瞬时故障重试一次（如限流/连接中断），避免误降级为纯对话
                logger.warning(f"agent round {_round}: model call failed, retrying once: {e}")
                resp = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=model,
                    messages=convo,
                    tools=schemas or None,
                )
        except Exception as e:
            logger.warning(f"agent round {_round}: model call failed after retry: {e}")
            return messages, trace

        msg = resp.choices[0].message if resp.choices else None
        tool_calls = getattr(msg, "tool_calls", None) if msg else None
        if not tool_calls:
            # 无工具意图：把助手的普通回答并入并结束（由外层决定是否流式重述）
            content = getattr(msg, "content", None) if msg else None
            if content:
                convo.append({"role": "assistant", "content": content})
            logger.info(f"agent surface={surface}: model chose not to call tools, answered directly")
            return convo, trace

        # 记录助手请求工具的消息
        convo.append({
            "role": "assistant",
            "content": getattr(msg, "content", None) or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            if on_progress:
                try:
                    on_progress({"tool": name, "args": args})
                except Exception:
                    pass
            handler = TOOL_HANDLERS.get(name)
            if handler is None:
                result = {"error": f"unknown tool {name}"}
            else:
                tool_db = None
                try:
                    async with AsyncSessionLocal() as session:
                        tool_db = session
                        result = await handler(session, args)
                except Exception as e:
                    logger.warning(f"agent tool {name} failed: {e}")
                    if tool_db is not None:
                        await tool_db.rollback()
                    result = {"error": f"tool execution failed: {type(e).__name__}"}

            # 给工具结果里的论文统一编号 + 补 url（模型在 tool 内容里看到的就是这些编号）
            if isinstance(result, dict) and isinstance(result.get("papers"), list):
                for p in result["papers"]:
                    if isinstance(p, dict):
                        p["n"] = next_paper_n
                        next_paper_n += 1
                        if p.get("id") and not p.get("url"):
                            p["url"] = f"/paper/{p['id']}"

            trace.append({"tool": name, "args": args, "result": result})
            convo.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": _clip(result),
            })

    logger.warning("agent reached max rounds; falling back to plain answer")
    return messages, trace
