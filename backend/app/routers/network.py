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
    from sqlalchemy import select as sa_select
    from app.models import PaperFeatures, Paper

    result = await db.execute(
        sa_select(PaperFeatures.keywords)
        .join(Paper)
        .where(PaperFeatures.keywords.isnot(None))
        .order_by(Paper.published_at.desc())
        .limit(limit)
    )

    nodes_map = {}
    links_map = {}

    for row in result:
        keywords = row[0] if row[0] else []
        for kw in keywords:
            if kw and kw not in nodes_map:
                nodes_map[kw] = {"id": kw, "name": kw, "count": 0, "group": "keyword"}
            if kw:
                nodes_map[kw]["count"] += 1

        for i in range(len(keywords)):
            for j in range(i + 1, len(keywords)):
                pair = tuple(sorted([keywords[i], keywords[j]]))
                if pair not in links_map:
                    links_map[pair] = {"source": pair[0], "target": pair[1], "value": 0}
                links_map[pair]["value"] += 1

    nodes = sorted(nodes_map.values(), key=lambda x: x["count"], reverse=True)[:80]
    node_ids = {n["id"] for n in nodes}
    links = [l for l in links_map.values() if l["source"] in node_ids and l["target"] in node_ids][:400]

    return {"nodes": nodes, "links": links}


