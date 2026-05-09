import logging
import re
from typing import List, Optional, Tuple
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
import json
import numpy as np

from app.models import Paper, PaperFeatures, PaperScore, TopicTrend, CrawlLog
from app.schemas import PaperCreate, CrawlLogCreate, CrawlLogUpdate
from app.config import settings

logger = logging.getLogger(__name__)


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
    async def get_similar_papers(
        db: AsyncSession,
        paper_id: str,
        limit: int = 5
    ) -> List[Paper]:
        paper = await PaperCRUD.get_paper_by_id(db, paper_id)
        if not paper:
            return []
        
        conditions = []
        
        if paper.features and paper.features.topic:
            conditions.append(
                Paper.features.has(PaperFeatures.topic == paper.features.topic)
            )
        
        from sqlalchemy import or_
        query = (
            select(Paper)
            .options(selectinload(Paper.features), selectinload(Paper.scores))
            .where(Paper.id != paper_id)
        )
        
        if conditions:
            query = query.where(or_(*conditions))
        
        query = query.order_by(Paper.published_at.desc()).limit(limit)
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def get_all_paper_urls(db: AsyncSession) -> List[str]:
        """获取所有论文URL列表"""
        result = await db.execute(select(Paper.url))
        return [row[0] for row in result.fetchall() if row[0]]
    
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
        
        query = query.order_by(desc(Paper.published_at))
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
            existing = await PaperCRUD.get_paper_by_url(db, paper_data['url'])
            if existing:
                logger.info(f"Paper already exists: {paper_data['title'][:50]}...")
                return None
            
            # 验证必需字段：作者和关键词
            authors = paper_data.get('authors', [])
            keywords = paper_data.get('keywords', [])
            
            if not authors or len(authors) == 0:
                logger.warning(f"Skipping paper (no authors): {paper_data['title'][:50]}...")
                return None
            
            if not keywords or len(keywords) == 0:
                logger.warning(f"Skipping paper (no keywords): {paper_data['title'][:50]}...")
                return None
            
            year = paper_data.get('year', datetime.now().year)
            journal_issue = paper_data.get('journal_issue')
            
            if journal_issue:
                issue_match = re.search(r'第(\d+)期', journal_issue)
                if issue_match:
                    issue_num = int(issue_match.group(1))
                    month = min(issue_num, 12)
                    published_at = datetime(year, month, 1)
                else:
                    published_at = datetime(year, 1, 1)
            else:
                published_at = datetime(year, 1, 1)
            
            db_paper = Paper(
                title=paper_data['title'],
                abstract=paper_data.get('abstract', ''),
                authors=authors,
                url=paper_data['url'],
                doi=paper_data.get('doi') or None,
                source=paper_data.get('source', 'CNKI'),
                venue=paper_data.get('journal_name', ''),
                published_at=published_at,
                discipline=paper_data.get('discipline', '经济学'),
                journal_name=paper_data.get('journal_name', ''),
                journal_issue=journal_issue,
                keywords_cn=keywords
            )
            
            db.add(db_paper)
            await db.flush()
            await db.refresh(db_paper)
            
            # 创建默认的features
            features = PaperFeatures(
                paper_id=db_paper.id,
                summary=paper_data.get('abstract', '')[:500],
                keywords=keywords,
                topic=None  # CNKI论文不自动分类主题
            )
            db.add(features)
            
            # 创建默认的scores
            scores = PaperScore(
                paper_id=db_paper.id,
                recency_score=0.5,
                venue_score=0.7,
                trend_score=0.5,
                final_score=0.55
            )
            db.add(scores)
            
            await db.flush()
            logger.info(f"Created paper: {paper_data['title'][:50]}...")
            return db_paper
            
        except Exception as e:
            logger.error(f"Error creating paper from CNKI data: {e}")
            return None

    @staticmethod
    async def get_keyword_monthly_counts(db: AsyncSession, months_back: int = 12) -> dict:
        """
        查询过去 N 个月的论文，按 (关键词, 月) 聚合论文数量
        返回格式：{keyword: {month_start_date: count, ...}, ...}
        支持 SQLite 和 PostgreSQL
        """
        from sqlalchemy import text
        
        # 使用更宽松的时间范围以包含所有历史数据
        cutoff_date = datetime(2020, 1, 1)
        
        # 使用原生SQL查询，因为需要展开JSON数组
        if settings.database_url.startswith("sqlite"):
            # SQLite 使用 json_each 展开 JSON 数组
            query = text("""
                SELECT 
                    value as keyword,
                    strftime('%Y-%m', published_at) as month_start,
                    COUNT(*) as count
                FROM papers, json_each(keywords_cn)
                WHERE published_at >= :cutoff_date
                    AND keywords_cn IS NOT NULL
                    AND json_array_length(keywords_cn) > 0
                GROUP BY value, month_start
                ORDER BY value, month_start
            """)
        else:
            # PostgreSQL 使用 jsonb_array_elements_text
            query = text("""
                SELECT 
                    keyword,
                    DATE_TRUNC('month', published_at)::date as month_start,
                    COUNT(*) as count
                FROM papers,
                jsonb_array_elements_text(keywords_cn::jsonb) as keyword
                WHERE published_at >= :cutoff_date
                    AND keywords_cn IS NOT NULL
                GROUP BY keyword, DATE_TRUNC('month', published_at)
                ORDER BY keyword, month_start
            """)
        
        result = await db.execute(query, {"cutoff_date": cutoff_date})
        
        # 整理结果
        keyword_monthly_counts = {}
        for row in result:
            keyword = row[0]
            month_start = row[1]
            count = row[2]
            
            if keyword not in keyword_monthly_counts:
                keyword_monthly_counts[keyword] = {}
            keyword_monthly_counts[keyword][month_start] = count
        
        return keyword_monthly_counts

    @staticmethod
    async def update_keyword_trends(db: AsyncSession, months_back: int = 6) -> int:
        """
        更新关键词趋势数据
        1. 调用 get_keyword_monthly_counts 获取数据
        2. 计算月增长率
        3. 存储到 TopicTrend 表（复用该表，但存储的是关键词数据）
        返回更新的记录数
        """
        monthly_counts = await PaperCRUD.get_keyword_monthly_counts(db, months_back)
        updated_count = 0
        
        for keyword, month_data in monthly_counts.items():
            # 按月排序
            sorted_months = sorted(month_data.keys())
            
            for i, month_start in enumerate(sorted_months):
                current_count = month_data[month_start]
                
                # 计算增长率
                if i == 0 or sorted_months[i-1] not in month_data:
                    # 第一个月或前一个月没有数据，增长率为 0
                    growth_rate = 0.0
                else:
                    previous_count = month_data[sorted_months[i-1]]
                    if previous_count == 0:
                        growth_rate = 1.0 if current_count > 0 else 0.0
                    else:
                        growth_rate = (current_count - previous_count) / previous_count
                
                # 删除该月旧数据
                delete_result = await db.execute(
                    select(TopicTrend).where(
                        and_(
                            TopicTrend.topic == keyword,
                            TopicTrend.week_start == month_start
                        )
                    )
                )
                existing = delete_result.scalar_one_or_none()
                if existing:
                    await db.delete(existing)
                
                # 创建新记录
                trend = TopicTrend(
                    topic=keyword,
                    week_start=month_start if isinstance(month_start, datetime) else datetime.strptime(f"{month_start}-01", "%Y-%m-%d"),
                    paper_count=current_count,
                    growth_rate=growth_rate
                )
                db.add(trend)
                updated_count += 1
        
        await db.flush()
        return updated_count

    @staticmethod
    async def bulk_update_paper_trend_scores(db: AsyncSession) -> int:
        """
        批量更新论文趋势分数
        1. 查询所有 topic 非空的论文及其 PaperScore
        2. 从 TopicTrend 表获取每个主题的最新增长率
        3. 使用公式 trend_score = 0.5 + 0.5 * tanh(growth_rate) 更新
        返回更新的记录数
        """
        # 查询所有 topic 非空的论文及其 PaperScore
        result = await db.execute(
            select(Paper.id, PaperFeatures.topic, PaperScore.id.label('score_id'))
            .join(PaperFeatures)
            .join(PaperScore)
            .where(PaperFeatures.topic.isnot(None))
        )
        
        papers = result.fetchall()
        if not papers:
            return 0
        
        # 获取每个主题的最新增长率
        topic_growth_rates = {}
        topics = set(paper[1] for paper in papers)
        
        for topic in topics:
            trend_result = await db.execute(
                select(TopicTrend.growth_rate)
                .where(TopicTrend.topic == topic)
                .order_by(desc(TopicTrend.week_start))
                .limit(1)
            )
            latest_growth = trend_result.scalar_one_or_none()
            if latest_growth is not None:
                topic_growth_rates[topic] = latest_growth
        
        # 更新论文趋势分数
        updated_count = 0
        for paper_id, topic, score_id in papers:
            if topic in topic_growth_rates:
                growth_rate = topic_growth_rates[topic]
                trend_score = 0.5 + 0.5 * np.tanh(growth_rate)
                
                # 获取 PaperScore 记录并更新
                score_result = await db.execute(
                    select(PaperScore).where(PaperScore.id == score_id)
                )
                score = score_result.scalar_one_or_none()
                if score:
                    score.trend_score = trend_score
                    updated_count += 1
        
        await db.flush()
        return updated_count


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


