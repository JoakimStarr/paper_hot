import logging
from fastapi import APIRouter, Depends, Query, HTTPException, Body, Request, Header
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
import hashlib
import json

from app.database import get_db
from app.config import settings
from app.schemas import (PaperResponse, PaperListResponse,
                         PaperCardResponse, PaperCardListResponse,
                         TrendingTopicsResponse, TrendingTopic,
                         PaperDetailResponse, SimilarPaper,
                         CrawlLogResponse, CrawlLogListResponse,
                         AIAnalysisReportResponse, AIAnalysisReportListResponse)
from app.crud import PaperCRUD, CrawlLogCRUD, AIAnalysisReportCRUD, PaperAnalysisCRUD, PaperSimilarityCRUD, PaperChatCRUD
from app.ai_processor import TrendAnalyzer
from app.fetchers import VenueDataFetcher


async def verify_token(x_api_token: str = Header(default=None)):
    if settings.api_token and settings.api_token != "":
        if x_api_token is None or x_api_token != settings.api_token:
            raise HTTPException(status_code=401, detail="Invalid or missing API token")
    return True
from app.ai_service import ai_trend_service
from app.config import settings
import asyncio
import concurrent.futures
import time
import os

logger = logging.getLogger(__name__)

router = APIRouter()


class CrawlStartRequest(BaseModel):
    journal_names: Optional[List[str]] = None


class UpdateSettingsRequest(BaseModel):
    api_keys: Optional[dict] = None
    model_priority: Optional[List[str]] = None


def _mask_api_key(key: Optional[str]) -> str:
    if not key:
        return ""
    if len(key) > 8:
        return key[:4] + "****" + key[-4:]
    return "****"


@router.get("/settings")
async def get_settings_endpoint(token: bool = Depends(verify_token)):
    from app.config import Settings
    api_keys = {
        "zhipu": {
            "configured": bool(settings.zhipu_api_key),
            "masked": _mask_api_key(settings.zhipu_api_key),
        },
        "openai": {
            "configured": bool(settings.openai_api_key),
            "masked": _mask_api_key(settings.openai_api_key),
        },
        "siliconflow": {
            "configured": bool(settings.siliconflow_api_key),
            "masked": _mask_api_key(settings.siliconflow_api_key),
        },
    }
    models = ai_trend_service.get_model_status()
    from app.main import scheduler
    scheduler_info = {
        "running": scheduler.is_running(),
        "jobs": scheduler.get_jobs_info(),
    }
    api_token_configured = bool(settings.api_token)
    return {
        "api_keys": api_keys,
        "models": models,
        "scheduler": scheduler_info,
        "api_token_configured": api_token_configured,
    }


@router.put("/settings")
async def update_settings_endpoint(
    body: UpdateSettingsRequest,
    token: bool = Depends(verify_token)
):
    from app.config import Settings
    keys_changed = False
    models_changed = False

    if body.api_keys:
        key_mapping = {
            "zhipu": "zhipu_api_key",
            "openai": "openai_api_key",
            "siliconflow": "siliconflow_api_key",
        }
        for provider, value in body.api_keys.items():
            env_key = key_mapping.get(provider)
            if env_key and value is not None:
                Settings.update_setting(env_key, value)
                keys_changed = True

    if body.model_priority:
        ai_trend_service.update_models(body.model_priority)
        models_changed = True

    if keys_changed:
        ai_trend_service.reload()

    return {"status": "ok", "keys_changed": keys_changed, "models_changed": models_changed}


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


def _clean_author_name(name: str) -> str:
    import re
    name = name.strip().rstrip(',').rstrip('，').strip()
    name = re.sub(r'[\w.+-]+@[\w.+-]+', '', name)
    name = re.sub(r'@\.com', '', name)
    name = re.sub(r'\s+', '', name)
    return name

