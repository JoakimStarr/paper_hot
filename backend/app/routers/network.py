"""作者合作与关键词共现网络接口。"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.deps import _parse_json_list

logger = logging.getLogger(__name__)
router = APIRouter()


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


