import logging
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel

from app.database import get_db
from app.schemas import (PaperResponse, PaperListResponse, TrendingTopicsResponse,
                         TrendingTopic, PaperDetailResponse, SimilarPaper,
                         CrawlLogResponse, CrawlLogListResponse,
                         AIAnalysisReportResponse, AIAnalysisReportListResponse)
from app.crud import PaperCRUD, CrawlLogCRUD, AIAnalysisReportCRUD
from app.ai_processor import TrendAnalyzer
from app.fetchers import VenueDataFetcher
from app.ai_service import ai_trend_service
from app.glm_analyzer import glm_analyzer
import asyncio
import time

logger = logging.getLogger(__name__)

router = APIRouter()


class CrawlStartRequest(BaseModel):
    journal_names: Optional[List[str]] = None


class CrawlStartResponse(BaseModel):
    crawl_log_id: int
    status: str
    message: str


class AIAnalysisResponse(BaseModel):
    analysis: str
    model: Optional[str] = None
    timestamp: Optional[str] = None
    status: str


class AIAnalysisV2Response(BaseModel):
    report: Optional[AIAnalysisReportResponse] = None
    cached: bool = False
    has_history: bool = False
    is_running: bool = False
    running_report_id: Optional[int] = None


@router.get("/papers", response_model=PaperListResponse)
async def get_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    topic: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, ge=0.0, le=1.0),
    days_back: Optional[int] = Query(None, ge=1),
    discipline: Optional[str] = Query(None),
    economics_subfield: Optional[str] = Query(None),
    journal_name: Optional[str] = Query(None),
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
        journal_name=journal_name
    )

    return PaperListResponse(
        papers=[PaperResponse.model_validate(paper) for paper in papers],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total
    )


