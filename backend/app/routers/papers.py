"""论文列表/详情/搜索/作者/论文级 AI 与对话接口。"""
import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException, Request, Header
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

    cutoff_date = datetime.now() - timedelta(weeks=weeks_back)

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


@router.get("/trends/explain")
async def explain_trend(
    topic: str = Query(..., min_length=1, max_length=100),
    weeks_back: int = Query(12, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
):
    """AI 解读单个话题的趋势（P2-13b）：一段话说明热度走势、驱动因素与机会。"""
    from sqlalchemy import select as sa_select, desc as sa_desc
    from app.models import TopicTrend

    cutoff = datetime.now() - timedelta(weeks=weeks_back)
    result = await db.execute(
        sa_select(TopicTrend)
        .where(TopicTrend.topic == topic.strip(), TopicTrend.week_start >= cutoff)
        .order_by(sa_desc(TopicTrend.week_start))
        .limit(12)
    )
    rows = result.scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="No trend data for this topic")

    series = [
        {"week": str(t.week_start)[:10], "paper_count": t.paper_count, "growth_rate": t.growth_rate}
        for t in sorted(rows, key=lambda x: x.week_start)
    ]
    total = sum(r.paper_count for r in rows)
    avg_growth = sum(r.growth_rate or 0 for r in rows) / len(rows)

    # 规则兜底（无 AI 时）
    direction = "上升" if avg_growth > 0.2 else ("回落" if avg_growth < -0.1 else "平稳")
    fallback = f"「{topic}」近 {len(rows)} 周共 {total} 篇论文，整体呈{direction}态势（平均周环比 {avg_growth*100:.0f}%）。"

    try:
        provider, bare_model = _resolve_model_provider(None)
        client, provider = _get_ai_client(provider)
        model = bare_model or _get_default_model(provider)
    except HTTPException:
        return {"topic": topic, "explanation": fallback, "series": series, "ai_used": False}

    try:
        import asyncio as _asyncio
        prompt = f"""这是话题「{topic}」在论文库中近 {len(rows)} 周的热度序列（周/篇数/环比）：
{chr(10).join(f"{s['week']}: {s['paper_count']} 篇, 环比 {s['growth_rate']*100:.0f}%" for s in series)}

请用中文写 2-3 句话解读这段趋势：热度走向、可能的驱动因素、对研究者是进入还是观望。只输出解读文本，不要标题。"""
        response = await _asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3,
        )
        explanation = (response.choices[0].message.content or fallback).strip()
        return {"topic": topic, "explanation": explanation, "series": series, "ai_used": True}
    except Exception:
        return {"topic": topic, "explanation": fallback, "series": series, "ai_used": False}


CACHE_TTL_HOURS = 6


class AnalyzePaperRequest(BaseModel):
    model: Optional[str] = None  # 'provider/model'；为空则用默认模型


