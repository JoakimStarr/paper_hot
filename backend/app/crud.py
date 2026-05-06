from typing import List, Optional, Tuple
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
import json
import numpy as np

from app.models import Paper, PaperFeatures, PaperScore, TopicTrend, CrawlLog
from app.schemas import PaperCreate, CrawlLogCreate, CrawlLogUpdate


class PaperCRUD:
    @staticmethod
    async def create_paper(db: AsyncSession, paper_data: PaperCreate) -> Paper:
        db_paper = Paper(**paper_data.model_dump())
        db.add(db_paper)
        await db.flush()
        await db.refresh(db_paper)
        return db_paper
    
    @staticmethod
    async def get_paper_by_url(db: AsyncSession, url: str) -> Optional[Paper]:
        result = await db.execute(
            select(Paper).where(Paper.url == url)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_paper_by_id(db: AsyncSession, paper_id: str) -> Optional[Paper]:
        result = await db.execute(
            select(Paper)
            .options(selectinload(Paper.features), selectinload(Paper.scores))
            .where(Paper.id == paper_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_papers(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        topic: Optional[str] = None,
        source: Optional[str] = None,
        min_score: Optional[float] = None,
        days_back: Optional[int] = None,
        discipline: Optional[str] = None,
        economics_subfield: Optional[str] = None,
        journal_name: Optional[str] = None
    ) -> Tuple[List[Paper], int]:
        query = (
            select(Paper)
            .options(selectinload(Paper.features), selectinload(Paper.scores))
        )
        
        if topic:
            query = query.join(PaperFeatures).where(PaperFeatures.topic == topic)
        
        if source:
            query = query.where(Paper.source == source)
        
        if min_score is not None:
            query = query.join(PaperScore).where(PaperScore.final_score >= min_score)
        
        if days_back:
            cutoff_date = datetime.now() - timedelta(days=days_back)
            query = query.where(Paper.published_at >= cutoff_date)
        
        if discipline:
            query = query.where(Paper.discipline == discipline)
        
        if economics_subfield:
            query = query.where(Paper.economics_subfield == economics_subfield)
        
        if journal_name:
            query = query.where(Paper.journal_name == journal_name)
        
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        query = query.order_by(desc(Paper.created_at))
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        result = await db.execute(query)
        papers = result.scalars().all()
        
        return papers, total
    
    @staticmethod
    async def create_paper_features(
        db: AsyncSession,
        paper_id: str,
        summary: Optional[str],
        keywords: List[str],
        embedding: Optional[str],
        topic: Optional[str]
    ) -> PaperFeatures:
        features = PaperFeatures(
            paper_id=paper_id,
            summary=summary,
            keywords=keywords,
            embedding=embedding,
            topic=topic
        )
        db.add(features)
        await db.flush()
        return features
    
    @staticmethod
    async def create_paper_score(
        db: AsyncSession,
        paper_id: str,
        recency_score: float,
        venue_score: float,
        trend_score: float,
        final_score: float
    ) -> PaperScore:
        score = PaperScore(
            paper_id=paper_id,
            recency_score=recency_score,
            venue_score=venue_score,
            trend_score=trend_score,
            final_score=final_score
        )
        db.add(score)
        await db.flush()
        return score
    
    @staticmethod
    async def get_papers_with_embeddings(db: AsyncSession) -> Tuple[List[str], np.ndarray]:
        result = await db.execute(
            select(Paper.id, PaperFeatures.embedding)
            .join(PaperFeatures)
            .where(PaperFeatures.embedding.isnot(None))
        )
        
        paper_ids = []
        embeddings = []
        
        for row in result:
            paper_ids.append(str(row[0]))
            embedding_list = json.loads(row[1].strip('[]'))
            embeddings.append(embedding_list)
        
        return paper_ids, np.array(embeddings) if embeddings else np.array([])
    
    @staticmethod
    async def get_keyword_frequencies(db: AsyncSession, days_back: int = 7) -> dict:
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        result = await db.execute(
            select(PaperFeatures.keywords)
            .join(Paper)
            .where(Paper.created_at >= cutoff_date)
        )
        
        frequencies = {}
        for row in result:
            keywords = row[0] if row[0] else []
            for keyword in keywords:
                frequencies[keyword] = frequencies.get(keyword, 0) + 1
        
        return frequencies
    
    @staticmethod
    async def create_topic_trend(
        db: AsyncSession,
        topic: str,
        week_start: datetime,
        paper_count: int,
        growth_rate: float
    ) -> TopicTrend:
        trend = TopicTrend(
            topic=topic,
            week_start=week_start,
            paper_count=paper_count,
            growth_rate=growth_rate
        )
        db.add(trend)
        await db.flush()
        return trend
    
    @staticmethod
    async def get_topic_trends(db: AsyncSession, weeks_back: int = 4) -> List[TopicTrend]:
        cutoff_date = datetime.now() - timedelta(weeks=weeks_back)
        
        result = await db.execute(
            select(TopicTrend)
            .where(TopicTrend.week_start >= cutoff_date)
            .order_by(desc(TopicTrend.week_start), desc(TopicTrend.growth_rate))
        )
        
        return result.scalars().all()
    
    @staticmethod
    async def get_papers_by_topic(db: AsyncSession, topic: str, limit: int = 100) -> List[Paper]:
        result = await db.execute(
            select(Paper)
            .options(selectinload(Paper.features), selectinload(Paper.scores))
            .join(PaperFeatures)
            .where(PaperFeatures.topic == topic)
            .order_by(desc(PaperScore.final_score))
            .limit(limit)
        )
        
        return result.scalars().all()
    
    @staticmethod
    async def get_filter_statistics(db: AsyncSession) -> dict:
        """获取筛选条件的统计数据"""
        from sqlalchemy import func
        
        # 统计学科
        discipline_result = await db.execute(
            select(Paper.discipline, func.count(Paper.id))
            .where(Paper.discipline.isnot(None))
            .group_by(Paper.discipline)
        )
        discipline_counts = {row[0]: row[1] for row in discipline_result}
        
        # 统计子领域
        subfield_result = await db.execute(
            select(Paper.economics_subfield, func.count(Paper.id))
            .where(Paper.economics_subfield.isnot(None))
            .group_by(Paper.economics_subfield)
        )
        subfield_counts = {row[0]: row[1] for row in subfield_result}
        
        # 统计期刊
        journal_result = await db.execute(
            select(Paper.journal_name, func.count(Paper.id))
            .where(Paper.journal_name.isnot(None))
            .group_by(Paper.journal_name)
        )
        journal_counts = {row[0]: row[1] for row in journal_result}
        
        # 统计来源
        source_result = await db.execute(
            select(Paper.source, func.count(Paper.id))
            .where(Paper.source.isnot(None))
            .group_by(Paper.source)
        )
        source_counts = {row[0]: row[1] for row in source_result}
        
        # 统计主题
        topic_result = await db.execute(
            select(PaperFeatures.topic, func.count(Paper.id))
            .join(Paper)
            .where(PaperFeatures.topic.isnot(None))
            .group_by(PaperFeatures.topic)
        )
        topic_counts = {row[0]: row[1] for row in topic_result}
        
        # 统计分数分布
        score_result = await db.execute(
            select(PaperScore.final_score)
            .join(Paper)
        )
        scores = [row[0] for row in score_result if row[0] is not None]
        
        score_counts = {}
        for threshold in [0.5, 0.6, 0.7, 0.8, 0.9]:
            count = sum(1 for s in scores if s >= threshold)
            score_counts[f"≥ {int(threshold * 100)}%"] = count
        
        return {
            "discipline_counts": discipline_counts,
            "subfield_counts": subfield_counts,
            "journal_counts": journal_counts,
            "source_counts": source_counts,
            "topic_counts": topic_counts,
            "score_counts": score_counts,
            "total_papers": sum(discipline_counts.values()) if discipline_counts else 0
        }
    
    @staticmethod
    async def create_paper_from_cnki(db: AsyncSession, paper_data: dict) -> Optional[Paper]:
        """从CNKI数据创建论文"""
        try:
            # 检查是否已存在
            existing = await PaperCRUD.get_paper_by_url(db, paper_data['url'])
            if existing:
                logger.info(f"Paper already exists: {paper_data['title'][:50]}...")
                return None
            
            # 创建论文对象
            db_paper = Paper(
                title=paper_data['title'],
                abstract=paper_data.get('abstract', ''),
                authors=paper_data.get('authors', []),
                url=paper_data['url'],
                doi=paper_data.get('doi') or None,
                source=paper_data.get('source', 'CNKI'),
                venue=paper_data.get('journal_name', ''),
                published_at=datetime(paper_data.get('year', datetime.now().year), 1, 1),
                discipline=paper_data.get('discipline', '经济学'),
                journal_name=paper_data.get('journal_name', ''),
                keywords_cn=paper_data.get('keywords', [])
            )
            
            db.add(db_paper)
            await db.flush()
            await db.refresh(db_paper)
            
            # 创建默认的features
            features = PaperFeatures(
                paper_id=db_paper.id,
                summary_cn=paper_data.get('abstract', '')[:500],
                keywords_cn=paper_data.get('keywords', []),
                topic=None  # CNKI论文不自动分类主题
            )
            db.add(features)
            
            # 创建默认的scores
            scores = PaperScore(
                paper_id=db_paper.id,
                novelty_score=0.5,
                impact_score=0.5,
                recency_score=0.5,
                venue_score=0.7,
                final_score=0.55
            )
            db.add(scores)
            
            await db.flush()
            logger.info(f"Created paper: {paper_data['title'][:50]}...")
            return db_paper
            
        except Exception as e:
            logger.error(f"Error creating paper from CNKI data: {e}")
            return None


class CrawlLogCRUD:
    @staticmethod
    async def create_crawl_log(db: AsyncSession, log_data: CrawlLogCreate) -> CrawlLog:
        crawl_log = CrawlLog(**log_data.model_dump())
        db.add(crawl_log)
        await db.flush()
        await db.refresh(crawl_log)
        return crawl_log
    
    @staticmethod
    async def update_crawl_log(
        db: AsyncSession,
        log_id: int,
        crawl_end_time: Optional[datetime] = None,
        papers_fetched: Optional[int] = None,
        papers_failed: Optional[int] = None,
        status: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> Optional[CrawlLog]:
        result = await db.execute(
            select(CrawlLog).where(CrawlLog.id == log_id)
        )
        crawl_log = result.scalar_one_or_none()
        
        if not crawl_log:
            return None
        
        if crawl_end_time is not None:
            crawl_log.crawl_end_time = crawl_end_time
        if papers_fetched is not None:
            crawl_log.papers_fetched = papers_fetched
        if papers_failed is not None:
            crawl_log.papers_failed = papers_failed
        if status is not None:
            crawl_log.status = status
        if error_message is not None:
            crawl_log.error_message = error_message
        
        await db.flush()
        await db.refresh(crawl_log)
        return crawl_log
    
    @staticmethod
    async def get_crawl_logs(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        journal_name: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Tuple[List[CrawlLog], int]:
        query = select(CrawlLog)
        
        if status:
            query = query.where(CrawlLog.status == status)
        
        if journal_name:
            query = query.where(CrawlLog.journal_name.ilike(f"%{journal_name}%"))
        
        if start_date:
            query = query.where(CrawlLog.crawl_start_time >= start_date)
        
        if end_date:
            query = query.where(CrawlLog.crawl_start_time <= end_date)
        
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        query = query.order_by(desc(CrawlLog.crawl_start_time))
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        return logs, total
    
    @staticmethod
    async def get_crawl_log_by_id(db: AsyncSession, log_id: int) -> Optional[CrawlLog]:
        result = await db.execute(
            select(CrawlLog).where(CrawlLog.id == log_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_active_crawl(db: AsyncSession, journal_name: Optional[str] = None) -> Optional[CrawlLog]:
        query = select(CrawlLog).where(CrawlLog.status == "running")
        
        if journal_name:
            query = query.where(CrawlLog.journal_name == journal_name)
        
        query = query.order_by(desc(CrawlLog.crawl_start_time)).limit(1)
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
