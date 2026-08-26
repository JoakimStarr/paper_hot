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


@router.get("/network/authors")
async def get_author_network(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select as sa_select
    from app.models import Paper as PaperModel

    result = await db.execute(
        sa_select(PaperModel.id, PaperModel.authors)
        .where(PaperModel.authors.isnot(None))
        .order_by(PaperModel.published_at.desc())
        .limit(limit)
    )
    papers = result.all()

    author_papers: dict[str, int] = {}
    paper_authors: list[list[str]] = []

    for paper in papers:
        authors: list[str] = _parse_json_list(paper.authors)
        cleaned: list[str] = []
        for author in authors:
            author = author.strip().rstrip(',')
            if not author or '@' in author:
                continue
            cleaned.append(author)
            author_papers[author] = author_papers.get(author, 0) + 1
        paper_authors.append(cleaned)

    sorted_authors = sorted(author_papers.items(), key=lambda x: x[1], reverse=True)[:100]
    nodes = [{"id": name, "name": name, "papers": count, "group": "author"} for name, count in sorted_authors]

    author_index = {name: idx for idx, (name, _) in enumerate(sorted_authors)}
    link_counts: dict[tuple[str, str], int] = {}
    for authors in paper_authors:
        for i in range(len(authors)):
            for j in range(i + 1, len(authors)):
                a, b = authors[i], authors[j]
                if a in author_index and b in author_index:
                    key = (a, b) if a < b else (b, a)
                    link_counts[key] = link_counts.get(key, 0) + 1

    links = sorted(
        [{"source": k[0], "target": k[1], "value": v} for k, v in link_counts.items()],
        key=lambda x: x["value"], reverse=True
    )[:300]

    return {"nodes": nodes, "links": links}


@router.get("/network/keywords")
async def get_keyword_network(
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db)
):
    from app.stats import keyword_network

    # 统计核心见 app/stats.py（与 ai.py / topic.py 共用同一实现，数据源 papers.keywords_cn）
    return await keyword_network(db, limit=limit)


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


@router.get("/network/keyword-map")
async def get_keyword_research_map(
    keyword: str = Query(..., min_length=1, max_length=80),
    db: AsyncSession = Depends(get_db),
):
    """查询驱动的研究版图（P2-13）：点一个关键词 -> 动态生成该词的研究版图。

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


