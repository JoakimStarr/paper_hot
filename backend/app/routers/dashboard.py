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
from sqlalchemy import select as sa_select, desc as sa_desc, func as sa_func, or_ as sa_or
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cache_util import ttl_cache
from app.database import get_db
from app.models import (
    Paper, PaperScore, PaperFeatures, Favorite, ReadingHistory, TopicProject,
    AIAnalysisReport, PaperAnalysis, FollowedSubfield, FollowedKeyword, TopicTrend,
    ReviewReport,
)
from app.crud import _hidden_paper_condition
from app.routers.personal import _load_hidden_preferences
from app.routers.deps import (
    verify_token, _paper_to_card, _isoformat_utc,
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


async def _build_user_profile_vector(db: AsyncSession, uid: str) -> Optional[List[float]]:
    """基于用户收藏+阅读历史构建画像向量（加权平均，收藏权重 2x 阅读）。

    结果按 (uid) 缓存 10 分钟，避免每次 dashboard 请求重新计算。
    无行为数据或 embedding 不可用时返回 None（降级为纯分数排序）。
    """
    cache_key = f"today_read:profile:{uid}"

    async def _compute():
        import json as _json

        # 收集 paper_id：收藏 20 篇 + 阅读 20 篇（去重）
        fav_ids, read_ids = [], []
        for model, limit in ((Favorite, 20), (ReadingHistory, 20)):
            rows = (
                await db.execute(
                    sa_select(model.paper_id)
                    .where(model.user_id == uid)
                    .order_by(model.id.desc())
                    .limit(limit)
                )
            ).all()
            if model is Favorite:
                fav_ids = [r[0] for r in rows]
            else:
                read_ids = [r[0] for r in rows]

        # 加权合并：收藏出现的 paper_id 权重 2.0，阅读 1.0
        weight_map: dict = {}
        for pid in read_ids:
            weight_map[pid] = weight_map.get(pid, 0) + 1.0
        for pid in fav_ids:
            weight_map[pid] = weight_map.get(pid, 0) + 2.0

        if not weight_map:
            return None

        # 查 embedding
        all_ids = list(weight_map.keys())
        rows = (
            await db.execute(
                sa_select(PaperFeatures.paper_id, PaperFeatures.embedding)
                .where(PaperFeatures.paper_id.in_(all_ids))
                .where(PaperFeatures.embedding.isnot(None))
            )
        ).all()

        if not rows:
            return None

        import numpy as np

        vec_sum = None
        total_weight = 0.0
        for pid, emb_str in rows:
            try:
                vec = np.asarray(_json.loads(emb_str), dtype=np.float64)
                if vec.ndim != 1 or vec.size == 0:
                    continue
                w = weight_map.get(pid, 1.0)
                vec_sum = vec * w if vec_sum is None else vec_sum + vec * w
                total_weight += w
            except Exception:
                continue

        if vec_sum is None or total_weight == 0:
            return None

        avg = vec_sum / total_weight
        norm = np.linalg.norm(avg)
        if norm == 0:
            return None
        return (avg / norm).tolist()

    return await ttl_cache(cache_key, 600, _compute)


async def _embedding_recall_for_dashboard(
    db: AsyncSession, query_vec: List[float], k: int = 20
) -> List[str]:
    """用 FAISS 召回与用户画像最相似的 k 篇论文 ID。"""
    from app.vector_index import search as faiss_search

    try:
        ids, _scores = await faiss_search(db, query_vec, k)
        return ids
    except Exception as e:
        logger.warning(f"dashboard FAISS recall failed: {e}")
        return []


def _diversity_filter(papers: List[Paper], max_sim: float = 0.92) -> List[Paper]:
    """多样性约束：相邻论文 embedding 余弦相似度 > max_sim 时跳过，从后续候选补入。"""
    import json as _json

    selected: List[Paper] = []
    selected_vecs: List = []

    for p in papers:
        if not p.features or not p.features.embedding:
            selected.append(p)
            continue
        try:
            vec = _json.loads(p.features.embedding)
            if not vec:
                selected.append(p)
                continue
        except Exception:
            selected.append(p)
            continue

        import numpy as np

        v = np.asarray(vec, dtype=np.float32)
        norm = np.linalg.norm(v)
        if norm == 0:
            selected.append(p)
            continue
        v = v / norm

        too_similar = False
        for sv in selected_vecs:
            sim = float(np.dot(v, sv))
            if sim > max_sim:
                too_similar = True
                break
        if not too_similar:
            selected.append(p)
            selected_vecs.append(v)

    return selected


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

    # ---- 关注关键词：驱动"今日值得读"关键词召回 ----
    kw_result = await db.execute(
        sa_select(FollowedKeyword.keyword).where(FollowedKeyword.user_id == uid)
    )
    followed_keywords = [r[0] for r in kw_result.all()]

    # ---- "不感兴趣"屏蔽（P2）：工作台推荐同样全局过滤，命中任一屏蔽项的论文不出现 ----
    hidden: dict = {}
    try:
        hidden = await _load_hidden_preferences(db, uid)
    except Exception:
        hidden = {}

    return {
        "today_read": await _today_read(db, uid, followed_subfields, followed_keywords, hidden),
        "briefing": await _briefing(db),
        "mine": await _mine(db, uid, has_followed=bool(followed_subfields)),
    }


async def _today_read(
    db: AsyncSession,
    uid: str,
    followed_subfields: List[str],
    followed_keywords: List[str],
    hidden: Optional[dict] = None,
) -> List[dict]:
    """今日值得读：向量召回 + 综合评分混排，多样性约束去重，共 6 篇。

    四路候选合并：
    1. 向量召回：用户画像向量 FAISS 检索语义相似论文（最多 10 篇）
    2. 子领域匹配：关注子领域按 final_score 降序（最多 4 篇）
    3. 关键词匹配：关注关键词按 final_score 降序（最多 4 篇）
    4. 全局高分：全库 final_score 降序补位

    合并后统一按 final_score 排序，再过多样性过滤（embedding 余弦 > 0.92 跳过）。
    """
    hidden_cond = _hidden_paper_condition(hidden or {})
    existing_ids: set = set()
    candidates: List[Paper] = []

    # ---- 路线 1：向量召回（用户画像相似） ----
    try:
        profile_vec = await _build_user_profile_vector(db, uid)
        if profile_vec:
            recall_ids = await _embedding_recall_for_dashboard(db, profile_vec, k=10)
            if recall_ids:
                where = [Paper.id.in_(recall_ids)]
                if hidden_cond is not None:
                    where.append(hidden_cond)
                result = await db.execute(
                    sa_select(Paper)
                    .options(selectinload(Paper.features), selectinload(Paper.scores))
                    .join(PaperScore, PaperScore.paper_id == Paper.id)
                    .where(*where)
                    .order_by(sa_desc(PaperScore.final_score))
                    .limit(10)
                )
                for p in result.scalars().all():
                    if p.id not in existing_ids:
                        candidates.append(p)
                        existing_ids.add(p.id)
    except Exception as e:
        logger.warning(f"embedding recall in today_read failed: {e}")

    # ---- 路线 2：子领域匹配（关注方向优先） ----
    if followed_subfields:
        where = [Paper.economics_subfield.in_(followed_subfields)]
        if hidden_cond is not None:
            where.append(hidden_cond)
        result = await db.execute(
            sa_select(Paper)
            .options(selectinload(Paper.features), selectinload(Paper.scores))
            .join(PaperScore, PaperScore.paper_id == Paper.id)
            .where(*where)
            .order_by(sa_desc(PaperScore.final_score))
            .limit(6)
        )
        for p in result.scalars().all():
            if p.id not in existing_ids:
                candidates.append(p)
                existing_ids.add(p.id)

    # ---- 路线 3：关键词匹配（关注关键词） ----
    if followed_keywords:
        from sqlalchemy import text as sa_text

        kw_placeholders = ", ".join(f":fk{i}" for i in range(len(followed_keywords)))
        kw_params = {f"fk{i}": kw for i, kw in enumerate(followed_keywords)}
        kw_subq = (
            sa_select(sa_text("p.id"))
            .select_from(sa_text("papers p, json_each(p.keywords_cn)"))
            .where(sa_text(f"json_each.value IN ({kw_placeholders})"))
            .params(**kw_params)
        )
        where = [Paper.id.in_(kw_subq)]
        if hidden_cond is not None:
            where.append(hidden_cond)
        result = await db.execute(
            sa_select(Paper)
            .options(selectinload(Paper.features), selectinload(Paper.scores))
            .join(PaperScore, PaperScore.paper_id == Paper.id)
            .where(*where)
            .order_by(sa_desc(PaperScore.final_score))
            .limit(6)
        )
        for p in result.scalars().all():
            if p.id not in existing_ids:
                candidates.append(p)
                existing_ids.add(p.id)

    # ---- 路线 4：全局高分补位 ----
    remaining = 20 - len(candidates)
    if remaining > 0:
        query = (
            sa_select(Paper)
            .options(selectinload(Paper.features), selectinload(Paper.scores))
            .join(PaperScore, PaperScore.paper_id == Paper.id)
        )
        if hidden_cond is not None:
            query = query.where(hidden_cond)
        result = await db.execute(
            query.order_by(sa_desc(PaperScore.final_score)).limit(remaining)
        )
        for p in result.scalars().all():
            if p.id not in existing_ids:
                candidates.append(p)
                existing_ids.add(p.id)

    # ---- 精排：按 final_score 降序 ----
    candidates.sort(
        key=lambda p: (p.scores.final_score if p.scores else 0.0),
        reverse=True,
    )

    # ---- 多样性过滤：相邻论文 embedding 余弦 > 0.92 跳过 ----
    diversified = _diversity_filter(candidates, max_sim=0.92)

    return [_paper_to_card(p) for p in diversified[:6]]


async def _briefing(db: AsyncSession) -> dict:
    """领域快讯：热点趋势 Top 5（复用 TopicTrend）+ 一句话结论。

    注意：TopicTrend.week_start 存「年份桶」（当年1月1日，CNKI 半数论文仅有年份精度），
    按自然周/月窗口过滤会在每年 2 月后恒返回空——这里取最近 3 个年份桶作为窗口。
    """
    recent_buckets = (
        await db.execute(
            sa_select(TopicTrend.week_start)
            .distinct()
            .order_by(sa_desc(TopicTrend.week_start))
            .limit(3)
        )
    ).scalars().all()

    if not recent_buckets:
        return {"topics": [], "ai_note": None}

    result = await db.execute(
        sa_select(TopicTrend)
        .where(TopicTrend.week_start.in_(recent_buckets))
        .order_by(sa_desc(TopicTrend.growth_rate))
        .limit(5)
    )
    total_result = await db.execute(
        sa_select(TopicTrend.topic, TopicTrend.paper_count)
        .where(TopicTrend.week_start.in_(recent_buckets))
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

    # 最近文献综述（producer 生成，按用户隔离；随记录带上其引用的论文数）
    review_rows = await db.execute(
        sa_select(ReviewReport)
        .where(
            sa_or(ReviewReport.user_id == uid, ReviewReport.user_id == "local"),
            ReviewReport.status == "success",
        )
        .order_by(sa_desc(ReviewReport.created_at))
        .limit(5)
    )
    reviews = [
        {
            "id": r.id,
            "topic": r.topic,
            "paper_count": len(r.papers_json or []),
            "created_at": _isoformat_utc(r.created_at),
        }
        for r in review_rows.scalars()
    ]

    return {
        "favorites": fav_papers,
        "recent_analyses": recent_analyses,
        "topic_projects": proj_out,
        "reviews": reviews,
        "latest_report_summary": report.summary if report else None,
        "latest_report_id": report.id if report else None,
        "favorite_count": len(fav_papers),
        "has_followed_subfields": has_followed,
    }


# ---------- 今日速览（首页速览条数据源）：60s 进程内缓存 ----------

_TODAY_BRIEF_TTL_SECONDS = 60


async def _build_today_brief(db: AsyncSession, uid: str) -> dict:
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now - timedelta(days=30)

    # 速览条展示「新发表」论文数，按论文发表时间 published_at 统计
    today_count = (
        await db.execute(
            sa_select(sa_func.count())
            .select_from(Paper)
            .where(Paper.published_at >= today_start)
        )
    ).scalar() or 0

    month_count = (
        await db.execute(
            sa_select(sa_func.count())
            .select_from(Paper)
            .where(Paper.published_at >= month_start)
        )
    ).scalar() or 0

    # 关注子领域：personal 偏好里的 FollowedSubfield；未关注任何子领域时返回 null
    watch_subfield_count: Optional[int] = None
    followed = await db.execute(
        sa_select(FollowedSubfield.subfield).where(FollowedSubfield.user_id == uid)
    )
    subfields = [r[0] for r in followed.all()]
    if subfields:
        watch_subfield_count = (
            await db.execute(
                sa_select(sa_func.count())
                .select_from(Paper)
                .where(
                    Paper.economics_subfield.in_(subfields),
                    Paper.published_at >= month_start,
                )
            )
        ).scalar() or 0

    return {
        "today_count": int(today_count),
        "month_count": int(month_count),
        "watch_subfield_count": watch_subfield_count,
        "generated_at": now.isoformat(),
    }


@router.get("/dashboard/today-brief")
async def get_today_brief(
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """今日速览：今日/近一个月新发表论文数 + 关注子领域近一个月数（60s TTL 缓存，按用户隔离）。"""
    uid = _uid(x_user_id)

    async def _compute() -> dict:
        return await _build_today_brief(db, uid)

    return await ttl_cache(f"today-brief:{uid}", _TODAY_BRIEF_TTL_SECONDS, _compute)