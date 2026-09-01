"""研究工作台（P1-7）：产品主入口，替换"打开就是列表"的首页体验。

一页回答三个问题：
- 今日值得读：按综合评分（+关注子领域优先）推荐 5 篇
- 领域快讯：热点趋势 Top 5 + 一句话 LLM 结论（AI 不可用时降级为纯数据）
- 我的研究栈：收藏、最近分析、最近验证的选题
"""
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List, Optional, Union

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select as sa_select, desc as sa_desc, func as sa_func, or_ as sa_or, case as sa_case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cache_util import ttl_cache
from app.database import get_db
from app.models import (
    Paper, PaperScore, PaperFeatures, Favorite, ReadingHistory, TopicProject,
    AIAnalysisReport, PaperAnalysis, FollowedSubfield, FollowedKeyword, TopicTrend,
    ReviewReport, ProjectPaper, PaperKeyword, UserEvent,
)
from app.crud import _hidden_paper_condition
from app.routers.personal import _load_hidden_preferences
from app.routers.deps import (
    verify_token, _paper_to_card, _isoformat_utc,
    _get_ai_client, _resolve_model_provider, _get_default_model,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# 领域快讯 AI 一句话结论：LLM 每次 Dashboard 都调太贵，做 1 小时缓存 + 降级兜底；
# 失败时 5 分钟内不重试，避免 AI 故障期间每个请求都打一次 LLM。
_briefing_ai_cache: dict = {"ts": None, "note": None, "failed_at": None}
_BRIEFING_AI_TTL = timedelta(hours=1)
_BRIEFING_AI_FAIL_TTL = timedelta(minutes=5)


def _uid(x_user_id: Optional[str]) -> str:
    return (x_user_id or "").strip() or "local"


def _hidden_fingerprint(hidden: Optional[dict]) -> str:
    """屏蔽偏好内容指纹，作为 today_read 缓存 key 的一部分：反馈「不感兴趣」后 key 变化即失效，
    避免 5 分钟 TTL 内仍看到被屏蔽的论文。"""
    import hashlib
    import json as _json

    return hashlib.md5(
        _json.dumps(hidden or {}, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]


async def _briefing_ai_note(topics: List[str]) -> Optional[str]:
    """用 LLM 给 Top 热点生成一句话领域结论；AI 不可用时返回 None（纯数据降级）。"""
    if not topics:
        return None
    now = datetime.now()
    cached = _briefing_ai_cache
    if cached["note"] and cached["ts"] and (now - cached["ts"]) < _BRIEFING_AI_TTL:
        return cached["note"]
    if cached["failed_at"] and (now - cached["failed_at"]) < _BRIEFING_AI_FAIL_TTL:
        return None
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
        cached["failed_at"] = None
        return note
    except Exception as e:
        logger.warning(f"dashboard ai_note generation failed: {e}")
        cached["ts"] = now
        cached["note"] = None
        cached["failed_at"] = now
        return None


async def _build_user_profile_vector(db: AsyncSession, uid: str) -> Optional[dict]:
    """基于收藏+阅读+埋点点击构建画像向量（加权平均）。

    权重：收藏 2.0 / 阅读 1.0 / 埋点点击 1.0（与阅读同权，均按论文去重）；
    曝光未点击 -0.2：按论文去重的弱负信号——曝光次数多不再叠加，避免高频展示的热门
    论文被误杀（曝光量 >> 点击量，若按次累计负权重会主导整个画像）。
    返回 {"vec": 归一化向量, "exemplar": {"paper_id", "source": fav|read}}；
    exemplar 是行为论文中与画像余弦最高的一篇（收藏优先），用于推荐理由
    「因为你收藏了《X》」。无行为数据或 embedding 不可用时返回 None。缓存 10 分钟。
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

        # 埋点信号（UserEvent）：点击 +1.0，曝光未点击 -0.2，均按论文去重
        clicked: set = set()
        seen: set = set()
        try:
            ev_rows = (
                await db.execute(
                    sa_select(UserEvent.event_type, UserEvent.ref_id)
                    .where(
                        UserEvent.user_id == uid,
                        UserEvent.event_type.in_(("click", "impression")),
                        UserEvent.ref_id.isnot(None),
                    )
                    .order_by(UserEvent.id.desc())
                    .limit(2000)
                )
            ).all()
            for etype, pid in ev_rows:
                if etype == "click":
                    clicked.add(pid)
                else:
                    seen.add(pid)
        except Exception as e:
            logger.warning(f"load user_events for profile failed: {e}")
        for pid in clicked:
            weight_map[pid] = weight_map.get(pid, 0) + 1.0
        for pid in seen:
            if pid not in clicked:
                weight_map[pid] = weight_map.get(pid, 0) - 0.2

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

        # 归一化后加权求和（负权重向量做减法），再整体 L2 归一化：
        # 不按 Σw 除平均，避免负权重把均值尺度拉歪
        vec_sum = None
        unit_vecs: dict = {}
        for pid, emb_str in rows:
            try:
                vec = np.asarray(_json.loads(emb_str), dtype=np.float64)
                if vec.ndim != 1 or vec.size == 0:
                    continue
                norm = np.linalg.norm(vec)
                if norm == 0:
                    continue
                unit = vec / norm
                w = weight_map.get(pid, 1.0)
                unit_vecs[pid] = (unit, w)
                vec_sum = unit * w if vec_sum is None else vec_sum + unit * w
            except Exception:
                continue

        if vec_sum is None:
            return None
        norm = np.linalg.norm(vec_sum)
        if norm == 0:
            return None
        profile = vec_sum / norm

        # 样本论文：正权重行为论文中与画像余弦最高的一篇（收藏加分优先）
        exemplar = None
        best = -2.0
        for pid, (unit, w) in unit_vecs.items():
            if w <= 0:
                continue
            score = float(np.dot(unit, profile)) + (0.05 if w >= 2.0 else 0.0)
            if score > best:
                best = score
                exemplar = {"paper_id": pid, "source": "fav" if w >= 2.0 else "read"}

        return {"vec": profile.tolist(), "exemplar": exemplar}

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


def _diversity_filter(papers: List[Paper], max_sim: float = 0.92, max_per_subfield: int = 2) -> List[Paper]:
    """多样性约束（MMR 思想）：

    - embedding 余弦与「全部已选」论文相似度 > max_sim 时跳过（旧版只比相邻两篇，
      画像召回的扎堆论文隔位即可溜进列表）；
    - 同一子领域最多 max_per_subfield 篇，避免单一方向刷屏；
    - 无 embedding 的论文不受相似度约束，但仍受子领域上限约束。
    """
    import json as _json

    selected: List[Paper] = []
    selected_vecs: List = []
    subfield_count: dict = {}

    for p in papers:
        sf = (p.economics_subfield or "").strip() or None
        if sf and subfield_count.get(sf, 0) >= max_per_subfield:
            continue

        vec = None
        if p.features and p.features.embedding:
            try:
                raw = _json.loads(p.features.embedding)
                if raw:
                    import numpy as np

                    v = np.asarray(raw, dtype=np.float32)
                    norm = np.linalg.norm(v)
                    if norm > 0:
                        vec = v / norm
            except Exception:
                vec = None

        if vec is not None:
            too_similar = False
            for sv in selected_vecs:
                if float(np.dot(vec, sv)) > max_sim:
                    too_similar = True
                    break
            if too_similar:
                continue

        selected.append(p)
        if vec is not None:
            selected_vecs.append(vec)
        if sf:
            subfield_count[sf] = subfield_count.get(sf, 0) + 1
    return selected


@router.get("/dashboard")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
    seed: int = Query(default=0, ge=0),
    sections: str = Query(default="", description="逗号分隔的子集：today_read,briefing,mine；空=全部（向后兼容）"),
):
    """工作台聚合数据。sections 支持按页签只取所需子集：

    前端「研究工作台」页签只拉 today_read+mine，领域快讯/研究栈页签各取所需，
    避免旧版一次请求把三个子集（含 briefing 的 LLM 结论）全部算完。
    """
    uid = _uid(x_user_id)
    wanted = {s.strip() for s in (sections or "").split(",") if s.strip()} or {"today_read", "briefing", "mine"}

    followed_subfields: List[str] = []
    followed_keywords: List[str] = []
    hidden: dict = {}
    if "today_read" in wanted or "mine" in wanted:
        # ---- 关注子领域：决定"今日值得读"是否个性化 ----
        followed = await db.execute(
            sa_select(FollowedSubfield.subfield)
            .where(FollowedSubfield.user_id == uid)
        )
        followed_subfields = [r[0] for r in followed.all()]
    if "today_read" in wanted:
        # ---- 关注关键词：驱动"今日值得读"关键词召回 ----
        kw_result = await db.execute(
            sa_select(FollowedKeyword.keyword).where(FollowedKeyword.user_id == uid)
        )
        followed_keywords = [r[0] for r in kw_result.all()]

        # ---- "不感兴趣"屏蔽（P2）：工作台推荐同样全局过滤，命中任一屏蔽项的论文不出现 ----
        try:
            hidden = await _load_hidden_preferences(db, uid)
        except Exception:
            hidden = {}

    resp: dict = {}
    if "today_read" in wanted:
        # 5 分钟 TTL：四路召回 + FAISS + numpy 精排成本高，短缓存足够保鲜
        # （key 含 seed 与 hidden 指纹：换一批 / 反馈「不感兴趣」后自动换新 key）
        resp["today_read"] = await ttl_cache(
            f"today-read:{uid}:{seed}:{_hidden_fingerprint(hidden)}",
            300,
            lambda: _today_read(db, uid, followed_subfields, followed_keywords, hidden, seed=seed),
        )
    if "briefing" in wanted:
        resp["briefing"] = await _briefing(db)
    if "mine" in wanted:
        resp["mine"] = await _mine(db, uid, has_followed=bool(followed_subfields))
    return resp


async def _today_read(
    db: AsyncSession,
    uid: str,
    followed_subfields: List[str],
    followed_keywords: List[str],
    hidden: Optional[dict] = None,
    seed: int = 0,
) -> List[dict]:
    """今日值得读：向量召回 + 综合评分混排，多样性约束去重，共 6 篇。

    四路候选合并：
    1. 向量召回：用户画像向量 FAISS 检索语义相似论文（最多 10 篇），
       理由落到具体论文（"因为你收藏了《X》"）
    2. 子领域匹配：关注子领域按 final_score 降序（最多 6 篇），理由带命中的子领域
    3. 关键词匹配：优先走 paper_keywords 平表（索引查找；表空回退 json_each 全表扫描），
       理由带命中的关键词
    4. 全局高分：全库 final_score 降序补位

    合并后统一按 final_score 排序；seed 非 0 时按偏移轮转候选池（「换一批」换的是
    不同窗口而非同一池子的排列）；已读论文（近 30 天阅读历史，NOT EXISTS 反连接）
    不参与推荐；多样性过滤 = 全选集余弦去重 + 每子领域最多 2 篇。
    """
    hidden_cond = _hidden_paper_condition(hidden or {})

    # 已读排除：近 30 天读过的论文不再推荐（NOT EXISTS 走 reading_history 的
    # unique(user_id, paper_id) 索引，替代旧版 500 条 id 的 not_in 参数列表；
    # 更早的历史阅读不拦截，允许自然回顾）
    read_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent_read_exists = (
        sa_select(ReadingHistory.id)
        .where(
            ReadingHistory.user_id == uid,
            ReadingHistory.paper_id == Paper.id,
            ReadingHistory.read_at >= read_cutoff,
        )
        .exists()
    )

    existing_ids: set = set()
    candidates: List[Paper] = []
    reason_map: dict = {}

    def _add_candidates(papers: List[Paper], reason: Union[dict, Callable[[Paper], dict]]) -> None:
        for p in papers:
            if p.id in existing_ids:
                continue
            existing_ids.add(p.id)
            candidates.append(p)
            reason_map[p.id] = reason(p) if callable(reason) else reason

    def _base_query() -> Any:
        q = (
            sa_select(Paper)
            .options(selectinload(Paper.features), selectinload(Paper.scores))
            .join(PaperScore, PaperScore.paper_id == Paper.id)
            .where(~recent_read_exists)
        )
        if hidden_cond is not None:
            q = q.where(hidden_cond)
        return q

    # ---- 「换一批」偏移：seed 每次把各路召回窗口向后推，换的是不同论文而非排列 ----
    # 先于向量召回计算：画像召回同样按窗口偏移，否则换一批对个性化用户的前排几乎不变
    off = (seed % 6) * 6

    # ---- 路线 1：向量召回（用户画像相似） ----
    try:
        profile = await _build_user_profile_vector(db, uid)
        profile_vec = (profile or {}).get("vec")
        if profile_vec:
            recall_ids = await _embedding_recall_for_dashboard(db, profile_vec, k=10 + off)
            if recall_ids:
                window = recall_ids[off:]
                if window:
                    result = await db.execute(
                        _base_query()
                        .where(Paper.id.in_(window))
                        .order_by(sa_desc(PaperScore.final_score))
                        .limit(10)
                    )
                    ex = (profile or {}).get("exemplar")
                    ex_label = None
                    if ex:
                        trow = (await db.execute(sa_select(Paper.title).where(Paper.id == ex["paper_id"]))).first()
                        if trow and trow[0]:
                            short = trow[0][:24] + ("…" if len(trow[0]) > 24 else "")
                            ex_label = f"因为你{'收藏' if ex.get('source') == 'fav' else '读'}过《{short}》"
                    _add_candidates(
                        result.scalars().all(),
                        {"type": "profile", "label": ex_label or "与你的阅读/收藏画像相似"},
                    )
    except Exception as e:
        logger.warning(f"embedding recall in today_read failed: {e}")

    # ---- 路线 2：子领域匹配（关注方向优先） ----
    if followed_subfields:
        result = await db.execute(
            _base_query()
            .where(Paper.economics_subfield.in_(followed_subfields))
            .order_by(sa_desc(PaperScore.final_score))
            .offset(off)
            .limit(6)
        )
        _add_candidates(
            result.scalars().all(),
            lambda p: {"type": "subfield", "label": f"你关注的子领域：{p.economics_subfield}"},
        )

    # ---- 路线 3：关键词匹配（关注关键词） ----
    if followed_keywords:
        kw_set = set(followed_keywords)
        kw_subq = None
        try:
            kw_count = (
                await db.execute(sa_select(sa_func.count()).select_from(PaperKeyword))
            ).scalar_one()
            if kw_count:
                # 平表：keyword 有索引，召回走索引查找（O(log n)）
                kw_subq = sa_select(PaperKeyword.paper_id).where(
                    PaperKeyword.keyword.in_(followed_keywords)
                )
        except Exception as e:
            logger.warning(f"paper_keywords lookup failed, fallback to json_each: {e}")
        if kw_subq is None:
            # 未回填的库回退 json_each 全表展开
            from sqlalchemy import text as sa_text

            kw_placeholders = ", ".join(f":fk{i}" for i in range(len(followed_keywords)))
            kw_params = {f"fk{i}": kw for i, kw in enumerate(followed_keywords)}
            kw_subq = (
                sa_select(sa_text("p.id"))
                .select_from(sa_text("papers p, json_each(p.keywords_cn)"))
                .where(sa_text(f"json_each.value IN ({kw_placeholders})"))
                .params(**kw_params)
            )
        result = await db.execute(
            _base_query()
            .where(Paper.id.in_(kw_subq))
            .order_by(sa_desc(PaperScore.final_score))
            .offset(off)
            .limit(6)
        )

        def _kw_reason(p: Paper) -> dict:
            matched = [kw for kw in (p.keywords_cn or []) if kw in kw_set][:2]
            label = f"命中你关注的关键词：{'、'.join(matched)}" if matched else "命中你关注的关键词"
            return {"type": "keyword", "label": label}

        _add_candidates(result.scalars().all(), _kw_reason)

    # ---- 路线 4：全局高分补位（偏移窗口更大，保证「换一批」有新面孔） ----
    remaining = 20 - len(candidates)
    if remaining > 0:
        result = await db.execute(
            _base_query()
            .order_by(sa_desc(PaperScore.final_score))
            .offset((seed % 8) * 20)
            .limit(remaining)
        )
        _add_candidates(result.scalars().all(), {"type": "top", "label": "全库高分推荐"})

    # ---- 精排：按 final_score 降序 ----
    candidates.sort(
        key=lambda p: (p.scores.final_score if p.scores else 0.0),
        reverse=True,
    )

    # ---- 多样性过滤：全选集余弦去重 + 每子领域最多 2 篇 ----
    diversified = _diversity_filter(candidates, max_sim=0.92, max_per_subfield=2)

    # 过滤后不足 6 篇时按原评分顺序回填被过滤掉的候选，避免推荐数量缩水
    # （冷启动 / 关注面很窄时余弦去重会把候选砍到只剩两三篇）
    if len(diversified) < 6:
        chosen = {p.id for p in diversified}
        for p in candidates:
            if len(diversified) >= 6:
                break
            if p.id not in chosen:
                diversified.append(p)
                chosen.add(p.id)

    return [_paper_to_card(p, reason=reason_map.get(p.id)) for p in diversified[:6]]


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

    # 按主题跨桶聚合：同一 topic 在多个年份桶上榜时合并，避免重复展示；
    # 篇数取各桶之和，增长率取桶内最大值（与「热度」排序语义一致）。
    result = await db.execute(
        sa_select(
            TopicTrend.topic,
            sa_func.sum(TopicTrend.paper_count),
            sa_func.max(TopicTrend.growth_rate),
        )
        .where(TopicTrend.week_start.in_(recent_buckets))
        .group_by(TopicTrend.topic)
        .order_by(sa_func.max(TopicTrend.growth_rate).desc())
        .limit(5)
    )

    topics = []
    for topic, paper_count, growth_rate in result.all():
        trend_status = "rising" if growth_rate > 0.2 else ("declining" if growth_rate < -0.1 else "stable")
        topics.append({
            "topic": topic,
            "paper_count": paper_count,
            "growth_rate": growth_rate,
            "trend": trend_status,
        })

    # 每个主题的逐年篇数序列（领域快讯 sparkline 数据源）：
    # 按「主题 × 年份桶」取逐桶篇数，供前端画迷你柱状图；
    # 失败时降级为空序列（不影响主体数据）。
    series_map: dict = {}
    series_ok = False
    try:
        series_rows = await db.execute(
            sa_select(TopicTrend.topic, TopicTrend.week_start, TopicTrend.paper_count)
            .where(TopicTrend.week_start.in_(recent_buckets))
            .where(TopicTrend.topic.in_([t["topic"] for t in topics]))
            .order_by(TopicTrend.week_start)
        )
        for st_topic, st_week, st_count in series_rows.all():
            series_map.setdefault(st_topic, {})[st_week.year] = int(st_count)
        series_ok = True
    except Exception as e:
        logger.warning(f"dashboard briefing series failed: {e}")

    years = sorted({ws.year for ws in recent_buckets})
    for topic_item in topics:
        if not series_ok:
            topic_item["series"] = []
            continue
        by_year = series_map.get(topic_item["topic"], {})
        topic_item["series"] = [
            {"year": str(y), "count": by_year.get(y, 0)}
            for y in years
        ]

    # P0 遗留#4：调用 LLM 生成一句话领域结论（带 1h 缓存，AI 不可用时降级为 None）
    ai_note = await _briefing_ai_note([t["topic"] for t in topics])
    return {"topics": topics, "ai_note": ai_note}


async def _mine(db: AsyncSession, uid: str, has_followed: bool = False) -> dict:
    """我的研究栈：最近分析 + 最近验证选题 + 收藏数/已读数。"""
    # 最近收藏：仅 Favorite 表（展示最近 8 篇），收藏数用真实 COUNT 避免被展示上限截断
    fav_result = await db.execute(
        sa_select(Favorite.paper_id)
        .where(Favorite.user_id == uid)
        .order_by(Favorite.id.desc())
        .limit(8)
    )
    fav_ids = [r[0] for r in fav_result.all()]

    fav_papers = []
    if fav_ids:
        # 轻量化：工作台只展示最近收藏的标题列表，无需完整卡片（含 embedding/scores 的 selectinload）
        presult = await db.execute(
            sa_select(Paper.id, Paper.title).where(Paper.id.in_(fav_ids))
        )
        title_map = {pid: title for pid, title in presult.all()}
        fav_papers = [{"id": pid, "title": title_map.get(pid, "")} for pid in fav_ids]

    favorite_count = (
        await db.execute(
            sa_select(sa_func.count()).select_from(Favorite).where(Favorite.user_id == uid)
        )
    ).scalar() or 0

    # 最近分析（paper_analyses 最新 5 条，按用户隔离，附带论文标题）
    recent_analyses = []
    try:
        an_result = await db.execute(
            sa_select(PaperAnalysis.paper_id, PaperAnalysis.status, PaperAnalysis.created_at)
            .where(PaperAnalysis.user_id == uid)
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

    # 进行中的选题（非 abandoned）：带五步向导进度与文献集精读统计（工作台进度条用）
    projects = await db.execute(
        sa_select(TopicProject)
        .where(TopicProject.user_id == uid, TopicProject.status != "abandoned")
        .order_by(sa_desc(TopicProject.updated_at))
        .limit(5)
    )
    proj_rows = projects.scalars().all()
    proj_stat: dict = {}
    if proj_rows:
        stat_rows = await db.execute(
            sa_select(
                ProjectPaper.project_id,
                sa_func.count(),
                sa_func.coalesce(
                    sa_func.sum(sa_case((ProjectPaper.read_status == "read", 1), else_=0)), 0
                ),
            )
            .where(
                ProjectPaper.user_id == uid,
                ProjectPaper.project_id.in_([p.id for p in proj_rows]),
            )
            .group_by(ProjectPaper.project_id)
        )
        for pid, total, read in stat_rows.all():
            proj_stat[pid] = (int(total or 0), int(read or 0))
    proj_out = []
    for p in proj_rows:
        paper_total, paper_read = proj_stat.get(p.id, (0, 0))
        proj_out.append({
            "id": p.id,
            "title": p.title,
            "status": p.status,
            "novelty": p.novelty,
            "crowding": p.crowding,
            "current_step": p.current_step or 1,
            "paper_count": paper_total,
            "read_count": paper_read,
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

    # 关注子领域近 30 天新增论文数（工作台「新论文提醒」入口，未关注任何子领域时为 None）
    watch_subfield_count: Optional[int] = None
    try:
        sf_result = await db.execute(
            sa_select(FollowedSubfield.subfield).where(FollowedSubfield.user_id == uid)
        )
        subfields = [r[0] for r in sf_result.all()]
        if subfields:
            month_start = datetime.now(timezone.utc) - timedelta(days=30)
            watch_subfield_count = (
                await db.execute(
                    sa_select(sa_func.count())
                    .select_from(Paper)
                    .where(
                        Paper.economics_subfield.in_(subfields),
                        Paper.created_at >= month_start,
                    )
                )
            ).scalar() or 0
    except Exception as e:
        logger.warning(f"watch_subfield_count failed: {e}")

    return {
        "favorites": fav_papers,
        "recent_analyses": recent_analyses,
        "topic_projects": proj_out,
        "reviews": reviews,
        "latest_report_summary": report.summary if report else None,
        "latest_report_id": report.id if report else None,
        "favorite_count": int(favorite_count),
        "has_followed_subfields": has_followed,
        "watch_subfield_count": int(watch_subfield_count) if watch_subfield_count is not None else None,
    }


# ---------- 今日速览（首页速览条数据源）：60s 进程内缓存 ----------

_TODAY_BRIEF_TTL_SECONDS = 60


async def _build_today_brief(db: AsyncSession, uid: str) -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now - timedelta(days=30)

    # 速览条展示「新收录」论文数，按入库时间 created_at 统计（期刊 published_at 有滞后，按发表统计长期为 0）
    today_count = (
        await db.execute(
            sa_select(sa_func.count())
            .select_from(Paper)
            .where(Paper.created_at >= today_start)
        )
    ).scalar() or 0

    month_count = (
        await db.execute(
            sa_select(sa_func.count())
            .select_from(Paper)
            .where(Paper.created_at >= month_start)
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
                    Paper.created_at >= month_start,
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
    """今日速览：今日/近一个月新收录论文数（created_at）+ 关注子领域近一个月数（60s TTL 缓存，按用户隔离）。"""
    uid = _uid(x_user_id)

    async def _compute() -> dict:
        return await _build_today_brief(db, uid)

    return await ttl_cache(f"today-brief:{uid}", _TODAY_BRIEF_TTL_SECONDS, _compute)

@router.get("/dashboard/watch-new-papers")
async def get_watch_new_papers(
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
    limit: int = Query(default=10, ge=1, le=30),
):
    """关注子领域近 30 天新论文列表（工作台「新论文提醒」就地展开，替代跳搜索页重拼条件）。

    与 _mine.watch_subfield_count 同口径：created_at >= 30 天前 + economics_subfield 命中
    关注集合，按发表时间降序；屏蔽项与全站列表一致过滤。total 为命中总数（供「还有 N 篇」）。
    """
    uid = _uid(x_user_id)
    sf_result = await db.execute(
        sa_select(FollowedSubfield.subfield).where(FollowedSubfield.user_id == uid)
    )
    subfields = [r[0] for r in sf_result.all()]
    if not subfields:
        return {"papers": [], "total": 0}

    try:
        hidden = await _load_hidden_preferences(db, uid)
    except Exception:
        hidden = {}
    hidden_cond = _hidden_paper_condition(hidden or {})

    # Paper.created_at 以 UTC 存储（server_default=func.now()），统一用带时区的 UTC 口径
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    filters = [
        Paper.economics_subfield.in_(subfields),
        Paper.created_at >= cutoff,
    ]
    if hidden_cond is not None:
        filters.append(hidden_cond)

    total = (
        await db.execute(
            sa_select(sa_func.count())
            .select_from(Paper)
            .join(PaperScore, PaperScore.paper_id == Paper.id)
            .where(*filters)
        )
    ).scalar() or 0

    result = await db.execute(
        sa_select(Paper)
        .options(selectinload(Paper.features), selectinload(Paper.scores))
        .join(PaperScore, PaperScore.paper_id == Paper.id)
        .where(*filters)
        .order_by(sa_desc(Paper.created_at), sa_desc(PaperScore.final_score))
        .limit(limit)
    )
    papers = result.scalars().all()
    cards = [
        _paper_to_card(
            p,
            reason={"type": "watch", "label": f"你关注的 {p.economics_subfield} 新论文"},
        )
        for p in papers
    ]
    return {"papers": cards, "total": int(total)}
