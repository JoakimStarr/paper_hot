from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
from typing import Optional, List


class AuthorSchema(BaseModel):
    name: str


class PaperBase(BaseModel):
    title: str
    abstract: str
    authors: List[str]
    url: str
    source: str
    venue: Optional[str] = None
    published_at: Optional[datetime] = None
    discipline: Optional[str] = None
    journal_name: Optional[str] = None
    journal_issue: Optional[str] = None
    economics_subfield: Optional[str] = None
    cnki_subject: Optional[str] = None
    doi: Optional[str] = None
    keywords_cn: List[str] = []
    
    @field_validator('doi', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        if v == '' or v is None:
            return None
        return v


class PaperCreate(PaperBase):
    pass


class PaperFeaturesSchema(BaseModel):
    summary: Optional[str] = None
    keywords: List[str] = []
    topic: Optional[str] = None
    
    class Config:
        from_attributes = True


class PaperScoreSchema(BaseModel):
    recency_score: float = 0.0
    venue_score: float = 0.0
    trend_score: float = 0.0
    final_score: float = 0.0
    
    class Config:
        from_attributes = True


class PaperResponse(BaseModel):
    id: str
    title: str
    abstract: str
    authors: List[str]
    url: str
    source: str
    venue: Optional[str] = None
    published_at: Optional[datetime] = None
    discipline: Optional[str] = None
    journal_name: Optional[str] = None
    journal_issue: Optional[str] = None
    economics_subfield: Optional[str] = None
    doi: Optional[str] = None
    keywords_cn: List[str] = []
    created_at: datetime
    features: Optional[PaperFeaturesSchema] = None
    scores: Optional[PaperScoreSchema] = None
    
    class Config:
        from_attributes = True


class PaperListResponse(BaseModel):
    papers: List[PaperResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class PaperCardResponse(BaseModel):
    id: str
    title: str
    abstract: Optional[str] = None
    authors: List[str] = []
    url: Optional[str] = None
    source: Optional[str] = None
    venue: Optional[str] = None
    journal_name: Optional[str] = None
    journal_issue: Optional[str] = None
    economics_subfield: Optional[str] = None
    cnki_subject: Optional[str] = None
    doi: Optional[str] = None
    keywords_cn: List[str] = []
    published_at: Optional[datetime] = None
    topic: Optional[str] = None
    recency_score: float = 0.0
    venue_score: float = 0.0
    trend_score: float = 0.0
    final_score: float = 0.0
    created_at: datetime

    class Config:
        from_attributes = True


class PaperCardListResponse(BaseModel):
    papers: List[PaperCardResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class TrendingTopic(BaseModel):
    topic: str
    paper_count: int
    growth_rate: float
    trend: str = Field(description="rising, stable, or declining")


class TrendingTopicsResponse(BaseModel):
    topics: List[TrendingTopic]
    week_start: datetime
    week_end: datetime


class SimilarPaper(BaseModel):
    id: str
    title: str
    similarity_score: float
    topic: Optional[str] = None
    keywords_cn: List[str] = []
    
    class Config:
        from_attributes = True


class PaperDetailResponse(PaperResponse):
    similar_papers: List[SimilarPaper] = []
    should_read_score: Optional[float] = Field(None, description="AI-generated recommendation score")


class CrawlLogBase(BaseModel):
    journal_name: str
    crawl_start_time: datetime
    papers_fetched: int = 0
    papers_failed: int = 0
    status: str = "running"


class CrawlLogCreate(CrawlLogBase):
    pass


class CrawlLogUpdate(BaseModel):
    crawl_end_time: Optional[datetime] = None
    papers_fetched: Optional[int] = None
    papers_failed: Optional[int] = None
    status: Optional[str] = None
    error_message: Optional[str] = None


class CrawlLogResponse(BaseModel):
    id: int
    journal_name: str
    crawl_start_time: datetime
    crawl_end_time: Optional[datetime] = None
    papers_fetched: int
    papers_failed: int
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class CrawlLogListResponse(BaseModel):
    logs: List[CrawlLogResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class StructuredAnalysis(BaseModel):
    hot_topics: List[dict] = []
    development_trends: List[dict] = []
    keyword_insights: List[dict] = []
    journal_insights: List[dict] = []
    recommendations: List[dict] = []


class AIAnalysisReportResponse(BaseModel):
    id: int
    summary: Optional[str] = None
    hot_topics: Optional[List[dict]] = None
    development_trends: Optional[List[dict]] = None
    keyword_insights: Optional[List[dict]] = None
    journal_insights: Optional[List[dict]] = None
    recommendations: Optional[List[dict]] = None
    raw_analysis: Optional[str] = None
    model: Optional[str] = None
    total_papers: int = 0
    tokens_used: int = 0
    processing_time_ms: int = 0
    status: str = "success"
    created_at: datetime

    @field_validator('created_at', mode='before')
    @classmethod
    def ensure_timezone_aware(cls, v):
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    class Config:
        from_attributes = True


class AIAnalysisReportListResponse(BaseModel):
    reports: List[AIAnalysisReportResponse]
    total: int


class AIAnalysisResponseV2(BaseModel):
    report: AIAnalysisReportResponse
    cached: bool = False