def _parse_json_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean_author_name(str(v)) for v in value if v and str(v).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [_clean_author_name(str(v)) for v in parsed if v and str(v).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _isoformat_utc(dt: datetime) -> str:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _paper_to_card(paper) -> PaperCardResponse:
    return PaperCardResponse(
        id=paper.id,
        title=paper.title,
        abstract=paper.abstract,
        authors=_parse_json_list(paper.authors),
        url=paper.url,
        source=paper.source,
        venue=paper.venue,
        journal_name=paper.journal_name,
        journal_issue=paper.journal_issue,
        economics_subfield=paper.economics_subfield,
        doi=paper.doi,
        keywords_cn=_parse_json_list(paper.keywords_cn),
        published_at=paper.published_at,
        topic=paper.features.topic if paper.features else None,
        recency_score=paper.scores.recency_score if paper.scores else 0.0,
        venue_score=paper.scores.venue_score if paper.scores else 0.0,
        trend_score=paper.scores.trend_score if paper.scores else 0.0,
        final_score=paper.scores.final_score if paper.scores else 0.0,
        created_at=paper.created_at
    )


def _compute_cache_key(prefix: str, total: int, page: int, page_size: int) -> str:
    return hashlib.md5(f"{prefix}:{total}:{page}:{page_size}".encode()).hexdigest()


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
        journal_name=journal_name,
        search=search,
        search_field=search_field,
        sort_by=sort_by,
        sort_order=sort_order
    )

    etag = _compute_cache_key("papers", total, page, page_size)

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


@router.get("/stats")
async def get_system_stats(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text as sa_text

    try:
        result = await db.execute(sa_text("""
            SELECT
                (SELECT COUNT(*) FROM papers) AS total_papers,
                (SELECT COUNT(DISTINCT journal_name) FROM papers WHERE journal_name IS NOT NULL) AS journal_count,
                (SELECT COUNT(DISTINCT keywords_cn) FROM papers WHERE keywords_cn IS NOT NULL) AS keyword_count,
                (SELECT created_at FROM papers ORDER BY created_at DESC LIMIT 1) AS latest_created_at,
                (SELECT created_at FROM crawl_logs ORDER BY created_at DESC LIMIT 1) AS latest_crawl_at
        """))
        row = result.fetchone()
        total_papers = row[0]
        journal_count = row[1]
        keyword_count = row[2]
        latest_created_at = row[3]
        latest_crawl_at = row[4]

        result = await db.execute(sa_text("""
            SELECT 'source' AS kind, source AS key, COUNT(*) AS cnt FROM papers GROUP BY source
            UNION ALL
            SELECT 'year' AS kind, CAST(SUBSTR(published_at, 1, 4) AS TEXT) AS key, COUNT(*) AS cnt
            FROM papers WHERE published_at IS NOT NULL GROUP BY SUBSTR(published_at, 1, 4)
        """))
        source_counts = {}
        year_counts = {}
        for row in result:
            if row[0] == 'source':
                source_counts[row[1]] = row[2]
            else:
                year_counts[row[1]] = row[2]

        result = await db.execute(sa_text("""
            SELECT journal_name, COUNT(*) AS cnt
            FROM papers
            WHERE journal_name IS NOT NULL
            GROUP BY journal_name
            ORDER BY cnt DESC
            LIMIT 10
        """))
        top_journals = {}
        for row in result:
            top_journals[row[0]] = row[1]

        from app.config import BASE_DIR
        db_path = BASE_DIR / "data" / "paperpulse.db"
        db_size_mb = 0.0
        if db_path.exists():
            db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)

        from app.main import scheduler
        scheduler_running = scheduler.is_running()

        return {
            "total_papers": total_papers,
            "journal_count": journal_count,
            "keyword_count": keyword_count,
            "latest_paper_at": str(latest_created_at) if latest_created_at else None,
            "latest_crawl_at": str(latest_crawl_at) if latest_crawl_at else None,
            "source_counts": source_counts,
            "year_counts": year_counts,
            "top_journals": top_journals,
            "db_size_mb": db_size_mb,
            "scheduler_running": scheduler_running,
        }
    except Exception as e:
        logger.error(f"Failed to get system stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

    cooccurrence_result = await db.execute(sa_text("""
        SELECT a.value AS kw1, b.value AS kw2, COUNT(*) AS cnt
        FROM papers p, json_each(p.keywords_cn) a, json_each(p.keywords_cn) b
        WHERE p.keywords_cn IS NOT NULL AND a.value < b.value
        GROUP BY a.value, b.value
        ORDER BY cnt DESC
        LIMIT 15
    """))
    cooccurrence_data = [{"kw1": row[0], "kw2": row[1], "count": row[2]} for row in cooccurrence_result.fetchall()]

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


@router.get("/ai-analysis", response_model=AIAnalysisResponse)
async def get_ai_analysis_legacy(
    db: AsyncSession = Depends(get_db)
):
    """使用GLM AI分析论文趋势（旧版接口，内部使用AITrendService）"""
    try:
        if not ai_trend_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="AI analysis service is not available. Please check Zhipu API key configuration."
            )

        analysis_data = await _collect_analysis_data(db)

        analysis_result = await ai_trend_service.analyze_trends(analysis_data)

        if not analysis_result:
            raise HTTPException(
                status_code=503,
                detail="AI analysis service returned no result."
            )

        return AIAnalysisResponse(
            analysis=analysis_result.get("raw_analysis", analysis_result.get("summary", "")),
            model=analysis_result.get("model"),
            timestamp=analysis_result.get("timestamp"),
            status=analysis_result.get("status", "success")
        )

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
                ai_trend_service.analyze_trends(analysis_data),
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


