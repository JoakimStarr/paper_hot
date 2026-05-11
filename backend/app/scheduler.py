from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import uuid
import asyncio

from app.fetchers import (
    ArxivFetcher,
    GuanliShijieFetcher,
    JingjiYanjiuFetcher,
    JingjixueJikanFetcher,
    ShijieJingjiFetcher,
    ZhongguoGongyeJingjiFetcher,
    AmericanEconomicReviewFetcher
)
from app.fetchers_cnki import (
    CNKIDrissionFetcher,
    CNKITop50BatchFetcher,
    CNKI_TOP50_JOURNALS
)
from app.crud import PaperCRUD, CrawlLogCRUD
from app.ai_processor import AIProcessor
from app.scoring import ScoringSystem
from app.database import AsyncSessionLocal
from app.schemas import PaperCreate, CrawlLogCreate

logger = logging.getLogger(__name__)


class PaperScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.arxiv_fetcher = ArxivFetcher()
        self.ai_processor = AIProcessor()
        self.scoring_system = ScoringSystem()
        
        # 所有已实现真实爬取的期刊
        self.economics_fetchers = {
            "管理世界": GuanliShijieFetcher(),
            "经济研究": JingjiYanjiuFetcher(),
            "经济学季刊": JingjixueJikanFetcher(),
            "世界经济": ShijieJingjiFetcher(),
            "中国工业经济": ZhongguoGongyeJingjiFetcher(),
            "American Economic Review": AmericanEconomicReviewFetcher(),
        }
        
        # CNKI DrissionPage 爬虫（用于爬取知网期刊）
        self.cnki_batch_fetcher = CNKITop50BatchFetcher(headless=False)
        
        self.active_crawl_tasks: Dict[str, Dict[str, Any]] = {}
    
    def start(self):
        self.scheduler.add_job(
            self.fetch_and_process_papers,
            trigger=IntervalTrigger(hours=24),
            id='fetch_papers',
            replace_existing=True
        )
        
        self.scheduler.add_job(
            self.update_trend_scores,
            trigger=IntervalTrigger(hours=6),
            id='update_trends',
            replace_existing=True
        )
        
        self.scheduler.add_job(
            self.fetch_and_process_economics_journals,
            trigger=CronTrigger(hour=2, minute=0),
            id='fetch_economics_journals',
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("Paper scheduler started")
    
    def stop(self):
        self.scheduler.shutdown()
        logger.info("Paper scheduler stopped")

    def get_jobs_info(self) -> List[Dict]:
        jobs = self.scheduler.get_jobs()
        result = []
        for job in jobs:
            next_run = job.next_run_time
            result.append({
                "id": job.id,
                "name": job.name,
                "trigger_str": str(job.trigger),
                "next_run_time": next_run.isoformat() if next_run else None,
                "pending": job.pending,
            })
        return result

    def trigger_job(self, job_id: str):
        job = self.scheduler.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        job.modify(next_run_time=datetime.now())

    def pause(self):
        self.scheduler.pause()

    def resume(self):
        self.scheduler.resume()

    def is_running(self) -> bool:
        return self.scheduler.running
    
    async def fetch_and_process_papers(self):
        logger.info("Starting paper fetch and process job")
        
        try:
            papers_data = await self.arxiv_fetcher.fetch_papers(days_back=1, max_results=50)
            
            async with AsyncSessionLocal() as db:
                keyword_frequencies = await PaperCRUD.get_keyword_frequencies(db, days_back=7)
                previous_frequencies = await PaperCRUD.get_keyword_frequencies(db, days_back=14)
                
                for paper_data in papers_data:
                    existing = await PaperCRUD.get_paper_by_url(db, paper_data["url"])
                    if existing:
                        continue
                    
                    paper_create = PaperCreate(**paper_data)
                    paper = await PaperCRUD.create_paper(db, paper_create)
                    
                    summary, keywords, embedding, topic = await self.ai_processor.process_paper(
                        paper.abstract,
                        paper.title
                    )
                    
                    await PaperCRUD.create_paper_features(
                        db,
                        paper.id,
                        summary,
                        keywords or [],
                        embedding,
                        topic
                    )
                    
                    recency_score = self.scoring_system.compute_recency_score(paper.published_at)
                    venue_score = self.scoring_system.compute_venue_score(paper.venue, paper.source)
                    trend_score = self.scoring_system.compute_trend_score(
                        keywords or [],
                        keyword_frequencies,
                        previous_frequencies
                    )
                    final_score = self.scoring_system.compute_final_score(
                        recency_score,
                        venue_score,
                        trend_score
                    )
                    
                    await PaperCRUD.create_paper_score(
                        db,
                        paper.id,
                        recency_score,
                        venue_score,
                        trend_score,
                        final_score
                    )
                    
                    logger.info(f"Processed paper: {paper.title[:50]}...")
                
                await db.commit()
            
            logger.info(f"Successfully processed {len(papers_data)} papers")
            
        except Exception as e:
            logger.error(f"Error in fetch_and_process_papers: {e}")
    
    async def update_trend_scores(self):
        logger.info("Starting trend score update job")
        
        try:
            async with AsyncSessionLocal() as db:
                topic_count = await PaperCRUD.update_keyword_trends(db, months_back=6)
                paper_count = await PaperCRUD.bulk_update_paper_trend_scores(db)
                
                logger.info(f"Trend scores updated: {topic_count} topics, {paper_count} papers")
                
        except Exception as e:
            logger.error(f"Error in update_trend_scores: {e}")
    
    async def run_initial_fetch(self):
        logger.info("Running initial paper fetch")
        await self.fetch_and_process_papers()
    
    async def fetch_and_process_economics_journals(self, journal_names: Optional[List[str]] = None):
        logger.info("Starting economics journals fetch job")
        
        fetchers_to_use = self.economics_fetchers
        if journal_names:
            fetchers_to_use = {
                name: fetcher 
                for name, fetcher in self.economics_fetchers.items() 
                if name in journal_names
            }
        
        for journal_name, fetcher in fetchers_to_use.items():
            try:
                async with AsyncSessionLocal() as db:
                    active_crawl = await CrawlLogCRUD.get_active_crawl(db, journal_name)
                    if active_crawl:
                        logger.warning(f"Skipping {journal_name}: crawl already running (ID: {active_crawl.id})")
                        continue
                    
                    crawl_log_data = CrawlLogCreate(
                        journal_name=journal_name,
                        crawl_start_time=datetime.now()
                    )
                    crawl_log = await CrawlLogCRUD.create_crawl_log(db, crawl_log_data)
                    await db.commit()
                    
                    task_id = str(uuid.uuid4())
                    self.active_crawl_tasks[task_id] = {
                        "journal_name": journal_name,
                        "crawl_log_id": crawl_log.id,
                        "start_time": datetime.now(),
                        "status": "running"
                    }
                
                papers_data = await fetcher.fetch_papers(
                    start_date=datetime.now() - timedelta(days=180),
                    max_results=50
                )
                
                papers_fetched = 0
                papers_failed = 0
                
                async with AsyncSessionLocal() as db:
                    keyword_frequencies = await PaperCRUD.get_keyword_frequencies(db, days_back=7)
                    previous_frequencies = await PaperCRUD.get_keyword_frequencies(db, days_back=14)
                    
                    for paper_data in papers_data:
                        try:
                            existing = await PaperCRUD.get_paper_by_url(db, paper_data["url"])
                            if existing:
                                continue
                            
                            # 处理DOI字段：空字符串转换为None
                            if paper_data.get("doi") == "" or paper_data.get("doi") is None:
                                paper_data["doi"] = None
                            
                            paper_create = PaperCreate(**paper_data)
                            paper = await PaperCRUD.create_paper(db, paper_create)
                            
                            summary, keywords, embedding, topic = await self.ai_processor.process_paper(
                                paper.abstract,
                                paper.title
                            )
                            
                            await PaperCRUD.create_paper_features(
                                db,
                                paper.id,
                                summary,
                                keywords or [],
                                embedding,
                                topic
                            )
                            
                            recency_score = self.scoring_system.compute_recency_score(paper.published_at)
                            venue_score = self.scoring_system.compute_venue_score(paper.venue, paper.source)
                            trend_score = self.scoring_system.compute_trend_score(
                                keywords or [],
                                keyword_frequencies,
                                previous_frequencies
                            )
                            final_score = self.scoring_system.compute_final_score(
                                recency_score,
                                venue_score,
                                trend_score
                            )
                            
                            await PaperCRUD.create_paper_score(
                                db,
                                paper.id,
                                recency_score,
                                venue_score,
                                trend_score,
                                final_score
                            )
                            
                            papers_fetched += 1
                            logger.info(f"Processed economics paper from {journal_name}: {paper.title[:50]}...")
                            
                        except Exception as e:
                            papers_failed += 1
                            logger.error(f"Error processing paper from {journal_name}: {e}")
                            continue
                    
                    await CrawlLogCRUD.update_crawl_log(
                        db,
                        crawl_log.id,
                        crawl_end_time=datetime.now(),
                        papers_fetched=papers_fetched,
                        papers_failed=papers_failed,
                        status="completed"
                    )
                    
                    await db.commit()
                
                if task_id in self.active_crawl_tasks:
                    self.active_crawl_tasks[task_id]["status"] = "completed"
                    self.active_crawl_tasks[task_id]["end_time"] = datetime.now()
                
                logger.info(f"Completed crawl for {journal_name}: {papers_fetched} papers fetched, {papers_failed} failed")
                
            except Exception as e:
                logger.error(f"Error crawling {journal_name}: {e}")
                
                async with AsyncSessionLocal() as db:
                    await CrawlLogCRUD.update_crawl_log(
                        db,
                        crawl_log.id,
                        crawl_end_time=datetime.now(),
                        status="failed",
                        error_message=str(e)
                    )
                    await db.commit()
                
                if task_id in self.active_crawl_tasks:
                    self.active_crawl_tasks[task_id]["status"] = "failed"
                    self.active_crawl_tasks[task_id]["error"] = str(e)
    
    async def trigger_manual_crawl(self, journal_names: Optional[List[str]] = None) -> str:
        logger.info(f"Manual crawl triggered for journals: {journal_names or 'all economics journals'}")
        
        task_id = str(uuid.uuid4())
        
        async def run_crawl():
            await self.fetch_and_process_economics_journals(journal_names)
        
        asyncio.create_task(run_crawl())
        
        return task_id
    
    async def fetch_and_process_cnki_navi_journals(
        self,
        max_journals: Optional[int] = None
    ):
        """
        使用知网期刊导航方法爬取经济学期刊
        
        Args:
            max_journals: 最大爬取期刊数量，None表示爬取所有
        """
        logger.info(f"Starting CNKI Navi journals fetch - max_journals: {max_journals}")
        
        task_id = str(uuid.uuid4())
        self.active_crawl_tasks[task_id] = {
            "task_type": "cnki_navi",
            "start_time": datetime.now(),
            "status": "running"
        }
        
        try:
            from app.fetchers_cnki_navi import CNKINaviFetcher
            
            fetcher = CNKINaviFetcher(headless=False)
            
            # 获取期刊列表
            journals = fetcher.get_journals_list()
            if not journals:
                logger.error("No journals fetched from CNKI Navi")
                self.active_crawl_tasks[task_id]["status"] = "failed"
                self.active_crawl_tasks[task_id]["error"] = "No journals fetched"
                return
            
            # 限制期刊数量
            journals_to_fetch = list(journals.items())
            if max_journals:
                journals_to_fetch = journals_to_fetch[:max_journals]
            
            total_fetched = 0
            total_failed = 0
            
            # 逐个期刊爬取
            for journal_name, journal_url in journals_to_fetch:
                try:
                    logger.info(f"\n{'='*60}")
                    logger.info(f"Fetching journal: {journal_name}")
                    logger.info(f"{'='*60}")
                    
                    papers = fetcher.get_papers_from_journal(journal_name, journal_url)
                    
                    papers_fetched = 0
                    papers_failed = 0
                    
                    async with AsyncSessionLocal() as db:
                        for paper_info in papers:
                            try:
                                detail = fetcher.get_paper_detail(paper_info['url'])
                                if not detail:
                                    papers_failed += 1
                                    continue
                                
                                # 构建论文数据
                                paper_data = {
                                    **detail,
                                    'journal_name': journal_name,
                                    'year': paper_info.get('year', datetime.now().year),
                                    'source': 'CNKI',
                                    'discipline': '经济学',
                                    'venue': journal_name,
                                    'published_at': datetime(paper_info.get('year', datetime.now().year), 1, 1)
                                }
                                
                                # 保存到数据库
                                result = await PaperCRUD.create_paper_from_cnki(db, paper_data)
                                if result:
                                    # AI 处理：生成摘要、关键词、嵌入向量和主题
                                    summary, keywords, embedding, topic = await self.ai_processor.process_paper(
                                        detail.get('abstract', ''),
                                        detail.get('title', '')
                                    )
                                    await PaperCRUD.create_paper_features(
                                        db,
                                        result.id,
                                        summary,
                                        keywords or [],
                                        embedding,
                                        topic
                                    )
                                    papers_fetched += 1
                                    logger.info(f"Saved paper: {detail['title'][:50]}... → Topic: {topic}")
                                
                                fetcher._random_delay(2, 4)
                                
                            except Exception as e:
                                papers_failed += 1
                                logger.error(f"Error processing paper: {e}")
                                continue
                        
                        await db.commit()
                    
                    total_fetched += papers_fetched
                    total_failed += papers_failed
                    logger.info(f"Completed {journal_name}: {papers_fetched} fetched, {papers_failed} failed")
                    
                    fetcher._random_delay(5, 8)
                    
                except Exception as e:
                    logger.error(f"Error processing journal {journal_name}: {e}")
                    continue
            
            fetcher._close_browser()
            
            self.active_crawl_tasks[task_id]["status"] = "completed"
            self.active_crawl_tasks[task_id]["end_time"] = datetime.now()
            self.active_crawl_tasks[task_id]["total_fetched"] = total_fetched
            self.active_crawl_tasks[task_id]["total_failed"] = total_failed
            
            logger.info(f"\n{'='*60}")
            logger.info(f"CNKI Navi crawl completed: {total_fetched} fetched, {total_failed} failed")
            logger.info(f"{'='*60}")
            
        except Exception as e:
            logger.error(f"Error in CNKI Navi fetch: {e}")
            self.active_crawl_tasks[task_id]["status"] = "failed"
            self.active_crawl_tasks[task_id]["error"] = str(e)
    
    async def trigger_manual_cnki_navi_crawl(
        self,
        max_journals: Optional[int] = None
    ) -> str:
        """
        手动触发知网期刊导航爬取
        
        Args:
            max_journals: 最大期刊数量
            
        Returns:
            任务ID
        """
        logger.info(f"Manual CNKI Navi crawl triggered - max_journals: {max_journals}")
        
        task_id = str(uuid.uuid4())
        
        async def run_crawl():
            await self.fetch_and_process_cnki_navi_journals(max_journals=max_journals)
        
        asyncio.create_task(run_crawl())
        
        return task_id
    
    def get_crawl_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.active_crawl_tasks.get(task_id)
    
    def get_all_active_crawls(self) -> Dict[str, Dict[str, Any]]:
        return {
            task_id: task_info 
            for task_id, task_info in self.active_crawl_tasks.items() 
            if task_info.get("status") == "running"
        }
    
    async def fetch_and_process_cnki_top50(
        self,
        journal_names: Optional[List[str]] = None,
        max_results_per_journal: int = 20,
        max_journals: Optional[int] = None
    ):
        """
        使用 DrissionPage 爬取知网经济学TOP50期刊
        
        Args:
            journal_names: 指定期刊列表，None表示爬取所有
            max_results_per_journal: 每个期刊最大爬取数量
            max_journals: 最大爬取期刊数量
        """
        logger.info(f"Starting CNKI TOP50 fetch - max_journals: {max_journals}, max_per_journal: {max_results_per_journal}")
        
        task_id = str(uuid.uuid4())
        self.active_crawl_tasks[task_id] = {
            "task_type": "cnki_top50",
            "start_time": datetime.now(),
            "status": "running"
        }
        
        try:
            # 如果指定了期刊列表，过滤配置
            journals_to_fetch = None
            if journal_names:
                journals_to_fetch = {
                    name: CNKI_TOP50_JOURNALS[name]
                    for name in journal_names
                    if name in CNKI_TOP50_JOURNALS
                }
            
            # 执行批量爬取
            results = await self.cnki_batch_fetcher.fetch_all_journals(
                start_date=datetime(2025, 1, 1),
                end_date=datetime.now(),
                max_results_per_journal=max_results_per_journal,
                max_journals=max_journals
            )
            
            total_fetched = 0
            total_failed = 0
            
            # 处理每个期刊的结果
            for journal_name, papers_data in results.items():
                try:
                    papers_fetched = 0
                    papers_failed = 0
                    
                    async with AsyncSessionLocal() as db:
                        keyword_frequencies = await PaperCRUD.get_keyword_frequencies(db, days_back=7)
                        previous_frequencies = await PaperCRUD.get_keyword_frequencies(db, days_back=14)
                        
                        for paper_data in papers_data:
                            try:
                                # 检查是否已存在
                                existing = await PaperCRUD.get_paper_by_url(db, paper_data.get("url", ""))
                                if existing:
                                    continue
                                
                                # 处理DOI字段
                                if paper_data.get("doi") == "" or paper_data.get("doi") is None:
                                    paper_data["doi"] = None
                                
                                # 确保 venue 字段存在
                                if not paper_data.get("venue"):
                                    paper_data["venue"] = journal_name
                                
                                paper_create = PaperCreate(**paper_data)
                                paper = await PaperCRUD.create_paper(db, paper_create)
                                
                                # AI处理
                                summary, keywords, embedding, topic = await self.ai_processor.process_paper(
                                    paper.abstract,
                                    paper.title
                                )
                                
                                await PaperCRUD.create_paper_features(
                                    db,
                                    paper.id,
                                    summary,
                                    keywords or [],
                                    embedding,
                                    topic
                                )
                                
                                # 计算分数
                                recency_score = self.scoring_system.compute_recency_score(paper.published_at)
                                venue_score = self.scoring_system.compute_venue_score(paper.venue, paper.source)
                                trend_score = self.scoring_system.compute_trend_score(
                                    keywords or [],
                                    keyword_frequencies,
                                    previous_frequencies
                                )
                                final_score = self.scoring_system.compute_final_score(
                                    recency_score,
                                    venue_score,
                                    trend_score
                                )
                                
                                await PaperCRUD.create_paper_score(
                                    db,
                                    paper.id,
                                    recency_score,
                                    venue_score,
                                    trend_score,
                                    final_score
                                )
                                
                                papers_fetched += 1
                                logger.info(f"Processed CNKI paper from {journal_name}: {paper.title[:50]}...")
                                
                            except Exception as e:
                                papers_failed += 1
                                logger.error(f"Error processing CNKI paper from {journal_name}: {e}")
                                continue
                        
                        await db.commit()
                    
                    total_fetched += papers_fetched
                    total_failed += papers_failed
                    logger.info(f"Completed CNKI crawl for {journal_name}: {papers_fetched} fetched, {papers_failed} failed")
                    
                except Exception as e:
                    logger.error(f"Error processing CNKI journal {journal_name}: {e}")
                    total_failed += len(papers_data)
                    continue
            
            self.active_crawl_tasks[task_id]["status"] = "completed"
            self.active_crawl_tasks[task_id]["end_time"] = datetime.now()
            self.active_crawl_tasks[task_id]["total_fetched"] = total_fetched
            self.active_crawl_tasks[task_id]["total_failed"] = total_failed
            
            logger.info(f"CNKI TOP50 crawl completed: {total_fetched} fetched, {total_failed} failed")
            
        except Exception as e:
            logger.error(f"Error in CNKI TOP50 fetch: {e}")
            self.active_crawl_tasks[task_id]["status"] = "failed"
            self.active_crawl_tasks[task_id]["error"] = str(e)
    
    async def trigger_manual_cnki_crawl(
        self,
        journal_names: Optional[List[str]] = None,
        max_results_per_journal: int = 20,
        max_journals: Optional[int] = None
    ) -> str:
        """
        手动触发知网TOP50期刊爬取
        
        Args:
            journal_names: 指定期刊列表
            max_results_per_journal: 每个期刊最大结果数
            max_journals: 最大期刊数量
            
        Returns:
            任务ID
        """
        logger.info(f"Manual CNKI crawl triggered for journals: {journal_names or 'TOP50'}")
        
        task_id = str(uuid.uuid4())
        
        async def run_crawl():
            await self.fetch_and_process_cnki_top50(
                journal_names=journal_names,
                max_results_per_journal=max_results_per_journal,
                max_journals=max_journals
            )
        
        asyncio.create_task(run_crawl())
        
        return task_id
