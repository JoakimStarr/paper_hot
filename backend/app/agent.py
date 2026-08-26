"""简易 AI Agent（PAGE_REDESIGN §9）：OpenAI 兼容 function calling 工具循环。

设计约束：
- 混合策略：一次性产出（报告/单篇分析）保持预聚合；Agent 仅用于多轮追问/深挖。
- 每个工具独立 DB 会话（异常回滚不污染外层）；LIMIT 封顶；max_rounds 防死循环；
  模型不返回合法 tool_calls 时原样返回消息（降级为普通对话）。
"""
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
}

TOOL_SCHEMAS_BY_SURFACE: dict[str, list[dict]] = {
    # 趋势追问（P0）
    "trend_chat": [
        _schema("search_papers", "按关键词/年份/期刊检索论文库中的论文",
                {"keyword": {"type": "string"}, "year_from": {"type": "integer"},
                 "year_to": {"type": "integer"}, "journal": {"type": "string"},
                 "limit": {"type": "integer"}}, ["keyword"]),
        _schema("paper_trend", "查询某关键词的逐年发文量趋势",
                {"keyword": {"type": "string"}}, ["keyword"]),
        _schema("keyword_gaps", "获取研究空白组合（高频但共现稀疏的关键词对）",
                {"top_n": {"type": "integer"}}, []),
        _schema("subfield_distribution", "获取经济学子领域论文分布",
                {}, []),
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
) -> tuple[list[dict], list[dict]]:
    """带工具调用循环的对话。

    返回 (messages, tool_trace)：messages 为补全了助手/工具轮次的完整消息，
    可直接交给流式接口做最终回答；tool_trace 供日志/调试。
    若模型未发起任何工具调用，messages 原样返回（普通对话降级）。
    """
    schemas = TOOL_SCHEMAS_BY_SURFACE.get(surface, [])
    convo = [dict(m) for m in messages]
    trace: list[dict] = []

    for _round in range(max_rounds):
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=convo,
                tools=schemas or None,
            )
        except Exception as e:
            logger.warning(f"agent round {_round}: model call failed: {e}")
            return messages, trace

        msg = resp.choices[0].message if resp.choices else None
        tool_calls = getattr(msg, "tool_calls", None) if msg else None
        if not tool_calls:
            # 无工具意图：把助手的普通回答并入并结束（由外层决定是否流式重述）
            content = getattr(msg, "content", None) if msg else None
            if content:
                convo.append({"role": "assistant", "content": content})
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
            handler = TOOL_HANDLERS.get(name)
            if handler is None:
                result = {"error": f"unknown tool {name}"}
            else:
                try:
                    async with AsyncSessionLocal() as tool_db:
                        result = await handler(tool_db, args)
                except Exception as e:
                    logger.warning(f"agent tool {name} failed: {e}")
                    await tool_db.rollback()
                    result = {"error": f"tool execution failed: {type(e).__name__}"}

            trace.append({"tool": name, "args": args})
            convo.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": _clip(result),
            })

    logger.warning("agent reached max rounds; falling back to plain answer")
    return messages, trace
