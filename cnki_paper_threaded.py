#!/usr/bin/env python3
"""
知网期刊爬虫 - 多线程版本
每个线程负责一个期刊，支持同时打开多个浏览器窗口
"""

import json
import re
import time
import random
import asyncio
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# 常量
BASE_URL = 'https://navi.cnki.net'
VERIFY_URL_PREFIX = 'https://kns.cnki.net/verify/'
TARGET_YEARS = ['2025', '2026']
JOURNAL_CACHE_DAYS = 7
PAPER_CACHE_DAYS = 30

# 文件路径
BACKEND_DIR = Path('backend')
DATA_DIR = BACKEND_DIR / 'data'
JOURNALS_HISTORY_FILE = DATA_DIR / 'journals_history.json'
PAPERS_HISTORY_FILE = DATA_DIR / 'papers_history.json'


class HistoryManager:
    """历史记录管理器"""

    @staticmethod
    def load_journals_history() -> dict:
        """加载期刊历史记录"""
        if JOURNALS_HISTORY_FILE.exists():
            with open(JOURNALS_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'last_updated': None, 'journals': {}}

    @staticmethod
    def save_journals_history(journals: dict):
        """保存期刊历史记录"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            'last_updated': datetime.now().isoformat(),
            'journals': journals
        }
        with open(JOURNALS_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_papers_history() -> dict:
        """加载论文链接历史记录"""
        if PAPERS_HISTORY_FILE.exists():
            with open(PAPERS_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'last_updated': None, 'papers': {}}

    @staticmethod
    def save_papers_history(papers: dict):
        """保存论文链接历史记录"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            'last_updated': datetime.now().isoformat(),
            'papers': papers
        }
        with open(PAPERS_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def is_journals_cache_valid() -> bool:
        """检查期刊缓存是否有效"""
        history = HistoryManager.load_journals_history()
        if not history['last_updated']:
            return False
        last_updated = datetime.fromisoformat(history['last_updated'])
        return datetime.now() - last_updated < timedelta(days=JOURNAL_CACHE_DAYS)

    @staticmethod
    def is_journal_year_crawled(journal_name: str, year: str) -> bool:
        """检查期刊某年份是否已爬取"""
        history = HistoryManager.load_papers_history()
        papers = history.get('papers', {})
        if journal_name not in papers:
            return False
        if year not in papers[journal_name]:
            return False
        year_data = papers[journal_name][year]
        return len(year_data) > 0

    @staticmethod
    def get_papers_for_journal_year(journal_name: str, year: str) -> list:
        """获取期刊某年份的所有论文链接（过滤非论文条目）"""
        history = HistoryManager.load_papers_history()
        papers = history.get('papers', {})
        if journal_name not in papers:
            return []
        if year not in papers[journal_name]:
            return []

        # 非论文条目的关键词
        skip_keywords = ['征稿启事', '征稿', '征文', '征订', '总目录']

        all_papers = []
        for issue_num, issue_data in papers[journal_name][year].items():
            if 'papers' in issue_data:
                for paper in issue_data['papers']:
                    title = paper.get('title', '')
                    # 过滤非论文条目
                    if any(keyword in title for keyword in skip_keywords):
                        continue
                    all_papers.append(paper)
        return all_papers

    @staticmethod
    def add_papers_for_journal_issue(journal_name: str, year: str, issue: str, papers: list):
        """添加期刊某期次的论文链接"""
        history = HistoryManager.load_papers_history()
        if 'papers' not in history:
            history['papers'] = {}
        if journal_name not in history['papers']:
            history['papers'][journal_name] = {}
        if year not in history['papers'][journal_name]:
            history['papers'][journal_name][year] = {}

        history['papers'][journal_name][year][issue] = {
            'last_crawled': datetime.now().isoformat(),
            'papers': papers
        }
        HistoryManager.save_papers_history(history['papers'])


class JournalCrawler:
    """单个期刊爬虫（每个线程一个实例）"""

    def __init__(self, headless=True, thread_id=0):
        self.headless = headless
        self.thread_id = thread_id
        self.page = None
        self.browser = None
        self.playwright = None
        self.db_initialized = False

    async def init_browser(self):
        """初始化浏览器"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--no-sandbox',
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )
        
        # 随机选择 user-agent
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        ]
        user_agent = random.choice(user_agents)
        
        # 随机 viewport
        viewports = [
            {'width': 1280, 'height': 800},
            {'width': 1366, 'height': 768},
            {'width': 1440, 'height': 900},
            {'width': 1536, 'height': 864},
            {'width': 1920, 'height': 1080},
        ]
        viewport = random.choice(viewports)
        
        context = await self.browser.new_context(
            user_agent=user_agent,
            viewport=viewport,
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            permissions=['geolocation'],
            geolocation={'latitude': 39.9042, 'longitude': 116.4074},
        )
        
        # 添加脚本隐藏 webdriver 痕迹
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
            window.chrome = { runtime: {} };
        """)
        
        self.page = await context.new_page()
        print(f"  [线程{self.thread_id}] 浏览器已启动")
        print(f"  [线程{self.thread_id}] 指纹: {user_agent[:40]}...")

    async def close_browser(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print(f"  [线程{self.thread_id}] 浏览器已关闭")

    async def random_scroll(self):
        """随机滚动页面模拟人类行为"""
        try:
            scroll_times = random.randint(1, 3)
            for _ in range(scroll_times):
                scroll_y = random.randint(100, 500)
                await self.page.evaluate(f'window.scrollBy(0, {scroll_y})')
                await asyncio.sleep(random.uniform(0.5, 2))
        except Exception:
            pass

    def is_verify_page(self, page_url: str) -> bool:
        """检查是否是验证码页面"""
        return page_url.startswith(VERIFY_URL_PREFIX)

    async def wait_for_page_stable(self, target_url: str, max_wait_time: int = 300) -> bool:
        """等待页面稳定"""
        current_url = self.page.url

        if not self.is_verify_page(current_url):
            return True

        print(f"    [线程{self.thread_id}] ⚠ 遇到验证码页面")

        if self.headless:
            print(f"    [线程{self.thread_id}] 当前为无头模式，无法手动解决验证码")
            return False

        print(f"    [线程{self.thread_id}] 请在浏览器窗口中手动完成验证...")

        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait_time:
                print(f"    [线程{self.thread_id}] 等待验证码解决超时")
                return False

            current_url = self.page.url

            if not self.is_verify_page(current_url):
                print(f"    [线程{self.thread_id}] ✓ 验证码已解决")
                return True

            await asyncio.sleep(1)

    async def get_year_issues(self, journal_url: str) -> list:
        """获取期刊的年份期次列表"""
        print(f"  [线程{self.thread_id}] 访问期刊页面: {journal_url[:60]}...")
        await self.page.goto(journal_url, wait_until='domcontentloaded', timeout=60000)

        if not await self.wait_for_page_stable(journal_url):
            return []

        await asyncio.sleep(8)

        current_year = datetime.now().year
        latest_issue = max(1, datetime.now().month - 2)

        print(f"  [线程{self.thread_id}] 应获取最新期次: {current_year}年第{latest_issue}期")

        issues = []
        html = await self.page.content()
        soup = BeautifulSoup(html, 'lxml')

        year_issue_container = soup.find('div', class_='yearissuepage')
        if not year_issue_container:
            year_issue_container = soup.find('div', id='YearIssueTree')

        if year_issue_container:
            year_dls = year_issue_container.find_all('dl')

            for year_dl in year_dls:
                dt = year_dl.find('dt')
                if not dt:
                    continue

                em = dt.find('em')
                if not em:
                    continue

                year_text = em.get_text(strip=True)
                year_match = re.search(r'(\d{4})', year_text)
                if not year_match:
                    continue

                year = year_match.group(1)

                if year not in TARGET_YEARS:
                    continue

                dd = year_dl.find('dd')
                if not dd:
                    continue

                issue_links = dd.find_all('a', id=True)

                for link in issue_links:
                    issue_id = link.get('id', '')
                    issue_text = link.get_text(strip=True)

                    if issue_id.startswith('yq'):
                        match = re.match(r'yq(\d{4})(\d{2})', issue_id)
                        if match:
                            issue_year = int(match.group(1))
                            issue_num = int(match.group(2))

                            should_include = False

                            if issue_year == current_year:
                                if issue_num <= latest_issue:
                                    should_include = True
                            elif issue_year < current_year:
                                should_include = True

                            if should_include:
                                issues.append({
                                    'year': str(issue_year),
                                    'issue_id': issue_id,
                                    'issue_text': issue_text,
                                    'issue_num': issue_num
                                })

        issues.sort(key=lambda x: (x['year'], x['issue_num']), reverse=True)
        print(f"  [线程{self.thread_id}] 共找到 {len(issues)} 个应获取的期次")

        return issues

    async def get_papers_from_page(self) -> list:
        """从当前页面获取论文列表（过滤非论文条目）"""
        papers = []
        html = await self.page.content()
        soup = BeautifulSoup(html, 'lxml')

        catalog = soup.find('div', id='rightCataloglist')
        if not catalog:
            catalog = soup.find('div', id='originalCatalogview')

        # 非论文条目 的关键词
        skip_keywords = ['征稿启事', '征稿', '征文', '征订', '总目录']

        if catalog:
            rows = catalog.find_all('dd', class_='row')
            for row in rows:
                name_span = row.find('span', class_='name')
                if name_span:
                    link = name_span.find('a')
                    if link:
                        title = link.get_text(strip=True)
                        href = link.get('href', '')
                        if title and href:
                            # 过滤非论文条目
                            if any(keyword in title for keyword in skip_keywords):
                                print(f"    [线程{self.thread_id}] 过滤非论文条目: {title[:40]}...")
                                continue
                            if href.startswith('/'):
                                href = urljoin(BASE_URL, href)
                            papers.append({'title': title, 'url': href, 'status': 0})

        return papers

    async def crawl_year_papers_with_larrow(self, journal_name: str, year: str, year_issue_list: list) -> list:
        """使用"前一期"按钮获取该年份的所有论文"""
        year_papers = []
        crawled_issues = set()

        target_issue_count = len(year_issue_list)
        print(f"    [线程{self.thread_id}] 应该获取的期次: {target_issue_count} 个")

        issue_count = 0
        while True:
            issue_count += 1

            html = await self.page.content()
            soup = BeautifulSoup(html, 'lxml')

            date_list_span = soup.find('span', class_='date-list')
            if date_list_span:
                date_list_value = date_list_span.get('value', '')
                date_list_text = date_list_span.get_text(strip=True)
                print(f"\n    [线程{self.thread_id}] 当前显示: {date_list_text} ({date_list_value})")
            else:
                current_issue_link = soup.find('a', class_='current', id=re.compile(r'yq\d+'))
                if current_issue_link:
                    date_list_value = current_issue_link.get('id', '')
                    date_list_text = current_issue_link.get_text(strip=True)
                    print(f"\n    [线程{self.thread_id}] 当前显示: {date_list_text} ({date_list_value})")
                else:
                    print(f"    [线程{self.thread_id}] 无法获取当前期次信息，跳过")
                    break

            match = re.match(r'yq(\d{4})(\d{2})', date_list_value)
            if match:
                current_year = match.group(1)
                issue_num = match.group(2)
            else:
                print(f"    [线程{self.thread_id}] 无法解析期次ID: {date_list_value}")
                break

            if current_year != year:
                print(f"    [线程{self.thread_id}] 当前年份 {current_year} 与目标年份 {year} 不一致，结束")
                break

            if date_list_value in crawled_issues:
                print(f"      [线程{self.thread_id}] 期次 {date_list_text} 已获取过，跳过")
            else:
                papers = await self.get_papers_from_page()
                print(f"      [线程{self.thread_id}] 当前期次获取到 {len(papers)} 篇论文")

                crawled_issues.add(date_list_value)
                HistoryManager.add_papers_for_journal_issue(journal_name, year, issue_num, papers)
                year_papers.extend(papers)

                print(f"      [线程{self.thread_id}] 期次 {date_list_text} 共 {len(papers)} 篇论文已保存")

            if len(crawled_issues) >= target_issue_count:
                print(f"    [线程{self.thread_id}] 已获取完所有目标期次 ({len(crawled_issues)}/{target_issue_count})，结束")
                break

            larrow = await self.page.query_selector('#larrow')
            if not larrow:
                print(f"    [线程{self.thread_id}] 未找到前一期按钮，结束")
                break

            class_attr = await larrow.get_attribute('class') or ''
            if 'disable' in class_attr:
                print(f"    [线程{self.thread_id}] 前一期按钮已禁用，该年份获取完成")
                break

            print(f"    [线程{self.thread_id}] 点击前一期按钮...")
            try:
                await self.page.evaluate('document.getElementById("larrow").click()')
                await asyncio.sleep(8)
            except Exception as e:
                print(f"    [线程{self.thread_id}] 点击前一期按钮失败: {e}")
                break

            if self.is_verify_page(self.page.url):
                print(f"    [线程{self.thread_id}] ⚠ 遇到验证码页面，等待解决...")
                if not await self.wait_for_page_stable(self.page.url):
                    print(f"    [线程{self.thread_id}] 验证码未解决，结束该年份获取")
                    break

        print(f"\n    [线程{self.thread_id}] 年份 {year} 共获取 {len(year_papers)} 篇论文，{len(crawled_issues)}/{target_issue_count} 个期次")
        return year_papers

    async def crawl_papers_for_journal(self, journal_name: str, journal_info: dict) -> list:
        """获取期刊论文链接"""
        journal_url = journal_info['url'] if isinstance(journal_info, dict) else journal_info

        print(f"\n[线程{self.thread_id}] {'=' * 60}")
        print(f"[线程{self.thread_id}] 处理期刊: {journal_name}")
        print(f"[线程{self.thread_id}] {'=' * 60}")

        all_papers = []

        for year in TARGET_YEARS:
            if HistoryManager.is_journal_year_crawled(journal_name, year):
                print(f"[线程{self.thread_id}] 年份 {year} 已存在历史记录，直接复用")
                papers = HistoryManager.get_papers_for_journal_year(journal_name, year)
                all_papers.extend(papers)
            else:
                print(f"[线程{self.thread_id}] 年份 {year} 无历史记录，需要爬取")

        if all(HistoryManager.is_journal_year_crawled(journal_name, year) for year in TARGET_YEARS):
            print(f"[线程{self.thread_id}] 所有年份已缓存，共 {len(all_papers)} 篇论文")
            return all_papers

        issues = await self.get_year_issues(journal_url)
        if not issues:
            print(f"[线程{self.thread_id}] 未找到期次列表")
            return all_papers

        issues_to_crawl = []
        for issue in issues:
            year = issue['year']
            issue_num = str(issue['issue_num'])
            history = HistoryManager.load_papers_history()
            if (journal_name in history.get('papers', {}) and
                year in history['papers'][journal_name] and
                issue_num in history['papers'][journal_name][year]):
                print(f"  [线程{self.thread_id}] 期次 {issue['issue_text']} 已缓存，跳过")
            else:
                issues_to_crawl.append(issue)

        print(f"[线程{self.thread_id}] 需要爬取 {len(issues_to_crawl)} 个期次")

        from collections import defaultdict
        year_issues = defaultdict(list)
        for issue in issues_to_crawl:
            year_issues[issue['year']].append(issue)

        current_year = str(datetime.now().year)

        for year in sorted(year_issues.keys(), reverse=True):
            year_issue_list = year_issues[year]
            print(f"\n  [线程{self.thread_id}] 处理年份: {year}年，共 {len(year_issue_list)} 个期次")

            if year != current_year:
                year_dl_id = f"{year}_Year_Issue"
                print(f"    [线程{self.thread_id}] 点击年份按钮展开: {year_dl_id}")
                try:
                    await self.page.evaluate(f'''
                        var dl = document.getElementById("{year_dl_id}");
                        if (dl) {{
                            var dt = dl.querySelector("dt");
                            if (dt) dt.click();
                        }}
                    ''')
                    await asyncio.sleep(3)
                    print(f"    [线程{self.thread_id}] 年份 {year} 已展开")

                    year_issues_sorted = sorted(year_issue_list, key=lambda x: x['issue_num'], reverse=True)
                    if year_issues_sorted:
                        latest_issue = year_issues_sorted[0]
                        latest_issue_id = latest_issue['issue_id']
                        latest_issue_text = latest_issue['issue_text']
                        print(f"    [线程{self.thread_id}] 点击最新期次: {latest_issue_text} ({latest_issue_id})")
                        await self.page.evaluate(f'document.getElementById("{latest_issue_id}").click()')
                        await asyncio.sleep(5)
                        print(f"    [线程{self.thread_id}] 已切换到 {year} 年最新期次")
                except Exception as e:
                    print(f"    [线程{self.thread_id}] 点击年份按钮或期次失败: {e}")
                    continue
            else:
                print(f"    [线程{self.thread_id}] 年份 {year} 是当前年份，无需点击展开")

            year_papers = await self.crawl_year_papers_with_larrow(journal_name, year, year_issue_list)
            all_papers.extend(year_papers)

        print(f"\n[线程{self.thread_id}] 期刊 {journal_name} 共获取 {len(all_papers)} 篇论文")
        return all_papers

    async def crawl_paper_detail(self, paper_info: dict, journal_name: str = None) -> dict:
        """获取论文详情"""
        paper_url = paper_info['url']

        try:
            import sys
            sys.path.insert(0, str(BACKEND_DIR))

            from app.crud import PaperCRUD
            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                existing = await PaperCRUD.get_paper_by_url(db, paper_url)
                if existing:
                    print(f"  [线程{self.thread_id}] 数据库中已存在，跳过")
                    return {'error': 'already_exists'}
        except Exception:
            pass

        print(f"  [线程{self.thread_id}] 获取论文详情: {paper_info['title'][:50]}...")

        wait_time = random.uniform(5, 10)
        await asyncio.sleep(wait_time)

        try:
            await self.page.goto(paper_url, wait_until='domcontentloaded', timeout=60000)

            if not await self.wait_for_page_stable(paper_url):
                return {'error': 'verify_page'}

            # 随机滚动页面模拟人类行为
            await self.random_scroll()

            await asyncio.sleep(random.uniform(3, 6))

            html = await self.page.content()
            soup = BeautifulSoup(html, 'lxml')

            title = ''
            title_elem = soup.find('div', class_='doc')
            if title_elem:
                h1 = title_elem.find('h1')
                if h1:
                    title = h1.get_text(strip=True)
            if not title:
                h1_elem = soup.find('h1')
                if h1_elem:
                    title = h1_elem.get_text(strip=True)

            # 筛选条件：跳过含有"征稿启事"、"征稿"、"征文"、"征订"或"总目录"的论文
            skip_keywords = ['征稿启事', '征稿', '征文', '征订', '总目录']
            if any(keyword in title for keyword in skip_keywords):
                print(f"    [线程{self.thread_id}] ✗ 跳过非论文条目: {title[:40]}...")
                return {'error': 'filtered_non_paper'}

            title = title.replace('附视频', '').strip()

            authors = []
            author_elem = soup.find('h3', class_='author')
            if author_elem:
                author_links = author_elem.find_all('a')
                for link in author_links:
                    author_name = link.get_text(strip=True)
                    author_name = re.sub(r'\d+', '', author_name).strip()
                    if author_name:
                        authors.append(author_name)

            abstract = ''
            abstract_elem = soup.find('span', class_='abstract-text')
            if abstract_elem:
                abstract = abstract_elem.get_text(strip=True)

            keywords = []
            keywords_elem = soup.find('p', class_='keywords')
            if keywords_elem:
                keywords_text = keywords_elem.get_text(strip=True)
                keywords_text = keywords_text.replace('关键词：', '').replace('关键词:', '')
                keywords = [k.strip() for k in keywords_text.split(';') if k.strip()]

            meta = {}
            row_divs = soup.find_all('div', class_='row')
            for row in row_divs:
                ul = row.find('ul')
                if ul:
                    for li in ul.find_all('li', class_='top-space'):
                        label_elem = li.find('span', class_='rowtit')
                        value_elem = li.find('p')
                        if label_elem and value_elem:
                            label = label_elem.get_text(strip=True).replace('：', '').replace(':', '')
                            value = value_elem.get_text(strip=True)
                            if label == 'DOI':
                                meta['doi'] = value
                            elif label == '专辑':
                                meta['album'] = value
                            elif label == '专题':
                                meta['subject'] = value
                            elif label == '分类号':
                                meta['classification'] = value
                            elif '在线公开时间' in label:
                                meta['online_date'] = value.split('（')[0].strip()

            result = {
                'title': title,
                'authors': authors,
                'abstract': abstract,
                'keywords': keywords,
                'url': paper_url,
                **meta
            }

            if title:
                print(f"    [线程{self.thread_id}] ✓ 成功获取: {title[:40]}...")
                await self.save_to_database(result, journal_name)
                return result
            else:
                print(f"    [线程{self.thread_id}] ✗ 获取失败: 无标题")
                return {'error': 'no_title'}

        except Exception as e:
            print(f"    [线程{self.thread_id}] ✗ 获取失败: {e}")
            return {'error': str(e)}

    async def save_to_database(self, paper_data: dict, journal_name: str = None):
        """异步保存到数据库"""
        try:
            import sys
            import re
            sys.path.insert(0, str(BACKEND_DIR))

            from app.database import init_db
            from app.crud import PaperCRUD
            from app.database import AsyncSessionLocal

            if not self.db_initialized:
                db_file = BACKEND_DIR / 'data' / 'paperpulse.db'
                if not db_file.exists():
                    print(f"    [线程{self.thread_id}] 数据库文件不存在，正在创建...")
                    await init_db()
                    print(f"    [线程{self.thread_id}] ✓ 数据库已创建")
                self.db_initialized = True

            async with AsyncSessionLocal() as db:
                existing = await PaperCRUD.get_paper_by_url(db, paper_data['url'])
                if existing:
                    print(f"    [线程{self.thread_id}] 数据库中已存在，跳过")
                    return

                if journal_name:
                    paper_data['journal_name'] = journal_name

                doi = paper_data.get('doi', '')
                if doi:
                    match = re.search(r'\.(\d{4})\.', doi)
                    if match:
                        paper_data['year'] = int(match.group(1))

                paper = await PaperCRUD.create_paper_from_cnki(db, paper_data)
                if paper:
                    await db.commit()
                    print(f"    [线程{self.thread_id}] ✓ 已保存到数据库")
        except Exception as e:
            print(f"    [线程{self.thread_id}] ✗ 保存到数据库失败: {e}")
            import traceback
            traceback.print_exc()

    async def process_journal(self, journal_name: str, journal_info: dict):
        """处理单个期刊（线程入口）"""
        try:
            await self.init_browser()

            papers = await self.crawl_papers_for_journal(journal_name, journal_info)

            if not papers:
                print(f"[线程{self.thread_id}] 期刊 {journal_name} 未获取到论文")
                return

            print(f"\n[线程{self.thread_id}] {'=' * 60}")
            print(f"[线程{self.thread_id}] 步骤8: 获取论文详情 - {journal_name}")
            print(f"[线程{self.thread_id}] {'=' * 60}")

            papers_history = HistoryManager.load_papers_history()
            journal_data = papers_history.get('papers', {}).get(journal_name, {})

            total_processed = 0
            total_papers = 0

            try:
                import sys
                sys.path.insert(0, str(BACKEND_DIR))

                from app.crud import PaperCRUD
                from app.database import AsyncSessionLocal

                async with AsyncSessionLocal() as db:
                    existing_urls = set(await PaperCRUD.get_all_paper_urls(db))
                    print(f"  [线程{self.thread_id}] 数据库中已有 {len(existing_urls)} 篇论文")
            except Exception as e:
                existing_urls = set()
                print(f"  [线程{self.thread_id}] 获取数据库已有论文失败: {e}")

            for year in sorted(journal_data.keys(), reverse=True):
                year_data = journal_data[year]
                for issue in sorted(year_data.keys(), reverse=True):
                    issue_data = year_data[issue]
                    papers_list = issue_data.get('papers', [])
                    total_papers += len(papers_list)

                    papers_to_process = [p for p in papers_list if p['url'] not in existing_urls]

                    if not papers_to_process:
                        print(f"  [线程{self.thread_id}] {year}年{issue}期: 所有论文已在数据库中，跳过")
                        continue

                    print(f"\n  [线程{self.thread_id}] {year}年{issue}期: 需要处理 {len(papers_to_process)}/{len(papers_list)} 篇论文")

                    for i, paper in enumerate(papers_to_process, 1):
                        print(f"\n  [线程{self.thread_id}] [{i}/{len(papers_to_process)}] {paper['title'][:50]}...")
                        detail = await self.crawl_paper_detail(paper, journal_name)

                        if 'error' not in detail:
                            total_processed += 1

                        await asyncio.sleep(random.uniform(3, 6))

            print(f"\n[线程{self.thread_id}] 期刊 {journal_name} 处理完成: {total_processed}/{total_papers} 篇论文")

        except Exception as e:
            print(f"[线程{self.thread_id}] 处理期刊 {journal_name} 时出错: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await self.close_browser()


class MultiThreadedCrawler:
    """多线程爬虫管理器"""

    def __init__(self, headless=True, max_workers=3):
        self.headless = headless
        self.max_workers = max_workers

    async def crawl_journals(self) -> dict:
        """获取期刊列表"""
        print("=" * 60)
        print("步骤1-3: 获取期刊列表")
        print("=" * 60)

        if HistoryManager.is_journals_cache_valid():
            print("发现有效的期刊历史记录，直接复用")
            history = HistoryManager.load_journals_history()
            return history['journals']

        print("未找到有效的期刊历史记录，开始爬取...")

        from playwright.async_api import async_playwright

        async with async_playwright().start() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            print("访问期刊导航页...")
            await page.goto(f'{BASE_URL}/knavi/journals/index', wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(5)

            print("点击'经济与管理科学'按钮...")
            try:
                btn = await page.wait_for_selector('a[title="经济与管理科学"]', timeout=10000)
                if btn:
                    await btn.click()
                    await asyncio.sleep(5)
            except Exception as e:
                print(f"点击按钮失败: {e}")

            html = await page.content()
            soup = BeautifulSoup(html, 'lxml')

            result_div = soup.find('div', class_='result')
            if not result_div:
                print("未找到div.result")
                await browser.close()
                return {}

            journals = {}
            links = result_div.find_all('a')
            for link in links:
                full_title = link.get_text(strip=True)
                href = link.get('href', '')
                if full_title and href:
                    if href.startswith('/'):
                        href = urljoin(BASE_URL, href)

                    match = re.match(r'(.+?)(?:网络首发|复合影响因子|$)', full_title)
                    if match:
                        clean_title = match.group(1).strip()
                    else:
                        clean_title = full_title

                    impact_factor = {}
                    if '复合影响因子：' in full_title:
                        match = re.search(r'复合影响因子：([\d.]+)', full_title)
                        if match:
                            impact_factor['composite'] = float(match.group(1))
                    if '综合影响因子：' in full_title:
                        match = re.search(r'综合影响因子：([\d.]+)', full_title)
                        if match:
                            impact_factor['comprehensive'] = float(match.group(1))

                    journals[clean_title] = {
                        'url': href,
                        'impact_factor': impact_factor,
                        'original_title': full_title
                    }

            print(f"获取到 {len(journals)} 个期刊")
            HistoryManager.save_journals_history(journals)

            await browser.close()

        return journals

    def run_thread(self, journal_name: str, journal_info: dict, headless: bool, thread_id: int):
        """运行单个线程"""
        crawler = JournalCrawler(headless=headless, thread_id=thread_id)
        asyncio.run(crawler.process_journal(journal_name, journal_info))

    async def run(self):
        """运行多线程爬虫"""
        print("=" * 60)
        print(f"知网期刊爬虫 - 多线程版本 (线程数: {self.max_workers})")
        print(f"浏览器模式: {'无头' if self.headless else '显示窗口'}")
        print("=" * 60)

        # 获取期刊列表（单线程）
        journals = await self.crawl_journals()
        if not journals:
            print("未获取到期刊列表，退出")
            return

        journal_list = list(journals.items())
        print(f"\n共 {len(journal_list)} 个期刊需要处理")
        print(f"使用 {self.max_workers} 个线程同时处理\n")

        # 使用线程池处理期刊
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for i, (journal_name, journal_info) in enumerate(journal_list):
                thread_id = i % self.max_workers + 1
                future = executor.submit(
                    self.run_thread,
                    journal_name,
                    journal_info,
                    self.headless,
                    thread_id
                )
                futures.append(future)

            # 等待所有线程完成
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"线程执行出错: {e}")

        print("\n" + "=" * 60)
        print("所有期刊处理完成")
        print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description='知网期刊爬虫 - 多线程版本')
    parser.add_argument('--show-browser', action='store_true', help='显示浏览器窗口（默认不显示）')
    parser.add_argument('--threads', type=int, default=3, help='线程数/浏览器窗口数（默认3）')
    args = parser.parse_args()

    crawler = MultiThreadedCrawler(headless=not args.show_browser, max_workers=args.threads)
    await crawler.run()


if __name__ == '__main__':
    asyncio.run(main())
