"""
CNKI (中国知网) 爬虫模块 - 使用 DrissionPage
爬取经济学TOP50期刊2025年至今的论文
"""

import asyncio
import random
import time
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from abc import ABC, abstractmethod
from functools import wraps

from DrissionPage import ChromiumOptions, Chromium
from bs4 import BeautifulSoup

from app.fetchers import EconomicsJournalFetcher, retry_on_failure

logger = logging.getLogger(__name__)


# 经济学TOP50期刊配置
CNKI_TOP50_JOURNALS = {
    # 顶级期刊
    "经济研究": {"code": "YJYA", "priority": 1.0},
    "管理世界": {"code": "GLSJ", "priority": 0.95},
    "经济学（季刊）": {"code": "JJXJ", "priority": 0.95},
    "世界经济": {"code": "SJJJ", "priority": 0.9},
    "中国工业经济": {"code": "GYJJ", "priority": 0.9},
    "中国社会科学": {"code": "ZSHK", "priority": 0.95},
    "金融研究": {"code": "JRYJ", "priority": 0.9},
    "数量经济技术经济研究": {"code": "SLJS", "priority": 0.85},
    
    # 重要期刊
    "财贸经济": {"code": "CMJJ", "priority": 0.85},
    "中国农村经济": {"code": "ZCNC", "priority": 0.85},
    "经济学动态": {"code": "JJXD", "priority": 0.8},
    "国际经济评论": {"code": "GJJP", "priority": 0.8},
    "改革": {"code": "GAIG", "priority": 0.8},
    "中国人口科学": {"code": "ZRKX", "priority": 0.8},
    "农业经济问题": {"code": "NYWT", "priority": 0.8},
    "中国农村观察": {"code": "ZCGC", "priority": 0.8},
    "财政研究": {"code": "CZYJ", "priority": 0.8},
    "税务研究": {"code": "SWYJ", "priority": 0.8},
    "会计研究": {"code": "KJYJ", "priority": 0.8},
    "审计研究": {"code": "SJYJ", "priority": 0.8},
    
    # 国际贸易与世界经济
    "国际贸易问题": {"code": "GMWT", "priority": 0.75},
    "国际经贸探索": {"code": "GJMT", "priority": 0.75},
    "世界经济研究": {"code": "SJYJ", "priority": 0.75},
    "经济社会体制比较": {"code": "SHTJ", "priority": 0.75},
    
    # 综合性经济期刊
    "经济学家": {"code": "JJXJ", "priority": 0.75},
    "经济科学": {"code": "JJKX", "priority": 0.75},
    "经济理论与经济管理": {"code": "LLJG", "priority": 0.75},
    "南开经济研究": {"code": "NKJJ", "priority": 0.75},
    "当代经济科学": {"code": "DDKX", "priority": 0.7},
    "当代经济研究": {"code": "DDYJ", "priority": 0.7},
    
    # 财经类期刊
    "财经科学": {"code": "CJKX", "priority": 0.7},
    "财经问题研究": {"code": "CJWT", "priority": 0.7},
    "上海经济研究": {"code": "SHYJ", "priority": 0.7},
    "经济纵横": {"code": "JJZH", "priority": 0.7},
    "经济问题探索": {"code": "WTTS", "priority": 0.7},
    "经济问题": {"code": "JJWT", "priority": 0.7},
    "经济经纬": {"code": "JJJW", "priority": 0.7},
    "经济评论": {"code": "JJPL", "priority": 0.7},
    
    # 区域经济和产业经济
    "经济导刊": {"code": "JJDK", "priority": 0.65},
    "经济研究参考": {"code": "YJCK", "priority": 0.65},
    "经济研究导刊": {"code": "YJDK", "priority": 0.65},
    "经济师": {"code": "JJSH", "priority": 0.6},
    "经济界": {"code": "JJJI", "priority": 0.6},
    "经济视角": {"code": "JJSJ", "priority": 0.6},
    "经济论坛": {"code": "JJLT", "priority": 0.6},
    "经济工作导刊": {"code": "GZDK", "priority": 0.6},
    "经济师论坛": {"code": "JSLT", "priority": 0.55},
    "经济学家论坛": {"code": "JJLT", "priority": 0.55},
    "经济学消息报": {"code": "XXB", "priority": 0.5},
}


