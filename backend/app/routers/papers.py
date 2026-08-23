"""论文列表/详情/搜索/作者/论文级 AI 与对话接口。"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.crud import PaperCRUD, PaperAnalysisCRUD, PaperChatCRUD, PaperSimilarityCRUD
from app.routers.deps import (
    verify_token, _parse_json_list, _isoformat_utc, _paper_to_card,
    _compute_cache_key, _get_ai_client, _resolve_model_provider,
    _get_default_model, _stream_chat_response,
)
from app.schemas import (
    PaperResponse, PaperCardListResponse, PaperDetailResponse, SimilarPaper,
    TrendingTopicsResponse, TrendingTopic,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/papers")
async def get_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    topic: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, ge=0.0, le=1.0),
    days_back: Optional[int] = Query(None, ge=1),
    discipline: Optional[str] = Query(None),
    economics_subfield: Optional[str] = Query(None),
    cnki_subject: Optional[str] = Query(None),
    journal_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    search_field: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("desc"),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    papers, total = await PaperCRUD.get_papers(
        db,
        page=page,
        page_size=page_size,
        topic=topic,
        source=source,
        min_score=min_score,
        days_back=days_back,
        discipline=discipline,
        economics_subfield=economics_subfield,
        cnki_subject=cnki_subject,
        journal_name=journal_name,
        search=search,
        search_field=search_field,
        sort_by=sort_by,
        sort_order=sort_order
    )

    etag = _compute_cache_key(
        "papers", total, page, page_size,
        topic=topic, source=source, min_score=min_score, days_back=days_back,
        discipline=discipline, economics_subfield=economics_subfield,
        cnki_subject=cnki_subject, journal_name=journal_name,
        search=search, search_field=search_field,
        sort_by=sort_by, sort_order=sort_order,
    )

    if request and request.headers.get("if-none-match") == etag:
        return JSONResponse(status_code=304, content=None)

    response_data = PaperCardListResponse(
        papers=[_paper_to_card(paper) for paper in papers],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total
    )

    return JSONResponse(
        content=json.loads(response_data.model_dump_json()),
        headers={
            "Cache-Control": "private, max-age=300",
            "ETag": etag,
        }
    )


@router.get("/papers/{paper_id}", response_model=PaperDetailResponse)
async def get_paper(
    paper_id: str,
    db: AsyncSession = Depends(get_db)
):
    paper = await PaperCRUD.get_paper_by_id(db, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    similar_papers, score_map = await PaperSimilarityCRUD.get_similar_papers_with_scores(db, paper_id, limit=5)

    should_read_score = None
    if paper.scores:
        should_read_score = paper.scores.final_score

    return PaperDetailResponse(
        **PaperResponse.model_validate(paper).model_dump(),
        similar_papers=[
            SimilarPaper(
                id=p.id,
                title=p.title,
                similarity_score=round(score_map.get(p.id, 0), 4),
                topic=p.features.topic if p.features else None,
                keywords_cn=p.keywords_cn or []
            )
            for p in similar_papers
        ],
        should_read_score=should_read_score
    )


@router.get("/filter-statistics")
async def get_filter_statistics(db: AsyncSession = Depends(get_db)):
    stats = await PaperCRUD.get_filter_statistics(db)
    return stats


@router.get("/trending-topics", response_model=TrendingTopicsResponse)
async def get_trending_topics(
    weeks_back: int = Query(4, ge=1, le=52),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select, desc
    from app.models import TopicTrend
    from datetime import timedelta

    cutoff_date = datetime.now() - timedelta(days=365)

    result = await db.execute(
        select(TopicTrend)
        .where(TopicTrend.week_start >= cutoff_date)
        .order_by(desc(TopicTrend.growth_rate))
    )
    trends = result.scalars().all()

    trending_topics = []
    for trend in trends:
        if trend.growth_rate > 0.2:
            trend_status = "rising"
        elif trend.growth_rate < -0.1:
            trend_status = "declining"
        else:
            trend_status = "stable"

        trending_topics.append(TrendingTopic(
            topic=trend.topic,
            paper_count=trend.paper_count,
            growth_rate=trend.growth_rate,
            trend=trend_status
        ))

    now = datetime.now()
    week_start = now - timedelta(days=7)

    return TrendingTopicsResponse(
        topics=trending_topics[:20],
        week_start=week_start,
        week_end=now
    )


CACHE_TTL_HOURS = 6


@router.post("/papers/{paper_id}/analyze")
async def analyze_paper(paper_id: str, db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    paper = await PaperCRUD.get_paper_by_id(db, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    pending = await PaperAnalysisCRUD.get_latest_pending(db, paper_id)
    if pending:
        return {"analysis": None, "status": "pending", "message": "分析正在进行中"}

    authors = ", ".join(_parse_json_list(paper.authors)) or "未知"
    keywords = ", ".join(_parse_json_list(paper.keywords_cn)) or "未知"
    journal = paper.journal_name or "未知"

    prompt = f"""请从学术角度分析以下论文：

