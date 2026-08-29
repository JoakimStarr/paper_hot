"""爬虫模式层：JournalCrawler（基类）/ JournalCollector / MultiThreadedCrawler /
KeywordSearchCrawler / ReferenceCrawler。

P0 阶段保结构搬迁（继承关系与类体逻辑原样）；后续阶段再拆成
journal_mode / search_mode / reference_mode 三个文件并抽详情流水线。
"""
import asyncio
import io
import json
import random
import re
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page

from cnki_crawler.paths import (
    BACKEND_DIR,
    CACHE_DIR,
    CNKI_STATE_FILE,
    _collect_state_file,
)
from cnki_crawler.pacing import (
    PACING_BASE_INTERVAL,
    PACING_MAX_INTERVAL,
    _pacing_wait,
    _report_captcha,
)
from cnki_crawler.parsing import (
    BASE_URL,
    SEARCH_FIELD_GROUP_MAP,
    TARGET_YEARS,
    _is_cnki_detail_url,
    _norm_title,
    _parse_ref_meta,
    _ref_title_keys,
)
from cnki_crawler.storage import (
    HistoryManager,
    _clear_search_checkpoint,
    _load_search_checkpoint,
    _save_search_checkpoint,
)
from cnki_crawler.captcha_solver import CaptchaSolver, DDDDOCR_AVAILABLE
from cnki_crawler.browser import _launch_kwargs
from cnki_crawler.captcha_gate import is_verify_url, wait_clean
from cnki_crawler import progress

# —— 详情抓取与搜索的防检测常量（原单文件脚本散落常量收敛于此）——
MIN_DETAIL_DELAY = 0.5
MAX_DETAIL_DELAY = 1.5
PAGE_STABLE_TIMEOUT = 30
DETAIL_MAX_RETRIES = 2
DETAIL_RETRY_BACKOFF = [3.0, 8.0]
SEARCH_MAX_RETRIES = 3


