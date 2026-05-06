"""
CNKI (中国知网) 期刊导航爬虫
按照知网期刊导航方法爬取经济学期刊论文
"""

import asyncio
import json
import logging
import os
import platform
import random
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

from DrissionPage import ChromiumPage, ChromiumOptions

from app.fetchers import retry_on_failure

logger = logging.getLogger(__name__)


class CNKINaviFetcher:
    """
    知网期刊导航爬虫
    使用 DrissionPage 进行浏览器自动化
    """
    
    BASE_URL = "https://navi.cnki.net"
    JOURNALS_INDEX_URL = "https://navi.cnki.net/knavi/journals/index"
    
    # 目标年份 - 优先获取最新年份
    TARGET_YEARS = [2026, 2025]
    
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.page: Optional[ChromiumPage] = None
        self.journals_data: Dict[str, str] = {}  # {期刊名: 链接}
        self.papers_data: List[Dict[str, Any]] = []
        
    def _init_browser(self):
        """初始化浏览器"""
        try:
            co = ChromiumOptions()
            
            # 设置浏览器路径（Linux系统）
            if platform.system() == 'Linux':
                possible_paths = [
                    '/usr/bin/chromium-browser',
                    '/usr/bin/chromium',
                    '/snap/bin/chromium',
                ]
                browser_path = None
                for path in possible_paths:
                    if os.path.exists(path):
                        if path == '/snap/bin/chromium':
                            try:
                                real_path = os.path.realpath(path)
                                if 'snap' in real_path and real_path == '/usr/bin/snap':
                                    continue
                            except:
                                pass
                        browser_path = path
                        break
                
                if browser_path:
                    co.set_browser_path(browser_path)
                    logger.info(f"Using browser at: {browser_path}")
            
            # 设置无头模式
            if self.headless:
                co.headless(True)
            else:
                co.headless(False)
            
            # 设置窗口大小
            co.set_argument('--window-size', '1920,1080')
            
            # Linux环境必要的参数
            co.set_argument('--no-sandbox')
            co.set_argument('--disable-dev-shm-usage')
            co.set_argument('--disable-gpu')
            
            # 设置User-Agent
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            ]
            co.set_user_agent(random.choice(user_agents))
            
            # 禁用自动化检测
            co.set_argument('--disable-blink-features', 'AutomationControlled')
            
            # 启动浏览器
            self.page = ChromiumPage(addr_or_opts=co)
            logger.info("Browser initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            raise
    
    def _close_browser(self):
        """关闭浏览器"""
        if self.page:
            try:
                self.page.quit()
                logger.info("Browser closed")
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
            finally:
                self.page = None
    
    def _random_delay(self, min_seconds: float = 2.0, max_seconds: float = 5.0):
        """随机延迟"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    def _check_captcha(self) -> bool:
        """检查是否有验证码 - 已禁用"""
        # 验证码检测已关闭，直接返回False
        return False
    
    def _handle_captcha(self):
        """处理验证码"""
        if self._check_captcha():
            logger.warning("Captcha detected! Please solve it manually.")
            print("\n" + "="*60)
            print("⚠️  检测到验证码，请在浏览器窗口中手动解决")
            print("="*60)
            input("解决验证码后，请按回车键继续...")
            time.sleep(2)
    
    def get_journals_list(self) -> Dict[str, str]:
        """
        获取期刊列表
        访问知网期刊导航页面，点击"经济与管理科学"分类，获取期刊列表
        """
        if not self.page:
            self._init_browser()
        
        try:
            logger.info("Accessing CNKI journals index page...")
            self.page.get(self.JOURNALS_INDEX_URL)
            time.sleep(3)
            
            # 处理验证码
            self._handle_captcha()
            
            # 点击"经济与管理科学"分类
            logger.info("Clicking '经济与管理科学' category...")
            category_btn = self.page.ele('css:a[title="经济与管理科学"]')
            if category_btn:
                category_btn.click()
                time.sleep(3)
                self._handle_captcha()
            else:
                logger.error("Could not find '经济与管理科学' category button")
                return {}
            
            # 获取div.result中的期刊列表
            logger.info("Fetching journals from div.result...")
            result_div = self.page.ele('css:div.result')
            if not result_div:
                logger.error("Could not find div.result")
                return {}
            
            # 获取所有期刊链接
            journal_links = result_div.eles('css:a')
            logger.info(f"Found {len(journal_links)} journal links")
            
            journals = {}
            for link in journal_links:
                try:
                    title = link.attr('title') or link.text
                    href = link.attr('href')
                    if title and href:
                        # 确保链接完整
                        if not href.startswith('http'):
                            href = self.BASE_URL + href
                        journals[title.strip()] = href
                except Exception as e:
                    logger.warning(f"Error extracting journal link: {e}")
                    continue
            
            self.journals_data = journals
            logger.info(f"Successfully fetched {len(journals)} journals")
            
            # 保存到JSON文件
            self._save_journals_to_json()
            
            return journals
            
        except Exception as e:
            logger.error(f"Error getting journals list: {e}")
            return {}
    
    def _save_journals_to_json(self, filepath: str = "journals_list.json"):
        """保存期刊列表到JSON文件"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.journals_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Journals saved to {filepath}")
        except Exception as e:
            logger.error(f"Error saving journals to JSON: {e}")
    
    def get_papers_from_journal(self, journal_name: str, journal_url: str) -> List[Dict[str, Any]]:
        """
        从指定期刊获取论文列表
        按年份和期号逐期爬取
        """
        if not self.page:
            self._init_browser()
        
        papers = []
        
        try:
            logger.info(f"Fetching papers from journal: {journal_name}")
            self.page.get(journal_url)
            time.sleep(3)
            self._handle_captcha()
            
            # 获取年份选择器
            for year in self.TARGET_YEARS:
                logger.info(f"Processing year: {year}")
                year_papers = self._get_papers_by_year(year)
                papers.extend(year_papers)
                logger.info(f"Fetched {len(year_papers)} papers from year {year}")
                self._random_delay(3, 5)
            
            return papers
            
        except Exception as e:
            logger.error(f"Error fetching papers from journal {journal_name}: {e}")
            return papers
    
    def _get_papers_by_year(self, year: int) -> List[Dict[str, Any]]:
        """获取指定年份的所有论文"""
        papers = []
        
        try:
            # 点击年份选择器 - 尝试多种可能的选择器
            year_selectors = [
                f'css:dl#{year}_Year_Issue',
                f'css:#{year}_Year_Issue',
                f'css:[id="{year}_Year_Issue"]',
                f'css:dl[data-year="{year}"]',
                f'css:.year-item[data-year="{year}"]',
            ]
            
            year_btn = None
            for selector in year_selectors:
                try:
                    year_btn = self.page.ele(selector, timeout=2)
                    if year_btn:
                        logger.info(f"Found year selector using: {selector}")
                        break
                except:
                    continue
            
            if year_btn:
                year_btn.click()
                time.sleep(2)
                self._handle_captcha()
            else:
                logger.warning(f"Could not find year selector for {year}, trying to continue with current view")
                # 不返回空列表，尝试继续获取当前显示的论文
            
            # 循环获取各期论文
            issue_count = 0
            while True:
                issue_count += 1
                logger.info(f"Processing issue #{issue_count} for year {year}")
                
                # 获取当前期的论文列表 - 尝试多种选择器
                paper_rows = []
                
                # 尝试从 originalCatalogview 获取
                try:
                    catalog_view = self.page.ele('css:div#originalCatalogview', timeout=3)
                    if catalog_view:
                        logger.info("Found div#originalCatalogview")
                        rows = catalog_view.eles('css:dd.row')
                        logger.info(f"Found {len(rows)} paper rows in catalog view")
                        paper_rows.extend(rows)
                except Exception as e:
                    logger.warning(f"Could not get papers from originalCatalogview: {e}")
                
                # 尝试从 listbox 获取（备用）
                if not paper_rows:
                    try:
                        listbox = self.page.ele('css:div#listbox', timeout=3)
                        if listbox:
                            logger.info("Found div#listbox")
                            rows = listbox.eles('css:dd.row')
                            if not rows:
                                rows = listbox.eles('css:a')
                            logger.info(f"Found {len(rows)} paper rows in listbox")
                            paper_rows.extend(rows)
                    except Exception as e:
                        logger.warning(f"Could not get papers from listbox: {e}")
                
                # 提取论文信息
                if paper_rows:
                    for row in paper_rows:
                        try:
                            # 查找链接
                            link = row.ele('css:span.name a', timeout=1)
                            if not link:
                                link = row.ele('css:a', timeout=1)
                            
                            if link:
                                title = link.attr('title') or link.text
                                href = link.attr('href')
                                
                                # 清理href中的反引号
                                if href:
                                    href = href.strip().strip('`')
                                
                                if title and href:
                                    if not href.startswith('http'):
                                        href = self.BASE_URL + href
                                    papers.append({
                                        'title': title.strip(),
                                        'url': href,
                                        'year': year
                                    })
                                    logger.debug(f"Extracted paper: {title[:50]}...")
                        except Exception as e:
                            logger.warning(f"Error extracting paper link: {e}")
                            continue
                    
                    logger.info(f"Extracted {len(papers)} papers so far")
                else:
                    logger.warning("No paper rows found in current view")
                
                # 检查是否有上一期按钮
                try:
                    larrow = self.page.ele('css:span#larrow', timeout=2)
                    if not larrow or 'disable' in (larrow.attr('class') or ''):
                        logger.info(f"No more issues for year {year}")
                        break
                    
                    # 点击上一期
                    logger.info("Clicking previous issue button")
                    larrow.click()
                    time.sleep(2)
                    self._random_delay(2, 4)
                except Exception as e:
                    logger.warning(f"Could not find or click previous issue button: {e}")
                    break
            
            return papers
            
        except Exception as e:
            logger.error(f"Error getting papers for year {year}: {e}")
            return papers
    
    def get_paper_detail(self, paper_url: str) -> Dict[str, Any]:
        """
        获取论文详情
        从论文详情页提取完整信息
        """
        if not self.page:
            self._init_browser()
        
        try:
            logger.info(f"Fetching paper detail: {paper_url}")
            self.page.get(paper_url)
            time.sleep(2)
            self._handle_captcha()
            
            detail = {
                'title': '',
                'authors': [],
                'abstract': '',
                'keywords': [],
                'doi': '',
                'album': '',  # 专辑
                'subject': '',  # 专题
                'classification': '',  # 分类号
                'online_date': '',  # 在线公开时间
                'journal_name_from_page': '',  # 页面中的期刊名
                'issue_info': '',  # 期号信息
                'url': paper_url
            }
            
            # 提取标题
            doc_div = self.page.ele('css:div.doc')
            if doc_div:
                title_elem = doc_div.ele('css:h1')
                if title_elem:
                    detail['title'] = title_elem.text.strip()
                
                # 提取作者
                author_elem = doc_div.ele('css:h3.author')
                if author_elem:
                    authors_text = author_elem.text.strip()
                    detail['authors'] = [a.strip() for a in re.split(r'[,，;；]', authors_text) if a.strip()]
                
                # 提取摘要
                abstract_elem = doc_div.ele('css:span.abstract-text')
                if abstract_elem:
                    detail['abstract'] = abstract_elem.text.strip()
                
                # 提取关键词
                keywords_elem = doc_div.ele('css:p.keywords')
                if keywords_elem:
                    keywords_text = keywords_elem.text.strip()
                    # 移除"关键词："前缀
                    keywords_text = re.sub(r'^关键词[：:]\s*', '', keywords_text)
                    detail['keywords'] = [k.strip() for k in re.split(r'[,，;；]', keywords_text) if k.strip()]
            
            # 提取DOI等元数据 - 改进版本
            row_divs = self.page.eles('css:div.row')
            for row in row_divs:
                try:
                    lis = row.eles('css:li.top-space')
                    for li in lis:
                        try:
                            span = li.ele('css:span.rowtit')
                            p = li.ele('css:p')
                            
                            if span and p:
                                label = span.text.strip()
                                value = p.text.strip()
                                
                                if 'DOI' in label:
                                    detail['doi'] = value
                                elif '专辑' in label:
                                    detail['album'] = value
                                elif '专题' in label:
                                    detail['subject'] = value
                                elif '分类号' in label:
                                    detail['classification'] = value
                                elif '在线公开时间' in label:
                                    detail['online_date'] = value
                        except:
                            continue
                except:
                    continue
            
            # 提取期刊名称和期号信息（从页面其他位置）
            try:
                journal_elem = self.page.ele('css:a.journalName', timeout=2)
                if journal_elem:
                    detail['journal_name_from_page'] = journal_elem.text.strip()
            except:
                pass
            
            try:
                issue_elem = self.page.ele('css:span.issue', timeout=2)
                if issue_elem:
                    detail['issue_info'] = issue_elem.text.strip()
            except:
                pass
            
            logger.info(f"Successfully extracted detail for: {detail['title'][:50]}...")
            logger.info(f"  DOI: {detail.get('doi', 'N/A')}")
            logger.info(f"  Album: {detail.get('album', 'N/A')}")
            logger.info(f"  Subject: {detail.get('subject', 'N/A')}")
            return detail
            
        except Exception as e:
            logger.error(f"Error getting paper detail: {e}")
            return {}
    
    async def fetch_all_papers(self, max_journals: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        爬取所有期刊的论文
        """
        all_papers = []
        
        try:
            # 获取期刊列表
            if not self.journals_data:
                self.get_journals_list()
            
            if not self.journals_data:
                logger.error("No journals fetched")
                return all_papers
            
            # 限制期刊数量
            journals_to_fetch = list(self.journals_data.items())
            if max_journals:
                journals_to_fetch = journals_to_fetch[:max_journals]
            
            # 逐个期刊爬取
            for journal_name, journal_url in journals_to_fetch:
                try:
                    logger.info(f"\n{'='*60}")
                    logger.info(f"Fetching journal: {journal_name}")
                    logger.info(f"{'='*60}")
                    
                    papers = self.get_papers_from_journal(journal_name, journal_url)
                    
                    # 获取每篇论文的详情
                    for paper_info in papers:
                        try:
                            detail = self.get_paper_detail(paper_info['url'])
                            if detail:
                                paper_data = {
                                    **detail,
                                    'journal_name': journal_name,
                                    'year': paper_info.get('year', datetime.now().year),
                                    'source': 'CNKI',
                                    'discipline': '经济学'
                                }
                                all_papers.append(paper_data)
                                self._random_delay(2, 4)
                        except Exception as e:
                            logger.warning(f"Error fetching paper detail: {e}")
                            continue
                    
                    logger.info(f"Fetched {len(papers)} papers from {journal_name}")
                    self._random_delay(5, 8)
                    
                except Exception as e:
                    logger.error(f"Error processing journal {journal_name}: {e}")
                    continue
            
            logger.info(f"\n{'='*60}")
            logger.info(f"Total papers fetched: {len(all_papers)}")
            logger.info(f"{'='*60}")
            
            return all_papers
            
        except Exception as e:
            logger.error(f"Error in fetch_all_papers: {e}")
            return all_papers
        finally:
            self._close_browser()
    
    def save_papers_to_json(self, filepath: str = "papers_data.json"):
        """保存论文数据到JSON文件"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.papers_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Papers saved to {filepath}")
        except Exception as e:
            logger.error(f"Error saving papers to JSON: {e}")
    
    async def save_papers_to_db(self, db) -> int:
        """保存论文数据到数据库"""
        from app.crud import PaperCRUD
        
        saved_count = 0
        for paper_data in self.papers_data:
            try:
                result = await PaperCRUD.create_paper_from_cnki(db, paper_data)
                if result:
                    saved_count += 1
            except Exception as e:
                logger.error(f"Error saving paper to DB: {e}")
                continue
        
        logger.info(f"Saved {saved_count} papers to database")
        return saved_count


# 便捷函数
async def crawl_cnki_journals(max_journals: Optional[int] = None, save_to_db: bool = False, db=None) -> List[Dict[str, Any]]:
    """
    爬取知网期刊论文的便捷函数
    
    Args:
        max_journals: 最大爬取期刊数量
        save_to_db: 是否保存到数据库
        db: 数据库session（save_to_db为True时需要）
    """
    fetcher = CNKINaviFetcher(headless=False)
    papers = await fetcher.fetch_all_papers(max_journals=max_journals)
    fetcher.papers_data = papers
    fetcher.save_papers_to_json()
    
    if save_to_db and db:
        await fetcher.save_papers_to_db(db)
    
    return papers
