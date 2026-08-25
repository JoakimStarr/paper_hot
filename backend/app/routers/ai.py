"""AI 趋势分析、报告与选题对话接口。"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db, AsyncSessionLocal
from app.crud import AIAnalysisReportCRUD, TrendChatCRUD
from app.ai_service import ai_trend_service
from app.routers.deps import (
    verify_token, _parse_json_list, _isoformat_utc,
    _get_ai_client, _resolve_model_provider, _get_default_model, _stream_chat_response,
)
from app.schemas import AIAnalysisReportResponse, AIAnalysisReportListResponse

logger = logging.getLogger(__name__)
router = APIRouter()


class AIAnalysisV2Response(BaseModel):
    report: Optional[AIAnalysisReportResponse] = None
    cached: bool = False
    has_history: bool = False
    is_running: bool = False
    running_report_id: Optional[int] = None


async def _purge_stale_running_reports(db: AsyncSession):
    """清理服务重启遗留的 running 报告，避免前端无限轮询、无法发起新分析。"""
    deleted = await AIAnalysisReportCRUD.delete_stale_running_reports(db)
    if deleted:
        await db.commit()
        logger.warning(f"Purged {deleted} stale running AI report(s) orphaned by restart")


async def _collect_analysis_data(db: AsyncSession) -> dict:
    """收集全量聚合统计数据 + 精选样本（用于AI分析）

    策略：全量聚合 + 精选样本
    - 所有统计维度（期刊、年份、子领域、关键词频次、共现）用 SQL 聚合全量数据
    - 高分论文摘要只取前20篇精选样本
    - 这样既覆盖100%数据，又控制了发给AI的prompt大小
    """
    import time as _time
    from sqlalchemy import select, text as sa_text, func
    from app.models import Paper, TopicTrend

    t0 = _time.time()

    total_result = await db.execute(sa_text("SELECT COUNT(*) FROM papers"))
    total_papers = total_result.scalar()

    journal_result = await db.execute(sa_text("""
        SELECT journal_name, COUNT(*) as cnt
        FROM papers
        WHERE journal_name IS NOT NULL AND journal_name != ''
        GROUP BY journal_name
        ORDER BY cnt DESC
        LIMIT 20
    """))
    journal_dist = [{"name": row[0], "count": row[1]} for row in journal_result.fetchall()]

    year_result = await db.execute(sa_text("""
        SELECT substr(published_at, 1, 4) as year, COUNT(*) as cnt
        FROM papers
        WHERE published_at IS NOT NULL
        GROUP BY year
        ORDER BY year
    """))
    year_dist = [{"year": row[0], "count": row[1]} for row in year_result.fetchall()]

    subfield_result = await db.execute(sa_text("""
        SELECT economics_subfield, COUNT(*) as cnt
        FROM papers
        WHERE economics_subfield IS NOT NULL AND economics_subfield != ''
        GROUP BY economics_subfield
        ORDER BY cnt DESC
    """))
    subfield_dist = [{"subfield": row[0], "count": row[1]} for row in subfield_result.fetchall()]

    keyword_freq_result = await db.execute(sa_text("""
        SELECT value AS keyword, COUNT(*) as cnt
        FROM papers, json_each(keywords_cn)
        WHERE keywords_cn IS NOT NULL
        GROUP BY value
        ORDER BY cnt DESC
        LIMIT 30
    """))
    keyword_freq = [{"keyword": row[0], "count": row[1]} for row in keyword_freq_result.fetchall()]

    # 关键词共现统计收敛在 app/stats.py（与 network.py / topic.py 共用同一实现）
    from app.stats import keyword_cooccurrence
    cooccurrence_data = await keyword_cooccurrence(db, limit=15)

    subfield_keyword_result = await db.execute(sa_text("""
        SELECT p.economics_subfield, j.value AS keyword, COUNT(*) as cnt
        FROM papers p, json_each(p.keywords_cn) j
        WHERE p.economics_subfield IS NOT NULL AND p.economics_subfield != ''
          AND p.keywords_cn IS NOT NULL
        GROUP BY p.economics_subfield, j.value
        ORDER BY p.economics_subfield, cnt DESC
    """))
    subfield_keywords_raw = subfield_keyword_result.fetchall()
    subfield_keywords = {}
    for row in subfield_keywords_raw:
        sf = row[0]
        if sf not in subfield_keywords:
            subfield_keywords[sf] = []
        if len(subfield_keywords[sf]) < 5:
            subfield_keywords[sf].append({"keyword": row[1], "count": row[2]})

    year_keyword_result = await db.execute(sa_text("""
        SELECT substr(p.published_at, 1, 4) as year, j.value AS keyword, COUNT(*) as cnt
        FROM papers p, json_each(p.keywords_cn) j
        WHERE p.published_at IS NOT NULL AND p.keywords_cn IS NOT NULL
        GROUP BY year, j.value
        ORDER BY year, cnt DESC
    """))
    year_keyword_raw = year_keyword_result.fetchall()
    year_keywords = {}
    for row in year_keyword_raw:
        yr = row[0]
        if yr not in year_keywords:
            year_keywords[yr] = []
        if len(year_keywords[yr]) < 5:
            year_keywords[yr].append({"keyword": row[1], "count": row[2]})

    top_papers_result = await db.execute(
        select(Paper).order_by(Paper.published_at.desc()).limit(20)
    )
    top_papers_raw = top_papers_result.scalars().all()
    top_papers = [{
        'title': p.title,
        'abstract': (p.abstract or '')[:150],
        'journal_name': p.journal_name,
        'economics_subfield': p.economics_subfield,
        'published_at': _isoformat_utc(p.published_at) if p.published_at else None,
        'keywords': _parse_json_list(p.keywords_cn),
    } for p in top_papers_raw]

    result = await db.execute(
        select(TopicTrend).order_by(TopicTrend.growth_rate.desc()).limit(30)
    )
    trends = result.scalars().all()
    keywords_data = [{
        'topic': t.topic,
        'paper_count': t.paper_count,
        'growth_rate': t.growth_rate,
    } for t in trends]

    author_freq_result = await db.execute(sa_text("""
        SELECT value AS author, COUNT(*) as cnt
        FROM papers, json_each(authors)
        WHERE authors IS NOT NULL
        GROUP BY value
        ORDER BY cnt DESC
        LIMIT 15
    """))
    author_freq = [{"author": row[0], "count": row[1]} for row in author_freq_result.fetchall()]

    elapsed_ms = int((_time.time() - t0) * 1000)
    logger.info(f"Data collection completed in {elapsed_ms}ms, total_papers={total_papers}")

    return {
        "total_papers": total_papers,
        "journal_dist": journal_dist,
        "year_dist": year_dist,
        "subfield_dist": subfield_dist,
        "keyword_freq": keyword_freq,
        "cooccurrence": cooccurrence_data,
        "subfield_keywords": subfield_keywords,
        "year_keywords": year_keywords,
        "top_papers": top_papers,
        "keywords_trend": keywords_data,
        "author_freq": author_freq,
    }


@router.get("/ai-analysis/v2", response_model=AIAnalysisV2Response)
async def get_ai_analysis_v2(
    db: AsyncSession = Depends(get_db)
):
    """
    AI趋势分析V2状态查询接口

    返回:
    - 如果有运行中的分析任务: is_running=true, running_report_id=report_id
    - 如果有已完成的最新报告: report=最新报告, has_history=true
    - 无任何记录: report=null, has_history=false
    """
    try:
        await _purge_stale_running_reports(db)
        running = await AIAnalysisReportCRUD.get_latest_running_report(db)
        if running:
            return AIAnalysisV2Response(
                report=None,
                cached=False,
                has_history=False,
                is_running=True,
                running_report_id=running.id
            )

        latest = await AIAnalysisReportCRUD.get_latest_report(db)
        if latest:
            return AIAnalysisV2Response(
                report=AIAnalysisReportResponse.model_validate(latest),
                cached=True,
                has_history=True,
                is_running=False
            )

        return AIAnalysisV2Response(
            report=None,
            cached=False,
            has_history=False,
            is_running=False
        )

    except Exception as e:
        logger.error(f"Failed to get AI analysis status: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error ({type(e).__name__})")


@router.get("/ai-analysis/models")
async def get_ai_analysis_models():
    """获取可选用的 AI 模型列表（格式 provider/model），供前端选择器使用"""
    return {"models": ai_trend_service.get_model_status()}


class AnalyzeRequest(BaseModel):
    model: Optional[str] = None


@router.post("/ai-analysis/v2/analyze", response_model=AIAnalysisV2Response)
async def start_ai_analysis(
    body: Optional[AnalyzeRequest] = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token)
):
    """
    异步触发趋势分析

    立即返回，分析在后台运行。前端通过 GET /ai-analysis/v2 轮询状态。
    body.model 可选，格式 'provider/model'（如 zhipu/glm-4.7、my-llm/gpt-4o），
    指定后仅使用该模型分析；不传则按默认顺序自动选择。
    """
    try:
        await _purge_stale_running_reports(db)
        running = await AIAnalysisReportCRUD.get_latest_running_report(db)
        if running:
            return AIAnalysisV2Response(
                report=None,
                cached=False,
                has_history=False,
                is_running=True,
                running_report_id=running.id
            )

        if not ai_trend_service.is_available():
            latest = await AIAnalysisReportCRUD.get_latest_report(db)
            if latest:
                return AIAnalysisV2Response(
                    report=AIAnalysisReportResponse.model_validate(latest),
                    cached=True,
                    has_history=True,
                    is_running=False
                )
            raise HTTPException(
                status_code=503,
                detail="AI analysis service is not available. Please configure Zhipu or SiliconFlow API key."
            )

        report = await AIAnalysisReportCRUD.create_report(
            db,
            summary=None,
            hot_topics=None,
            development_trends=None,
            keyword_insights=None,
            journal_insights=None,
            recommendations=None,
            raw_analysis=None,
            model=None,
            total_papers=0,
            tokens_used=0,
            processing_time_ms=0,
            status="running"
        )
        await db.commit()
        report_id = report.id
        model = body.model if body else None
        logger.info(f"AI analysis task created (report_id={report_id}, model={model})")

        from app.main import spawn_background_task
        spawn_background_task(_run_analysis_background(report_id, model=model))

        return AIAnalysisV2Response(
            report=None,
            cached=False,
            has_history=False,
            is_running=True,
            running_report_id=report_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start AI analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error ({type(e).__name__})")


async def _run_analysis_background(report_id: int, model: Optional[str] = None):
    """后台运行AI分析任务（带120秒超时保护）"""
    from app.database import AsyncSessionLocal

    logger.info(f"Background analysis started for report_id={report_id}")
    start_time = time.time()

    try:
        async with AsyncSessionLocal() as db:
            report = await AIAnalysisReportCRUD.get_report_by_id(db, report_id)
            if not report:
                logger.error(f"Report {report_id} not found for background task")
                return

            analysis_data = await _collect_analysis_data(db)

        try:
            analysis_result = await asyncio.wait_for(
                ai_trend_service.analyze_trends(analysis_data, model=model),
                timeout=120
            )
        except asyncio.TimeoutError:
            async with AsyncSessionLocal() as db:
                await AIAnalysisReportCRUD.delete_report(db, report_id)
                await db.commit()
            logger.error(f"Background analysis {report_id} timed out after 120s, record deleted")
            return

        async with AsyncSessionLocal() as db:
            report = await AIAnalysisReportCRUD.get_report_by_id(db, report_id)
            if not report:
                return

            if not analysis_result:
                await AIAnalysisReportCRUD.delete_report(db, report_id)
                await db.commit()
                logger.error(f"Background analysis {report_id} failed: no result, record deleted")
                return

            elapsed_ms = int((time.time() - start_time) * 1000)
            report.summary = analysis_result.get("summary")
            report.hot_topics = analysis_result.get("hot_topics")
            report.development_trends = analysis_result.get("development_trends")
            report.keyword_insights = analysis_result.get("keyword_insights")
            report.journal_insights = analysis_result.get("journal_insights")
            report.recommendations = analysis_result.get("recommendations")
            report.raw_analysis = analysis_result.get("raw_analysis")
            report.model = analysis_result.get("model")
            report.total_papers = analysis_data.get("total_papers", 0)
            report.tokens_used = analysis_result.get("tokens_used", 0)
            report.processing_time_ms = elapsed_ms
            report.status = analysis_result.get("status", "success")
            await db.commit()

            logger.info(f"Background analysis {report_id} completed: "
                       f"model={report.model}, tokens={report.tokens_used}, time={elapsed_ms}ms")

    except Exception as e:
        logger.error(f"Background analysis {report_id} failed with exception: {e}")
        try:
            async with AsyncSessionLocal() as db:
                await AIAnalysisReportCRUD.delete_report(db, report_id)
                await db.commit()
        except Exception as db_e:
            logger.error(f"Failed to delete failed report {report_id}: {db_e}")


@router.get("/ai-analysis/reports", response_model=AIAnalysisReportListResponse)
async def get_ai_analysis_reports(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """获取历史AI分析报告列表"""
    reports = await AIAnalysisReportCRUD.get_recent_reports(db, limit=limit)
    return AIAnalysisReportListResponse(
        reports=[AIAnalysisReportResponse.model_validate(r) for r in reports],
        total=len(reports)
    )


@router.get("/ai-analysis/reports/{report_id}", response_model=AIAnalysisReportResponse)
async def get_ai_analysis_report(
    report_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取指定AI分析报告详情"""
    report = await AIAnalysisReportCRUD.get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return AIAnalysisReportResponse.model_validate(report)