@router.get("/papers/{paper_id}", response_model=PaperDetailResponse)
async def get_paper(
    paper_id: str,
    db: AsyncSession = Depends(get_db)
):
    paper = await PaperCRUD.get_paper_by_id(db, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    similar_papers = await PaperCRUD.get_similar_papers(db, paper_id, limit=5)

    should_read_score = None
    if paper.scores:
        should_read_score = paper.scores.final_score

    return PaperDetailResponse(
        **PaperResponse.model_validate(paper).model_dump(),
        similar_papers=[
            SimilarPaper(
                id=p.id,
                title=p.title,
                similarity_score=0.85,
                topic=p.features.topic if p.features else None
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


async def _collect_papers_and_keywords(db: AsyncSession) -> tuple:
    """收集论文数据和关键词趋势数据（用于AI分析）"""
    from sqlalchemy import select
    from app.models import Paper, TopicTrend

    result = await db.execute(
        select(Paper).order_by(Paper.published_at.desc())
    )
    papers = result.scalars().all()

    papers_data = [{
        'id': p.id,
        'title': p.title,
        'authors': p.authors if p.authors else [],
        'keywords': p.keywords_cn if p.keywords_cn else [],
        'abstract': p.abstract,
        'journal_name': p.journal_name,
        'published_at': p.published_at.isoformat() if p.published_at else None,
        'doi': p.doi,
    } for p in papers]

    result = await db.execute(
        select(TopicTrend).order_by(TopicTrend.growth_rate.desc())
    )
    trends = result.scalars().all()

    keywords_data = [{
        'topic': t.topic,
        'paper_count': t.paper_count,
        'growth_rate': t.growth_rate,
    } for t in trends]

    return papers_data, keywords_data


@router.get("/ai-analysis", response_model=AIAnalysisResponse)
async def get_ai_analysis_legacy(
    db: AsyncSession = Depends(get_db)
):
    """使用GLM AI分析论文趋势（旧版接口，保持兼容）"""
    from sqlalchemy import select
    from app.models import Paper, TopicTrend

    try:
        result = await db.execute(
            select(Paper).order_by(Paper.published_at.desc())
        )
        papers = result.scalars().all()

        papers_data = []
        for paper in papers:
            papers_data.append({
                'id': paper.id,
                'title': paper.title,
                'authors': paper.authors if paper.authors else [],
                'keywords': paper.keywords_cn if paper.keywords_cn else [],
                'abstract': paper.abstract,
                'journal_name': paper.journal_name,
                'published_at': paper.published_at.isoformat() if paper.published_at else None,
                'doi': paper.doi,
            })

        result = await db.execute(
            select(TopicTrend).order_by(TopicTrend.growth_rate.desc())
        )
        trends = result.scalars().all()

        keywords_data = []
        for trend in trends:
            keywords_data.append({
                'topic': trend.topic,
                'paper_count': trend.paper_count,
                'growth_rate': trend.growth_rate,
            })

        analysis_result = await glm_analyzer.analyze_trends(papers_data, keywords_data)

        if not analysis_result:
            raise HTTPException(
                status_code=503,
                detail="AI analysis service is not available. Please check Zhipu API key configuration."
            )

        return AIAnalysisResponse(**analysis_result)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze trends: {str(e)}")


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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai-analysis/v2/analyze", response_model=AIAnalysisV2Response)
async def start_ai_analysis(
    db: AsyncSession = Depends(get_db)
):
    """
    异步触发GLM趋势分析

    立即返回，分析在后台运行。前端通过 GET /ai-analysis/v2 轮询状态。
    """
    try:
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
                detail="AI analysis service is not available. Please check Zhipu API key configuration."
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
        logger.info(f"AI analysis task created (report_id={report_id})")

        asyncio.create_task(_run_analysis_background(report_id))

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
        raise HTTPException(status_code=500, detail=str(e))


async def _run_analysis_background(report_id: int):
    """后台运行AI分析任务"""
    from app.database import AsyncSessionLocal

    logger.info(f"Background analysis started for report_id={report_id}")
    start_time = time.time()

    try:
        async with AsyncSessionLocal() as db:
            report = await AIAnalysisReportCRUD.get_report_by_id(db, report_id)
            if not report:
                logger.error(f"Report {report_id} not found for background task")
                return

            papers_data, keywords_data = await _collect_papers_and_keywords(db)

            analysis_result = await ai_trend_service.analyze_trends(papers_data, keywords_data)

            if not analysis_result:
                report.status = "failed"
                report.error_message = "AI analysis returned no result after retries"
                await db.commit()
                logger.error(f"Background analysis {report_id} failed: no result")
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
            report.total_papers = len(papers_data)
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
                report = await AIAnalysisReportCRUD.get_report_by_id(db, report_id)
                if report:
                    report.status = "failed"
                    report.error_message = str(e)[:500]
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    report.processing_time_ms = elapsed_ms
                    await db.commit()
        except Exception as db_e:
            logger.error(f"Failed to update failed report {report_id}: {db_e}")


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


@router.post("/crawl/start", response_model=CrawlStartResponse)
async def start_crawl(
    request: CrawlStartRequest = Body(default=CrawlStartRequest()),
    db: AsyncSession = Depends(get_db)
):
    try:
        active_crawl = await CrawlLogCRUD.get_active_crawl(db)
        if active_crawl:
            raise HTTPException(
                status_code=400,
                detail="A crawl task is already running. Please wait for it to complete."
            )

        from app.main import scheduler
        task_id = await scheduler.trigger_manual_crawl(request.journal_names)

        return CrawlStartResponse(
            crawl_log_id=task_id,
            status="started",
            message=f"Crawl task started for journals: {request.journal_names or 'all'}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/crawl/status", response_model=CrawlLogListResponse)
async def get_crawl_status(
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    logs = await CrawlLogCRUD.get_recent_crawls(db, limit=limit)
    return CrawlLogListResponse(
        logs=[CrawlLogResponse.model_validate(log) for log in logs],
        total=len(logs)
    )


@router.post("/update-trend-scores")
async def update_trend_scores(db: AsyncSession = Depends(get_db)):
    """手动触发趋势分数更新"""
    try:
        await PaperCRUD.update_paper_trend_scores(db)
        await db.commit()
        return {"status": "success", "message": "Trend scores updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))