class JournalCrawler:
    """期刊/详情爬虫基类（单浏览器 + 多标签页并发模型）"""

    def __init__(self, headless=True, thread_id=0, state_file=None,
                 refs_with_details=False, ref_max_items=None, ref_detail_max=None):
        self.headless = headless
        self.thread_id = thread_id
        # --detail-refs：详情入库后在同一页顺带抓参考文献（省二次导航，防风控）
        self.refs_with_details = refs_with_details
        self.max_items = ref_max_items
        # 每篇最多抓多少条参考文献的详情（None=不限）
        self.ref_detail_max = ref_detail_max
        self.page = None
        self.browser = None
        self.playwright = None
        self.context = None
        # 会话态文件：存在则复用（暖会话），结束时保存（供下次/详情阶段使用）
        self.state_file = Path(state_file) if state_file else None
        self.db_initialized = False
        self.captcha_solver = CaptchaSolver(thread_id=thread_id)

    async def init_browser(self):
        """初始化浏览器"""
        self.playwright = await async_playwright().start()
        launch_kwargs = _launch_kwargs(self.headless)
        self.browser = await self.playwright.chromium.launch(**launch_kwargs)

        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        ]
        user_agent = random.choice(user_agents)

        viewports = [
            {'width': 1280, 'height': 800},
            {'width': 1366, 'height': 768},
            {'width': 1440, 'height': 900},
            {'width': 1536, 'height': 864},
            {'width': 1920, 'height': 1080},
        ]
        viewport = random.choice(viewports)

        ctx_kwargs = {
            'user_agent': user_agent,
            'viewport': viewport,
            'locale': 'zh-CN',
            'timezone_id': 'Asia/Shanghai',
            'permissions': ['geolocation'],
            'geolocation': {'latitude': 39.9042, 'longitude': 116.4074},
        }
        # 复用已保存的会话态（暖会话，显著降低冷会话首波验证码）
        if self.state_file and self.state_file.exists():
            ctx_kwargs['storage_state'] = str(self.state_file)
            print(f"  [线程{self.thread_id}] 复用会话态: {self.state_file}")

        context = await self.browser.new_context(**ctx_kwargs)

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

        # 保存 context，供详情并发阶段（fetch_details_concurrent）开 worker tab
        self.context = context
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

    async def save_storage_state(self):
        """保存会话态到 state_file（供下次运行 / 详情阶段复用）。"""
        if not self.state_file or not self.page:
            return
        try:
            await self.page.context.storage_state(path=str(self.state_file))
            print(f"  [线程{self.thread_id}] 会话态已保存: {self.state_file}")
        except Exception as e:
            print(f"  [线程{self.thread_id}] 保存会话态失败: {e}")

    async def _warmup(self):
        """暖场：访问知网首页停留片刻并保存会话态，降低冷会话首波验证码概率。"""
        if not self.page:
            return
        try:
            await _pacing_wait()
            await self.page.goto('https://www.cnki.net/', wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(random.uniform(2, 4))
            await self.random_scroll()
            await self.save_storage_state()
            print(f"  [线程{self.thread_id}] 暖场完成")
        except Exception as e:
            print(f"  [线程{self.thread_id}] 暖场跳过: {e}")

    async def random_scroll(self, page=None):
        """随机滚动页面模拟人类行为"""
        page = page or self.page
        try:
            scroll_times = random.randint(1, 3)
            for _ in range(scroll_times):
                scroll_y = random.randint(100, 500)
                await page.evaluate(f'window.scrollBy(0, {scroll_y})')
                await asyncio.sleep(random.uniform(0.5, 2))
        except Exception:
            pass

    def is_verify_page(self, page_url: str) -> bool:
        """检查是否是验证码页面（委托统一验证码闸的 URL 判定）。"""
        return is_verify_url(page_url)

    async def wait_for_page_stable(self, target_url: str, max_wait_time: int = 300, page=None) -> bool:
        """等待页面稳定，自动解决验证码（委托统一验证码闸 captcha_gate.wait_clean）。

        与原实现相比：现在同时检测不改变 URL 的弹窗/遮罩验证码，且失败会上报熔断。
        """
        page = page or self.page
        return await wait_clean(
            page, tag=f"    [线程{self.thread_id}]", timeout=max_wait_time,
            headless=self.headless, solver=self.captcha_solver)

    async def get_year_issues(self, journal_url: str) -> list:
        """获取期刊的年份期次列表"""
        print(f"  [线程{self.thread_id}] 访问期刊页面: {journal_url[:60]}...")
        await _pacing_wait()
        await self.page.goto(journal_url, wait_until='domcontentloaded', timeout=60000)

        if not await self.wait_for_page_stable(journal_url):
            return []

        # 事件驱动：等期次树容器出现再解析，替代固定 8s 等待
        try:
            await self.page.wait_for_selector(
                'div.yearissuepage, #YearIssueTree', timeout=PAGE_STABLE_TIMEOUT * 1000
            )
        except Exception:
            print(f"  [线程{self.thread_id}] 等待期次容器超时，继续尝试解析")
        await asyncio.sleep(random.uniform(MIN_DETAIL_DELAY, MAX_DETAIL_DELAY))

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

        skip_keywords = [
            '征稿启事', '征稿', '征文', '征订', '稿约', '投稿须知', '投稿指南',
            '总目录', '目录', '索引', '内容提要',
            '编辑部公告', '编辑部关于', '编辑部声明', '公告', '声明', '启事', '通知', '更正', '勘误', '补遗',
            '书评', '评介', '学院简介', '中心简介', '新书介绍', '新书评介',
            '会议纪要', '会议综述', '会议报道', '会议简报',
            '新闻', '消息', '简讯', '报道',
            '广告', '致谢名单', '致谢专家', '鸣谢',
            '卷首语', '编者按', '导读', '操作指南', '使用指南', '手册',
            '人才招聘', '全球人才招聘', '招生', '培训', '课程', '讲座',
            '版权声明', '著作权', '授权声明',
            '欢迎订阅', '订阅杂志', '订购', '欢迎购买',
        ]

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
                await _pacing_wait()
                await self.page.evaluate('document.getElementById("larrow").click()')
                # 事件驱动：等目录容器重新出现再继续，替代固定 8s
                try:
                    await self.page.wait_for_selector(
                        '#rightCataloglist, #originalCatalogview', timeout=PAGE_STABLE_TIMEOUT * 1000
                    )
                except Exception:
                    print(f"    [线程{self.thread_id}] 等待目录容器超时，继续尝试解析")
                await asyncio.sleep(random.uniform(MIN_DETAIL_DELAY, MAX_DETAIL_DELAY))
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
            issue_num = f"{issue['issue_num']:02d}"
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

    async def crawl_paper_detail(self, paper_info: dict, journal_name: str = None, year: str = None, issue: str = None, page=None) -> dict:
        """获取论文详情（编排：去重 → 加载详情页 → 解析 → 入库）。

        加载与解析拆成 _load_detail_html / _parse_detail_html 两个可复用片段，
        供参考文献详情抓取复用（后者只需「加载+解析+入库」，不再递归抓参考文献）。
        """
        page = page or self.page
        paper_url = paper_info['url']

        # 去重检查（并发 worker 间安全网；批量阶段已预取 existing_urls 做过一次过滤）
        if await self._db_paper_exists(paper_url):
            print(f"  [线程{self.thread_id}] 数据库中已存在，跳过")
            return {'error': 'already_exists'}

        print(f"  [线程{self.thread_id}] 获取论文详情: {paper_info['title'][:50]}...")

        html, err = await self._load_detail_html(paper_url, page=page)
        if html is None:
            return {'error': err or 'load_failed'}

        result = self._parse_detail_html(html, paper_url, paper_info.get('journal', ''))
        if result.get('error'):
            return result

        print(f"    [线程{self.thread_id}] ✓ 成功获取: {result['title'][:40]}...")
        await self.save_to_database(result, journal_name, year, issue)
        # --detail-refs：详情入库后顺带抓参考文献（失败只记日志，不回滚详情）
        if self.refs_with_details:
            await self._fetch_refs_for_detail(paper_url, result['title'])
        return result

    async def _load_detail_html(self, paper_url: str, page=None) -> tuple:
        """打开论文详情页并取回 HTML：成功 (html, None)，失败 (None, 错误原因)。

        goto 前过全局导航闸；安全验证页直接判定失败不再重试（重试只会连撞风控），
        其余网络/解析失败按 DETAIL_RETRY_BACKOFF 退避重试。
        """
        page = page or self.page
        for attempt in range(DETAIL_MAX_RETRIES + 1):
            try:
                await _pacing_wait()
                await page.goto(paper_url, wait_until='domcontentloaded', timeout=60000)

                if not await self.wait_for_page_stable(paper_url, page=page):
                    return None, 'verify_page'

                await self.random_scroll(page=page)
                try:
                    await page.wait_for_selector('div.doc h1, h1', timeout=20000)
                except Exception:
                    pass
                await asyncio.sleep(random.uniform(MIN_DETAIL_DELAY, MAX_DETAIL_DELAY))

                return await page.content(), None
            except Exception as e:
                if attempt < DETAIL_MAX_RETRIES:
                    backoff = DETAIL_RETRY_BACKOFF[min(attempt, len(DETAIL_RETRY_BACKOFF) - 1)]
                    print(f"    [线程{self.thread_id}] 详情页加载失败（{e}），{backoff}s 后重试 ({attempt + 1}/{DETAIL_MAX_RETRIES})")
                    await asyncio.sleep(backoff)
                else:
                    print(f"    [线程{self.thread_id}] ✗ 获取失败: {e}")
                    return None, str(e)
        return None, 'load_failed'

    def _parse_detail_html(self, html: str, paper_url: str, fallback_journal: str = '') -> dict:
        """解析详情页 HTML：成功返回论文字典，失败返回 {'error': ...}（不入库、不抓参考文献）。"""
        try:
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

            skip_keywords = [
                '征稿启事', '征稿', '征文', '征订', '稿约', '投稿须知', '投稿指南',
                '总目录', '目录', '索引', '内容提要',
                '编辑部公告', '编辑部关于', '编辑部声明', '公告', '声明', '启事', '通知', '更正', '勘误', '补遗',
                '书评', '评介', '学院简介', '中心简介', '新书介绍', '新书评介',
                '会议纪要', '会议综述', '会议报道', '会议简报',
                '新闻', '消息', '简讯', '报道',
                '广告', '致谢名单', '致谢专家', '鸣谢',
                '卷首语', '编者按', '导读', '操作指南', '使用指南', '手册',
                '人才招聘', '全球人才招聘', '招生', '培训', '课程', '讲座',
                '版权声明', '著作权', '授权声明',
                '欢迎订阅', '订阅杂志', '订购', '欢迎购买',
            ]
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
                    author_name = re.sub(r'[\w.+-]+@[\w.+-]+', '', author_name).strip()
                    author_name = re.sub(r'@\.com', '', author_name).strip()
                    author_name = author_name.strip().rstrip(',').rstrip('，').strip()
                    author_name = re.sub(r'\s+', '', author_name)
                    if not author_name or len(author_name) < 2:
                        continue
                    if not re.search(r'[\u4e00-\u9fff]', author_name):
                        continue
                    if re.search(r'[@\d]', author_name):
                        continue
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

            if not title:
                print(f"    [线程{self.thread_id}] ✗ 获取失败: 无标题")
                return {'error': 'no_title'}

            return {
                'title': title,
                'authors': authors,
                'abstract': abstract,
                'keywords': keywords,
                'url': paper_url,
                'journal': fallback_journal,
                **meta
            }

        except Exception as e:
            print(f"    [线程{self.thread_id}] ✗ 获取失败: {e}")
            return {'error': str(e)}

    async def _ensure_db(self):
        """确保数据库文件存在并初始化表结构（首次运行自动建库）。"""
        if self.db_initialized:
            return
        from app.database import init_db
        db_file = BACKEND_DIR / 'data' / 'paperpulse.db'
        # SQLite 不会自动创建父目录：先确保 backend/data/ 存在，
        # 否则 init_db() 报 unable to open database file
        db_file.parent.mkdir(parents=True, exist_ok=True)
        if not db_file.exists():
            print(f"    [线程{self.thread_id}] 数据库文件不存在，正在创建...")
            await init_db()
            print(f"    [线程{self.thread_id}] ✓ 数据库已创建")
        self.db_initialized = True

    async def _db_paper_exists(self, paper_url: str) -> bool:
        """按 URL 判断论文是否已在库中。"""
        try:
            from app.crud import PaperCRUD
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                return (await PaperCRUD.get_paper_by_url(db, paper_url)) is not None
        except Exception:
            return False

    async def _db_existing_urls(self) -> set:
        """批量获取库中全部论文 URL（详情阶段开始时调用一次，避免逐篇 roundtrip）。"""
        try:
            from app.crud import PaperCRUD
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                return set(await PaperCRUD.get_all_paper_urls(db))
        except Exception as e:
            print(f"  [线程{self.thread_id}] 获取数据库已有论文失败: {e}")
            return set()

    async def _db_existing_titles(self) -> set:
        """批量获取库中全部论文标题的归一化 key（参考文献详情去重用：本地已有就不打开详情页）。

        知网详情页 URL 带会话态 v 令牌，同一篇论文每次入口都不同，只按 URL 判重会漏；
        标题是跨入口稳定的判重键，这里一次取全量避免逐条查库。
        """
        try:
            from sqlalchemy import select
            from app.models import Paper
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                rows = (await db.execute(select(Paper.title))).all()
            return {_norm_title(r[0]) for r in rows if r[0]}
        except Exception as e:
            print(f"  [线程{self.thread_id}] 获取数据库已有标题失败: {e}")
            return set()

    async def _create_crawl_log(self, journal_name: str) -> Optional[int]:
        """创建爬取日志，返回 crawl_log_id。"""
        try:
            from app.schemas import CrawlLogCreate
            from app.crud import CrawlLogCRUD
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                crawl_log = await CrawlLogCRUD.create_crawl_log(
                    db, CrawlLogCreate(journal_name=journal_name, crawl_start_time=datetime.now())
                )
                await db.commit()
                return crawl_log.id
        except Exception as e:
            print(f"  [线程{self.thread_id}] 创建爬取日志失败: {e}")
            return None

    async def _update_crawl_log(self, crawl_log_id: Optional[int], **fields):
        """更新爬取日志（成功/失败均走这里）。"""
        if not crawl_log_id:
            return
        try:
            from app.crud import CrawlLogCRUD
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                await CrawlLogCRUD.update_crawl_log(db, crawl_log_id, **fields)
                await db.commit()
        except Exception as e:
            print(f"  [线程{self.thread_id}] 更新爬取日志失败: {e}")

    async def save_to_database(self, paper_data: dict, journal_name: str = None, year: str = None, issue: str = None):
        """异步保存到数据库"""
        # 多 worker 并发写库会撞 SQLite 写锁：实例级锁串行化写操作
        if not hasattr(self, "_db_lock"):
            self._db_lock = asyncio.Lock()
        async with self._db_lock:
            try:
                import re
                await self._ensure_db()

                from app.crud import PaperCRUD
                from app.database import AsyncSessionLocal

                async with AsyncSessionLocal() as db:
                    existing = await PaperCRUD.get_paper_by_url(db, paper_data['url'])
                    if existing:
                        print(f"    [线程{self.thread_id}] 数据库中已存在，跳过")
                        return False

                    if journal_name:
                        paper_data['journal_name'] = journal_name
                    elif paper_data.get('journal'):
                        paper_data['journal_name'] = paper_data.pop('journal')

                    if year and issue:
                        paper_data['journal_issue'] = f"{year}年第{issue}期"

                    doi = paper_data.get('doi', '')
                    if doi:
                        match = re.search(r'\.(\d{4})\.', doi)
                        if match:
                            paper_data['year'] = int(match.group(1))

                    paper = await PaperCRUD.create_paper_from_cnki(db, paper_data)
                    if paper:
                        await db.commit()
                        print(f"    [线程{self.thread_id}] ✓ 已保存到数据库")
                        return True
                    # create_paper_from_cnki 返回 None：URL/标题已存在，或缺作者/缺关键词被拒收
                    return False
            except Exception as e:
                print(f"    [线程{self.thread_id}] ✗ 保存到数据库失败: {e}")
                import traceback
                traceback.print_exc()
                return False

    # —— 参考文献抓取（详情流程 --detail-refs 与独立参考文献模式共用）——
    REF_LIST_SELECTOR = 'ul.ebBd'
    REF_NEXT_SELECTOR = 'a.next'
    # 「参考文献」页签：先点击（onclick=changeRefTypeTag）列表才渲染，按优先级逐个尝试
    REF_TAB_SELECTORS = [
        'li[data-id="references"]',
        'li[onclick*="changeRefTypeTag"]',
        'li:text-is("参考文献")',
        'a:text-is("参考文献")',
    ]
    # 防风控节奏（参考文献抓取专用，默认偏保守）
    REF_PAGE_INTERVAL = (2.0, 4.5)   # 每次翻页前的随机间隔（秒）
    REF_TAB_WAIT = 15                # 点击页签后等待 ul.ebBd 渲染的超时（秒）

    async def _fetch_refs_for_detail(self, paper_url: str, title: str):
        """--detail-refs：详情入库后在同一页顺带抓参考文献；任何失败只记日志不回滚详情。"""
        tag = f"[线程{self.thread_id}]"
        try:
            refs = await self._crawl_references(tag)
            if not refs:
                print(f"    {tag} 该详情页未抓到参考文献条目，跳过")
                return
            if self.max_items and len(refs) > self.max_items:
                refs = refs[:self.max_items]
            await self._save_references(paper_url, title, refs)
            self._refs_done = getattr(self, '_refs_done', 0) + 1
        except Exception as e:
            print(f"    {tag} ✗ 参考文献抓取失败（不影响已入库详情）: {e}")
            self._refs_failed = getattr(self, '_refs_failed', 0) + 1

    async def _open_references_tab(self, tag: str):
        """点击详情页「参考文献」页签（li[data-id="references"]，onclick=changeRefTypeTag）。

        列表在点击页签后才异步渲染；按优先级逐个尝试选择器，普通点击失败时
        用 JS click 兜底（onclick 绑定在 li 上，JS 触发同样生效），点击后等待
        ul.ebBd 渲染出来再返回。
        """
        for sel in self.REF_TAB_SELECTORS:
            loc = self.page.locator(sel).first
            if await loc.count() == 0:
                continue
            try:
                await loc.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            try:
                await loc.click(timeout=5000)
            except Exception:
                try:
                    await loc.evaluate('el => el.click()')
                except Exception as e:
                    print(f"{tag} 点击页签 {sel} 失败: {e}")
                    continue
            print(f"{tag} 已点击「参考文献」页签: {sel}")
            # 列表多为滚动到可视区域才懒加载渲染：点完页签把文献区滚进视口，边滚边等 ul.ebBd 出现
            deadline = asyncio.get_event_loop().time() + self.REF_TAB_WAIT
            while asyncio.get_event_loop().time() < deadline:
                if await self.page.locator(self.REF_LIST_SELECTOR).count() > 0:
                    break
                try:
                    await loc.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                try:
                    await self.page.evaluate('window.scrollBy(0, 320)')
                except Exception:
                    pass
                await asyncio.sleep(random.uniform(0.4, 0.8))
            try:
                await self.page.locator(self.REF_LIST_SELECTOR).first.wait_for(
                    state='visible', timeout=3000)
            except Exception:
                print(f"{tag} 点击页签并滚动后仍未见到 ul.ebBd，继续尝试直接解析")
            return True
        print(f"{tag} 未找到「参考文献」页签，尝试直接解析列表")
        return False

    async def _crawl_references(self, tag: str) -> list:
        """抓取参考文献条目：ul.ebBd 下每页 li，a.next 翻页，按钮消失即末页。"""
        refs: list = []
        seen = set()
        page_no = 1
        while True:
            # 需求确认：先点击「参考文献」页签（changeRefTypeTag）列表才渲染，每篇开始必点
            if page_no == 1:
                await self._open_references_tab(tag)
            loc = self.page.locator(self.REF_LIST_SELECTOR)
            if await loc.count() == 0:
                print(f"{tag} 第 {page_no} 页未找到参考文献容器 ul.ebBd（可加 --show-browser 人工核对页面）")
                break
            # 懒加载：把列表滚进视口再取（翻页后的新条目同样需要滚到可见才渲染）
            try:
                await loc.first.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            items = await loc.locator('xpath=./li').evaluate_all(
                """(lis) => lis.map((li) => {
                    const a = li.querySelector('a[href]');
                    const text = (li.innerText || '').replace(/\\s+/g, ' ').trim();
                    return { text, url: a ? a.href : null };
                }).filter((x) => x.text)"""
            )
            # 跨页去重：翻页未生效时重复收集的同一页内容会被去重掉，不会重复入库
            new_count = 0
            for it in items:
                key = (it.get('url') or '', it['text'])
                if key in seen:
                    continue
                seen.add(key)
                refs.append(it)
                new_count += 1
            progress.emit_refs_page_progress(tag, page_no, len(items), new_count, len(refs))
            if self.max_items and len(refs) >= self.max_items:
                print(f"{tag} 已达上限 {self.max_items} 条，停止翻页")
                break
            # 「下一页」按钮：不存在即末页（需求）；置灰(disable)同样视为末页
            nxt = self.page.locator(self.REF_NEXT_SELECTOR).first
            if await nxt.count() == 0:
                print(f"{tag} 「下一页」按钮已消失，参考文献抓取完成")
                break
            cls = (await nxt.get_attribute('class')) or ''
            if 'disable' in cls:
                print(f"{tag} 「下一页」按钮已置灰，已是末页，参考文献抓取完成")
                break
            first_before = items[0]['text'][:60] if items else ''
            # 翻页请求同样计入风控：先随机停顿，再过全局导航闸
            await asyncio.sleep(random.uniform(*self.REF_PAGE_INTERVAL))
            await _pacing_wait()
            try:
                await nxt.click(timeout=8000)
            except Exception as e:
                print(f"{tag} 点击下一页失败: {e}")
                break
            # 等翻页真正生效：列表重新可见且首条内容变化（最多约 20s），防点击未生效导致死循环
            advanced = False
            deadline = asyncio.get_event_loop().time() + 20
            while asyncio.get_event_loop().time() < deadline:
                try:
                    await self.page.locator(self.REF_LIST_SELECTOR).first.wait_for(state='visible', timeout=5000)
                except Exception:
                    pass
                cur_first = await self._first_ref_text()
                if cur_first and cur_first != first_before:
                    advanced = True
                    break
                if await self.page.locator(self.REF_LIST_SELECTOR).count() == 0:
                    break
                await asyncio.sleep(0.8)
            if not advanced:
                print(f"{tag} 点击下一页后列表内容未变化，视为已到末页，停止")
                break
            page_no += 1
        return refs

    async def _first_ref_text(self) -> str:
        """读取当前参考文献列表首条文本（用于判断翻页是否生效）。"""
        try:
            loc = self.page.locator(f'{self.REF_LIST_SELECTOR} > li').first
            text = await loc.inner_text(timeout=3000)
            return (text or '').replace('\n', ' ').strip()[:60]
        except Exception:
            return ''

    async def _save_references(self, paper_url: str, paper_title: str, refs: list):
        """覆盖式写入论文行的 references_cn JSON（[{index, text, url}]）。

        知网 kcms2 URL 的 v 令牌随入口变化：先按 URL 精确更新，未命中再按标题更新；
        论文不在库中则明确提示（参考文献随论文行存储，未入库无处挂载）。
        """
        payload = json.dumps(
            [{"index": i, "text": (r.get('text') or '')[:2000], "url": r.get('url')}
             for i, r in enumerate(refs, start=1)],
            ensure_ascii=False)
        if not hasattr(self, "_db_lock"):
            self._db_lock = asyncio.Lock()
        async with self._db_lock:
            try:
                await self._ensure_db()
                from sqlalchemy import update
                from app.models import Paper
                from app.database import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        update(Paper).where(Paper.url == paper_url).values(references_cn=payload))
                    if result.rowcount == 0 and (paper_title or '').strip():
                        result = await db.execute(
                            update(Paper).where(Paper.title == paper_title.strip()).values(references_cn=payload))
                    await db.commit()
                    if result.rowcount:
                        progress.emit_refs_saved(f"    [线程{self.thread_id}]", len(refs),
                                                 extra=f" -> {(paper_title or paper_url)[:60]}")
                    else:
                        print(f"    [线程{self.thread_id}] ⚠ 该论文不在库中，参考文献未保存（可先入库再抓取）: {(paper_title or paper_url)[:60]}")
            except Exception as e:
                progress.emit_refs_failed(f"    [线程{self.thread_id}]", e)
                import traceback
                traceback.print_exc()

    async def _crawl_reference_details(self, refs: list, tag: str) -> dict:
        """把每条参考文献当一篇论文抓详情入库（只走「加载 + 解析 + 入库」，不再递归抓它自己的参考文献）。

        每条都要一次页面导航，是风控的主要来源，因此：
        - 本地库已有的（URL 或标题命中）直接跳过，不打开详情页；
        - 条目原文解析不出年份的跳过（否则 published_at 落到今年，综合分里 recency 权重 0.35
          会把老文献顶到发现流前面）；
        - 每条之间随机停顿并过全局导航闸；一旦撞上安全验证页立即中止本轮剩余条目。

        日志里的进度写成 (i/total) 而不是 [i/total]：后端把 [N/M] 当详情页进度解析
        （backend/app/routers/crawler.py 的 _parse_cnki_progress），这里不能污染它。
        """
        stats = {'saved': 0, 'dup_local': 0, 'dup_in_run': 0, 'no_url': 0, 'non_cnki': 0,
                 'no_year': 0, 'incomplete': 0, 'filtered': 0, 'failed': 0, 'aborted': 0}
        candidates = []
        for r in refs:
            url = r.get('url')
            if not url:
                stats['no_url'] += 1
            elif not _is_cnki_detail_url(url):
                stats['non_cnki'] += 1
            else:
                candidates.append(r)
        if self.ref_detail_max and len(candidates) > self.ref_detail_max:
            print(f"{tag} 参考文献详情超出上限 {self.ref_detail_max} 条，截断（可抓 {len(candidates)} 条）")
            candidates = candidates[:self.ref_detail_max]
        total = len(candidates)
        print(f"{tag} 参考文献条目 {len(refs)} 条：无链接 {stats['no_url']} 条、"
              f"非知网链接 {stats['non_cnki']} 条，本次抓详情 {total} 条")
        if not total:
            return stats

        existing_urls = await self._db_existing_urls()
        existing_titles = await self._db_existing_titles()
        seen = set()
        for i, r in enumerate(candidates, 1):
            url, text = r['url'], (r.get('text') or '')
            if url in seen:
                stats['dup_in_run'] += 1
                continue
            seen.add(url)
            if url in existing_urls or (_ref_title_keys(text) & existing_titles):
                stats['dup_local'] += 1
                print(f"{tag} 参考文献详情 ({i}/{total}) 本地已有，跳过打开：{text[:40]}")
                continue
            year, journal = _parse_ref_meta(text)
            if not year:
                stats['no_year'] += 1
                print(f"{tag} 参考文献详情 ({i}/{total}) 条目解析不出年份，跳过：{text[:40]}")
                continue
            await asyncio.sleep(random.uniform(*self.REF_PAGE_INTERVAL))
            html, err = await self._load_detail_html(url)
            if err == 'verify_page':
                stats['aborted'] = total - i + 1
                print(f"{tag} ⚠ 遇到安全验证页，中止本轮参考文献详情抓取（已处理 {i - 1} 条）")
                break
            if html is None:
                stats['failed'] += 1
                print(f"{tag} 参考文献详情 ({i}/{total}) 详情页加载失败：{text[:40]}")
                continue
            result = self._parse_detail_html(html, url, journal or '')
            if result.get('error'):
                stats['filtered'] += 1
                print(f"{tag} 参考文献详情 ({i}/{total}) 非论文条目，跳过：{text[:40]}")
                continue
            result['year'] = year
            if await self.save_to_database(result, journal_name=journal):
                stats['saved'] += 1
                existing_urls.add(url)
                existing_titles.add(_norm_title(result['title']))
                print(f"{tag} 参考文献详情 ({i}/{total}) ✓ 已入库：{result['title'][:30]}（{year}）")
            else:
                stats['incomplete'] += 1
                print(f"{tag} 参考文献详情 ({i}/{total}) 未入库（已存在 / 缺作者或关键词 / 入库异常）：{text[:40]}")

        print(f"{tag} 参考文献详情小结：入库 {stats['saved']} 条，本地已有跳过 {stats['dup_local']} 条，"
              f"本轮重复 {stats['dup_in_run']} 条，年份缺失 {stats['no_year']} 条，"
              f"著录不全 {stats['incomplete']} 条，非论文条目 {stats['filtered']} 条，"
              f"失败 {stats['failed']} 条"
              + (f"，遇验证页中止剩余 {stats['aborted']} 条" if stats['aborted'] else ""))
        return stats

    async def fetch_journals(self) -> dict:
        """获取期刊列表（复用共享浏览器的主页面，不再单独开浏览器）。"""
        print("=" * 60)
        print("步骤1-3: 获取期刊列表")
        print("=" * 60)

        if HistoryManager.is_journals_cache_valid():
            print("发现有效的期刊历史记录，直接复用")
            history = HistoryManager.load_journals_history()
            return history['journals']

        print("未找到有效的期刊历史记录，开始爬取...")

        page = self.page
        try:
            print("访问期刊导航页...")
            await _pacing_wait()
            await page.goto(f'{BASE_URL}/knavi/journals/index', wait_until='domcontentloaded', timeout=60000)

            print("点击'经济与管理科学'按钮...")
            try:
                # 尝试多种选择器
                selectors = [
                    'a[title="经济与管理科学"]',
                    'a:has-text("经济与管理科学")',
                    'a:text("经济与管理科学")',
                ]
                btn = None
                for selector in selectors:
                    try:
                        btn = await page.wait_for_selector(selector, timeout=5000)
                        if btn:
                            print(f"  使用选择器找到按钮: {selector}")
                            break
                    except:
                        continue

                if btn:
                    await btn.click()
                else:
                    print("  未找到按钮，尝试通过文本查找...")
                    # 通过页面文本查找
                    elements = await page.query_selector_all('a')
                    for elem in elements:
                        text = await elem.text_content()
                        if text and '经济与管理科学' in text:
                            await elem.click()
                            print("  通过文本内容找到并点击")
                            break
                # 事件驱动：等期刊列表容器出现，替代固定 5s
                try:
                    await page.wait_for_selector('div.result, div.resultList, #gridTable', timeout=PAGE_STABLE_TIMEOUT * 1000)
                except Exception:
                    print("  等待期刊列表容器超时，继续尝试解析")
                await asyncio.sleep(random.uniform(MIN_DETAIL_DELAY, MAX_DETAIL_DELAY))
            except Exception as e:
                print(f"点击按钮失败: {e}")

            html = await page.content()
            soup = BeautifulSoup(html, 'lxml')

            result_div = soup.find('div', class_='result')
            if not result_div:
                # 尝试其他选择器
                result_div = soup.find('div', class_='resultList')
                if not result_div:
                    result_div = soup.find('div', id='gridTable')
            if not result_div:
                print("未找到期刊列表容器")
                print("页面标题:", await page.title())
                print("当前URL:", page.url)
                # 保存页面HTML用于调试
                debug_file = BACKEND_DIR / 'data' / 'debug_journals.html'
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"已保存页面HTML到: {debug_file}")
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

            return journals

        except Exception as e:
            print(f"爬取期刊列表失败: {e}")
            import traceback
            traceback.print_exc()
            return {}

    async def fetch_details_concurrent(self, workers: int, collected_journals: list):
        """集中并发抓详情入库（单浏览器 + N 个 worker tab）。

        collected_journals: [{'name': str, 'log_id': int|None, 'count': int}, ...]
        论文清单从 HistoryManager 读取（收集阶段已写入），并对库中已有 URL 批量去重。
        """
        if not collected_journals:
            return
        tag = f"[线程{self.thread_id}]"
        journal_names = [j['name'] for j in collected_journals]
        log_by_name = {j['name']: j['log_id'] for j in collected_journals}

        # 从 HistoryManager 摊平出 (journal, year, issue, paper) 任务
        history = HistoryManager.load_papers_history()
        tasks = []
        per_journal_total = {jn: 0 for jn in journal_names}
        for jn in journal_names:
            jdata = history.get('papers', {}).get(jn, {})
            for year in sorted(jdata.keys(), reverse=True):
                for issue in sorted(jdata[year].keys(), reverse=True):
                    for p in jdata[year][issue].get('papers', []):
                        tasks.append((jn, year, issue, p))
                        per_journal_total[jn] += 1

        print(f"\n{tag} 共收集 {len(tasks)} 篇待处理论文，预取数据库已有 URL ...")
        existing_urls = await self._db_existing_urls()
        print(f"{tag} 数据库中已有 {len(existing_urls)} 篇论文")

        queue = asyncio.Queue()
        skipped = 0
        for jn, year, issue, p in tasks:
            if p.get('url') in existing_urls:
                skipped += 1
                continue
            queue.put_nowait((jn, year, issue, p))
        print(f"{tag} 已在库跳过 {skipped} 篇，待抓 {queue.qsize()} 篇")

        total = queue.qsize()
        done = ok = 0
        stats = {'already_exists': skipped, 'filtered': 0, 'verify_failed': 0, 'failed': 0}
        per_journal_ok = {jn: 0 for jn in journal_names}

        async def detail_worker(wid: int):
            nonlocal done, ok
            wtag = f"{tag}[W{wid}]"
            page = await self.context.new_page()
            try:
                while True:
                    try:
                        jn, year, issue, paper = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    done += 1
                    print(f"{wtag} [{done}/{total}] 处理: {paper['title'][:30]}...")
                    res = await self.crawl_paper_detail(paper, jn, year, issue, page=page)
                    if res and res.get('title'):
                        ok += 1
                        per_journal_ok[jn] += 1
                    else:
                        reason = res.get('error', 'failed') if res else 'failed'
                        if reason == 'already_exists':
                            stats['already_exists'] += 1
                        elif reason == 'verify_page':
                            stats['verify_failed'] += 1
                        elif reason == 'filtered_non_paper':
                            stats['filtered'] += 1
                        else:
                            stats['failed'] += 1
                    await asyncio.sleep(random.uniform(0.5, 1.5))
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

        n = max(1, workers)
        print(f"{tag} 详情并发数: {n}")
        await asyncio.gather(*[detail_worker(i) for i in range(n)])

        # 汇总输出（按原因统计，便于定位问题）
        print(f"\n{tag} {'=' * 60}")
        progress.emit_detail_summary(tag, ok, total, stats['already_exists'],
                                     stats['filtered'], stats['verify_failed'], stats['failed'])
        if getattr(self, '_refs_done', 0) or getattr(self, '_refs_failed', 0):
            progress.emit_refs_detail_summary(tag, getattr(self, '_refs_done', 0),
                                              getattr(self, '_refs_failed', 0))
        print(f"{tag} {'=' * 60}")

        # 更新各期刊爬取日志
        for jn in journal_names:
            ok_j = per_journal_ok[jn]
            total_j = per_journal_total[jn]
            await self._update_crawl_log(
                log_by_name.get(jn),
                crawl_end_time=datetime.now(),
                papers_fetched=ok_j,
                papers_failed=total_j - ok_j,
                status="completed",
            )


