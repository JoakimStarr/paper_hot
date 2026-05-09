#!/usr/bin/env python3
"""
知网期刊爬虫 - 增量式版本
按照《期刊爬取方法-知网版本.md》实现
支持历史记录复用和断点续传
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

# 常量
BASE_URL = 'https://navi.cnki.net'
VERIFY_URL_PREFIX = 'https://kns.cnki.net/verify/'
TARGET_YEARS = ['2025', '2026']
JOURNAL_CACHE_DAYS = 7  # 期刊缓存有效期（天）
PAPER_CACHE_DAYS = 30  # 论文链接缓存有效期（天）

# 文件路径
BACKEND_DIR = Path('backend')
DATA_DIR = BACKEND_DIR / 'data'
JOURNALS_HISTORY_FILE = DATA_DIR / 'journals_history.json'
PAPERS_HISTORY_FILE = DATA_DIR / 'papers_history.json'
DETAILS_HISTORY_FILE = DATA_DIR / 'paper_details_history.json'


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
        print(f"    期刊历史记录已保存到 {JOURNALS_HISTORY_FILE}")

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
        print(f"    论文链接历史记录已保存到 {PAPERS_HISTORY_FILE}")

    @staticmethod
    def load_details_history() -> dict:
        """加载论文详情历史记录"""
        if DETAILS_HISTORY_FILE.exists():
            with open(DETAILS_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'last_updated': None, 'details': {}}

    @staticmethod
    def save_details_history(details: dict):
        """保存论文详情历史记录"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            'last_updated': datetime.now().isoformat(),
            'details': details
        }
        with open(DETAILS_HISTORY_FILE, 'w', encoding='utf-8') as f:
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
        # 检查是否有数据
        year_data = papers[journal_name][year]
        return len(year_data) > 0

    @staticmethod
    def is_paper_crawled(paper_url: str) -> bool:
        """检查论文是否已获取详情"""
        history = HistoryManager.load_details_history()
        details = history.get('details', {})
        if paper_url not in details:
            return False
        return details[paper_url].get('status') == 1

    @staticmethod
    def update_paper_status(paper_url: str, status: int, data: dict = None, journal_name: str = None):
        """更新论文获取状态"""
        history = HistoryManager.load_details_history()
        if 'details' not in history:
            history['details'] = {}

        entry = {
            'status': status,
            'crawled_at': datetime.now().isoformat() if status == 1 else None,
            'data': data
        }
        
        # 添加期刊信息
        if journal_name:
            entry['journal_name'] = journal_name
        
        history['details'][paper_url] = entry
        HistoryManager.save_details_history(history['details'])

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


