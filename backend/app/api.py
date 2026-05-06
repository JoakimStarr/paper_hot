from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from app.database import get_db
from app.schemas import (
    PaperResponse,
    PaperListResponse,
    TrendingTopicsResponse,
    TrendingTopic,
    PaperDetailResponse,
    SimilarPaper,
    CrawlLogResponse,
    CrawlLogListResponse
)
from app.crud import PaperCRUD, CrawlLogCRUD
from app.ai_processor import TrendAnalyzer
from app.fetchers import VenueDataFetcher
import json
import numpy as np

router = APIRouter()


class CrawlStartRequest(BaseModel):
    journal_names: Optional[List[str]] = None


class CrawlStartResponse(BaseModel):
    crawl_log_id: int
    status: str
    message: str


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


@router.get("/filter-statistics")
async def get_filter_statistics(db: AsyncSession = Depends(get_db)):
    """获取筛选条件的统计数据"""
    stats = await PaperCRUD.get_filter_statistics(db)
    return stats


@router.get("/papers/{paper_id}", response_model=PaperDetailResponse)
async def get_paper_detail(
    paper_id: str,
    db: AsyncSession = Depends(get_db)
):
    paper = await PaperCRUD.get_paper_by_id(db, paper_id)
    
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    similar_papers = []
    should_read_score = None
    
    if paper.features and paper.features.embedding:
        try:
            paper_ids, embeddings = await PaperCRUD.get_papers_with_embeddings(db)
            
            if len(embeddings) > 0:
                target_embedding = np.array(json.loads(paper.features.embedding.strip('[]')))
                
                analyzer = TrendAnalyzer()
                similar = analyzer.find_similar_papers(
                    target_embedding,
                    embeddings,
                    paper_ids,
                    top_k=5
                )
                
                for similar_id, similarity_score in similar:
                    if similar_id != str(paper.id):
                        similar_paper = await PaperCRUD.get_paper_by_id(db, similar_id)
                        if similar_paper:
                            similar_papers.append(SimilarPaper(
                                id=str(similar_paper.id),
                                title=similar_paper.title,
                                similarity_score=similarity_score,
                                topic=similar_paper.features.topic if similar_paper.features else None
                            ))
        except Exception as e:
            pass
    
    if paper.scores:
        should_read_score = paper.scores.final_score * 1.1
        should_read_score = min(should_read_score, 1.0)
    
    response = PaperDetailResponse(
        id=str(paper.id),
        title=paper.title,
        abstract=paper.abstract,
        authors=paper.authors,
        url=paper.url,
        source=paper.source,
        venue=paper.venue,
        published_at=paper.published_at,
        created_at=paper.created_at,
        features=paper.features,
        scores=paper.scores,
        similar_papers=similar_papers[:5],
        should_read_score=should_read_score
    )
    
    return response


@router.get("/trending-topics", response_model=TrendingTopicsResponse)
async def get_trending_topics(
    weeks_back: int = Query(4, ge=1, le=12),
    db: AsyncSession = Depends(get_db)
):
    trends = await PaperCRUD.get_topic_trends(db, weeks_back=weeks_back)
    
    topic_data = {}
    for trend in trends:
        if trend.topic not in topic_data:
            topic_data[trend.topic] = {
                "paper_count": 0,
                "growth_rate": 0.0
            }
        
        topic_data[trend.topic]["paper_count"] += trend.paper_count
        topic_data[trend.topic]["growth_rate"] = max(
            topic_data[trend.topic]["growth_rate"],
            trend.growth_rate
        )
    
    trending_topics = []
    for topic, data in topic_data.items():
        if data["growth_rate"] > 0.2:
            trend_status = "rising"
        elif data["growth_rate"] < -0.1:
            trend_status = "declining"
        else:
            trend_status = "stable"
        
        trending_topics.append(TrendingTopic(
            topic=topic,
            paper_count=data["paper_count"],
            growth_rate=data["growth_rate"],
            trend=trend_status
        ))
    
    trending_topics.sort(key=lambda x: x.growth_rate, reverse=True)
    
    now = datetime.now()
    week_start = now - __import__('datetime').timedelta(days=7)
    
    return TrendingTopicsResponse(
        topics=trending_topics[:10],
        week_start=week_start,
        week_end=now
    )


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
            crawl_log_id=0,
            status="started",
            message=f"Crawl task started with ID: {task_id}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start crawl: {str(e)}")


@router.get("/crawl/logs", response_model=CrawlLogListResponse)
async def get_crawl_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    journal_name: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    logs, total = await CrawlLogCRUD.get_crawl_logs(
        db,
        page=page,
        page_size=page_size,
        status=status,
        journal_name=journal_name,
        start_date=start_date,
        end_date=end_date
    )
    
    return CrawlLogListResponse(
        logs=[CrawlLogResponse.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total
    )


@router.get("/crawl/status")
async def get_crawl_status(db: AsyncSession = Depends(get_db)):
    active_crawl = await CrawlLogCRUD.get_active_crawl(db)
    
    recent_logs, _ = await CrawlLogCRUD.get_crawl_logs(db, page=1, page_size=5)
    
    return {
        "active_crawl": CrawlLogResponse.model_validate(active_crawl) if active_crawl else None,
        "recent_crawls": [CrawlLogResponse.model_validate(log) for log in recent_logs]
    }


@router.get("/journals")
async def get_journals():
    venue_scores = VenueDataFetcher.VENUE_SCORES
    
    economics_journals = [
        {"name": "经济研究", "score": 1.0, "type": "经济学"},
        {"name": "管理世界", "score": 0.95, "type": "经济学"},
        {"name": "经济学（季刊）", "score": 0.95, "type": "经济学"},
        {"name": "世界经济", "score": 0.9, "type": "经济学"},
        {"name": "中国工业经济", "score": 0.9, "type": "经济学"},
        {"name": "American Economic Review", "score": 1.0, "type": "经济学"},
    ]
    
    return {
        "journals": economics_journals,
        "total": len(economics_journals)
    }