class TrendChatRequest(BaseModel):
    messages: List[dict]
    model: Optional[str] = None


class TrendChatSaveRequest(BaseModel):
    messages: List[dict]


@router.post("/ai-analysis/reports/{report_id}/chat")
async def chat_about_trend(report_id: int, body: TrendChatRequest, db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    report = await AIAnalysisReportCRUD.get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    analysis_context = ""
    if report.summary:
        analysis_context += f"分析摘要：{report.summary[:500]}\n\n"
    if report.hot_topics:
        topics_text = "\n".join([
            f"- {t.get('topic', '')}: {t.get('description', '')[:200]}"
            for t in report.hot_topics if t.get('topic')
        ])
        if topics_text:
            analysis_context += f"研究热点：\n{topics_text}\n\n"
    if report.development_trends:
        trends_text = "\n".join([
            f"- {t.get('trend', '')} ({t.get('direction', '')}): {t.get('description', '')[:200]}"
            for t in report.development_trends if t.get('trend')
        ])
        if trends_text:
            analysis_context += f"发展趋势：\n{trends_text}\n\n"
    if report.keyword_insights:
        kw_text = "\n".join([
            f"- {t.get('cluster', '')}: {t.get('insight', '')[:200]}"
            for t in report.keyword_insights if t.get('cluster')
        ])
        if kw_text:
            analysis_context += f"关键词聚类：\n{kw_text}\n\n"
    if report.journal_insights:
        journal_text = "\n".join([
            f"- {t.get('journal', '')}: {t.get('focus', '')[:200]}"
            for t in report.journal_insights if t.get('journal')
        ])
        if journal_text:
            analysis_context += f"期刊分析：\n{journal_text}\n\n"
    if report.recommendations:
        rec_text = "\n".join([
            f"- {t.get('area', '')} ({t.get('opportunity_level', '')}): {t.get('description', '')[:200]}"
            for t in report.recommendations if t.get('area')
        ])
        if rec_text:
            analysis_context += f"研究建议：\n{rec_text}\n\n"

    if len(analysis_context) > 6000:
        analysis_context = analysis_context[:6000] + "\n\n...(内容过长已截断)"

    system_prompt = f"""你是一位专业的论文选题分析师。你的职责是基于AI趋势分析结果，帮助用户深入理解研究热点、发现选题机会、评估研究方向可行性。

以下是当前AI趋势分析的结果：

{analysis_context}

请基于以上分析结果回答用户的问题。你可以：
1. 深入解读某个研究热点的具体含义和潜在方向
2. 帮助用户评估某个选题的可行性和创新性
3. 提供具体的研究建议和切入点
4. 分析不同研究方向之间的关联和差异
5. 结合分析数据给出选题的优劣势分析

如果问题超出分析数据范围，请诚实说明，但可以基于你的专业知识给出合理建议。用中文回答，回答要有深度和针对性。"""

    messages = [{"role": "system", "content": system_prompt}] + body.messages

    try:
        provider, bare_model = _resolve_model_provider(body.model)
        client, provider = _get_ai_client(provider)
    except HTTPException:
        raise HTTPException(status_code=503, detail="AI API key not configured")

    return _stream_chat_response(client, provider, messages, model=bare_model)


@router.get("/ai-analysis/reports/{report_id}/chats")
async def get_trend_chat_history(report_id: int, db: AsyncSession = Depends(get_db)):
    messages = await TrendChatCRUD.get_chats(db, report_id)
    return [
        {"role": m.role, "content": m.content, "created_at": _isoformat_utc(m.created_at)}
        for m in messages
    ]


@router.post("/ai-analysis/reports/{report_id}/chats")
async def save_trend_chat_messages(report_id: int, body: TrendChatSaveRequest, db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    report = await AIAnalysisReportCRUD.get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    messages = body.messages
    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")
    for msg in messages:
        await TrendChatCRUD.save_message(db, report_id, msg["role"], msg["content"])
    await db.commit()
    return {"status": "saved", "count": len(messages)}


@router.delete("/ai-analysis/reports/{report_id}/chats")
async def clear_trend_chat_history(report_id: int, db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    report = await AIAnalysisReportCRUD.get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    await TrendChatCRUD.clear_chats(db, report_id)
    await db.commit()
    return {"status": "cleared"}


