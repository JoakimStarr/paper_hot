#!/usr/bin/env python3
"""
CNKI 期刊导航优化版爬取脚本
支持无头模式、5线程并发、异步保存、智能去重
"""

import sys
import os
import subprocess

# 自动激活虚拟环境
possible_venvs = [
    os.path.join(os.path.dirname(__file__), 'backend', '.venv'),
    os.path.join(os.path.dirname(__file__), 'backend', 'venv'),
    os.path.join(os.path.dirname(__file__), '.venv'),
    os.path.join(os.path.dirname(__file__), 'venv'),
]

VENV_PATH = None
for venv in possible_venvs:
    if os.path.exists(venv):
        VENV_PATH = venv
        break

if VENV_PATH:
    if sys.platform == 'win32':
        venv_python = os.path.join(VENV_PATH, 'Scripts', 'python.exe')
    else:
        venv_python = os.path.join(VENV_PATH, 'bin', 'python')
    
    if sys.executable != venv_python and os.path.exists(venv_python):
        print(f"正在激活虚拟环境: {VENV_PATH}")
        result = subprocess.run([venv_python] + sys.argv)
        sys.exit(result.returncode)
    else:
        print(f"✓ 虚拟环境已激活: {VENV_PATH}")
else:
    print(f"⚠ 未找到虚拟环境，使用系统 Python")

import asyncio
import json
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import threading

