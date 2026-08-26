"""研究工作台（P1-7）：产品主入口，替换"打开就是列表"的首页体验。

一页回答三个问题：
- 今日值得读：按综合评分（+关注子领域优先）推荐 5 篇
- 领域快讯：热点趋势 Top 5 + 一句话 LLM 结论（AI 不可用时降级为纯数据）
- 我的研究栈：收藏、最近分析、最近验证的选题
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select as sa_select, desc as sa_desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import (
    Paper, PaperScore, Favorite, ReadingHistory, TopicProject,
    AIAnalysisReport, PaperAnalysis, FollowedSubfield, TopicTrend,
)
from app.crud import _hidden_paper_condition
from app.routers.personal import _load_hidden_preferences
from app.routers.deps import (
    verify_token, _paper_to_card,
    _get_ai_client, _resolve_model_provider, _get_default_model,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# 领域快讯 AI 一句话结论：LLM 每次 Dashboard 都调太贵，做 1 小时缓存 + 降级兜底
_briefing_ai_cache: dict = {"ts": None, "note": None}
_BRIEFING_AI_TTL = timedelta(hours=1)


def _uid(x_user_id: Optional[str]) -> str:
    return (x_user_id or "").strip() or "local"


async def _briefing_ai_note(topics: List[str]) -> Optional[str]:
    """用 LLM 给 Top 热点生成一句话领域结论；AI 不可用时返回 None（纯数据降级）。"""
    if not topics:
        return None
    now = datetime.now()
    cached = _briefing_ai_cache
    if cached["note"] and cached["ts"] and (now - cached["ts"]) < _BRIEFING_AI_TTL:
        return cached["note"]
    try:
        provider, bare_model = _resolve_model_provider(None)
        client, provider = _get_ai_client(provider)
        if not bare_model:
            bare_model = _get_default_model(provider)
        prompt = (
            "近期经管研究的热点依次为：" + "、".join(topics[:5])
            + "。请用一句中文（40 字以内）概括这一波研究动向，并点出最值得切入的空白。"
        )
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model=bare_model,
            messages=[
                {"role": "system", "content": "你是经管研究选题顾问，回答精炼，只说一句话结论。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=100,
            temperature=0.5,
        )
        note = (resp.choices[0].message.content or "").strip() or None
        cached["ts"] = now
        cached["note"] = note
        return note
    except Exception as e:
        logger.warning(f"dashboard ai_note generation failed: {e}")
        cached["ts"] = now
        cached["note"] = None
        return None


@router.get("/dashboard")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    uid = _uid(x_user_id)

    # ---- 关注子领域：决定"今日值得读"是否个性化 ----
    followed = await db.execute(
        sa_select(FollowedSubfield.subfield)
        .where(FollowedSubfield.user_id == uid)
    )
    followed_subfields = [r[0] for r in followed.all()]

    # ---- "不感兴趣"屏蔽（P2）：工作台推荐同样全局过滤，命中任一屏蔽项的论文不出现 ----
    hidden: dict = {}
    try:
        hidden = await _load_hidden_preferences(db, uid)
    except Exception:
        hidden = {}

    return {
        "today_read": await _today_read(db, followed_subfields, hidden),
        "briefing": await _briefing(db),
        "mine": await _mine(db, uid, has_followed=bool(followed_subfields)),
    }


async def _today_read(db: AsyncSession, followed_subfields: List[str], hidden: Optional[dict] = None) -> List[dict]:
    """今日值得读：综合评分 top 6；关注了子领域则优先保证覆盖关注方向；全部过滤"不感兴趣"项。"""
    papers: List[Paper] = []
    hidden_cond = _hidden_paper_condition(hidden or {})

    if followed_subfields:
        where = [Paper.economics_subfield.in_(followed_subfields)] + ([hidden_cond] if hidden_cond is not None else [])
        result = await db.execute(
            sa_select(Paper)
            .options(selectinload(Paper.features), selectinload(Paper.scores))
            .join(PaperScore, PaperScore.paper_id == Paper.id)
            .where(*where)
            .order_by(sa_desc(PaperScore.final_score))
            .limit(4)
        )
        papers = list(result.scalars().all())

    remaining = 6 - len(papers)
    if remaining > 0:
        query = (
            sa_select(Paper)
            .options(selectinload(Paper.features), selectinload(Paper.scores))
            .join(PaperScore, PaperScore.paper_id == Paper.id)
        )
        if hidden_cond is not None:
            query = query.where(hidden_cond)
        result = await db.execute(
            query
            .order_by(sa_desc(PaperScore.final_score))
            .limit(remaining + 20)
        )
        top = list(result.scalars().all())
        existing_ids = {p.id for p in papers}
        for p in top:
            if p.id not in existing_ids:
                papers.append(p)
                existing_ids.add(p.id)
            if len(papers) >= 6:
                break

    return [_paper_to_card(p) for p in papers]


async def _briefing(db: AsyncSession) -> dict:
    """领域快讯：热点趋势 Top 5（复用 TopicTrend）+ 一句话结论。"""
    cutoff = datetime.now() - timedelta(weeks=8)
    result = await db.execute(
        sa_select(TopicTrend)
        .where(TopicTrend.week_start >= cutoff)
        .order_by(sa_desc(TopicTrend.growth_rate))
        .limit(5)
    )
    total_result = await db.execute(
        sa_select(TopicTrend.topic, TopicTrend.paper_count)
        .where(TopicTrend.week_start >= cutoff)
    )
    stats = {row[0]: row[1] for row in total_result.all()}

    topics = []
    for trend in result.scalars():
        trend_status = "rising" if trend.growth_rate > 0.2 else ("declining" if trend.growth_rate < -0.1 else "stable")
        topics.append({
            "topic": trend.topic,
            "paper_count": stats.get(trend.topic, trend.paper_count),
            "growth_rate": trend.growth_rate,
            "trend": trend_status,
        })
    # P0 遗留#4：调用 LLM 生成一句话领域结论（带 1h 缓存，AI 不可用时降级为 None）
    ai_note = await _briefing_ai_note([t["topic"] for t in topics])
    return {"topics": topics, "ai_note": ai_note}


async def _mine(db: AsyncSession, uid: str, has_followed: bool = False) -> dict:
    """我的研究栈：最近分析 + 最近验证选题 + 收藏数/已读数。"""
    fav_ids = []
    for model in (Favorite, ReadingHistory):
        result = await db.execute(
            sa_select(model.paper_id).where(model.user_id == uid).order_by(model.id.desc()).limit(200)
        )
        fav_ids.extend(r[0] for r in result.all())

    fav_papers = []
    if fav_ids:
        presult = await db.execute(
            sa_select(Paper)
            .options(selectinload(Paper.features), selectinload(Paper.scores))
            .where(Paper.id.in_(fav_ids))
        )
        fav_papers = [_paper_to_card(p) for p in presult.scalars().all()][:8]

    # 最近分析（paper_analyses 最新 5 条，附带论文标题）
    recent_analyses = []
    try:
        an_result = await db.execute(
            sa_select(PaperAnalysis.paper_id, PaperAnalysis.status, PaperAnalysis.created_at)
            .order_by(sa_desc(PaperAnalysis.created_at))
            .limit(5)
        )
        an_rows = an_result.all()
        if an_rows:
            ap_ids = [r[0] for r in an_rows]
            tresult = await db.execute(
                sa_select(Paper.id, Paper.title).where(Paper.id.in_(ap_ids))
            )
            title_map = {r[0]: r[1] for r in tresult.all()}
            for pid, status, created in an_rows:
                recent_analyses.append({
                    "paper_id": pid,
                    "title": title_map.get(pid, ""),
                    "status": status,
                    "created_at": str(created) if created else None,
                })
    except Exception as e:
        logger.warning(f"recent_analyses failed: {e}")

    # 进行中的选题（非 abandoned）
    projects = await db.execute(
        sa_select(TopicProject)
        .where(TopicProject.user_id == uid, TopicProject.status != "abandoned")
        .order_by(sa_desc(TopicProject.updated_at))
        .limit(5)
    )
    proj_out = []
    for p in projects.scalars():
        proj_out.append({
            "id": p.id,
            "title": p.title,
            "status": p.status,
            "novelty": p.novelty,
            "crowding": p.crowding,
        })

    # 最近成功报告
    latest_report = await db.execute(
        sa_select(AIAnalysisReport)
        .where(AIAnalysisReport.status == "success")
        .order_by(sa_desc(AIAnalysisReport.created_at))
        .limit(1)
    )
    report = latest_report.scalar_one_or_none()

    return {
        "favorites": fav_papers,
        "recent_analyses": recent_analyses,
        "topic_projects": proj_out,
        "latest_report_summary": report.summary if report else None,
        "latest_report_id": report.id if report else None,
        "favorite_count": len(fav_papers),
        "has_followed_subfields": has_followed,
    }