标题：{paper.title}
作者：{authors}
期刊：{journal}
关键词：{keywords}
摘要：{paper.abstract or '无'}

请从以下方面进行分析：
1. 研究背景与核心问题
2. 研究方法与创新点
3. 主要发现与结论
4. 研究意义与局限性

请用中文回答，结构清晰。"""

    try:
        client, provider = _get_ai_client()
    except HTTPException:
        raise HTTPException(status_code=503, detail="AI API key not configured")
    model = _get_default_model(provider)

    analysis_id = await PaperAnalysisCRUD.create_pending(db, paper_id, model=model)
    await db.commit()

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        analysis_text = response.choices[0].message.content
        await PaperAnalysisCRUD.update_analysis(db, analysis_id, analysis_text, "success")
        await db.commit()
        return {"analysis": analysis_text, "status": "success", "model": model}
    except Exception as e:
        await PaperAnalysisCRUD.update_analysis(db, analysis_id, f"分析失败: {str(e)}", "failed")
        await db.commit()
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")


@router.get("/papers/{paper_id}/analyses")
async def get_paper_analyses(paper_id: str, db: AsyncSession = Depends(get_db)):
    records = await PaperAnalysisCRUD.get_history(db, paper_id)
    return [{"id": r.id, "analysis": r.analysis, "model": r.model, "created_at": _isoformat_utc(r.created_at)} for r in records]


@router.get("/papers/{paper_id}/analyses/latest")
async def get_latest_analysis(paper_id: str, db: AsyncSession = Depends(get_db)):
    record = await PaperAnalysisCRUD.get_latest(db, paper_id)
    if not record:
        return {"analysis": None, "status": None}
    return {
        "analysis": record.analysis,
        "model": record.model,
        "status": record.status,
        "created_at": _isoformat_utc(record.created_at)
    }


class ChatRequest(BaseModel):
    messages: List[dict]
    model: Optional[str] = None


class ChatSaveRequest(BaseModel):
    messages: List[dict]


@router.post("/papers/{paper_id}/chat")
async def chat_about_paper(paper_id: str, body: ChatRequest, db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    paper = await PaperCRUD.get_paper_by_id(db, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    authors = ", ".join(_parse_json_list(paper.authors)) or "未知"
    keywords = ", ".join(_parse_json_list(paper.keywords_cn)) or "未知"
    journal = paper.journal_name or "未知"

    system_prompt = f"""你是一个学术论文分析助手。以下是当前讨论的论文信息：

标题：{paper.title}
作者：{authors}
期刊：{journal}
关键词：{keywords}
摘要：{paper.abstract or '无'}