# 设置工作目录
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('cnki_crawl_optimized.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

from app.fetchers_cnki_navi import CNKINaviFetcher
from app.database import AsyncSessionLocal
from app.crud import PaperCRUD


class OptimizedCNKICrawler:
    """优化版CNKI爬虫"""
    
    def __init__(self, max_workers: int = 5, headless: bool = True):
        self.max_workers = max_workers
        self.headless = headless
        self.journal_queue = Queue()
        self.existing_urls = set()  # 内存中的已存在URL集合
        self.stats = {
            'total_journals': 0,
            'completed_journals': 0,
            'total_papers': 0,
            'saved_papers': 0,
            'skipped_papers': 0,
            'failed_papers': 0
        }
        self.stats_lock = threading.Lock()
        
    async def load_existing_urls(self):
        """加载数据库中已存在的论文URL"""
        logger.info("加载已存在的论文URL...")
        try:
            async with AsyncSessionLocal() as db:
                # 获取所有已存在的URL
                from sqlalchemy import select
                from app.models import Paper
                result = await db.execute(select(Paper.url))
                urls = result.scalars().all()
                self.existing_urls = set(urls)
                logger.info(f"已加载 {len(self.existing_urls)} 个已存在的URL")
        except Exception as e:
            logger.error(f"加载已存在URL失败: {e}")
            self.existing_urls = set()
    
    def is_url_exists(self, url: str) -> bool:
        """检查URL是否已存在"""
        return url in self.existing_urls
    
    def add_url_to_cache(self, url: str):
        """将URL添加到缓存"""
        self.existing_urls.add(url)
    
    async def save_papers_batch(self, papers_data: list):
        """批量保存论文到数据库"""
        if not papers_data:
            return 0, 0
        
        saved = 0
        skipped = 0
        
        try:
            async with AsyncSessionLocal() as db:
                for paper_data in papers_data:
                    try:
                        # 再次检查URL是否已存在
                        if self.is_url_exists(paper_data['url']):
                            skipped += 1
                            continue
                        
                        result = await PaperCRUD.create_paper_from_cnki(db, paper_data)
                        if result:
                            saved += 1
                            self.add_url_to_cache(paper_data['url'])
                            logger.info(f"Saved: {paper_data['title'][:60]}...")
                        else:
                            skipped += 1
                    except Exception as e:
                        logger.error(f"Error saving paper: {e}")
                        continue
                
                await db.commit()
        except Exception as e:
            logger.error(f"Error in batch save: {e}")
        
        return saved, skipped
    
    def crawl_journal(self, journal_name: str, journal_url: str, thread_id: int) -> list:
        """单个线程爬取一个期刊"""
        logger.info(f"[线程{thread_id}] 开始爬取期刊: {journal_name}")
        papers = []
        
        # 每个线程创建独立的fetcher实例
        fetcher = CNKINaviFetcher(headless=self.headless)
        
        try:
            # 获取论文列表
            paper_links = fetcher.get_papers_from_journal(journal_name, journal_url)
            logger.info(f"[线程{thread_id}] 期刊 '{journal_name}' 获取到 {len(paper_links)} 篇论文链接")
            
            # 检查是否遇到已存在的论文
            should_skip_journal = False
            for paper_info in paper_links:
                if self.is_url_exists(paper_info['url']):
                    logger.info(f"[线程{thread_id}] 遇到已存在论文，跳过期刊 '{journal_name}'")
                    should_skip_journal = True
                    break
            
            if should_skip_journal:
                return papers
            
            # 获取每篇论文的详情
            for i, paper_info in enumerate(paper_links, 1):
                try:
                    # 再次检查URL
                    if self.is_url_exists(paper_info['url']):
                        logger.info(f"[线程{thread_id}] 论文已存在，跳过: {paper_info['title'][:50]}...")
                        continue
                    
                    logger.info(f"[线程{thread_id}] [{i}/{len(paper_links)}] {paper_info['title'][:50]}...")
                    
                    detail = fetcher.get_paper_detail(paper_info['url'])
                    if detail:
                        paper_data = {
                            **detail,
                            'journal_name': journal_name,
                            'year': paper_info.get('year', datetime.now().year),
                            'source': 'CNKI',
                            'discipline': '经济学'
                        }
                        papers.append(paper_data)
                        self.add_url_to_cache(paper_info['url'])
                    
                    # 随机延迟
                    fetcher._random_delay(2, 4)
                    
                except Exception as e:
                    logger.error(f"[线程{thread_id}] 获取论文详情失败: {e}")
                    continue
            
            logger.info(f"[线程{thread_id}] 期刊 '{journal_name}' 完成，获取 {len(papers)} 篇论文")
            
        except Exception as e:
            logger.error(f"[线程{thread_id}] 爬取期刊 '{journal_name}' 失败: {e}")
        finally:
            fetcher._close_browser()
        
        # 更新统计
        with self.stats_lock:
            self.stats['completed_journals'] += 1
            self.stats['total_papers'] += len(papers)
        
        return papers
    
    async def run(self):
        """运行优化版爬虫"""
        print("="*70)
        print("CNKI 期刊导航优化版爬取脚本")
        print(f"配置: {self.max_workers}线程, 无头模式={self.headless}")
        print("="*70)
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-"*70)
        
        # 步骤1: 加载已存在的URL
        await self.load_existing_urls()
        
        # 步骤2: 获取期刊列表（使用一个fetcher实例）
        print("\n[步骤1/3] 获取期刊列表...")
        temp_fetcher = CNKINaviFetcher(headless=self.headless)
        try:
            journals = temp_fetcher.get_journals_list()
            print(f"✓ 成功获取 {len(journals)} 个期刊")
            
            # 保存期刊列表
            with open('journals_list.json', 'w', encoding='utf-8') as f:
                json.dump(journals, f, ensure_ascii=False, indent=2)
        finally:
            temp_fetcher._close_browser()
        
        if not journals:
            print("✗ 未获取到期刊列表，退出")
            return
        
        self.stats['total_journals'] = len(journals)
        
        # 步骤3: 使用线程池并发爬取
        print(f"\n[步骤2/3] 使用{self.max_workers}个线程并发爬取...")
        all_papers = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_journal = {
                executor.submit(self.crawl_journal, name, url, i+1): (name, url)
                for i, (name, url) in enumerate(journals.items())
            }
            
            # 处理完成的任务
            for future in as_completed(future_to_journal):
                journal_name, _ = future_to_journal[future]
                try:
                    papers = future.result()
                    all_papers.extend(papers)
                    
                    # 每获取10篇论文就异步保存
                    if len(all_papers) >= 10:
                        batch = all_papers[:10]
                        all_papers = all_papers[10:]
                        saved, skipped = await self.save_papers_batch(batch)
                        
                        with self.stats_lock:
                            self.stats['saved_papers'] += saved
                            self.stats['skipped_papers'] += skipped
                        
                        print(f"\n[进度] 已保存: {self.stats['saved_papers']}, 跳过: {self.stats['skipped_papers']}")
                
                except Exception as e:
                    logger.error(f"处理期刊 '{journal_name}' 结果时出错: {e}")
        
        # 保存剩余的论文
        if all_papers:
            saved, skipped = await self.save_papers_batch(all_papers)
            with self.stats_lock:
                self.stats['saved_papers'] += saved
                self.stats['skipped_papers'] += skipped
        
        # 步骤4: 保存到JSON
        print(f"\n[步骤3/3] 保存数据...")
        output_file = f'cnki_papers_optimized_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_papers, f, ensure_ascii=False, indent=2)
        print(f"✓ 论文数据已保存到 {output_file}")
        
        # 统计信息
        print(f"\n{'='*70}")
        print("爬取统计")
        print(f"{'='*70}")
        print(f"期刊数量: {self.stats['total_journals']}")
        print(f"完成期刊: {self.stats['completed_journals']}")
        print(f"论文总数: {self.stats['total_papers']}")
        print(f"保存成功: {self.stats['saved_papers']}")
        print(f"跳过重复: {self.stats['skipped_papers']}")
        print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")


async def main():
    """主函数"""
    # 创建优化版爬虫实例
    crawler = OptimizedCNKICrawler(max_workers=5, headless=True)
    
    try:
        await crawler.run()
    except KeyboardInterrupt:
        print("\n\n用户中断爬取")
    except Exception as e:
        print(f"\n✗ 爬取过程出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