@dataclass
class PaperInfo:
    """论文信息数据类"""
    title: str
    authors: List[str]
    abstract: str
    keywords: List[str]
    journal: str
    year: int
    issue: str
    doi: Optional[str] = None
    url: Optional[str] = None
    citations: int = 0
    downloads: int = 0


class DrissionPageBase:
    """DrissionPage 基础封装类"""
    
    def __init__(self, headless: bool = False, use_system_user: bool = True):
        self.headless = headless
        self.use_system_user = use_system_user
        self.browser = None
        self.tab = None
        self._init_browser()
    
    def _init_browser(self):
        """初始化浏览器"""
        try:
            co = ChromiumOptions()
            
            # 设置无头模式
            if self.headless:
                co.headless(True)
            
            # 使用系统浏览器配置（保持登录状态）
            if self.use_system_user:
                co.use_system_user_path()
            
            # 设置 User-Agent
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
            ]
            co.set_user_agent(random.choice(user_agents))
            
            # 设置窗口大小
            co.set_argument("--window-size", f"{random.randint(1200, 1400)},{random.randint(800, 900)}")
            
            # 禁用自动化检测
            co.set_argument("--disable-blink-features", "AutomationControlled")
            co.set_argument("--disable-web-security")
            co.set_argument("--disable-features", "IsolateOrigins,site-per-process")
            
            # 初始化浏览器
            self.browser = Chromium(co)
            self.tab = self.browser.latest_tab
            
            logger.info("DrissionPage browser initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize DrissionPage browser: {e}")
            raise
    
    def check_captcha(self) -> bool:
        """检测当前页面是否有验证码"""
        try:
            # 常见的验证码标识
            captcha_indicators = [
                "验证码",
                "captcha",
                "验证",
                "verification",
                "安全验证",
                "请点击",
                "拖动滑块",
            ]
            
            page_text = self.tab.html.lower()
            
            for indicator in captcha_indicators:
                if indicator in page_text:
                    return True
            
            # 检查特定的验证码元素
            captcha_selectors = [
                'img[src*="captcha"]',
                'img[src*="verify"]',
                '.captcha',
                '#captcha',
                '[class*="captcha"]',
                '[id*="captcha"]',
                '.verify-code',
                '#verify-code',
            ]
            
            for selector in captcha_selectors:
                try:
                    if self.tab.ele(selector, timeout=1):
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking captcha: {e}")
            return False
    
    def handle_captcha(self, timeout: int = 300):
        """处理验证码 - 提示用户手动完成"""
        if not self.check_captcha():
            return True
        
        logger.warning("=" * 60)
        logger.warning("检测到验证码！请手动完成验证")
        logger.warning(f"请在浏览器中完成验证码，超时时间: {timeout}秒")
        logger.warning("=" * 60)
        
        # 在浏览器中显示提示（如果浏览器可见）
        try:
            js_code = """
            var div = document.createElement('div');
            div.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#ff6b6b;color:white;padding:20px;border-radius:10px;z-index:99999;font-size:16px;font-weight:bold;box-shadow:0 4px 12px rgba(0,0,0,0.3);';
            div.innerHTML = '【爬虫提示】请手动完成验证码验证，完成后等待自动继续...';
            document.body.appendChild(div);
            """
            self.tab.run_js(js_code)
        except:
            pass
        
        # 等待用户完成验证码
        start_time = time.time()
        check_interval = 3
        
        while time.time() - start_time < timeout:
            time.sleep(check_interval)
            
            if not self.check_captcha():
                logger.info("验证码已通过，继续爬取")
                return True
            
            remaining = int(timeout - (time.time() - start_time))
            if remaining % 30 == 0:  # 每30秒提醒一次
                logger.info(f"等待验证码完成... 剩余时间: {remaining}秒")
        
        logger.error("验证码处理超时")
        return False
    
    def wait_for_page_load(self, timeout: int = 30):
        """等待页面加载完成"""
        try:
            self.tab.wait.doc_loaded(timeout=timeout)
            # 额外等待确保动态内容加载
            time.sleep(random.uniform(2, 4))
            return True
        except Exception as e:
            logger.error(f"Page load timeout: {e}")
            return False
    
    def random_delay(self, min_seconds: float = 3.0, max_seconds: float = 8.0):
        """随机延迟，避免反爬"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    def close(self):
        """关闭浏览器"""
        try:
            if self.browser:
                self.browser.quit()
                logger.info("Browser closed")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class CNKIDrissionFetcher(EconomicsJournalFetcher):
    """
    CNKI 知网爬虫 - 使用 DrissionPage
    爬取经济学TOP50期刊2025年至今的论文
    """
    
    # 知网期刊导航URL模板
    CNKI_JOURNAL_URL = "https://navi.cnki.net/knavi/journals/index"
    CNKI_SEARCH_URL = "https://kns.cnki.net/kns8/defaultresult/index"
    
    def __init__(self, journal_name: str, headless: bool = False):
        super().__init__(journal_name)
        self.headless = headless
        self.drission = None
        self.journal_config = CNKI_TOP50_JOURNALS.get(journal_name, {})
        self.journal_code = self.journal_config.get("code", "")
        self.priority = self.journal_config.get("priority", 0.6)
    
    def _init_drission(self):
        """初始化 DrissionPage"""
        if not self.drission:
            self.drission = DrissionPageBase(headless=self.headless)
    
    def _close_drission(self):
        """关闭 DrissionPage"""
        if self.drission:
            self.drission.close()
            self.drission = None
    
    def _build_journal_url(self, year: int, issue: int) -> str:
        """
        构建期刊页面URL
        知网期刊导航URL格式
        """
        # 使用知网期刊导航搜索
        base_url = "https://navi.cnki.net/knavi/journals/index"
        
        # 构建搜索参数
        params = {
            "uniplatform": "NZKPT",
            "kw": self.journal_name,
        }
        
        import urllib.parse
        query_string = urllib.parse.urlencode(params)
        return f"{base_url}?{query_string}"
    
    def _build_search_url(self, year: int, issue: Optional[int] = None) -> str:
        """
        构建知网高级搜索URL
        通过文献来源搜索特定期刊的论文
        """
        # 知网高级搜索URL
        base_url = "https://kns.cnki.net/kns8/defaultresult/index"
        
        # 构建查询参数
        query_parts = []
        
        # 期刊名称
        if self.journal_name:
            query_parts.append(f"LY='{self.journal_name}'")
        
        # 年份范围（2025年至今）
        query_parts.append(f"YE>={year}")
        
        # 期号
        if issue:
            query_parts.append(f"QI={issue}")
        
        # 学科领域 - 经济与管理科学
        query_parts.append("CLC=E")
        
        query = " AND ".join(query_parts)
        
        import urllib.parse
        params = {
            "kw": query,
            "korder": "SU",
            "uniplatform": "NZKPT",
        }
        
        query_string = urllib.parse.urlencode(params)
        return f"{base_url}?{query_string}"
    
    def _extract_papers_from_search_page(self) -> List[Dict[str, Any]]:
        """
        从知网搜索结果页面提取论文列表
        """
        papers = []
        
        try:
            # 等待搜索结果加载
            self.drission.tab.wait.ele_displayed("css:.result-table-list", timeout=15)
            
            # 获取所有论文行
            rows = self.drission.tab.eles("css:.result-table-list tbody tr")
            
            logger.info(f"Found {len(rows)} papers on current page")
            
            for row in rows:
                try:
                    # 提取标题
                    title_elem = row.ele("css:.name a", timeout=1)
                    title = title_elem.text if title_elem else ""
                    paper_url = title_elem.attr("href") if title_elem else ""
                    
                    # 提取作者
                    author_elem = row.ele("css:.author", timeout=1)
                    authors_text = author_elem.text if author_elem else ""
                    authors = [a.strip() for a in authors_text.replace("；", ";").split(";") if a.strip()]
                    
                    # 提取来源（期刊）
                    source_elem = row.ele("css:.source", timeout=1)
                    source = source_elem.text if source_elem else self.journal_name
                    
                    # 提取发表时间
                    date_elem = row.ele("css:.date", timeout=1)
                    date_text = date_elem.text if date_elem else ""
                    
                    # 提取被引次数
                    cite_elem = row.ele("css:.cite", timeout=1)
                    citations = 0
                    if cite_elem:
                        cite_text = cite_elem.text.replace("被引：", "").strip()
                        try:
                            citations = int(cite_text) if cite_text else 0
                        except:
                            pass
                    
                    # 提取下载次数
                    download_elem = row.ele("css:.download", timeout=1)
                    downloads = 0
                    if download_elem:
                        download_text = download_elem.text.replace("下载：", "").strip()
                        try:
                            downloads = int(download_text) if download_text else 0
                        except:
                            pass
                    
                    if title:
                        paper_info = {
                            "title": title,
                            "authors": authors,
                            "journal": source,
                            "date_text": date_text,
                            "citations": citations,
                            "downloads": downloads,
                            "url": paper_url,
                        }
                        papers.append(paper_info)
                        
                except Exception as e:
                    logger.error(f"Error parsing paper row: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting papers from search page: {e}")
        
        return papers
    
    def _extract_paper_detail(self, paper_url: str) -> Dict[str, Any]:
        """
        提取论文详情页的详细信息
        """
        detail = {
            "abstract": "",
            "keywords": [],
            "doi": "",
            "year": None,
            "issue": "",
        }
        
        try:
            # 访问详情页
            if not paper_url.startswith("http"):
                paper_url = f"https://kns.cnki.net{paper_url}"
            
            self.drission.tab.get(paper_url)
            self.drission.wait_for_page_load()
            
            # 检查验证码
            if not self.drission.handle_captcha():
                logger.warning("Captcha handling failed, skipping paper detail")
                return detail
            
            # 提取摘要
            try:
                abstract_elem = self.drission.tab.ele("css:.abstract-text, .abstract p, [class*='abstract']", timeout=3)
                if abstract_elem:
                    detail["abstract"] = abstract_elem.text.strip()
            except:
                pass
            
            # 提取关键词
            try:
                keyword_elems = self.drission.tab.eles("css:.keywords a, .keyword a, [class*='keyword'] a", timeout=3)
                keywords = []
                for elem in keyword_elems:
                    kw = elem.text.strip()
                    if kw:
                        keywords.append(kw)
                detail["keywords"] = keywords
            except:
                pass
            
            # 提取DOI
            try:
                doi_elem = self.drission.tab.ele("css:.doi, [class*='doi']", timeout=2)
                if doi_elem:
                    doi_text = doi_elem.text
                    if "DOI" in doi_text.upper():
                        detail["doi"] = doi_text.replace("DOI:", "").replace("DOI：", "").strip()
            except:
                pass
            
            # 提取年份和期号
            try:
                # 从页面文本中提取年份和期号
                page_text = self.drission.tab.text
                import re
                
                # 匹配年份
                year_match = re.search(r'(20\d{2})年', page_text)
                if year_match:
                    detail["year"] = int(year_match.group(1))
                
                # 匹配期号
                issue_match = re.search(r'第(\d+)期', page_text)
                if issue_match:
                    detail["issue"] = issue_match.group(1)
            except:
                pass
            
        except Exception as e:
            logger.error(f"Error extracting paper detail from {paper_url}: {e}")
        
        return detail
    
    def _has_next_page(self) -> bool:
        """检查是否有下一页"""
        try:
            next_btn = self.drission.tab.ele("css:.next, .next-page, [class*='next']", timeout=2)
            if next_btn:
                # 检查是否禁用
                class_attr = next_btn.attr("class") or ""
                if "disabled" in class_attr or "disable" in class_attr:
                    return False
                return True
        except:
            pass
        return False
    
    def _go_to_next_page(self):
        """跳转到下一页"""
        try:
            next_btn = self.drission.tab.ele("css:.next, .next-page", timeout=3)
            if next_btn:
                next_btn.click()
                self.drission.random_delay(3, 6)
                self.drission.wait_for_page_load()
                return True
        except Exception as e:
            logger.error(f"Error going to next page: {e}")
        return False
    
    @retry_on_failure(max_retries=3, delay=3.0)
    async def fetch_papers(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        从知网爬取指定期刊的论文
        
        Args:
            start_date: 开始日期，用于过滤
            end_date: 结束日期，用于过滤
            max_results: 最大返回结果数
            
        Returns:
            论文列表，每个论文为字典格式
        """
        logger.info(f"Fetching papers from CNKI - Journal: {self.journal_name}, max_results: {max_results}")
        
        # 默认2025年至今
        if not start_date:
            start_date = datetime(2025, 1, 1)
        if not end_date:
            end_date = datetime.now()
        
        papers = []
        
        try:
            # 初始化 DrissionPage
            self._init_drission()
            
            # 构建搜索URL
            search_url = self._build_search_url(start_date.year)
            logger.info(f"Opening search URL: {search_url}")
            
            # 打开搜索页面
            self.drission.tab.get(search_url)
            self.drission.wait_for_page_load()
            
            # 检查验证码
            if not self.drission.handle_captcha():
                logger.error("Failed to handle captcha on initial page")
                return papers
            
            page_num = 1
            max_pages = 10  # 最多爬取10页
            
            while len(papers) < max_results and page_num <= max_pages:
                logger.info(f"Processing page {page_num}...")
                
                # 提取当前页面的论文
                page_papers = self._extract_papers_from_search_page()
                
                if not page_papers:
                    logger.info("No more papers found on this page")
                    break
                
                # 处理每篇论文
                for paper_info in page_papers:
                    if len(papers) >= max_results:
                        break
                    
                    try:
                        # 获取论文详情
                        if paper_info.get("url"):
                            detail = self._extract_paper_detail(paper_info["url"])
                            paper_info.update(detail)
                        
                        # 解析日期
                        published_date = self._parse_date(paper_info.get("date_text", ""))
                        
                        # 日期过滤
                        if published_date:
                            if start_date and published_date < start_date:
                                continue
                            if end_date and published_date > end_date:
                                continue
                        
                        # 构建标准格式的论文数据
                        paper_data = self._generate_paper_data(
                            title=paper_info.get("title", ""),
                            abstract=paper_info.get("abstract", ""),
                            authors=paper_info.get("authors", []),
                            published_date=published_date or datetime.now(),
                            doi=paper_info.get("doi") or None,
                            keywords=paper_info.get("keywords", []),
                            issue=paper_info.get("issue", "")
                        )
                        
                        # 添加额外信息
                        paper_data["url"] = paper_info.get("url", "")
                        paper_data["citations"] = paper_info.get("citations", 0)
                        paper_data["downloads"] = paper_info.get("downloads", 0)
                        paper_data["source"] = "cnki"
                        paper_data["journal_name"] = self.journal_name
                        
                        papers.append(paper_data)
                        logger.info(f"Added paper: {paper_info.get('title', '')[:50]}...")
                        
                        # 随机延迟
                        self.drission.random_delay(3, 6)
                        
                    except Exception as e:
                        logger.error(f"Error processing paper: {e}")
                        continue
                
                # 检查是否有下一页
                if not self._has_next_page():
                    logger.info("No more pages")
                    break
                
                # 跳转到下一页
                if not self._go_to_next_page():
                    break
                
                # 检查验证码
                if not self.drission.handle_captcha():
                    logger.error("Failed to handle captcha on next page")
                    break
                
                page_num += 1
            
            logger.info(f"Successfully fetched {len(papers)} papers from CNKI - {self.journal_name}")
            
        except Exception as e:
            logger.error(f"Error fetching papers from CNKI: {e}")
        
        finally:
            self._close_drission()
        
        return papers[:max_results]
    
    def _parse_date(self, date_text: str) -> Optional[datetime]:
        """解析日期文本"""
        if not date_text:
            return None
        
        import re
        
        # 尝试匹配各种日期格式
        patterns = [
            r'(\d{4})-(\d{1,2})-(\d{1,2})',
            r'(\d{4})年(\d{1,2})月(\d{1,2})日',
            r'(\d{4})年(\d{1,2})月',
            r'(\d{4})-(\d{1,2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, date_text)
            if match:
                groups = match.groups()
                try:
                    year = int(groups[0])
                    month = int(groups[1]) if len(groups) > 1 else 1
                    day = int(groups[2]) if len(groups) > 2 else 1
                    return datetime(year, month, day)
                except:
                    pass
        
        return None


class CNKITop50BatchFetcher:
    """
    CNKI TOP50 期刊批量爬取器
    """
    
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.journals = CNKI_TOP50_JOURNALS
    
    async def fetch_all_journals(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_results_per_journal: int = 20,
        max_journals: Optional[int] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        批量爬取多个期刊的论文
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            max_results_per_journal: 每个期刊最大爬取数量
            max_journals: 最大爬取期刊数量（None表示全部）
            
        Returns:
            按期刊名分类的论文字典
        """
        results = {}
        
        # 按优先级排序期刊
        sorted_journals = sorted(
            self.journals.items(),
            key=lambda x: x[1].get("priority", 0),
            reverse=True
        )
        
        if max_journals:
            sorted_journals = sorted_journals[:max_journals]
        
        logger.info(f"Starting batch fetch for {len(sorted_journals)} journals")
        
        for journal_name, config in sorted_journals:
            try:
                logger.info(f"Fetching journal: {journal_name}")
                
                fetcher = CNKIDrissionFetcher(journal_name, headless=self.headless)
                papers = await fetcher.fetch_papers(
                    start_date=start_date,
                    end_date=end_date,
                    max_results=max_results_per_journal
                )
                
                results[journal_name] = papers
                logger.info(f"Fetched {len(papers)} papers from {journal_name}")
                
                # 期刊间延迟
                await asyncio.sleep(random.uniform(5, 10))
                
            except Exception as e:
                logger.error(f"Error fetching journal {journal_name}: {e}")
                results[journal_name] = []
                continue
        
        return results
    
    def get_journal_list(self) -> List[str]:
        """获取期刊列表"""
        return list(self.journals.keys())
    
    def get_journal_info(self, journal_name: str) -> Optional[Dict[str, Any]]:
        """获取期刊信息"""
        return self.journals.get(journal_name)


# 便捷函数
async def fetch_cnki_journal(
    journal_name: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    max_results: int = 50,
    headless: bool = False
) -> List[Dict[str, Any]]:
    """
    爬取单个知网期刊的论文
    
    Args:
        journal_name: 期刊名称
        start_date: 开始日期
        end_date: 结束日期
        max_results: 最大结果数
        headless: 是否使用无头模式
        
    Returns:
        论文列表
    """
    fetcher = CNKIDrissionFetcher(journal_name, headless=headless)
    return await fetcher.fetch_papers(start_date, end_date, max_results)


async def fetch_cnki_top50(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    max_results_per_journal: int = 20,
    max_journals: Optional[int] = None,
    headless: bool = False
) -> Dict[str, List[Dict[str, Any]]]:
    """
    批量爬取知网经济学TOP50期刊
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        max_results_per_journal: 每个期刊最大结果数
        max_journals: 最大期刊数量
        headless: 是否使用无头模式
        
    Returns:
        按期刊分类的论文字典
    """
    batch_fetcher = CNKITop50BatchFetcher(headless=headless)
    return await batch_fetcher.fetch_all_journals(
        start_date=start_date,
        end_date=end_date,
        max_results_per_journal=max_results_per_journal,
        max_journals=max_journals
    )