@router.post("/crawl/start", response_model=CrawlStartResponse)
async def start_crawl(
    request: CrawlStartRequest = Body(default=CrawlStartRequest()),
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token)
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
async def update_trend_scores(db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    """手动触发趋势分数更新"""
    try:
        await PaperCRUD.bulk_update_paper_trend_scores(db)
        await db.commit()
        return {"status": "success", "message": "Trend scores updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_glm_client():
    from zai import ZhipuAiClient
    api_key = settings.zhipu_api_key
    if not api_key:
        raise HTTPException(status_code=503, detail="Zhipu API key not configured")
    return ZhipuAiClient(api_key=api_key)


@router.post("/papers/{paper_id}/analyze")
async def analyze_paper(paper_id: str, db: AsyncSession = Depends(get_db)):
    paper = await PaperCRUD.get_paper_by_id(db, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    pending = await PaperAnalysisCRUD.get_latest_pending(db, paper_id)
    if pending:
        return {"analysis": None, "status": "pending", "message": "分析正在进行中"}

    authors = ", ".join(paper.authors) if paper.authors else "未知"
    keywords = ", ".join(paper.keywords_cn) if paper.keywords_cn else "未知"
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

    analysis_id = await PaperAnalysisCRUD.create_pending(db, paper_id)
    await db.commit()

    try:
        client = _get_glm_client()
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="glm-4.5-air",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        analysis_text = response.choices[0].message.content
        await PaperAnalysisCRUD.update_analysis(db, analysis_id, analysis_text, "success")
        await db.commit()
        return {"analysis": analysis_text, "status": "success"}
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


class ChatSaveRequest(BaseModel):
    messages: List[dict]


@router.post("/papers/{paper_id}/chat")
async def chat_about_paper(paper_id: str, body: ChatRequest, db: AsyncSession = Depends(get_db)):
    paper = await PaperCRUD.get_paper_by_id(db, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    authors = ", ".join(paper.authors) if paper.authors else "未知"
    keywords = ", ".join(paper.keywords_cn) if paper.keywords_cn else "未知"
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
        client = _get_glm_client()
    except HTTPException:
        raise HTTPException(status_code=503, detail="Zhipu API key not configured")

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def run_stream():
            try:
                response = client.chat.completions.create(
                    model="glm-4.5-air",
                    messages=messages,
                    stream=True,
                    max_tokens=4096,
                )
                for chunk in response:
                    if chunk.choices:
                        delta = chunk.choices[0].delta
                        content = getattr(delta, "content", None)
                        if content:
                            loop.call_soon_threadsafe(queue.put_nowait, content)
                loop.call_soon_threadsafe(queue.put_nowait, None)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, f"[ERROR] {e}")
                loop.call_soon_threadsafe(queue.put_nowait, None)

        with concurrent.futures.ThreadPoolExecutor() as pool:
            pool.submit(run_stream)
            while True:
                item = await queue.get()
                if item is None:
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    break
                yield f"data: {json.dumps({'content': item})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/papers/{paper_id}/chats")
async def get_chat_history(paper_id: str, db: AsyncSession = Depends(get_db)):
    messages = await PaperChatCRUD.get_chats(db, paper_id)
    return [
        {"role": m.role, "content": m.content, "created_at": _isoformat_utc(m.created_at)}
        for m in messages
    ]


@router.post("/papers/{paper_id}/chats")
async def save_chat_messages(paper_id: str, body: ChatSaveRequest, db: AsyncSession = Depends(get_db)):
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


@router.post("/recompute-all-similarities")
async def recompute_all_similarities(db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    from sqlalchemy import select
    from app.models import Paper
    from app.similarity import compute_all_similarities

    try:
        batch_size = 200
        offset = 0
        all_pairs = []

        while True:
            result = await db.execute(
                select(Paper.id, Paper.abstract)
                .order_by(Paper.id)
                .offset(offset)
                .limit(batch_size)
            )
            batch = [(r[0], r[1]) for r in result.all()]
            if not batch:
                break

            if len(batch) >= 2:
                similarities = compute_all_similarities(batch)
                all_pairs.extend(similarities)

            offset += batch_size

        if len(all_pairs) == 0:
            return {"status": "skipped", "message": "Need at least 2 papers", "pairs": 0}

        await PaperSimilarityCRUD.clear_all(db)
        await db.flush()

        from app.models import PaperSimilarity
        for id_a, id_b, score in all_pairs:
            sim = PaperSimilarity(paper_id_a=id_a, paper_id_b=id_b, similarity_score=score)
            db.add(sim)

        await db.commit()
        return {"status": "success", "message": f"Computed {len(all_pairs)} pairs"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recompute all failed: {str(e)}")


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


@router.get("/scheduler/jobs")
async def get_scheduler_jobs(token: bool = Depends(verify_token)):
    from app.main import scheduler
    jobs = scheduler.get_jobs_info()
    running = scheduler.is_running()
    return {"running": running, "jobs": jobs}


@router.post("/scheduler/trigger/{job_id}")
async def trigger_scheduler_job(job_id: str, token: bool = Depends(verify_token)):
    from app.main import scheduler
    try:
        scheduler.trigger_job(job_id)
        return {"status": "ok", "message": f"Job {job_id} triggered"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/scheduler/toggle")
async def toggle_scheduler(token: bool = Depends(verify_token)):
    from app.main import scheduler
    if scheduler.is_running():
        scheduler.pause()
        return {"status": "paused"}
    else:
        scheduler.resume()
        return {"status": "resumed"}


@router.post("/maintenance/cleanup")
async def cleanup_database(db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    from sqlalchemy import text as sa_text

    try:
        deleted_papers = 0
        deleted_features = 0
        deleted_scores = 0
        deleted_reports = 0

        result = await db.execute(sa_text("""
            DELETE FROM papers
            WHERE title IS NULL OR title = '' OR abstract IS NULL OR abstract = ''
        """))
        deleted_papers = result.rowcount or 0
        await db.flush()

        result = await db.execute(sa_text("""
            DELETE FROM paper_features
            WHERE paper_id NOT IN (SELECT id FROM papers)
        """))
        deleted_features = result.rowcount or 0
        await db.flush()

        result = await db.execute(sa_text("""
            DELETE FROM paper_scores
            WHERE paper_id NOT IN (SELECT id FROM papers)
        """))
        deleted_scores = result.rowcount or 0
        await db.flush()

        result = await db.execute(sa_text("""
            DELETE FROM ai_analysis_reports
            WHERE status = 'running'
            AND created_at < datetime('now', '-10 minutes')
        """))
        deleted_reports = result.rowcount or 0

        await db.commit()

        return {
            "deleted_papers": deleted_papers,
            "deleted_features": deleted_features,
            "deleted_scores": deleted_scores,
            "deleted_reports": deleted_reports,
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))