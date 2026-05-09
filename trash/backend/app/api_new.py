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
from app.glm_analyzer import glm_analyzer
import json
import numpy as np

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