class JournalCollector:
    """期刊链接收集器：一个浏览器负责一批期刊，并行收集论文链接写入 HistoryManager。"""

    def __init__(self, headless: bool, thread_id: int, journals: list, state_file: Optional[Path]):
        self.crawler = JournalCrawler(headless=headless, thread_id=thread_id, state_file=state_file)
        self.journals = journals
        self.results: list = []  # [{'name','log_id','count'}, ...]

    async def run(self):
        tag = f"[收集器{self.crawler.thread_id}]"
        await self.crawler.init_browser()
        try:
            await self.crawler._warmup()
            total = len(self.journals)
            for i, (journal_name, journal_info) in enumerate(self.journals, 1):
                print(f"\n{tag} [{i}/{total}] 收集期刊: {journal_name}")
                try:
                    papers = await self.crawler.crawl_papers_for_journal(journal_name, journal_info)
                    crawl_log_id = await self.crawler._create_crawl_log(journal_name)
                    self.results.append({
                        'name': journal_name,
                        'log_id': crawl_log_id,
                        'count': len(papers),
                    })
                    print(f"{tag} [{i}/{total}] 期刊 {journal_name} 共收集 {len(papers)} 篇论文")
                except Exception as e:
                    print(f"{tag} 收集期刊 {journal_name} 出错: {e}")
                    import traceback
                    traceback.print_exc()
                    # 单期刊失败不阻塞其他期刊（继续下一批）
        finally:
            await self.crawler.save_storage_state()
            await self.crawler.close_browser()