@router.post("/papers/{paper_id}/analyze")
async def analyze_paper(
    paper_id: str,
    body: Optional[AnalyzePaperRequest] = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    paper = await PaperCRUD.get_paper_by_id(db, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    pending = await PaperAnalysisCRUD.get_latest_pending(db, paper_id)
    if pending:
        return {"analysis": None, "status": "pending", "message": "分析正在进行中"}

    authors = ", ".join(_parse_json_list(paper.authors)) or "未知"
    keywords = ", ".join(_parse_json_list(paper.keywords_cn)) or "未知"
    journal = paper.journal_name or "未知"
    journal_issue = paper.journal_issue or ""
    subfield = paper.economics_subfield or "未知"

    system_prompt = (
        "你是一位严谨的学术分析专家，擅长从论文标题、作者、期刊、关键词与摘要中提炼结构化洞见。"
        "回答使用中文，采用清晰的 Markdown 结构（可用标题、加粗、列表），做到有理有据、不空泛。"
    )
    prompt = f"""请从学术角度分析以下论文：

- 标题：{paper.title}
- 作者：{authors}
- 期刊：{journal} {journal_issue}
- 学科子领域：{subfield}
- 关键词：{keywords}

摘要：
{paper.abstract or '无'}

请从以下方面进行分析，用中文作答：
1. **研究背景与核心问题**：论文试图解决什么问题，为什么重要
2. **研究方法与创新点**：采用什么方法，创新之处在哪里
3. **主要发现与结论**：核心结论与证据链条
4. **研究意义与局限性**：对学术与实践的意义，以及存在的不足

要求：结构清晰，观点明确；基于给出的论文信息作答，不要臆造未提供的内容。"""

    try:
        if body and body.model:
            provider, bare_model = _resolve_model_provider(body.model)
            client, provider = _get_ai_client(provider)
            model = bare_model
        else:
            client, provider = _get_ai_client()
            model = _get_default_model(provider)
    except HTTPException:
        raise HTTPException(status_code=503, detail="AI API key not configured")

    analysis_id = await PaperAnalysisCRUD.create_pending(db, paper_id, model=model)
    await db.commit()

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
            temperature=0.4,
        )
        analysis_text = response.choices[0].message.content
        await PaperAnalysisCRUD.update_analysis(db, analysis_id, analysis_text, "success")
        await db.commit()
        return {"analysis": analysis_text, "status": "success", "model": model}
    except Exception as e:
        await PaperAnalysisCRUD.update_analysis(db, analysis_id, f"分析失败: {str(e)}", "failed")
        await db.commit()
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")


class BatchAnalyzeRequest(BaseModel):
    paper_ids: List[str]
    model: Optional[str] = None


@router.post("/papers/batch-analyze")
async def batch_analyze_papers(
    body: BatchAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """批量分析（P1-8）：多选 5-10 篇论文 -> 生成一份领域综述摘要。

    同步返回 markdown 文本；论文数上限 10，超出截断。
    """
    ids = [pid for pid in (body.paper_ids or []) if pid][:10]
    if not ids:
        raise HTTPException(status_code=400, detail="paper_ids is required")

    papers = []
    for pid in ids:
        p = await PaperCRUD.get_paper_by_id(db, pid)
        if p:
            papers.append(p)
    if not papers:
        raise HTTPException(status_code=404, detail="No valid papers found")

    papers_text = "\n\n".join([
        f"【{i+1}】《{p.title}》\n"
        f"- 期刊：{p.journal_name or '未知'} {p.journal_issue or ''}\n"
        f"- 作者：{', '.join(_parse_json_list(p.authors)) or '未知'}\n"
        f"- 关键词：{', '.join(_parse_json_list(p.keywords_cn)) or '未知'}\n"
        f"- 摘要：{(p.abstract or '无')[:300]}"
        for i, p in enumerate(papers)
    ])

    system_prompt = (
        "你是一位严谨的学术综述专家。回答使用中文、清晰的 Markdown 结构，"
        "引用文献时用【编号】标注，结论必须有文献支撑，不臆造。"
    )
    prompt = f"""以下是用户从论文库中挑选的 {len(papers)} 篇论文，请生成一份「领域综述摘要」：

{papers_text}

请按以下结构输出：
## 共同主题与背景
这批论文共同关注的问题域及其研究价值
## 方法图谱
各篇采用的方法归类对比（可用列表），指出方法上的共性与分歧
## 核心发现对照
逐篇一句话核心结论（【编号】标注），并指出相互印证或矛盾之处
## 研究空白与下一步
综合来看还有哪些空隙值得研究，给出 2-3 个可行切入点"""

    try:
        if body.model:
            provider, bare_model = _resolve_model_provider(body.model)
            client, provider = _get_ai_client(provider)
            model = bare_model
        else:
            client, provider = _get_ai_client()
            model = _get_default_model(provider)
    except HTTPException:
        raise HTTPException(status_code=503, detail="AI API key not configured")

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=3072,
            temperature=0.4,
        )
        summary = (response.choices[0].message.content or "").strip()

        for p in papers:
            analysis_id = await PaperAnalysisCRUD.create_pending(db, p.id, model=model)
            await PaperAnalysisCRUD.update_analysis(db, analysis_id, summary, "success")
        await db.commit()
        return {"summary": summary, "model": model, "paper_count": len(papers)}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Batch analyze failed: {str(e)}")


class RelevanceRequest(BaseModel):
    topic: Optional[str] = None  # 不传则取用户进行中的选题


@router.post("/papers/{paper_id}/relevance")
async def paper_topic_relevance(
    paper_id: str,
    body: RelevanceRequest,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """「与我的选题相关性」评分（P1-8c）：LLM 打分 + 关键词重合规则兜底。"""
    from sqlalchemy import select as sa_select, desc as sa_desc
    from app.models import TopicProject

    paper = await PaperCRUD.get_paper_by_id(db, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    topic = (body.topic or "").strip()
    if not topic:
        uid = (x_user_id or "").strip() or "local"
        result = await db.execute(
            sa_select(TopicProject.title)
            .where(TopicProject.user_id == uid, TopicProject.status != "abandoned")
            .order_by(sa_desc(TopicProject.updated_at))
            .limit(3)
        )
        topics = [r[0] for r in result.all()]
        topic = "；".join(topics) if topics else ""
    if not topic:
        return {"score": None, "reason": "尚未设置研究选题：在选题中心保存一个选题后即可评估相关性。", "ai_used": False}

    paper_kws = _parse_json_list(paper.keywords_cn)
    overlap = [kw for kw in paper_kws if kw and kw[:6] in topic or (len(kw) > 1 and kw in topic)]
    rule_score = min(1.0, len(overlap) / max(1, min(5, len(paper_kws) or 1)))

    try:
        provider, bare_model = _resolve_model_provider(None)
        client, provider = _get_ai_client(provider)
        model = bare_model or _get_default_model(provider)
    except HTTPException:
        reason = f"关键词重合：{('、'.join(overlap[:5]) or '无')}。" if overlap else "关键词无直接重合。"
        return {"score": round(rule_score, 2), "reason": reason, "ai_used": False, "overlaps": overlap}

    try:
        prompt = f"""我的研究选题：{topic}

论文信息：
- 标题：{paper.title}
- 摘要：{(paper.abstract or '无')[:500]}
- 关键词：{', '.join(paper_kws) or '无'}

请评估这篇论文与我的选题的相关性，只输出 JSON（不要其他内容）：
{{"score": 0到1的小数, "reason": "一句话理由"}}"""
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.2,
        )
        import json as _json
        raw = (response.choices[0].message.content or "").strip()
        m = re.search(r"\{.*\}", raw, re.S)
        data = _json.loads(m.group(0)) if m else {}
        score = float(data.get("score", rule_score))
        score = max(0.0, min(1.0, score))
        return {"score": round(score, 2), "reason": str(data.get("reason", ""))[:300], "ai_used": True}
    except Exception:
        reason = f"关键词重合：{('、'.join(overlap[:5]) or '无')}。"
        return {"score": round(rule_score, 2), "reason": reason, "ai_used": False, "overlaps": overlap}


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

    system_prompt = f"""你是一位学术论文分析助手，正在与用户围绕一篇论文进行多轮对话。以下是当前讨论的论文信息：

## 论文信息
- 标题：{paper.title}
- 作者：{authors}
- 期刊：{journal}
- 关键词：{keywords}
- 子领域：{paper.economics_subfield or '未知'}

## 摘要
{paper.abstract or '无'}

## 对话规则
1. 基于以上论文信息回答用户问题，用中文，回答做到结构清晰、有针对性。
2. 可结合论文信息展开分析，但不要臆造论文中不存在的数据或内容。
3. 若问题超出论文范围，先诚实说明，再基于你的专业知识给出合理建议。
4. 这是多轮对话，请注意结合上下文保持回答连贯，不要自相矛盾。"""

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


@router.get("/authors/{author_name:path}/stats")
async def get_author_stats(author_name: str, db: AsyncSession = Depends(get_db)):
    """作者统计聚合（后端算，避免前端拉全量论文自行统计）。"""
    from sqlalchemy import text as sa_text

    result = await db.execute(
        sa_text("""
            SELECT DISTINCT p.id, p.authors, p.published_at, p.journal_name,
                   p.keywords_cn, p.economics_subfield
            FROM papers p, json_each(p.authors)
            WHERE p.authors IS NOT NULL AND json_each.value = :author_name
        """),
        {"author_name": author_name}
    )
    rows = result.fetchall()

    coauthor_counts: dict = {}
    year_counts: dict = {}
    journal_counts: dict = {}
    keyword_counts: dict = {}
    subfield_counts: dict = {}
    first_author_count = 0

    for _id, authors_raw, published_at, journal_name, keywords_raw, subfield in rows:
        authors = _parse_json_list(authors_raw)
        if authors and authors[0].strip() == author_name:
            first_author_count += 1
        for a in authors:
            a_clean = a.strip()
            if a_clean and a_clean != author_name:
                coauthor_counts[a_clean] = coauthor_counts.get(a_clean, 0) + 1
        if published_at:
            year_counts[str(published_at)[:4]] = year_counts.get(str(published_at)[:4], 0) + 1
        if journal_name:
            journal_counts[journal_name] = journal_counts.get(journal_name, 0) + 1
        for kw in _parse_json_list(keywords_raw):
            keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
        if subfield:
            subfield_counts[subfield] = subfield_counts.get(subfield, 0) + 1

    top = lambda d, n=1: sorted(d.items(), key=lambda x: -x[1])[:n]
    return {
        "total_papers": len(rows),
        "first_author_count": first_author_count,
        "recent_year": (sorted(year_counts, reverse=True) or [None])[0],
        "top_journal": (top(journal_counts) or [(None,)])[0][0],
        "top_keywords": [k for k, _ in top(keyword_counts, 5)],
        "top_subfield": (top(subfield_counts) or [(None,)])[0][0],
        "coauthors": [{"name": n, "count": c} for n, c in top(coauthor_counts, 10)],
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