class IncrementalCrawler:
    """增量爬虫主类"""

    def __init__(self, headless=True):
        self.headless = headless
        self.page = None
        self.browser = None
        self.playwright = None
        self.db_initialized = False  # 数据库初始化标志

    async def init_browser(self):
        """初始化浏览器（带指纹伪装）"""
        self.playwright = await async_playwright().start()
        
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
        
        context = await self.browser.new_context(
            user_agent=user_agent,
            viewport=viewport,
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            permissions=['geolocation'],
            geolocation={'latitude': 39.9042, 'longitude': 116.4074},  # 北京
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
        print(f"  浏览器指纹: {user_agent[:50]}...")
        print(f"  视口大小: {viewport['width']}x{viewport['height']}")

    async def close_browser(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def random_scroll(self):
        """随机滚动页面模拟人类行为"""
        try:
            # 随机滚动 1-3 次
            scroll_times = random.randint(1, 3)
            for _ in range(scroll_times):
                # 随机滚动距离
                scroll_y = random.randint(100, 500)
                await self.page.evaluate(f'window.scrollBy(0, {scroll_y})')
                # 随机等待
                await asyncio.sleep(random.uniform(0.5, 2))
        except Exception:
            pass  # 滚动失败不影响主要逻辑

    def is_verify_page(self, page_url: str) -> bool:
        """检查是否是验证码页面
        知网验证码网站为：https://kns.cnki.net/verify/
        """
        # 检查URL是否以验证码前缀开头
        if page_url.startswith(VERIFY_URL_PREFIX):
            return True
        return False

    async def wait_for_verify_solved(self, max_wait_time: int = 300) -> bool:
        """等待用户手动解决验证码

        Args:
            max_wait_time: 最大等待时间（秒），默认5分钟

        Returns:
            是否成功解决验证码
        """
        if self.headless:
            print("    当前为无头模式，无法手动解决验证码")
            print("    请使用 --show-browser 参数显示浏览器窗口")
            return False

        print("    ⚠ 遇到验证码页面 (https://kns.cnki.net/verify/)")
        print("    请在浏览器窗口中手动完成验证...")
        print(f"    最多等待 {max_wait_time} 秒")

        start_time = asyncio.get_event_loop().time()
        check_interval = 2  # 每2秒检查一次

        while True:
            # 检查是否超时
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait_time:
                print(f"    等待验证码解决超时 ({max_wait_time}秒)")
                return False

            # 获取当前页面URL
            current_url = self.page.url

            # 检查是否还在验证码页面
            if not self.is_verify_page(current_url):
                print(f"    ✓ 验证码已解决，页面已跳转")
                print(f"    当前URL: {current_url[:80]}...")
                return True

            # 等待一段时间后再次检查
            await asyncio.sleep(check_interval)

            # 显示等待进度（每30秒显示一次）
            if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                remaining = max_wait_time - int(elapsed)
                print(f"    仍在等待验证码解决... 剩余 {remaining} 秒")

    async def wait_for_page_stable(self, target_url: str, max_wait_time: int = 300) -> bool:
        """等待页面稳定，即当前URL不是验证码页面

        进入链接后，循环判断当前页面是否是验证码页面
        如果是验证码页面，等待用户手动解决
        如果不是验证码页面，立即返回继续下一步操作

        Args:
            target_url: 目标URL（仅用于显示）
            max_wait_time: 最大等待时间（秒），默认5分钟

        Returns:
            页面是否稳定（不是验证码页面）
        """
        # 获取当前页面URL
        current_url = self.page.url

        # 检查是否是验证码页面
        if not self.is_verify_page(current_url):
            # 不是验证码页面，直接返回成功
            return True

        # 是验证码页面，需要等待解决
        print(f"    ⚠ 页面跳转到了验证码页面")
        print(f"    目标URL: {target_url[:80]}...")
        print(f"    当前URL: {current_url[:80]}...")

        if self.headless:
            print("    当前为无头模式，无法手动解决验证码")
            print("    请使用 --show-browser 参数显示浏览器窗口")
            return False

        print("    请在浏览器窗口中手动完成验证...")
        print(f"    最多等待 {max_wait_time} 秒")

        start_time = asyncio.get_event_loop().time()
        last_printed_second = -1

        while True:
            # 检查是否超时
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait_time:
                print(f"    等待页面稳定超时 ({max_wait_time}秒)")
                return False

            # 获取当前页面URL
            current_url = self.page.url

            # 检查是否还在验证码页面
            if not self.is_verify_page(current_url):
                print(f"    ✓ 验证码已解决，页面已跳转")
                print(f"    当前URL: {current_url[:80]}...")
                return True

            # 每秒打印一次当前URL
            current_second = int(elapsed)
            if current_second != last_printed_second:
                remaining = max_wait_time - current_second
                print(f"    [{current_second}s] 当前URL: {current_url[:80]}... (剩余 {remaining} 秒)")
                last_printed_second = current_second

            # 等待1秒后再次检查
            await asyncio.sleep(1)

    async def crawl_journals(self) -> dict:
        """
        步骤1-3: 获取期刊列表（带缓存）
        """
        print("=" * 60)
        print("步骤1-3: 获取期刊列表")
        print("=" * 60)

        # 检查历史记录
        if HistoryManager.is_journals_cache_valid():
            print("发现有效的期刊历史记录，直接复用")
            history = HistoryManager.load_journals_history()
            return history['journals']

        print("未找到有效的期刊历史记录，开始爬取...")

        # 访问期刊导航页
        print("访问期刊导航页...")
        await self.page.goto(f'{BASE_URL}/knavi/journals/index', wait_until='domcontentloaded', timeout=60000)

        # 等待页面稳定（检查是否进入验证码页面）
        if not await self.wait_for_page_stable(f'{BASE_URL}/knavi/journals/index'):
            return {}

        await asyncio.sleep(5)

        # 点击"经济与管理科学"按钮
        print("点击'经济与管理科学'按钮...")
        try:
            btn = await self.page.wait_for_selector('a[title="经济与管理科学"]', timeout=10000)
            if btn:
                await btn.click()
                await asyncio.sleep(5)
        except Exception as e:
            print(f"点击按钮失败: {e}")

        # 获取页面HTML
        html = await self.page.content()
        soup = BeautifulSoup(html, 'lxml')

        # 获取div.result中的期刊列表
        result_div = soup.find('div', class_='result')
        if not result_div:
            print("未找到div.result")
            return {}

        import re
        journals = {}
        links = result_div.find_all('a')
        for link in links:
            full_title = link.get_text(strip=True)
            href = link.get('href', '')
            if full_title and href:
                if href.startswith('/'):
                    href = urljoin(BASE_URL, href)

                # 提取干净的期刊名称（去掉影响因子等信息）
                match = re.match(r'(.+?)(?:网络首发|复合影响因子|$)', full_title)
                if match:
                    clean_title = match.group(1).strip()
                else:
                    clean_title = full_title

                # 提取影响因子信息
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

        # 立即保存历史记录
        HistoryManager.save_journals_history(journals)

        return journals

    def calculate_latest_issue(self) -> tuple:
        """计算最新期次
        知网规则：当前月份-2 = 最新期次
        例如：当前5月，最新期次为第3期
        """
        now = datetime.now()
        current_month = now.month
        current_year = now.year

        # 计算最新期次（月份-2）
        latest_issue = max(1, current_month - 2)

        return current_year, latest_issue

    async def get_year_issues(self, journal_url: str) -> list:
        """获取期刊的年份期次列表，只获取到最新期次
        
        通过解析 div.yearissuepage 下面的 dl 结构：
        - dt 下面的 em 的文字为年份
        - dd 下面的 a 标签数量表示期数
        """
        print(f"访问期刊页面: {journal_url[:60]}...")
        await self.page.goto(journal_url, wait_until='domcontentloaded', timeout=60000)

        # 等待页面稳定（检查是否进入验证码页面）
        if not await self.wait_for_page_stable(journal_url):
            return []

        await asyncio.sleep(8)

        # 计算应该获取的最新期次
        current_year, latest_issue = self.calculate_latest_issue()
        print(f"  当前时间: {datetime.now().strftime('%Y年%m月')}")
        print(f"  应获取最新期次: {current_year}年第{latest_issue}期")

        issues = []
        html = await self.page.content()
        soup = BeautifulSoup(html, 'lxml')

        # 查找 div.yearissuepage 或 div#YearIssueTree 下的年份期次结构
        year_issue_container = soup.find('div', class_='yearissuepage')
        if not year_issue_container:
            year_issue_container = soup.find('div', id='YearIssueTree')
        
        if year_issue_container:
            # 查找所有的 dl 元素（每个dl包含一个年份的期次）
            year_dls = year_issue_container.find_all('dl')
            
            for year_dl in year_dls:
                # 从 dt > em 获取年份
                dt = year_dl.find('dt')
                if not dt:
                    continue
                    
                em = dt.find('em')
                if not em:
                    continue
                    
                year_text = em.get_text(strip=True)
                # 提取年份数字
                year_match = re.search(r'(\d{4})', year_text)
                if not year_match:
                    continue
                    
                year = year_match.group(1)
                
                # 只处理目标年份
                if year not in TARGET_YEARS:
                    continue
                
                print(f"  查找年份: {year}")
                
                # 从 dd > a 获取期次
                dd = year_dl.find('dd')
                if not dd:
                    continue
                
                issue_links = dd.find_all('a', id=True)
                print(f"    找到 {len(issue_links)} 个期次")
                
                for link in issue_links:
                    issue_id = link.get('id', '')
                    issue_text = link.get_text(strip=True)
                    
                    if issue_id.startswith('yq'):
                        # 从issue_id提取年份和期号 (格式: yqYYYYMM)
                        match = re.match(r'yq(\d{4})(\d{2})', issue_id)
                        if match:
                            issue_year = int(match.group(1))
                            issue_num = int(match.group(2))

                            # 判断是否应该获取该期次
                            should_include = False

                            if issue_year == current_year:
                                # 当前年份：只获取小于等于最新期次的
                                if issue_num <= latest_issue:
                                    should_include = True
                            elif issue_year < current_year:
                                # 之前的年份：获取所有期次
                                should_include = True

                            if should_include:
                                issues.append({
                                    'year': str(issue_year),
                                    'issue_id': issue_id,
                                    'issue_text': issue_text,
                                    'issue_num': issue_num
                                })
        else:
            # 备用方案：使用原来的id查找方式
            print("  未找到 yearissuepage 容器，使用备用方案")
            for year in TARGET_YEARS:
                year_dl = soup.find('dl', id=f'{year}_Year_Issue')
                if year_dl:
                    print(f"  查找年份: {year}")
                    issue_links = year_dl.find_all('a', id=True)
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

        # 按年份和期次排序（降序）
        issues.sort(key=lambda x: (x['year'], x['issue_num']), reverse=True)

        print(f"  共找到 {len(issues)} 个应获取的期次")
        for issue in issues[:5]:  # 只显示前5个
            print(f"    - {issue['year']}年 {issue['issue_text']} (期号: {issue['issue_num']:02d})")
        if len(issues) > 5:
            print(f"    ... 还有 {len(issues) - 5} 个期次")

        return issues

    async def get_papers_from_page(self) -> list:
        """从当前页面获取论文列表（过滤非论文条目）"""
        papers = []
        html = await self.page.content()
        soup = BeautifulSoup(html, 'lxml')

        catalog = soup.find('div', id='rightCataloglist')
        if not catalog:
            catalog = soup.find('div', id='originalCatalogview')

        # 非论文条目的关键词
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
                                print(f"    过滤非论文条目: {title[:40]}...")
                                continue
                            if href.startswith('/'):
                                href = urljoin(BASE_URL, href)
                            papers.append({'title': title, 'url': href, 'status': 0})

        return papers

    async def click_issue(self, issue_id: str) -> bool:
        """点击期次链接"""
        try:
            await self.page.evaluate(f'document.getElementById("{issue_id}").click()')
            await asyncio.sleep(8)
            return True
        except Exception as e:
            print(f"点击期次失败: {e}")
            return False

    async def click_larrow(self) -> tuple:
        """点击前一期按钮"""
        try:
            larrow = await self.page.query_selector('#larrow')
            if not larrow:
                return False, []

            class_attr = await larrow.get_attribute('class') or ''
            if 'disable' in class_attr:
                return False, []

            await self.page.evaluate('document.getElementById("larrow").click()')
            await asyncio.sleep(8)

            papers = await self.get_papers_from_page()
            return True, papers
        except Exception as e:
            return False, []

    async def crawl_papers_for_journal(self, journal_name: str, journal_info: dict) -> list:
        """
        步骤5-7: 获取期刊论文链接（带缓存）
        """
        journal_url = journal_info['url'] if isinstance(journal_info, dict) else journal_info

        print(f"\n{'=' * 60}")
        print(f"处理期刊: {journal_name}")
        if isinstance(journal_info, dict) and journal_info.get('impact_factor'):
            print(f"影响因子: 复合{journal_info['impact_factor'].get('composite', 'N/A')}, 综合{journal_info['impact_factor'].get('comprehensive', 'N/A')}")
        print(f"{'=' * 60}")

        all_papers = []

        # 检查每个年份的缓存
        for year in TARGET_YEARS:
            if HistoryManager.is_journal_year_crawled(journal_name, year):
                print(f"年份 {year} 已存在历史记录，直接复用")
                papers = HistoryManager.get_papers_for_journal_year(journal_name, year)
                all_papers.extend(papers)
            else:
                print(f"年份 {year} 无历史记录，需要爬取")

        # 如果所有年份都有缓存，直接返回
        if all(HistoryManager.is_journal_year_crawled(journal_name, year) for year in TARGET_YEARS):
            print(f"所有年份已缓存，共 {len(all_papers)} 篇论文")
            return all_papers

        # 获取期次列表
        issues = await self.get_year_issues(journal_url)
        if not issues:
            print("未找到期次列表")
            return all_papers

        # 过滤掉已爬取的年份期次
        issues_to_crawl = []
        for issue in issues:
            year = issue['year']
            issue_num = f"{issue['issue_num']:02d}"
            history = HistoryManager.load_papers_history()
            if (journal_name in history.get('papers', {}) and
                year in history['papers'][journal_name] and
                issue_num in history['papers'][journal_name][year]):
                print(f"  期次 {issue['issue_text']} 已缓存，跳过")
            else:
                issues_to_crawl.append(issue)

        print(f"需要爬取 {len(issues_to_crawl)} 个期次")

        # 按年份分组处理期次
        from collections import defaultdict
        year_issues = defaultdict(list)
        for issue in issues_to_crawl:
            year_issues[issue['year']].append(issue)

        # 计算当前年份
        current_year = str(datetime.now().year)

        # 按年份降序处理
        for year in sorted(year_issues.keys(), reverse=True):
            year_issue_list = year_issues[year]
            print(f"\n  处理年份: {year}年，共 {len(year_issue_list)} 个期次")

            # 只有非当前年份才需要点击年份按钮展开
            if year != current_year:
                # 点击 dt 元素展开该年份的期次
                year_dl_id = f"{year}_Year_Issue"
                print(f"    点击年份按钮展开: {year_dl_id}")
                try:
                    # 点击 dt 元素（包含年份标题和em标签）
                    await self.page.evaluate(f'''
                        var dl = document.getElementById("{year_dl_id}");
                        if (dl) {{
                            var dt = dl.querySelector("dt");
                            if (dt) dt.click();
                        }}
                    ''')
                    await asyncio.sleep(3)
                    print(f"    年份 {year} 已展开")

                    # 点击该年份的最新期次（第一个期次链接）
                    # 从 year_issue_list 中找到该年份的最新期次
                    year_issues_sorted = sorted(year_issue_list, key=lambda x: x['issue_num'], reverse=True)
                    if year_issues_sorted:
                        latest_issue = year_issues_sorted[0]
                        latest_issue_id = latest_issue['issue_id']
                        latest_issue_text = latest_issue['issue_text']
                        print(f"    点击最新期次: {latest_issue_text} ({latest_issue_id})")
                        await self.page.evaluate(f'document.getElementById("{latest_issue_id}").click()')
                        await asyncio.sleep(5)
                        print(f"    已切换到 {year} 年最新期次")
                except Exception as e:
                    print(f"    点击年份按钮或期次失败: {e}")
                    continue
            else:
                print(f"    年份 {year} 是当前年份，无需点击展开")

            # 获取该年份最新一期的数据（默认显示的期次）
            # 然后循环点击"前一期"按钮直到按钮禁用
            year_papers = await self.crawl_year_papers_with_larrow(journal_name, year, year_issue_list)
            all_papers.extend(year_papers)

        print(f"\n期刊 {journal_name} 共获取 {len(all_papers)} 篇论文")
        return all_papers

    async def crawl_year_papers_with_larrow(self, journal_name: str, year: str, year_issue_list: list) -> list:
        """
        使用"前一期"按钮获取该年份的所有论文

        逻辑：
        1. 获取当前显示的期次数据（从 <span class="date-list"> 获取当前年份和期）
        2. 获取当前期次论文
        3. 点击"前一期"按钮获取上一期
        4. 重复直到按钮变成 disable 状态
        """
        year_papers = []
        crawled_issues = set()  # 记录已获取的期次ID

        # 应该获取的期次数
        target_issue_count = len(year_issue_list)
        print(f"    应该获取的期次: {target_issue_count} 个")

        # 开始循环获取论文
        issue_count = 0
        while True:
            issue_count += 1

            # 获取当前页面显示的期次信息
            html = await self.page.content()
            soup = BeautifulSoup(html, 'lxml')

            # 从 <span class="date-list"> 获取当前年份和期
            date_list_span = soup.find('span', class_='date-list')
            if date_list_span:
                date_list_value = date_list_span.get('value', '')  # yq202603
                date_list_text = date_list_span.get_text(strip=True)  # 2026年03期
                print(f"\n    当前显示: {date_list_text} ({date_list_value})")
            else:
                # 备用：从 current 类的 a 标签获取
                current_issue_link = soup.find('a', class_='current', id=re.compile(r'yq\d+'))
                if current_issue_link:
                    date_list_value = current_issue_link.get('id', '')
                    date_list_text = current_issue_link.get_text(strip=True)
                    print(f"\n    当前显示: {date_list_text} ({date_list_value})")
                else:
                    print(f"    无法获取当前期次信息，跳过")
                    break

            # 从 value 提取年份和期号
            match = re.match(r'yq(\d{4})(\d{2})', date_list_value)
            if match:
                current_year = match.group(1)
                issue_num = match.group(2)
            else:
                print(f"    无法解析期次ID: {date_list_value}")
                break

            # 检查是否还在目标年份
            if current_year != year:
                print(f"    当前年份 {current_year} 与目标年份 {year} 不一致，结束")
                break

            # 检查是否已经获取过该期次
            if date_list_value in crawled_issues:
                print(f"      期次 {date_list_text} 已获取过，跳过")
            else:
                # 获取当前期次论文
                papers = await self.get_papers_from_page()
                print(f"      当前期次获取到 {len(papers)} 篇论文")

                # 记录已获取的期次
                crawled_issues.add(date_list_value)

                # 立即保存该期次的论文
                HistoryManager.add_papers_for_journal_issue(journal_name, year, issue_num, papers)
                year_papers.extend(papers)

                print(f"      期次 {date_list_text} 共 {len(papers)} 篇论文已保存")

            # 检查是否已经获取完所有目标期次
            if len(crawled_issues) >= target_issue_count:
                print(f"    已获取完所有目标期次 ({len(crawled_issues)}/{target_issue_count})，结束")
                break

            # 检查"前一期"按钮是否可用
            larrow = await self.page.query_selector('#larrow')
            if not larrow:
                print(f"    未找到前一期按钮，结束")
                break

            class_attr = await larrow.get_attribute('class') or ''
            if 'disable' in class_attr:
                print(f"    前一期按钮已禁用，该年份获取完成")
                break

            # 点击"前一期"按钮
            print(f"    点击前一期按钮...")
            try:
                await self.page.evaluate('document.getElementById("larrow").click()')
                await asyncio.sleep(8)  # 等待页面加载
            except Exception as e:
                print(f"    点击前一期按钮失败: {e}")
                break

            # 检查是否跳转到了验证码页面
            if self.is_verify_page(self.page.url):
                print(f"    ⚠ 遇到验证码页面，等待解决...")
                if not await self.wait_for_page_stable(self.page.url):
                    print(f"    验证码未解决，结束该年份获取")
                    break

        print(f"\n    年份 {year} 共获取 {len(year_papers)} 篇论文，{len(crawled_issues)}/{target_issue_count} 个期次")
        return year_papers

    async def crawl_paper_detail(self, paper_info: dict, journal_name: str = None) -> dict:
        """
        步骤8: 获取论文详情（带状态检查）
        """
        paper_url = paper_info['url']

        # 检查数据库中是否已存在
        try:
            import sys
            sys.path.insert(0, str(BACKEND_DIR))
            
            from app.crud import PaperCRUD
            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                existing = await PaperCRUD.get_paper_by_url(db, paper_url)
                if existing:
                    print(f"  数据库中已存在，跳过")
                    return {'error': 'already_exists'}
        except Exception:
            pass  # 如果检查失败，继续尝试获取

        print(f"  获取论文详情: {paper_info['title'][:50]}...")

        # 随机延迟
        wait_time = random.uniform(5, 10)
        await asyncio.sleep(wait_time)

        try:
            await self.page.goto(paper_url, wait_until='domcontentloaded', timeout=60000)

            # 等待页面稳定（检查是否进入验证码页面）
            if not await self.wait_for_page_stable(paper_url):
                return {'error': 'verify_page'}

            # 随机滚动页面模拟人类行为
            await self.random_scroll()

            await asyncio.sleep(random.uniform(3, 6))

            html = await self.page.content()
            soup = BeautifulSoup(html, 'lxml')

            # 提取标题
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
                print(f"    ✗ 跳过非论文条目: {title[:40]}...")
                return {'error': 'filtered_non_paper'}
            
            # 去掉标题中的"附视频"
            title = title.replace('附视频', '').strip()

            # 提取作者 - 从 h3.author 中的每个 a 标签提取
            authors = []
            author_elem = soup.find('h3', class_='author')
            if author_elem:
                # 查找所有作者链接
                author_links = author_elem.find_all('a')
                for link in author_links:
                    author_name = link.get_text(strip=True)
                    # 去掉作者名称中的数字
                    author_name = re.sub(r'\d+', '', author_name).strip()
                    if author_name:
                        authors.append(author_name)

            # 提取摘要
            abstract = ''
            abstract_elem = soup.find('span', class_='abstract-text')
            if abstract_elem:
                abstract = abstract_elem.get_text(strip=True)

            # 提取关键词
            keywords = []
            keywords_elem = soup.find('p', class_='keywords')
            if keywords_elem:
                keywords_text = keywords_elem.get_text(strip=True)
                keywords_text = keywords_text.replace('关键词：', '').replace('关键词:', '')
                keywords = [k.strip() for k in keywords_text.split(';') if k.strip()]

            # 提取元数据
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
                print(f"    ✓ 成功获取: {title[:40]}...")
                # 更新状态为1并保存，同时传递期刊名称
                HistoryManager.update_paper_status(paper_url, 1, result, journal_name)
                return result
            else:
                print(f"    ✗ 获取失败: 无标题")
                return {'error': 'no_title'}

        except Exception as e:
            print(f"    ✗ 获取失败: {e}")
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
            
            # 检查数据库文件是否存在，不存在则创建（只检查一次）
            if not self.db_initialized:
                db_file = BACKEND_DIR / 'data' / 'paperpulse.db'
                if not db_file.exists():
                    print(f"    数据库文件不存在，正在创建...")
                    await init_db()
                    print(f"    ✓ 数据库已创建")
                self.db_initialized = True

            async with AsyncSessionLocal() as db:
                # 检查是否已存在
                existing = await PaperCRUD.get_paper_by_url(db, paper_data['url'])
                if existing:
                    print(f"    数据库中已存在，跳过")
                    return

                # 添加期刊名称
                if journal_name:
                    paper_data['journal_name'] = journal_name

                # 从 DOI 中提取年份
                doi = paper_data.get('doi', '')
                if doi:
                    match = re.search(r'\.(\d{4})\.', doi)
                    if match:
                        paper_data['year'] = int(match.group(1))

                # 创建论文记录
                paper = await PaperCRUD.create_paper_from_cnki(db, paper_data)
                if paper:
                    await db.commit()  # 显式提交事务
                    print(f"    ✓ 已保存到数据库")
        except Exception as e:
            print(f"    ✗ 保存到数据库失败: {e}")
            import traceback
            traceback.print_exc()

    async def run(self):
        """运行爬虫主流程"""
        print("=" * 60)
        print("知网期刊爬虫 - 增量式版本")
        print(f"浏览器模式: {'无头' if self.headless else '显示窗口'}")
        print("=" * 60)

        try:
            # 初始化浏览器
            await self.init_browser()
            print("浏览器已启动")

            # 步骤1-3: 获取期刊列表
            journals = await self.crawl_journals()
            if not journals:
                print("未获取到期刊列表，退出")
                return

            # 遍历每个期刊
            for journal_name, journal_info in journals.items():
                crawl_log_id = None
                try:
                    from app.schemas import CrawlLogCreate
                    from app.crud import CrawlLogCRUD
                    from app.database import AsyncSessionLocal
                    async with AsyncSessionLocal() as db:
                        crawl_log_data = CrawlLogCreate(
                            journal_name=journal_name,
                            crawl_start_time=datetime.now()
                        )
                        crawl_log = await CrawlLogCRUD.create_crawl_log(db, crawl_log_data)
                        crawl_log_id = crawl_log.id
                        await db.commit()
                except Exception as e:
                    print(f"  创建爬取日志失败: {e}")

                crawl_error = None
                try:
                    # 步骤5-7: 获取论文链接
                    papers = await self.crawl_papers_for_journal(journal_name, journal_info)

                    if not papers:
                        print(f"期刊 {journal_name} 未获取到论文，跳过")
                        continue

                    print(f"\n{'=' * 60}")
                    print(f"步骤8: 获取论文详情 - {journal_name}")
                    print(f"{'=' * 60}")

                    # 按照 papers_history.json 的结构顺序获取论文详情
                    # 期刊 -> 年份 -> 期次 -> 论文列表
                    papers_history = HistoryManager.load_papers_history()
                    journal_data = papers_history.get('papers', {}).get(journal_name, {})

                    total_processed = 0
                    total_papers = 0

                    # 获取数据库中已存在的URL列表
                    existing_urls = set()
                    try:
                        import sys
                        sys.path.insert(0, str(BACKEND_DIR))
                        
                        from app.crud import PaperCRUD
                        from app.database import AsyncSessionLocal

                        async with AsyncSessionLocal() as db:
                            existing_urls = set(await PaperCRUD.get_all_paper_urls(db))
                            print(f"  数据库中已有 {len(existing_urls)} 篇论文")
                    except Exception as e:
                        print(f"  获取数据库已有论文失败: {e}")

                    # 按年份排序（降序，最新的年份在前）
                    for year in sorted(journal_data.keys(), reverse=True):
                        year_data = journal_data[year]
                        # 按期次排序（降序，最新的期次在前）
                        for issue in sorted(year_data.keys(), reverse=True):
                            issue_data = year_data[issue]
                            papers_list = issue_data.get('papers', [])
                            total_papers += len(papers_list)

                            # 过滤掉数据库中已存在的论文
                            papers_to_process = [p for p in papers_list if p['url'] not in existing_urls]

                            if not papers_to_process:
                                print(f"  {year}年{issue}期: 所有论文已在数据库中，跳过")
                                continue

                            print(f"\n  {year}年{issue}期: 需要处理 {len(papers_to_process)}/{len(papers_list)} 篇论文")

                            # 按照 papers_history.json 中的顺序（从上到下）获取论文详情
                            for i, paper in enumerate(papers_to_process, 1):
                                print(f"\n  [{i}/{len(papers_to_process)}] {paper['title'][:50]}...")
                                detail = await self.crawl_paper_detail(paper, journal_name)

                                if 'error' not in detail:
                                    # 异步保存到数据库，传递期刊名称
                                    await self.save_to_database(detail, journal_name)
                                    total_processed += 1

                                await asyncio.sleep(random.uniform(3, 6))

                    print(f"\n期刊 {journal_name} 处理完成: {total_processed}/{total_papers} 篇论文")

                    # 更新爬取日志为成功
                    if crawl_log_id:
                        try:
                            import sys
                            sys.path.insert(0, str(BACKEND_DIR))
                            from app.crud import CrawlLogCRUD
                            from app.database import AsyncSessionLocal
                            async with AsyncSessionLocal() as db:
                                await CrawlLogCRUD.update_crawl_log(
                                    db, crawl_log_id,
                                    crawl_end_time=datetime.now(),
                                    papers_fetched=total_processed,
                                    papers_failed=total_papers - total_processed,
                                    status="completed"
                                )
                                await db.commit()
                        except Exception as e:
                            print(f"  更新爬取日志失败: {e}")

                except Exception as e:
                    crawl_error = e
                    print(f"  处理期刊 {journal_name} 时出错: {e}")
                    import traceback
                    traceback.print_exc()

                    # 更新爬取日志为失败
                    if crawl_log_id:
                        try:
                            import sys
                            sys.path.insert(0, str(BACKEND_DIR))
                            from app.crud import CrawlLogCRUD
                            from app.database import AsyncSessionLocal
                            async with AsyncSessionLocal() as db:
                                await CrawlLogCRUD.update_crawl_log(
                                    db, crawl_log_id,
                                    crawl_end_time=datetime.now(),
                                    status="failed",
                                    error_message=str(e)
                                )
                                await db.commit()
                        except Exception:
                            pass

                if crawl_error:
                    continue

            print("\n" + "=" * 60)
            print("所有期刊处理完成")
            print("=" * 60)

        except Exception as e:
            print(f"运行错误: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await self.close_browser()
            print("\n浏览器已关闭")


async def main():
    parser = argparse.ArgumentParser(description='知网期刊爬虫 - 增量式版本')
    parser.add_argument('--show-browser', action='store_true', help='显示浏览器窗口（默认不显示）')
    args = parser.parse_args()

    crawler = IncrementalCrawler(headless=not args.show_browser)
    await crawler.run()


if __name__ == '__main__':
    asyncio.run(main())