class MultiThreadedCrawler:
    """期刊模式爬虫管理器。

    阶段一（收集）：N 个浏览器（--threads）并行收集各期刊论文链接；
    阶段二（详情）：单浏览器 + M 个 worker tab（--detail-workers）并发抓详情入库。
    两个阶段共享全局导航闸/熔断，避免聚合请求率过高触发验证码。
    """

    def __init__(self, headless=True, max_workers=3, detail_workers=3,
                 refs_with_details=False, ref_max_items=None):
        self.headless = headless
        self.max_workers = max(1, int(max_workers))
        self.detail_workers = max(1, int(detail_workers))
        self.refs_with_details = refs_with_details
        self.ref_max_items = ref_max_items

    async def run(self):
        """运行期刊爬虫（收集并行 -> 详情并发）。"""
        print("=" * 60)
        print(f"知网期刊爬虫 - 验证码自动解决版本")
        print(f"收集并发浏览器数: {self.max_workers} | 详情并发 tab 数: {self.detail_workers}")
        print(f"全局导航间隔: {PACING_BASE_INTERVAL}s（熔断上限 {PACING_MAX_INTERVAL}s）")
        print(f"浏览器模式: {'无头' if self.headless else '显示窗口'}")
        if DDDDOCR_AVAILABLE:
            print("验证码解决: ddddocr 已启用")
        else:
            print("验证码解决: ddddocr 未安装，将使用手动模式")
        print("=" * 60)

        # 步骤0：单个浏览器获取期刊列表（复用暖会话）
        listing = JournalCrawler(headless=self.headless, thread_id=0, state_file=CNKI_STATE_FILE)
        await listing.init_browser()
        try:
            journals = await listing.fetch_journals()
        finally:
            await listing.save_storage_state()
            await listing.close_browser()
        if not journals:
            print("未获取到期刊列表，退出")
            return

        journal_list = list(journals.items())
        print(f"\n共 {len(journal_list)} 个期刊需要处理")

        # 阶段一：N 个浏览器并行收集（每个浏览器独立会话态文件，避免共享 cookie）
        n = self.max_workers
        slices = [journal_list[i::n] for i in range(n)]
        slices = [s for s in slices if s]
        collectors = [
            JournalCollector(self.headless, i + 1, sl, _collect_state_file(i))
            for i, sl in enumerate(slices)
        ]
        print(f"使用 {len(collectors)} 个收集浏览器并行处理\n")
        await asyncio.gather(*[c.run() for c in collectors])

        collected_journals = [item for c in collectors for item in c.results]
        print(f"\n共收集 {len(collected_journals)} 个期刊的论文链接")

        # 阶段二：单浏览器 + M tab 并发抓详情入库（复用收集阶段保存的暖会话）
        detail = JournalCrawler(headless=self.headless, thread_id=0, state_file=CNKI_STATE_FILE,
                                refs_with_details=self.refs_with_details,
                                ref_max_items=self.ref_max_items)
        await detail.init_browser()
        try:
            await detail._warmup()
            await detail.fetch_details_concurrent(self.detail_workers, collected_journals)
        finally:
            await detail.save_storage_state()
            await detail.close_browser()

        print("\n" + "=" * 60)
        print("所有期刊处理完成")
        print("=" * 60)