请基于以上论文信息回答用户的问题，如果问题超出论文范围，请诚实说明。用中文回答。"""

    messages = [{"role": "system", "content": system_prompt}] + body.messages

    try:
        provider, bare_model = _resolve_model_provider(body.model)
        client, provider = _get_ai_client(provider)
    except HTTPException:
        raise HTTPException(status_code=503, detail="AI API key not configured")

    return _stream_chat_response(client, provider, messages, model=bare_model)


@router.get("/papers/{paper_id}/chats")
async def get_chat_history(paper_id: str, db: AsyncSession = Depends(get_db)):
    messages = await PaperChatCRUD.get_chats(db, paper_id)
    return [
        {"role": m.role, "content": m.content, "created_at": _isoformat_utc(m.created_at)}
        for m in messages
    ]


@router.post("/papers/{paper_id}/chats")
async def save_chat_messages(paper_id: str, body: ChatSaveRequest, db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    messages = body.messages
    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")
    for msg in messages:
        await PaperChatCRUD.save_message(db, paper_id, msg["role"], msg["content"])
    await db.commit()
    return {"status": "saved", "count": len(messages)}


@router.post("/papers/{paper_id}/recompute-similarities")
async def recompute_paper_similarities(paper_id: str, db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    paper = await PaperCRUD.get_paper_by_id(db, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    try:
        from app.similarity import compute_and_store_for_paper
        await compute_and_store_for_paper(db, paper_id)
        await db.commit()
        return {"status": "success", "message": "Similarities recomputed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recompute failed: {str(e)}")


@router.get("/authors/{author_name:path}/papers")
async def get_author_papers(
    author_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import text as sa_text

    count_result = await db.execute(
        sa_text("""
            SELECT COUNT(DISTINCT p.id)
            FROM papers p, json_each(p.authors)
            WHERE p.authors IS NOT NULL AND json_each.value = :author_name
        """),
        {"author_name": author_name}
    )
    total = count_result.scalar() or 0

    offset = (page - 1) * page_size

    result = await db.execute(
        sa_text("""
            SELECT DISTINCT p.id, p.title, p.abstract, p.authors, p.url, p.source, p.venue,
                   p.journal_name, p.journal_issue, p.economics_subfield, p.doi,
                   p.keywords_cn, p.published_at, p.created_at,
                   pf.topic,
                   ps.recency_score, ps.venue_score, ps.trend_score, ps.final_score
            FROM papers p, json_each(p.authors)
            LEFT JOIN paper_features pf ON pf.paper_id = p.id
            LEFT JOIN paper_scores ps ON ps.paper_id = p.id
            WHERE p.authors IS NOT NULL AND json_each.value = :author_name
            ORDER BY p.published_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"author_name": author_name, "limit": page_size, "offset": offset}
    )
    rows = result.fetchall()

    cards = []
    for row in rows:
        cards.append({
            "id": row[0],
            "title": row[1],
            "abstract": row[2],
            "authors": _parse_json_list(row[3]),
            "url": row[4],
            "source": row[5],
            "venue": row[6],
            "journal_name": row[7],
            "journal_issue": row[8],
            "economics_subfield": row[9],
            "doi": row[10],
            "keywords_cn": _parse_json_list(row[11]),
            "published_at": row[12],
            "created_at": str(row[13]) if row[13] else "",
            "topic": row[14],
            "recency_score": float(row[15] or 0),
            "venue_score": float(row[16] or 0),
            "trend_score": float(row[17] or 0),
            "final_score": float(row[18] or 0),
        })

    return {
        "papers": cards,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": offset + page_size < total,
        "author_name": author_name
    }


@router.get("/search/suggest")
async def search_suggest(
    q: str = Query(..., min_length=1),
    limit: int = Query(8, ge=1, le=20),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import text as sa_text
    from app.models import Paper as PaperModel
    from sqlalchemy import select as sa_select

    suggestions: list[dict] = []
    half = max(limit // 3, 2)

    try:
        kw_result = await db.execute(
            sa_text("""
                SELECT kw, COUNT(*) as cnt FROM (
                    SELECT value as kw FROM papers, json_each(keywords_cn)
                    WHERE keywords_cn IS NOT NULL
                )
                WHERE kw LIKE :pattern AND length(kw) > 1
                GROUP BY kw ORDER BY cnt DESC LIMIT :lim
            """),
            {"pattern": f"%{q}%", "lim": half}
        )
        for row in kw_result:
            val = str(row[0])
            if not val.startswith('[') and not val.startswith('"') and val.strip():
                suggestions.append({"text": val, "type": "keyword", "count": row[1]})
    except Exception:
        pass

    try:
        author_result = await db.execute(
            sa_text("""
                SELECT author_name, COUNT(*) as cnt FROM (
                    SELECT value as author_name FROM papers, json_each(authors)
                    WHERE authors IS NOT NULL
                )
                WHERE author_name LIKE :pattern AND length(author_name) > 1
                GROUP BY author_name ORDER BY cnt DESC LIMIT :lim
            """),
            {"pattern": f"%{q}%", "lim": half}
        )
        for row in author_result:
            val = str(row[0])
            if val.strip() and not val.startswith('[') and not val.startswith('"'):
                suggestions.append({"text": val, "type": "author", "count": row[1]})
    except Exception:
        pass

    try:
        title_result = await db.execute(
            sa_select(PaperModel.title)
            .where(PaperModel.title.ilike(f"%{q}%"))
            .limit(half)
        )
        for row in title_result:
            t = row[0]
            if t and t.strip():
                suggestions.append({"text": t[:80], "type": "title", "count": 0})
    except Exception:
        pass

    return {"suggestions": suggestions[:limit]}


@router.get("/subfield-distribution")
async def get_subfield_distribution(
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select as sa_select, func
    from app.models import Paper as PaperModel

    result = await db.execute(
        sa_select(
            PaperModel.economics_subfield,
            func.count(PaperModel.id)
        )
        .where(PaperModel.economics_subfield.isnot(None))
        .group_by(PaperModel.economics_subfield)
        .order_by(func.count(PaperModel.id).desc())
    )

    distribution = [
        {"subfield": row[0], "count": row[1]}
        for row in result
    ]
    return {"distribution": distribution}