class AIAnalysisReportCRUD:
    @staticmethod
    async def create_report(
        db: AsyncSession,
        summary: Optional[str],
        hot_topics: Optional[list],
        development_trends: Optional[list],
        keyword_insights: Optional[list],
        journal_insights: Optional[list],
        recommendations: Optional[list],
        raw_analysis: Optional[str],
        model: Optional[str],
        total_papers: int,
        tokens_used: int,
        processing_time_ms: int,
        status: str = "success",
        error_message: Optional[str] = None
    ) -> "AIAnalysisReport":
        from app.models import AIAnalysisReport
        report = AIAnalysisReport(
            summary=summary,
            hot_topics=hot_topics,
            development_trends=development_trends,
            keyword_insights=keyword_insights,
            journal_insights=journal_insights,
            recommendations=recommendations,
            raw_analysis=raw_analysis,
            model=model,
            total_papers=total_papers,
            tokens_used=tokens_used,
            processing_time_ms=processing_time_ms,
            status=status,
            error_message=error_message
        )
        db.add(report)
        await db.flush()
        await db.refresh(report)
        return report

    @staticmethod
    async def get_latest_report(db: AsyncSession) -> Optional["AIAnalysisReport"]:
        from app.models import AIAnalysisReport
        from sqlalchemy import select
        result = await db.execute(
            select(AIAnalysisReport)
            .where(AIAnalysisReport.status == "success")
            .order_by(desc(AIAnalysisReport.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_recent_reports(db: AsyncSession, limit: int = 10) -> list:
        from app.models import AIAnalysisReport
        from sqlalchemy import select
        result = await db.execute(
            select(AIAnalysisReport)
            .order_by(desc(AIAnalysisReport.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def get_report_by_id(db: AsyncSession, report_id: int) -> Optional["AIAnalysisReport"]:
        from app.models import AIAnalysisReport
        from sqlalchemy import select
        result = await db.execute(
            select(AIAnalysisReport).where(AIAnalysisReport.id == report_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_running_report(db: AsyncSession) -> Optional["AIAnalysisReport"]:
        from app.models import AIAnalysisReport
        result = await db.execute(
            select(AIAnalysisReport)
            .where(AIAnalysisReport.status == "running")
            .order_by(desc(AIAnalysisReport.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()