class KeywordSearchCrawler(JournalCrawler):
    """按关键词/主题检索知网论文（结合关键词检索流程与主脚本的验证码/入库能力）。

    复用父类：CaptchaSolver 自动解验证码、wait_for_page_stable、
    random_scroll、crawl_paper_detail / save_to_database（去重入库）。
    新增：登录态复用(storage_state)、检索入口、主要主题/学术期刊筛选、翻页。

    用法:
        python cnki_paper_captcha.py --search "新质生产力" --show-browser
        python cnki_paper_captcha.py --search "新质生产力" --max-pages 3 --years 2025-2026
    """

    # CNKI 检索页 XPath 选择器
    SEARCH_SELECTOR = '//textarea[@id="txt_SearchText"]'
    # 检索字段下拉：现行首页/检索页（参考 demo.py）
    FIELD_SORT_DEFAULT_SELECTOR = '//div[contains(@class, "sort-default")]'
    FIELD_LIST_SELECTOR = '//div[@id="DBFieldList"]'
    FIELD_LI_SELECTOR = '//div[@id="DBFieldList"]//li'
    # 旧版检索字段下拉（兜底）
    FIELD_SELECTOR = '//dd[@id="searchField"]'
    # 侧边栏筛选容器（搜索结果页左侧分组：主题/学科/年度/研究层次/期刊/文献来源/来源类别/作者/机构/基金/OA出版）
    GROUP_CONTAINER_SELECTOR = '//div[@id="divGroup"]'
    RESULT_TABLE_SELECTOR = '//table[contains(@class, "result-table-list")]'
    NEXT_PAGE_SELECTOR = '//a[@id="PageNext"]'
    TITLE_LINK_SELECTOR = './/a[contains(@class, "fz14")]'
    ROW_LINK_SELECTOR = './/td[1]//a'

    def __init__(self, headless=True, keyword="", search_field="主题", max_pages=None,
                 min_year=None, max_year=None, state_file=None, thread_id=0,
                 urls_only=False, urls_file=None, debug_html=None,
                 search_url=None, search_url_file=None, detail_workers=3,
                 resume=False, refs_with_details=False, ref_max_items=None,
                 ref_detail_max=None):
        super().__init__(headless=headless, thread_id=thread_id,
                         refs_with_details=refs_with_details, ref_max_items=ref_max_items,
                         ref_detail_max=ref_detail_max)
        self.keyword = keyword
        self.search_field = search_field
        self.max_pages = max_pages
        self.min_year = min_year
        self.max_year = max_year
        self.state_file = Path(state_file) if state_file else None
        # 断点续跑：同关键词存在断点时从上次进度继续（详情阶段靠 URL 去重跳过已入库）
        self.resume = resume
        # 只收集 URL 模式（不抓详情入库），并保存到 urls_file
        self.urls_only = urls_only
        self.urls_file = Path(urls_file) if urls_file else CACHE_DIR / 'urls.txt'
        self.search_url = search_url
        # 保存/复用检索结果页 URL（供 --search-url 直接跳转，跳过首页重复检索）
        self.search_url_file = Path(search_url_file) if search_url_file else CACHE_DIR / 'search_url.txt'
        self.debug_html = Path(debug_html) if debug_html else CACHE_DIR / 'debug_page1.html'

        # 详情页并发抓取数（翻页收集仍串行）
        self.detail_workers = max(1, int(detail_workers))
        self.context = None  # init_browser 时保存，供详情并发阶段开 worker tab

    async def init_browser(self):
        """初始化浏览器（支持复用已保存的登录态）。"""
        self.playwright = await async_playwright().start()
        launch_kwargs = _launch_kwargs(self.headless)
        self.browser = await self.playwright.chromium.launch(**launch_kwargs)

        ctx_kwargs = {
            'locale': 'zh-CN',
            'timezone_id': 'Asia/Shanghai',
        }
        if self.state_file and self.state_file.exists():
            ctx_kwargs['storage_state'] = str(self.state_file)
            print(f"  [关键词#{self.thread_id}] 复用登录态: {self.state_file}")

        self.context = await self.browser.new_context(**ctx_kwargs)
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN','zh','en'] });
            window.chrome = { runtime: {} };
        """)
        self.page = await self.context.new_page()
        print(f"  [关键词#{self.thread_id}] 浏览器已启动 (headless={self.headless})")

    async def _fast_forward(self, target_page: int) -> int:
        """断点恢复：从结果页第 1 页连续点「下一页」直达 target_page，返回实际到达的页码。

        知网结果页翻页为 AJAX（URL 不变），只能逐页点击前进；站点结构变化导致
        无法到达目标页时提前停在上 reach 到的页（重复收集的论文由入库去重兜底）。
        """
        cur = await self._current_page_num() or 1
        while cur < target_page:
            if not await self._next_page_exists():
                print(f"  [关键词#{self.thread_id}] 快进翻页时已是末页（第 {cur} 页），停止快进")
                break
            await self._wait_loading_gone()
            await _pacing_wait()
            prev = cur
            try:
                await self.page.locator(self.NEXT_PAGE_SELECTOR).first.evaluate('el => el.click()')
            except Exception:
                try:
                    await self.page.locator(self.NEXT_PAGE_SELECTOR).first.click(force=True, timeout=10000)
                except Exception:
                    pass
            await self._ensure_no_captcha(timeout=120)
            advanced = False
            deadline = asyncio.get_event_loop().time() + 20
            while asyncio.get_event_loop().time() < deadline:
                await self._wait_loading_gone(timeout=5000)
                try:
                    await self.page.locator(self.RESULT_TABLE_SELECTOR).first.wait_for(state='visible', timeout=3000)
                except Exception:
                    continue
                new_cur = await self._current_page_num()
                if new_cur is not None and new_cur > prev:
                    cur = new_cur
                    advanced = True
                    break
                if not await self._next_page_exists():
                    break
                await asyncio.sleep(0.5)
            if not advanced:
                break
        return cur

    async def _ensure_no_captcha(self, timeout: int = 180) -> bool:
        """确保当前无安全验证：委托统一验证码闸 captcha_gate.wait_clean。"""
        return await wait_clean(
            self.page, tag=f"  [关键词#{self.thread_id}]", timeout=timeout,
            headless=self.headless, solver=self.captcha_solver)

    async def _pick_field_filter(self) -> bool:
        """按检索字段在侧边栏筛选(div#divGroup)中做分组匹配并点选。

        检索字段 → 分组：主题→「主题」，作者/第一作者/通讯作者→「作者」，
        作者单位→「机构」，基金→「基金」，文献来源→「文献来源」，分类号→「学科」。
        在对应分组里选出与关键词最匹配的一项并点击；无匹配或无需筛选返回 False。
        """
        tag = f"[关键词#{self.thread_id}]"
        target = SEARCH_FIELD_GROUP_MAP.get((self.search_field or '').strip())
        if not target:
            print(f"{tag} 检索字段「{self.search_field}」无对应侧边栏分组，跳过分组筛选")
            return False

        # 等待侧边栏容器出现后再定位分组（结果页异步渲染，直接定位可能扑空）
        try:
            await self.page.locator(self.GROUP_CONTAINER_SELECTOR).first.wait_for(state='visible', timeout=15000)
        except Exception:
            print(f"{tag} 侧边栏筛选容器(#divGroup)未出现")
            return False

        # 按 groupitem 定位分组 dl（如 主题/作者/机构/基金/文献来源/学科）
        dl = self.page.locator(
            f'{self.GROUP_CONTAINER_SELECTOR}//dl[dt[@groupitem="{target}"]]'
        )
        if await dl.count() == 0:
            print(f"{tag} 未找到侧边栏分组「{target}」")
            return False

        # 分组列表若为空（分组默认折叠、懒加载），点击 dt 标题展开并等待列表加载
        lis = dl.locator('xpath=.//dd//li')
        if await lis.count() == 0:
            try:
                await dl.locator('xpath=.//dt').first.click()
            except Exception:
                pass
            try:
                await lis.first.wait_for(state='visible', timeout=15000)
            except Exception:
                pass
            if await lis.count() == 0:
                print(f"{tag} 分组「{target}」列表未加载")
                return False

        # 一次性批量取所有候选项文本，避免逐项 inner_text 的多次往返
        texts = await lis.evaluate_all(
            """(lis) => lis.map((li) => (li.textContent || '').trim())"""
        )
        best_i, best_score = None, 0
        for i, text in enumerate(texts):
            base = re.split(r"[（(]", text)[0].strip()
            if base == self.keyword:
                score = 100
            elif base in self.keyword or self.keyword in base:
                score = 50
            else:
                score = len(set(base) & set(self.keyword))
            if score > best_score:
                best_i, best_score = i, score
        if best_i is None or best_score <= 0:
            print(f"{tag} 分组「{target}」中没有与关键词匹配的项")
            return False
        try:
            best_li = lis.nth(best_i)
            clickable = best_li.locator('xpath=.//a').first
            if await clickable.count() == 0:
                clickable = best_li
            await clickable.click()
            print(f"{tag} 已在「{target}」分组选中: {texts[best_i][:30]}")
            return True
        except Exception as e:
            print(f"{tag} 点击分组「{target}」项失败: {e}")
            return False

    async def _search_navigation_failed(self, timeout: int = 20) -> bool:
        """判断首页检索触发后的导航是否被风控拦截。

        触发搜索后可能出现三种落点：
        - /verify 验证码页、defaultresult 结果页：正常，返回 False
        - chrome-error（403 被拦）：失败，返回 True，调用方需重试
        超时未明确失败按成功处理（翻页收集阶段会对缺失结果表格兜底）。
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            url = self.page.url
            if 'chrome-error' in url or 'chromewebdata' in url:
                return True
            if 'defaultresult' in url or 'verify' in url:
                return False
            try:
                if await self.page.locator(self.RESULT_TABLE_SELECTOR).first.count() > 0:
                    return False
            except Exception:
                pass
            await asyncio.sleep(1)
        return False

    async def _set_search_field(self) -> bool:
        """设置检索字段（主题/篇关摘/关键词/篇名/作者...）。

        参考 demo.py：悬停展开「检索字段」下拉框（div.sort-default）→ 在
        #DBFieldList 中点击目标字段；旧版 dd#searchField 下拉保留作兜底。
        失败静默回到默认字段（通常为「主题」）。
        """
        target = (self.search_field or '').strip() or '主题'
        if target == '主题':
            return True  # 默认主题无需切换

        # 方案一：现行首页/检索页的检索字段下拉（sort-default + #DBFieldList）
        try:
            cur = ''
            try:
                cur = (await self.page.locator(self.FIELD_SORT_DEFAULT_SELECTOR + '/span').first.inner_text()).strip()
            except Exception:
                pass
            if cur == target:
                return True
            await self.page.locator(self.FIELD_SORT_DEFAULT_SELECTOR).first.hover()
            await self.page.locator(self.FIELD_LIST_SELECTOR).first.wait_for(state='visible', timeout=8000)
            texts = await self.page.locator(self.FIELD_LI_SELECTOR).evaluate_all(
                """(lis) => lis.map((li) => (li.textContent || '').trim())"""
            )
            for i, text in enumerate(texts):
                if text == target:
                    item = self.page.locator(self.FIELD_LI_SELECTOR).nth(i)
                    clickable = item.locator('xpath=.//a').first
                    if await clickable.count() == 0:
                        clickable = item
                    await clickable.click()
                    print(f"  [关键词#{self.thread_id}] 已切换检索字段为: {target}")
                    return True
        except Exception as e:
            print(f"  [关键词#{self.thread_id}] sort-default 下拉切换检索字段失败，尝试旧版选择器: {e}")

        # 方案二：旧版 dd#searchField 下拉（兜底）
        try:
            dd = self.page.locator(self.FIELD_SELECTOR)
            if await dd.count() == 0:
                return False
            await dd.click()
            texts = await dd.locator('xpath=.//li').evaluate_all(
                """(lis) => lis.map((li) => (li.textContent || '').trim())"""
            )
            for text in texts:
                if target in text:
                    await dd.locator('xpath=.//li', has_text=text).first.click()
                    print(f"  [关键词#{self.thread_id}] 已切换检索字段为: {target}")
                    return True
        except Exception:
            pass
        print(f"  [关键词#{self.thread_id}] 未找到检索字段: {target}，保持默认")
        return False

    async def _collect_papers_from_rows(self) -> list:
        """从结果表格收集论文（url + title + 年份信息）。

        用 evaluate_all 在浏览器端一次性批量提取，避免逐行的多次往返通信
        （每调用一次内燃 inner_text / count 都是一次 CDP 往返，是收集阶段的性能热点）。
        """
        loc = self.page.locator(self.RESULT_TABLE_SELECTOR)
        if await loc.count() == 0:
            return []
        raw = await loc.locator('xpath=.//tr').evaluate_all(
            """(rows) => rows.map((row) => {
                const titleA = row.querySelector('a.fz14');
                const fallbackA = row.querySelector('td:first-child a');
                const a = (titleA || fallbackA);
                if (!a) return null;
                const href = a.getAttribute('href') || '';
                const title = (a.textContent || '').trim();
                if (!href || href === 'javascript:void(0)' || !title) return null;
                const ym = (row.textContent || '').match(/(20\\d{2})/);
                const srcA = row.querySelector('.source a, td.source a');
                const journal = srcA ? (srcA.textContent || '').trim() : '';
                return { href, title, year: ym ? Number(ym[1]) : null, journal };
            })"""
        )
        papers = []
        for r in raw:
            if r is None:
                continue
            papers.append({
                'url': urljoin('https://kns.cnki.net/', r['href']),
                'title': r['title'],
                'year': r['year'],
                'journal': r['journal'],
            })
        return papers

    async def _dump_page_html(self):
        """把当前页面 HTML 保存到文件，便于核对真实结构。"""
        try:
            self.debug_html.write_text(await self.page.content(), encoding='utf-8')
            print(f"  [关键词#{self.thread_id}] 已保存页面 HTML 到 {self.debug_html}")
        except Exception as e:
            print(f"  [关键词#{self.thread_id}] 保存调试 HTML 失败: {e}")

    def _within_year_range(self, year) -> bool:
        if not year:
            return True
        if self.min_year is not None and year < self.min_year:
            return False
        if self.max_year is not None and year > self.max_year:
            return False
        return True

    async def _next_page_exists(self) -> bool:
        nxt = self.page.locator(self.NEXT_PAGE_SELECTOR)
        if await nxt.count() == 0:
            return False
        cls = await nxt.first.get_attribute("class") or ""
        return "disabled" not in cls

    async def _current_page_num(self) -> int | None:
        """读取「下一页」按钮上的 data-curpage（当前页码），用于判断翻页是否真的前进。"""
        try:
            nxt = self.page.locator(self.NEXT_PAGE_SELECTOR)
            if await nxt.count() == 0:
                return None
            v = await nxt.first.get_attribute("data-curpage")
            if v is None:
                return None
            return int(v)
        except Exception:
            return None
    async def _wait_loading_gone(self, timeout=30000):
        """等待结果页分页 loading 遮罩（div.divLoading）消失，避免遮挡翻页点击。"""
        try:
            loader = self.page.locator('div.divLoading')
            if await loader.count() > 0:
                await loader.first.wait_for(state='hidden', timeout=timeout)
        except Exception:
            pass

    async def run_search(self):
        """执行关键词检索：搜索 -> 按检索字段做侧边栏分组筛选 -> 翻页收集 -> 详情入库。"""
        tag = f"[关键词#{self.thread_id}]"
        print("=" * 60)
        print(f"{tag} 关键词检索: {self.keyword} (字段: {self.search_field})")
        print(f"{tag} 当前年份区间: {self.min_year or '不限'} ~ {self.max_year or '不限'}, 最大翻页: {self.max_pages or '不限'}")
        print("=" * 60)

        await self.init_browser()
        try:
            # —— 断点恢复：--resume 且断点属于同一关键词时，从上次进度继续 ——
            cp = _load_search_checkpoint() if self.resume else None
            if cp and cp.get('keyword') != self.keyword:
                print(f"{tag} 断点属于其他关键词（{cp.get('keyword')}），忽略并从头执行")
                cp = None
            if not cp:
                _clear_search_checkpoint()
            resumed_papers: list = list(cp.get('papers') or []) if cp else []
            resume_page = int(cp.get('page') or 0) if cp else 0
            resume_phase = cp.get('phase') if cp else None
            resume_url = cp.get('search_url') if cp else None
            if cp:
                print(f"{tag} 检测到断点：phase={resume_phase}，已收集 {len(resumed_papers)} 篇（第 {resume_page} 页，存档 {cp.get('saved_at')}）")
                if resume_url:
                    self.search_url = resume_url  # 复用断点里的检索结果页 URL，跳过首页检索

            if self.search_url:
                # 复用已保存的检索结果页 URL，跳过首页检索/主题/类型筛选
                print(f"{tag} 直接打开已保存的检索结果页: {self.search_url}")
                await _pacing_wait()
                await self.page.goto(self.search_url, wait_until='domcontentloaded', timeout=60000)
                await self._ensure_no_captcha(timeout=180)
                await asyncio.sleep(random.uniform(2, 4))
            else:
                # 1. 打开知网首页（校外经登录态直接进，否则等待手动登录跳回）
                print(f"{tag} 打开知网首页...")
                await _pacing_wait()
                await self.page.goto('https://www.cnki.net/', wait_until='domcontentloaded', timeout=60000)
                for _ in range(90):
                    if 'cnki.net' in self.page.url:
                        break
                    await asyncio.sleep(2)

                # 2. 等待搜索框
                box = self.page.locator(self.SEARCH_SELECTOR)
                await box.wait_for(state='visible', timeout=60000)
                print(f"{tag} 已进入检索页")

                # 保存登录态（供下次复用）
                if self.state_file:
                    try:
                        await self.page.context.storage_state(path=str(self.state_file))
                        print(f"{tag} 登录态已保存: {self.state_file}")
                    except Exception:
                        pass

                # 3. 设置检索字段并输入关键词触发搜索。
                #    知网风控可能以 403 拦截首页表单提交（页面落到 chrome-error）。
                #    直连导航比表单提交稳定（实测直连返回 302→verify 页，可被验证码逻辑处理），
                #    失败时用页面 JS 拼好的检索 URL 直连重试。
                search_ok = False
                nav_url = None

                def _capture_nav_url(req):
                    nonlocal nav_url
                    if 'defaultresult' in req.url and req.method == 'GET':
                        nav_url = req.url

                self.page.on('request', _capture_nav_url)
                try:
                    for attempt in range(1, SEARCH_MAX_RETRIES + 1):
                        await self._set_search_field()
                        await self.random_scroll()
                        await box.click()
                        await box.fill(self.keyword)
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        nav_url = None
                        await box.press('Enter')
                        await self._ensure_no_captcha(timeout=180)
                        if not await self._search_navigation_failed(timeout=20):
                            search_ok = True
                            break
                        print(f"{tag} 搜索请求被风控拦截(403/chrome-error)，第 {attempt}/{SEARCH_MAX_RETRIES} 次重试...")
                        # 短停顿让风控降级后再直连（连续快速重试会持续 403）
                        await asyncio.sleep(random.uniform(5, 9))
                        if nav_url:
                            # 表单提交被拦：改用直连导航（crossids/korder/kw 已由页面 JS 拼好）
                            await _pacing_wait()
                            try:
                                await self.page.goto(nav_url, wait_until='domcontentloaded', timeout=60000)
                                await self._ensure_no_captcha(timeout=180)
                                if not await self._search_navigation_failed(timeout=20):
                                    search_ok = True
                                    break
                            except Exception as e:
                                print(f"{tag} 直连重试失败: {e}")
                        # 回到首页准备下一次尝试
                        await asyncio.sleep(random.uniform(3, 6))
                        await _pacing_wait()
                        try:
                            await self.page.goto('https://www.cnki.net/', wait_until='domcontentloaded', timeout=60000)
                        except Exception:
                            pass
                        box = self.page.locator(self.SEARCH_SELECTOR)
                        try:
                            await box.wait_for(state='visible', timeout=60000)
                        except Exception:
                            pass
                finally:
                    try:
                        self.page.remove_listener('request', _capture_nav_url)
                    except Exception:
                        pass
                if not search_ok:
                    print(f"{tag} 搜索重试 {SEARCH_MAX_RETRIES} 次仍被拦截，放弃本次关键词检索")
                    return

                # 4. 按检索字段做侧边栏分组筛选（主题/作者/机构/基金/文献来源/学科）
                # 点击最匹配的分组项后等待结果刷新（参考 demo 的 zyzt 点击流程）
                if await self._pick_field_filter():
                    try:
                        await self.page.wait_for_load_state('domcontentloaded')
                    except Exception:
                        pass
                    await asyncio.sleep(random.uniform(2.5, 5))

                # 4.5 记录当前检索结果页 URL 到本地，供下次 --search-url 直接复用
                try:
                    self.search_url_file.write_text(self.page.url, encoding='utf-8')
                    print(f"{tag} 已保存检索结果页 URL -> {self.search_url_file}")
                except Exception as e:
                    print(f"{tag} 保存检索 URL 失败: {e}")

            # 5. 翻页收集论文
            all_papers: list = list(resumed_papers)
            # phase=detail：上次在详情入库阶段被中断，收集已完成，直接跳过翻页
            skip_collect = bool(cp and resume_phase == 'detail')
            page_no = 1
            if cp and resume_phase == 'collect' and resume_page > 0:
                # 快进到断点页的下一页（第 1..resume_page 页已收集过）
                reached = await self._fast_forward(resume_page + 1)
                print(f"{tag} 断点快进完成：当前第 {reached} 页")
                page_no = max(1, reached)
            if skip_collect:
                print(f"{tag} 断点恢复：跳过翻页收集，直接进入详情入库（{len(all_papers)} 篇待处理）")
            while not skip_collect:
                await self._ensure_no_captcha(timeout=120)
                try:
                    await self.page.locator(self.RESULT_TABLE_SELECTOR).first.wait_for(state='visible', timeout=30000)
                except Exception:
                    print(f"{tag} 第 {page_no} 页结果表格未出现")
                page_papers = await self._collect_papers_from_rows()
                page_papers = [p for p in page_papers if self._within_year_range(p.get('year'))]
                all_papers.extend(page_papers)
                progress.emit_page_collected(tag, page_no, len(page_papers), len(all_papers))
                # 每页收集完写断点：停止/崩溃后可从下一页续跑
                _save_search_checkpoint({
                    'keyword': self.keyword, 'search_field': self.search_field,
                    'search_url': self.page.url, 'phase': 'collect',
                    'page': page_no, 'papers': all_papers,
                })
                # 首页无内容时 dump 页面 HTML 便于核对真实结构
                if not page_papers and page_no == 1:
                    await self._dump_page_html()

                if self.max_pages is not None and page_no >= self.max_pages:
                    print(f"{tag} 已达到最大翻页数 {self.max_pages}，停止")
                    break
                if not await self._next_page_exists():
                    print(f"{tag} 已是最后一页")
                    break
                # 翻页：等 loading 遮罩消失后「单击」下一页（JS 点击优先，失败才用 force 兜底；
                # 不能两种点击都执行——双击会把分页器状态点乱，导致页码误判提前停止）
                await self._wait_loading_gone()
                await _pacing_wait()
                prev_cur = await self._current_page_num()
                click_ok = False
                try:
                    await self.page.locator(self.NEXT_PAGE_SELECTOR).first.evaluate('el => el.click()')
                    click_ok = True
                except Exception:
                    try:
                        await self.page.locator(self.NEXT_PAGE_SELECTOR).first.click(force=True, timeout=10000)
                        click_ok = True
                    except Exception:
                        click_ok = False
                if not click_ok:
                    print(f"{tag} 「下一页」点击失败（元素脱离/被遮挡），等待页面稳定后判断")
                await self._ensure_no_captcha(timeout=120)

                # 等翻页真正完成：loading 消失 + 结果表格重新可见 + 页码前进（最多 20 秒）
                advanced = False
                deadline = asyncio.get_event_loop().time() + 20
                while asyncio.get_event_loop().time() < deadline:
                    await self._wait_loading_gone(timeout=5000)
                    try:
                        await self.page.locator(self.RESULT_TABLE_SELECTOR).first.wait_for(state='visible', timeout=3000)
                    except Exception:
                        continue  # 结果表格还没重绘完，继续等
                    new_cur = await self._current_page_num()
                    if new_cur is not None and prev_cur is not None and new_cur > prev_cur:
                        advanced = True
                        break
                    if not await self._next_page_exists():
                        break  # 页面稳定后按钮已消失 → 翻到了真正的末页
                    await asyncio.sleep(0.5)

                if not advanced:
                    # 首要停止条件：下一页按钮不存在
                    if not await self._next_page_exists():
                        print(f"{tag} 下一页按钮不存在，已是最后一页")
                        break
                    # 按钮还在但页码未前进：复核一次，仍未前进才视为末页
                    await asyncio.sleep(2)
                    new_cur = await self._current_page_num()
                    if new_cur is not None and prev_cur is not None and new_cur <= prev_cur:
                        print(f"{tag} 翻页后页码未前进（{prev_cur} -> {new_cur}），视为已到末页，停止")
                        break
                page_no += 1

            progress.emit_collected_total(tag, len(all_papers))

            # —— 分支：只收集 URL vs 抓详情入库 ——
            if self.urls_only:
                hrefs = [p.get('url') for p in all_papers if p.get('url')]
                try:
                    self.urls_file.write_text("\n".join(hrefs), encoding='utf-8')
                    print(f"{tag} 已写入 {len(hrefs)} 条 URL 到 {self.urls_file}")
                except Exception as e:
                    print(f"{tag} 写入 URL 文件失败: {e}")
                return

            # 并发获取详情并入库（含去重，见 crawl_paper_detail）：
            # 翻页收集必须串行（同一结果页），详情抓取用 detail_workers 个 tab 并行
            # 先批量预取库中已有 URL，跳过已入库论文（逐篇检查仍保留作安全网）
            # 详情阶段断点：中断后恢复时跳过翻页收集，直接对本列表续抓（已入库 URL 会被跳过）
            _save_search_checkpoint({
                'keyword': self.keyword, 'search_field': self.search_field,
                'search_url': self.page.url, 'phase': 'detail',
                'page': page_no, 'papers': all_papers,
            })
            existing_urls = await self._db_existing_urls()
            queue = asyncio.Queue()
            skipped = 0
            for p in all_papers:
                if p.get('url') in existing_urls:
                    skipped += 1
                    continue
                queue.put_nowait(p)
            total = queue.qsize()
            done = 0
            ok = 0
            stats = {'already_exists': skipped, 'filtered': 0, 'verify_failed': 0, 'failed': 0}

            async def detail_worker(wid: int):
                nonlocal done, ok
                wtag = f"{tag}[W{wid}]"
                page = await self.context.new_page()
                try:
                    while True:
                        try:
                            paper = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            return
                        done += 1
                        print(f"{wtag} [{done}/{total}] 处理: {paper['title'][:30]}...")
                        res = await self.crawl_paper_detail(paper, page=page)
                        if res and res.get('title'):
                            ok += 1
                        else:
                            reason = res.get('error', 'failed') if res else 'failed'
                            if reason == 'already_exists':
                                stats['already_exists'] += 1
                            elif reason == 'verify_page':
                                stats['verify_failed'] += 1
                            elif reason == 'filtered_non_paper':
                                stats['filtered'] += 1
                            else:
                                stats['failed'] += 1
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                finally:
                    try:
                        await page.close()
                    except Exception:
                        pass

            n = max(1, self.detail_workers)
            progress.emit_detail_concurrency(tag, n, total, skipped)
            await asyncio.gather(*[detail_worker(i) for i in range(n)])

            progress.emit_detail_summary(tag, ok, total, stats['already_exists'],
                                         stats['filtered'], stats['verify_failed'], stats['failed'])
            if getattr(self, '_refs_done', 0) or getattr(self, '_refs_failed', 0):
                progress.emit_refs_detail_summary(tag, getattr(self, '_refs_done', 0),
                                                  getattr(self, '_refs_failed', 0))
            _clear_search_checkpoint()
            print(f"{tag} 断点已清除")
        except Exception as e:
            print(f"{tag} 检索流程异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.close_browser()


class ReferenceCrawler(KeywordSearchCrawler):
    """参考文献爬取：给定论文详情页链接（可批量）或论文标题，进入详情页抓取参考文献列表条目。

    抓取/翻页/入库复用 JournalCrawler 上的共享实现（_open_references_tab /
    _crawl_references / _save_references 等，页面结构与防风控节奏见其 REF_* 常量）。
    列表条目（文本+链接）按 paper_url 覆盖式写入论文行的 references_cn。

    列表抓完后继续抓**每条参考文献自身的详情**并入库 papers 表（_crawl_reference_details）：
    复用详情页的加载与解析代码，但不再往下递归（不抓参考文献的参考文献）；本地库已有的
    （URL 或标题命中）不打开详情页；条目原文解析不出年份的跳过，避免老文献因 published_at
    落到今年而霸占发现流。可用 --ref-no-details 关闭、--ref-detail-max 限制每篇条数。

    防风控：详情页导航与翻页请求都计入节奏——篇间隔默认 6s（随机上浮，--ref-interval
    可调）、每条详情前再随机停 2~4.5s 并过全局导航闸；触发验证码多时调大 --ref-interval
    或 --show-browser 人工配合。

    用法:
        python cnki_paper_captcha.py --ref-paper-url "https://kns.cnki.net/..."
        python cnki_paper_captcha.py --ref-urls-file .cache/urls.txt
        python cnki_paper_captcha.py --ref-title "论文标题" --ref-max-items 100
        python cnki_paper_captcha.py --ref-paper-url "..." --ref-detail-max 2   # 小批量试跑
    """


    def __init__(self, headless=True, thread_id=0, state_file=None,
                 paper_urls=None, paper_title=None, max_items=None, interval=6.0,
                 crawl_ref_details=True, ref_detail_max=None):
        super().__init__(headless=headless, thread_id=thread_id, state_file=state_file,
                         ref_detail_max=ref_detail_max)
        self.paper_urls = list(paper_urls or [])
        self.paper_title = (paper_title or '').strip()
        self.max_items = max_items
        self.ref_interval = max(1.0, float(interval))
        # 列表抓完后是否继续抓每条参考文献的详情并入库（默认开启）
        self.crawl_ref_details = crawl_ref_details

    async def run(self):
        tag = f"[参考文献#{self.thread_id}]"
        print("=" * 60)
        print(f"{tag} 参考文献爬取: {len(self.paper_urls)} 个链接"
              + (f" + 标题「{self.paper_title}」" if self.paper_title else "")
              + f" | 篇间隔 {self.ref_interval}s（防风控）")
        print("=" * 60)

        # 组装任务：URL 直接打开；标题先检索定位（默认取第一条结果）
        tasks = [{'paper_url': u, 'paper_title': ''} for u in self.paper_urls]
        if self.paper_title:
            tasks.append({'paper_url': None, 'paper_title': self.paper_title})
        if not tasks:
            print(f"{tag} 未提供论文链接/标题，退出")
            return

        await self.init_browser()
        total_refs = 0
        ok_papers = 0
        total_detail_stats: dict = {}
        try:
            for i, task in enumerate(tasks, 1):
                paper_url = task['paper_url']
                paper_title = task['paper_title']
                print(f"\n{tag} [{i}/{len(tasks)}] 处理论文: {paper_title or paper_url[:70]}")
                try:
                    # —— 定位论文详情页 ——
                    if not paper_url:
                        located = await self._locate_paper_by_title(tag)
                        if not located:
                            print(f"{tag} 未能在检索结果中定位到论文，跳过")
                            continue
                        paper_url, paper_title = located
                    else:
                        print(f"{tag} 直接打开论文详情页: {paper_url}")

                    await _pacing_wait()
                    await self.page.goto(paper_url, wait_until='domcontentloaded', timeout=60000)
                    if not await self.wait_for_page_stable(paper_url):
                        print(f"{tag} ✗ 详情页遇到安全验证且未通过，跳过")
                        continue
                    await self._ensure_no_captcha(timeout=120)
                    # 模拟真人浏览：先随机滚动再点页签，降低风控敏感度
                    await self.random_scroll()
                    await asyncio.sleep(random.uniform(MIN_DETAIL_DELAY, MAX_DETAIL_DELAY))

                    # URL 入口时从详情页提取标题（标题入口在检索阶段已拿到）
                    if not paper_title:
                        try:
                            paper_title = (await self.page.locator('div.doc h1, h1')
                                           .first.inner_text(timeout=8000)).strip()
                        except Exception:
                            paper_title = ''

                    refs = await self._crawl_references(tag)
                    if not refs:
                        print(f"{tag} 未抓到参考文献（详情页可能没有参考文献区块）")
                        continue
                    if self.max_items and len(refs) > self.max_items:
                        print(f"{tag} 超过上限 {self.max_items} 条，截断")
                        refs = refs[:self.max_items]

                    print(f"{tag} 完成：共抓取参考文献 {len(refs)} 条，前 3 条预览：")
                    for r in refs[:3]:
                        print(f"{tag}   - {r['text'][:70]}")
                    await self._save_references(paper_url, paper_title, refs)
                    total_refs += len(refs)
                    ok_papers += 1
                    # 继续抓每条参考文献自身的详情并入库（失败/中止只记日志，不影响已入库的列表）
                    if self.crawl_ref_details:
                        detail_stats = await self._crawl_reference_details(refs, tag)
                        for k, v in detail_stats.items():
                            total_detail_stats[k] = total_detail_stats.get(k, 0) + v
                except Exception as e:
                    print(f"{tag} 处理论文异常: {e}")
                    import traceback
                    traceback.print_exc()
                # 篇间退避：详情页导航频率是触发风控的主因，宁慢勿封
                if i < len(tasks):
                    gap = random.uniform(self.ref_interval, self.ref_interval * 1.8)
                    print(f"{tag} 停 {gap:.1f}s 再处理下一篇（防风控）")
                    await asyncio.sleep(gap)
        finally:
            await self.close_browser()

        print(f"\n{tag} {'=' * 60}")
        progress.emit_refs_all_done(tag, ok_papers, len(tasks), total_refs)
        if total_detail_stats:
            print(f"{tag} 参考文献详情累计：入库 {total_detail_stats.get('saved', 0)} 篇，"
                  f"本地已有跳过 {total_detail_stats.get('dup_local', 0)} 条，"
                  f"著录不全 {total_detail_stats.get('incomplete', 0)} 条，"
                  f"年份缺失 {total_detail_stats.get('no_year', 0)} 条，"
                  f"失败 {total_detail_stats.get('failed', 0)} 条")
        print(f"{tag} {'=' * 60}")

    async def _locate_paper_by_title(self, tag: str):
        """按论文标题搜索知网并定位详情页：默认取第一条结果，其余候选打印到日志供人工核对。"""
        print(f"{tag} 按标题检索: {self.paper_title}")
        await _pacing_wait()
        await self.page.goto('https://www.cnki.net/', wait_until='domcontentloaded', timeout=60000)
        for _ in range(90):
            if 'cnki.net' in self.page.url:
                break
            await asyncio.sleep(2)
        box = self.page.locator(self.SEARCH_SELECTOR).first
        await box.wait_for(state='visible', timeout=60000)
        # 检索触发可能被风控以 403 拦截（页面落到 chrome-error）：退避重试，
        # 策略与关键词检索流程一致（重试间回首页、过全局导航闸）
        nav_ok = False
        for attempt in range(1, SEARCH_MAX_RETRIES + 1):
            await self.random_scroll()
            await box.click()
            await box.fill(self.paper_title)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await box.press('Enter')
            await self._ensure_no_captcha(timeout=180)
            if not await self._search_navigation_failed(timeout=20):
                nav_ok = True
                break
            print(f"{tag} 检索被风控拦截（第 {attempt}/{SEARCH_MAX_RETRIES} 次），退避后重试...")
            await asyncio.sleep(random.uniform(5, 9))
            try:
                await _pacing_wait()
                await self.page.goto('https://www.cnki.net/', wait_until='domcontentloaded', timeout=60000)
                box = self.page.locator(self.SEARCH_SELECTOR).first
                await box.wait_for(state='visible', timeout=60000)
            except Exception as e:
                print(f"{tag} 回首页准备重试失败: {e}")
                return None
        if not nav_ok:
            print(f"{tag} 检索连续 {SEARCH_MAX_RETRIES} 次被风控拦截，退出")
            return None

        # 事件驱动等检索结果表渲染（站点反应快慢不一，固定 sleep 会拿到空结果）
        try:
            await self.page.locator(self.RESULT_TABLE_SELECTOR).first.wait_for(
                state='visible', timeout=30000)
        except Exception:
            print(f"{tag} 等待检索结果表 30s 未出现，进入兜底重试")

        # 结果可能懒加载：多轮重试收集，仍为空才放弃并落调试 HTML 供核对
        candidates: list = []
        for attempt in range(4):
            candidates = await self._collect_papers_from_rows()
            if candidates:
                break
            if attempt < 3:
                print(f"{tag} 第 {attempt + 1} 次未取到结果，等待页面加载后重试...")
                await asyncio.sleep(random.uniform(2.5, 4))
        if not candidates:
            print(f"{tag} 检索结果为空，已保存页面 HTML 供核对")
            await self._dump_page_html()
            return None
        print(f"{tag} 检索到 {len(candidates)} 条候选，前 5 条：")
        for i, c in enumerate(candidates[:5]):
            print(f"{tag}   [{i + 1}] {c['title'][:60]} ({c.get('journal', '')} {c.get('year') or ''})")
        first = candidates[0]
        print(f"{tag} 默认取第 1 条: {first['title'][:60]}")
        return first['url'], first['title']

