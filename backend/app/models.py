from sqlalchemy import Column, String, DateTime, Float, JSON, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base
from app.config import settings


def get_uuid_column():
    if settings.database_url.startswith("sqlite"):
        return Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    else:
        from sqlalchemy.dialects.postgresql import UUID
        return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Paper(Base):
    __tablename__ = "papers"
    
    id = get_uuid_column()
    title = Column(String(500), nullable=False, index=True)
    abstract = Column(Text, nullable=False)
    authors = Column(JSON, default=list)
    url = Column(String(500), nullable=False, unique=True)
    source = Column(String(50), nullable=False, index=True)
    venue = Column(String(100), nullable=True)
    published_at = Column(DateTime, nullable=True, index=True)
    discipline = Column(String(50), nullable=True, index=True)
    journal_name = Column(String(200), nullable=True, index=True)
    journal_issue = Column(String(100), nullable=True)
    economics_subfield = Column(String(100), nullable=True, index=True)
    doi = Column(String(200), nullable=True, unique=True)
    keywords_cn = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    features = relationship("PaperFeatures", back_populates="paper", uselist=False, cascade="all, delete-orphan")
    scores = relationship("PaperScore", back_populates="paper", uselist=False, cascade="all, delete-orphan")


class PaperFeatures(Base):
    __tablename__ = "paper_features"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), unique=True, nullable=False)
    summary = Column(Text, nullable=True)
    keywords = Column(JSON, default=list)
    embedding = Column(String, nullable=True)
    topic = Column(String(50), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    paper = relationship("Paper", back_populates="features")


class PaperScore(Base):
    __tablename__ = "paper_scores"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), unique=True, nullable=False)
    recency_score = Column(Float, default=0.0)
    venue_score = Column(Float, default=0.0)
    trend_score = Column(Float, default=0.0)
    final_score = Column(Float, default=0.0, index=True)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    paper = relationship("Paper", back_populates="scores")


class TopicTrend(Base):
    __tablename__ = "topic_trends"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    topic = Column(String(50), nullable=False, index=True)
    week_start = Column(DateTime, nullable=False, index=True)
    paper_count = Column(Integer, default=0)
    growth_rate = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CrawlLog(Base):
    __tablename__ = "crawl_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    journal_name = Column(String(200), nullable=False, index=True)
    crawl_start_time = Column(DateTime, nullable=False)
    crawl_end_time = Column(DateTime, nullable=True)
    papers_fetched = Column(Integer, default=0)
    papers_failed = Column(Integer, default=0)
    status = Column(String(20), nullable=False, default="running", index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
