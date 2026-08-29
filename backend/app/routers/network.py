"""作者合作与关键词共现网络接口。"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.deps import _parse_json_list

logger = logging.getLogger(__name__)
router = APIRouter()


def _aggregate_research_map(keyword: str, papers) -> tuple[dict, dict, dict]:
    """对一个关键词命中的论文列表做聚合统计（#14 可测纯函数）。

    返回 (cooccur, yearly, journals)：
    - cooccur: dict[其他关键词] -> 共现次数（排除自身与含该词子串的宽泛词）
    - yearly:  dict[年份(YYYY)] -> 论文数
    - journals:dict[期刊名] -> 论文数
    papers 为带 keywords_cn / published_at / journal_name / venue 属性的对象（ORM 或 mock）。
    """
    cooccur: dict = {}
    yearly: dict = {}
    journals: dict = {}
    for p in papers:
        for other in p.keywords_cn or []:
            other = (other or "").strip()
            # 排除自身关键词及包含该词子串的宽泛词（如查询"经济"时剔除"经济研究"）
            if other and other != keyword and keyword not in other:
                cooccur[other] = cooccur.get(other, 0) + 1
        if p.published_at:
            year = str(p.published_at)[:4]
            yearly[year] = yearly.get(year, 0) + 1
        j = p.journal_name or p.venue
        if j:
            journals[j] = journals.get(j, 0) + 1
    return cooccur, yearly, journals


@router.get("/network/keywords")
async def get_keyword_network(
    db: AsyncSession = Depends(get_db)
):
    """关键词共现网络：全库聚合（节点 top80 / 边 top400 在 stats 层裁剪）。

    此前仅统计最近 limit 篇，计数严重失真；现与作者网络一致改为全库。
    """
    from app.stats import keyword_network

    # 统计核心见 app/stats.py（与 ai.py / topic.py 共用同一实现，数据源 papers.keywords_cn）
    return await keyword_network(db)


@router.get("/network/topic-clusters")
async def get_topic_clusters(
    k: int = Query(18, ge=4, le=40),
    db: AsyncSession = Depends(get_db)
):
    """主题聚类地图（P2）：本地 bge-m3 向量全库 KMeans 聚类 + PCA 二维投影。

    结果带进程内缓存（签名=向量论文数+最大特征行id，TTL 30分钟）。
    """
    from app.clusters import build_topic_clusters

    return await build_topic_clusters(db, k=k)


@router.get("/network/keyword-trends")
async def get_keyword_trends(
    top: int = Query(12, ge=3, le=30),
    keywords: Optional[str] = Query(None, description="逗号分隔的指定关键词，缺省取近一年最热"),
    db: AsyncSession = Depends(get_db)
):
    """关键词年度演化线 + 新兴/衰退动量（近12月 vs 前12月，全库统计）。"""
    from app.clusters import compute_keyword_trends

    kw_list = [k for k in (keywords or "").split(",") if k.strip()] or None
    return await compute_keyword_trends(db, top=top, keywords=kw_list)


async def _compute_keyword_gaps(db: AsyncSession, limit: int = 10) -> list:
    """研究空白识别（薄代理：实现收敛在 app/stats.py，供 /network/gaps 与 topic.py 复用）。"""
    from app.stats import compute_keyword_gaps

    return await compute_keyword_gaps(db, limit=limit)


@router.get("/network/gaps")
async def get_keyword_gaps(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """研究空白组合列表（纯数据接口，无 LLM 调用，秒回）。

    LLM 解读走 POST /network/gaps/analyze（后台任务），见 topic.py。
    """
    gaps = await _compute_keyword_gaps(db, limit=limit)
    return {"gaps": gaps, "total": len(gaps)}


async def compute_keyword_research_map(db, keyword: str) -> dict:
    """研究版图核心实现（端点 /network/keyword-map 与 agent 工具 keyword_map 共用）。

    返回：共现词（含计数）、年度趋势、代表论文（综合评分 top）、期刊分布。
    """
    from sqlalchemy import select as sa_select, desc as sa_desc, or_ as sa_or, String as SAString
    from app.models import Paper as PaperModel, PaperScore

    kw = keyword.strip()
    # P0 遗留#9（性能）：不再全表拉进 Python 过滤，改为数据库侧 OR LIKE 先筛该关键词
    # 命中的论文（keywords_cn 为 JSON 文本，子串 LIKE 足够；标题 LIKE 兜底），取 top 500 候选。
    cond = sa_or(
        PaperModel.keywords_cn.cast(SAString).ilike(f"%{kw}%"),
        PaperModel.title.ilike(f"%{kw}%"),
    )
    result = await db.execute(
        sa_select(PaperModel)
        .where(cond)
        .order_by(PaperModel.published_at.desc())
        .limit(500)
    )
    papers = []
    for p in result.scalars():
        kws = p.keywords_cn or []
        # Python 侧精确复检，避免关键词子串误报（如 "经济" 命中 "经济研究"）
        if any(kw in (k or "") for k in kws) or kw in (p.title or ""):
            papers.append(p)

    cooccur, yearly, journals = _aggregate_research_map(kw, papers)

    # 代表论文：有评分按评分排，否则按时间倒序
    try:
        scored = await db.execute(
            sa_select(PaperModel.id, PaperModel.title, PaperModel.journal_name, PaperScore.final_score)
            .join(PaperScore, PaperScore.paper_id == PaperModel.id)
            .where(PaperModel.id.in_([p.id for p in papers[:600]]))
            .order_by(sa_desc(PaperScore.final_score))
            .limit(8)
        )
        representative = [
            {"id": r[0], "title": r[1], "journal_name": r[2], "score": round(float(r[3] or 0), 3)}
            for r in scored.all()
        ]
    except Exception:
        representative = []

    if not representative and papers:
        representative = [
            {"id": p.id, "title": p.title, "journal_name": p.journal_name, "score": None}
            for p in papers[:8]
        ]

    return {
        "keyword": kw,
        "total_papers": len(papers),
        "cooccurring_keywords": sorted(cooccur.items(), key=lambda x: x[1], reverse=True)[:15],
        "yearly_trend": sorted(yearly.items()),
        "representative_papers": representative,
        "journal_distribution": sorted(journals.items(), key=lambda x: x[1], reverse=True)[:10],
    }


@router.get("/network/keyword-map")
async def get_keyword_research_map(
    keyword: str = Query(..., min_length=1, max_length=80),
    db: AsyncSession = Depends(get_db),
):
    """查询驱动的研究版图（P2-13）：点一个关键词 -> 动态生成该词的研究版图。"""
    return await compute_keyword_research_map(db, keyword)


