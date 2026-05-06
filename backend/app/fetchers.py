import arxiv
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import asyncio
from app.models import Paper
from app.config import settings
import logging
import random
from abc import ABC, abstractmethod
from functools import wraps
import time
import requests
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)


class ArxivFetcher:
    def __init__(self):
        self.categories = settings.arxiv_categories
        
    async def fetch_papers(
        self,
        days_back: int = 7,
        max_results: int = 100
    ) -> List[dict]:
        try:
            search = arxiv.Search(
                query=" OR ".join([f"cat:{cat}" for cat in self.categories]),
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            
            papers = []
            cutoff_date = datetime.now() - timedelta(days=days_back)
            
            for result in search.results():
                if result.published.replace(tzinfo=None) < cutoff_date.replace(tzinfo=None):
                    continue
                    
                paper_data = {
                    "title": result.title,
                    "abstract": result.summary.replace('\n', ' ').strip(),
                    "authors": [author.name for author in result.authors],
                    "url": result.entry_id,
                    "source": "arxiv",
                    "venue": self._extract_venue_from_categories(result.categories),
                    "published_at": result.published
                }
                papers.append(paper_data)
            
            logger.info(f"Fetched {len(papers)} papers from arXiv")
            return papers
            
        except Exception as e:
            logger.error(f"Error fetching from arXiv: {e}")
            return []
    
    def _extract_venue_from_categories(self, categories: List[str]) -> Optional[str]:
        venue_mapping = {
            "cs.AI": "Artificial Intelligence",
            "cs.CL": "Computation and Language",
            "cs.LG": "Machine Learning",
            "cs.CV": "Computer Vision"
        }
        
        for cat in categories:
            if cat in venue_mapping:
                return venue_mapping[cat]
        
        return None


class VenueDataFetcher:
    VENUE_SCORES = {
        "NeurIPS": 1.0,
        "ICML": 1.0,
        "ICLR": 1.0,
        "CVPR": 0.9,
        "ACL": 0.9,
        "Nature": 1.0,
        "Science": 1.0,
        "IEEE": 0.9,
        "JMLR": 0.95,
        "arxiv": 0.6,
        "American Economic Review": 1.0,
        "AER": 1.0,
        "Journal of Political Economy": 1.0,
        "JPE": 1.0,
        "Econometrica": 1.0,
        "Quarterly Journal of Economics": 1.0,
        "QJE": 1.0,
        "Review of Economic Studies": 1.0,
        "RES": 1.0,
        "Journal of Economic Theory": 0.95,
        "JET": 0.95,
        "Journal of Finance": 0.95,
        "Review of Financial Studies": 0.95,
        "RFS": 0.95,
        "Journal of Financial Economics": 0.95,
        "JFE": 0.95,
        "Journal of Econometrics": 0.9,
        "Journal of Monetary Economics": 0.9,
        "JME": 0.9,
        "Journal of International Economics": 0.9,
        "Journal of Development Economics": 0.9,
        "JDE": 0.9,
        "Journal of Industrial Economics": 0.85,
        "Journal of Ind Econ": 0.85,
        "Review of Economics and Statistics": 0.9,
        "REStat": 0.9,
        "Economic Journal": 0.85,
        "Journal of Public Economics": 0.85,
        "Journal of Labor Economics": 0.85,
        "JOLE": 0.85,
        "American Economic Journal": 0.85,
        "AEJ": 0.85,
        "Review of Economic Dynamics": 0.8,
        "RED": 0.8,
        "International Economic Review": 0.8,
        "IER": 0.8,
        "Journal of Economic Perspectives": 0.8,
        "JEP": 0.8,
        "经济研究": 1.0,
        "管理世界": 0.95,
        "经济学（季刊）": 0.95,
        "世界经济": 0.9,
        "中国工业经济": 0.9,
    }
    
    @classmethod
    def get_venue_score(cls, venue: Optional[str]) -> float:
        if not venue:
            return 0.6
        
        venue_lower = venue.lower()
        for known_venue, score in cls.VENUE_SCORES.items():
            if known_venue.lower() in venue_lower:
                return score
        
        return 0.6


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay * (attempt + 1))
            
            logger.error(f"All {max_retries} attempts failed for {func.__name__}")
            raise last_exception
        return wrapper
    return decorator


class EconomicsJournalFetcher(ABC):
    def __init__(self, journal_name: str):
        self.journal_name = journal_name
        self.discipline = "经济学"
        
    @abstractmethod
    async def fetch_papers(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        pass
    
    def _generate_paper_data(
        self,
        title: str,
        abstract: str,
        authors: List[str],
        published_date: datetime,
        doi: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        issue: Optional[str] = None
    ) -> Dict[str, Any]:
        return {
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "url": f"https://example.com/{self.journal_name}/{doi or 'unknown'}",
            "source": self.journal_name,
            "venue": self.journal_name,
            "published_at": published_date,
            "discipline": self.discipline,
            "journal_name": self.journal_name,
            "journal_issue": issue,
            "doi": doi,
            "keywords_cn": keywords or []
        }
    
    def _filter_by_date_range(
        self,
        papers: List[Dict[str, Any]],
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> List[Dict[str, Any]]:
        filtered = []
        for paper in papers:
            pub_date = paper.get("published_at")
            if not pub_date:
                continue
            
            if start_date and pub_date < start_date:
                continue
            if end_date and pub_date > end_date:
                continue
            
            filtered.append(paper)
        
        return filtered


class JingjiYanjiuFetcher(EconomicsJournalFetcher):
    def __init__(self):
        super().__init__("经济研究")
        self.api_url = "https://api.ajcass.com/api/JournalInfoApi/GetIssueinfoList"
        
    @retry_on_failure(max_retries=3, delay=2.0)
    async def fetch_papers(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        logger.info(f"Fetching papers from 经济研究 - max_results: {max_results}")
        
        papers = []
        current_year = datetime.now().year
        
        # 爬取最近几期的论文
        for issue in range(1, 13):
            if len(papers) >= max_results:
                break
                
            try:
                payload = {
                    "JournalID": "201803050001",
                    "curr": 1,
                    "issue": issue,
                    "limit": 50,
                    "year": current_year,
                    "keywords": ""
                }
                
                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                response = requests.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=10
                )
                response.raise_for_status()
                
                data = response.json()
                
                if data.get('code') != 200:
                    logger.warning(f"API returned error code {data.get('code')} for issue {issue}")
                    continue
                
                items = data.get('data', [])
                
                for item in items:
                    try:
                        title = item.get('title', '').strip()
                        authors_text = item.get('authors', '')
                        # 将中文逗号分隔的作者字符串分割成列表
                        authors = [a.strip() for a in authors_text.replace('，', ',').split(',') if a.strip()]
                        
                        year = item.get('year', current_year)
                        issue_num = item.get('issue', issue)
                        paper_id = item.get('id', '')
                        
                        # 构建论文URL
                        article_url = f"https://erj.ajcass.com/#/article/{paper_id}" if paper_id else ""
                        
                        # 构建期号信息
                        issue_info = f"{year}年{issue_num:02d}期"
                        
                        paper_data = {
                            "title": title,
                            "abstract": "",  # API不返回摘要，需要单独获取
                            "authors": authors,
                            "published_date": datetime(year, issue_num, 1),
                            "doi": "",
                            "keywords": [],
                            "issue": issue_info
                        }
                        
                        paper = self._generate_paper_data(**paper_data)
                        paper['url'] = article_url
                        paper['hits'] = item.get('hits', 0)
                        paper['downloads'] = item.get('downloads', 0)
                        paper['volume'] = item.get('volume', '')
                        paper['page_num'] = item.get('pageNum', '')
                        
                        papers.append(paper)
                        
                        if len(papers) >= max_results:
                            break
                            
                    except Exception as e:
                        logger.error(f"Error parsing paper item: {e}")
                        continue
                
                # 添加延迟，避免请求过快
                await asyncio.sleep(random.uniform(0.5, 1.0))
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Network error fetching issue {issue}: {e}")
                continue
            except Exception as e:
                logger.error(f"Error fetching issue {issue}: {e}")
                continue
        
        filtered_papers = self._filter_by_date_range(papers, start_date, end_date)
        
        logger.info(f"Fetched {len(filtered_papers)} papers from 经济研究")
        return filtered_papers


class GuanliShijieFetcher(EconomicsJournalFetcher):
    def __init__(self):
        super().__init__("管理世界")
        self.base_url = "https://glsj.cbpt.cnki.net/WKB2/WebPublication/wkTextContent.aspx"

    def _construct_url(self, year: int, issue: int) -> str:
        """构造管理世界期刊列表URL"""
        return f"{self.base_url}?colType=4&yt={year}&st={issue:02d}"

    def _parse_papers_from_html(self, html_content: str, year: int, issue: int) -> List[Dict[str, Any]]:
        """从HTML内容中解析论文列表"""
        papers = []
        soup = BeautifulSoup(html_content, 'html.parser')

        # 查找论文列表容器
        zxlist = soup.find('div', class_='zxlist')
        if not zxlist:
            logger.warning(f"No zxlist found in page for {year}年{issue:02d}期")
            return papers

        # 获取所有论文项
        items = zxlist.find_all('li')
        logger.info(f"Found {len(items)} papers in {year}年{issue:02d}期")

        for item in items:
            try:
                # 提取标题和链接
                h3_elem = item.find('h3')
                if not h3_elem:
                    continue
                title_elem = h3_elem.find('a')
                if not title_elem:
                    continue

                title = title_elem.text.strip()
                link = title_elem.get('href', '')

                # 构造完整URL
                if link and not link.startswith('http'):
                    link = f"https://glsj.cbpt.cnki.net/WKB2/WebPublication/{link}"

                # 提取作者
                authors_elem = item.find('samp')
                authors_text = authors_elem.text.strip() if authors_elem else ""
                # 处理作者分隔符（可能是分号或逗号）
                authors = [a.strip() for a in authors_text.replace('，', ';').replace(',', ';').split(';') if a.strip()]

                # 提取摘要
                abstract_elem = item.find('p')
                abstract = abstract_elem.text.strip() if abstract_elem else ""

                # 提取期号信息
                issue_info = f"{year}年{issue:02d}期"

                paper_data = {
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "published_date": datetime(year, ((issue - 1) // 2) * 2 + 1, 1),  # 大致估算发表月份
                    "doi": "",
                    "keywords": [],
                    "issue": issue_info
                }

                paper = self._generate_paper_data(**paper_data)
                # 手动设置URL
                paper['url'] = link if link else f"https://glsj.cbpt.cnki.net/"

                papers.append(paper)

            except Exception as e:
                logger.error(f"Error parsing paper item: {e}")
                continue

        return papers

    @retry_on_failure(max_retries=3, delay=2.0)
    async def fetch_papers(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        logger.info(f"Fetching papers from 管理世界 - max_results: {max_results}")

        papers = []
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://glsj.cbpt.cnki.net/'
        }

        # 确定要爬取的年份和期号
        current_year = datetime.now().year
        current_month = datetime.now().month

        # 管理世界是月刊，每月一期
        # 从当前年份开始，向前爬取
        years_to_fetch = [current_year, current_year - 1]

        for year in years_to_fetch:
            if len(papers) >= max_results:
                break

            # 对于当前年份，只爬取已发布的期号
            max_issue = 12
            if year == current_year:
                max_issue = min(current_month, 12)

            # 从最新期号开始向前爬取
            for issue in range(max_issue, 0, -1):
                if len(papers) >= max_results:
                    break

                try:
                    url = self._construct_url(year, issue)
                    logger.info(f"Fetching from URL: {url}")

                    # 使用同步requests在异步上下文中执行
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: requests.get(url, headers=headers, timeout=15)
                    )

                    if response.status_code != 200:
                        logger.warning(f"Failed to fetch {url}: Status {response.status_code}")
                        continue

                    # 设置编码
                    response.encoding = 'utf-8'

                    # 解析论文
                    issue_papers = self._parse_papers_from_html(response.text, year, issue)
                    papers.extend(issue_papers)

                    logger.info(f"Successfully fetched {len(issue_papers)} papers from {year}年{issue:02d}期")

                    # 添加随机延迟，避免被封
                    delay = random.uniform(2.0, 4.0)
                    logger.debug(f"Sleeping for {delay:.2f} seconds")
                    await asyncio.sleep(delay)

                except requests.exceptions.RequestException as e:
                    logger.error(f"Network error fetching {year}年{issue:02d}期: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Error fetching {year}年{issue:02d}期: {e}")
                    continue

        # 根据日期范围过滤
        filtered_papers = self._filter_by_date_range(papers, start_date, end_date)

        # 限制返回数量
        result_papers = filtered_papers[:max_results]

        logger.info(f"Fetched {len(result_papers)} papers from 管理世界 (total: {len(filtered_papers)}, raw: {len(papers)})")
        return result_papers


class JingjixueJikanFetcher(EconomicsJournalFetcher):
    """
    经济学（季刊）爬虫
    网站: https://ccj.pku.edu.cn/
    使用北京大学期刊系统API获取论文数据
    """
    
    def __init__(self):
        super().__init__("经济学（季刊）")
        self.base_url = "https://ccj.pku.edu.cn"
        self.journal_id = "96822"  # 经济学季刊的期刊ID
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest'
        }
        
    def _get_latest_volume_issues(self) -> List[Dict[str, Any]]:
        """
        获取最新的卷期列表
        由于API限制，我们使用已知的卷期ID来获取最新文章
        """
        # 经济学季刊是双月刊，每年6期
        # 根据分析，viid格式为期刊卷期ID
        # 这里使用已知的近期卷期ID
        current_year = datetime.now().year
        
        # 构建卷期列表（基于实际观察到的ID模式）
        # 注意：这些ID需要定期更新，或者通过其他方式动态获取
        volume_issues = []
        
        # 2025年的卷期（第25卷，第1-6期）
        # 基于观察，viid大约是递增的
        base_viid = 15709294  # 2025年第1期的大致viid
        for issue in range(1, 7):
            volume_issues.append({
                'year': 2025,
                'volume': 25,
                'issue': issue,
                'viid': base_viid + issue - 1
            })
        
        # 2024年的卷期（第24卷，第1-6期）
        base_viid_2024 = 15709288
        for issue in range(1, 7):
            volume_issues.append({
                'year': 2024,
                'volume': 24,
                'issue': issue,
                'viid': base_viid_2024 + issue - 1
            })
        
        return volume_issues
        
    def _fetch_articles_by_viid(self, viid: str) -> List[Dict[str, Any]]:
        """
        通过卷期ID获取文章列表
        """
        url = f"{self.base_url}/Journal/GetJournalArticle"
        params = {
            'jid': self.journal_id,
            'viid': viid
        }
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('StatusCode') != 200:
                logger.warning(f"API returned error code {data.get('StatusCode')} for viid {viid}")
                return []
            
            return data.get('Data', {}).get('data', [])
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching articles for viid {viid}: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for viid {viid}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching articles for viid {viid}: {e}")
            return []
            
    def _parse_authors(self, author_text: str) -> List[str]:
        """
        解析作者字符串为列表
        """
        if not author_text:
            return []
        
        # 处理中英文逗号分隔的作者
        authors = []
        for author in author_text.replace('，', ',').split(','):
            author = author.strip()
            if author:
                authors.append(author)
        
        return authors
        
    def _convert_to_paper_data(
        self,
        article: Dict[str, Any],
        year: int,
        issue: int
    ) -> Optional[Dict[str, Any]]:
        """
        将API返回的文章数据转换为标准格式
        """
        try:
            title = article.get('Title', '').strip()
            if not title:
                return None
                
            authors_text = article.get('Author', '')
            authors = self._parse_authors(authors_text)
            
            # 构建发表日期（使用年份和期数估算）
            # 经济学季刊是双月刊：1月、3月、5月、7月、9月、11月
            month_map = {1: 1, 2: 3, 3: 5, 4: 7, 5: 9, 6: 11}
            month = month_map.get(issue, 1)
            published_date = datetime(year, month, 1)
            
            # 构建期号信息
            volume = article.get('JournalNUmber', '')
            issue_info = f"{year}年{issue:02d}期"
            if volume:
                issue_info = f"第{volume}卷{issue_info}"
            
            # 构建文章URL
            article_id = article.get('ArticleId', '')
            article_url = f"{self.base_url}/article/info?aid={article_id}" if article_id else ""
            
            # 获取DOI
            doi = article.get('Doi', '')
            
            # 获取页码
            page_str = article.get('PageStr', '')
            
            paper_data = {
                "title": title,
                "abstract": "",  # API不返回摘要，需要通过CNKI获取
                "authors": authors,
                "published_date": published_date,
                "doi": doi,
                "keywords": [],
                "issue": issue_info
            }
            
            paper = self._generate_paper_data(**paper_data)
            paper['url'] = article_url
            paper['article_id'] = article_id
            paper['page_range'] = page_str
            paper['subject'] = article.get('Subject', '')
            paper['cnki_url'] = article.get('AbstractUrl', '')
            
            return paper
            
        except Exception as e:
            logger.error(f"Error converting article data: {e}")
            return None
            
    @retry_on_failure(max_retries=3, delay=2.0)
    async def fetch_papers(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        logger.info(f"Fetching papers from 经济学（季刊） - max_results: {max_results}")
        
        papers = []
        
        try:
            # 获取卷期列表
            volume_issues = self._get_latest_volume_issues()
            
            # 在事件循环中执行同步的HTTP请求
            loop = asyncio.get_event_loop()
            
            for vol_issue in volume_issues:
                if len(papers) >= max_results:
                    break
                    
                year = vol_issue['year']
                issue = vol_issue['issue']
                viid = vol_issue['viid']
                
                # 估算发表日期用于预过滤
                month_map = {1: 1, 2: 3, 3: 5, 4: 7, 5: 9, 6: 11}
                month = month_map.get(issue, 1)
                estimated_date = datetime(year, month, 1)
                
                # 根据日期范围预过滤
                if start_date and estimated_date < start_date:
                    continue
                if end_date and estimated_date > end_date:
                    continue
                
                try:
                    # 使用线程池执行同步请求
                    articles = await loop.run_in_executor(
                        None,
                        lambda: self._fetch_articles_by_viid(str(viid))
                    )
                    
                    if not articles:
                        logger.debug(f"No articles found for {year}年{issue:02d}期 (viid={viid})")
                        continue
                    
                    logger.info(f"Fetched {len(articles)} articles from {year}年{issue:02d}期")
                    
                    for article in articles:
                        paper = self._convert_to_paper_data(article, year, issue)
                        if paper:
                            papers.append(paper)
                            
                            if len(papers) >= max_results:
                                break
                    
                    # 添加随机延迟，避免被封
                    delay = random.uniform(1.0, 2.0)
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    logger.error(f"Error processing {year}年{issue:02d}期: {e}")
                    continue
            
            # 根据日期范围过滤
            filtered_papers = self._filter_by_date_range(papers, start_date, end_date)
            
            # 限制返回数量
            result_papers = filtered_papers[:max_results]
            
            logger.info(f"Fetched {len(result_papers)} papers from 经济学（季刊） (total: {len(filtered_papers)}, raw: {len(papers)})")
            return result_papers
            
        except Exception as e:
            logger.error(f"Error fetching papers from 经济学（季刊）: {e}")
            return []


class ShijieJingjiFetcher(EconomicsJournalFetcher):
    def __init__(self):
        super().__init__("世界经济")
        
    @retry_on_failure(max_retries=3, delay=2.0)
    async def fetch_papers(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        logger.info(f"Fetching papers from 世界经济 - max_results: {max_results}")
        
        papers = []
        
        # 计算年份和卷号
        current_year = datetime.now().year
        volume = 48 + (current_year - 2025)  # 2025年是48卷
        
        # 爬取最近几期的论文
        for issue in range(1, 13):
            if len(papers) >= max_results:
                break
                
            try:
                url = f"https://sjjj.magtech.com.cn/CN/Y{current_year}/V{volume}/I{issue}"
                logger.info(f"Fetching from URL: {url}")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                response = requests.get(url, headers=headers, timeout=10)
                response.encoding = 'utf-8'
                
                if response.status_code != 200:
                    logger.warning(f"Failed to fetch {url}: Status {response.status_code}")
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # 查找所有文章
                articles = soup.find_all('div', class_='article-l')
                
                for article in articles:
                    try:
                        # 提取标题
                        title_div = article.find('div', class_='j-title-1')
                        if not title_div:
                            continue
                        title_link = title_div.find('a')
                        if not title_link:
                            continue
                        title = title_link.text.strip()
                        article_url = title_link.get('href', '')
                        
                        # 提取作者
                        author_div = article.find('div', class_='j-author')
                        authors_text = author_div.text.strip() if author_div else ""
                        authors = [a.strip() for a in authors_text.split(',')]
                        
                        # 提取摘要
                        abstract_div = article.find('div', class_='j-abstract')
                        abstract = abstract_div.text.strip() if abstract_div else ""
                        
                        # 提取期号信息
                        volumn_div = article.find('div', class_='j-volumn-doi')
                        volumn_span = volumn_div.find('span', class_='j-volumn') if volumn_div else None
                        issue_info = volumn_span.text.strip() if volumn_span else f"{current_year}年第{issue}期"
                        
                        # 提取栏目
                        column_span = article.find('span', class_='j-column')
                        column = column_span.text.strip() if column_span else ""
                        
                        paper_data = {
                            "title": title,
                            "abstract": abstract,
                            "authors": authors,
                            "published_date": datetime(current_year, issue, 1),
                            "doi": "",
                            "keywords": [],
                            "issue": issue_info
                        }
                        
                        paper = self._generate_paper_data(**paper_data)
                        # 手动设置URL
                        paper['url'] = article_url
                        paper['column'] = column
                        
                        papers.append(paper)
                        
                    except Exception as e:
                        logger.error(f"Error parsing article: {e}")
                        continue
                
                # 添加延迟，避免被封
                await asyncio.sleep(random.uniform(1.0, 2.0))
                
            except Exception as e:
                logger.error(f"Error fetching issue {issue}: {e}")
                continue
        
        filtered_papers = self._filter_by_date_range(papers, start_date, end_date)
        
        logger.info(f"Fetched {len(filtered_papers)} papers from 世界经济")
        return filtered_papers


class ZhongguoGongyeJingjiFetcher(EconomicsJournalFetcher):
    """中国工业经济期刊爬虫
    
    网站: https://ciejournal.ajcass.com/
    API接口: https://api.ajcass.com/api/JournalInfoApi/GetIssueinfoList
    JournalID: 201606280001
    """
    
    def __init__(self):
        super().__init__("中国工业经济")
        self.base_url = "https://ciejournal.ajcass.com"
        self.api_url = "https://api.ajcass.com/api/JournalInfoApi/GetIssueinfoList"
        self.journal_id = 201606280001
        
    @retry_on_failure(max_retries=3, delay=2.0)
    async def fetch_papers(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        logger.info(f"Fetching papers from 中国工业经济 - max_results: {max_results}")
        
        papers = []
        current_year = datetime.now().year
        
        # 爬取最近几期的论文
        for issue in range(1, 13):
            if len(papers) >= max_results:
                break
                
            try:
                payload = {
                    "JournalID": self.journal_id,
                    "curr": 1,
                    "issue": issue,
                    "limit": 50,
                    "year": current_year,
                    "keywords": ""
                }
                
                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                response = requests.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=10
                )
                response.raise_for_status()
                
                data = response.json()
                
                if data.get('code') != 200:
                    logger.warning(f"API returned error code {data.get('code')} for issue {issue}")
                    continue
                
                items = data.get('data', [])
                
                for item in items:
                    try:
                        title = item.get('title', '').strip()
                        authors_text = item.get('authors', '')
                        # 将中文逗号分隔的作者字符串分割成列表
                        authors = [a.strip() for a in authors_text.replace('，', ',').split(',') if a.strip()]
                        
                        year = item.get('year', current_year)
                        issue_num = item.get('issue', issue)
                        paper_id = item.get('id', '')
                        
                        # 构建论文URL
                        article_url = f"https://ciejournal.ajcass.com/#/article/{paper_id}" if paper_id else self.base_url
                        
                        # 构建期号信息
                        issue_info = f"{year}年{issue_num:02d}期"
                        
                        paper_data = {
                            "title": title,
                            "abstract": "",  # API不返回摘要，需要单独获取
                            "authors": authors,
                            "published_date": datetime(year, issue_num, 1),
                            "doi": "",
                            "keywords": [],
                            "issue": issue_info
                        }
                        
                        paper = self._generate_paper_data(**paper_data)
                        paper['url'] = article_url
                        
                        papers.append(paper)
                        
                    except Exception as e:
                        logger.error(f"Error parsing paper item: {e}")
                        continue
                
                # 添加延迟，避免请求过快
                await asyncio.sleep(random.uniform(0.5, 1.0))
                
            except Exception as e:
                logger.error(f"Error fetching issue {issue}: {e}")
                continue
        
        # 按日期过滤
        filtered_papers = self._filter_by_date_range(papers, start_date, end_date)
        
        logger.info(f"Fetched {len(filtered_papers)} papers from 中国工业经济")
        return filtered_papers[:max_results]


class AmericanEconomicReviewFetcher(EconomicsJournalFetcher):
    """
    American Economic Review (AER) 期刊爬虫
    
    网站: https://www.aeaweb.org/journals/aer
    期刊列表: https://www.aeaweb.org/issues/{volume}/{issue}
    卷号计算: volume = year - 1910
    """
    
    def __init__(self):
        super().__init__("American Economic Review")
        self.base_url = "https://www.aeaweb.org"
        
    def _calculate_volume(self, year: int) -> int:
        """根据年份计算卷号: volume = year - 1910"""
        return year - 1910
    
    def _get_issue_url(self, volume: int, issue: int) -> str:
        """构造期刊issue页面URL"""
        return f"{self.base_url}/issues/{volume}/{issue}"
    
    def _parse_authors(self, authors_text: str) -> List[str]:
        """解析作者列表，处理多种分隔符"""
        if not authors_text:
            return []
        
        # 处理常见的作者分隔符
        for separator in [',', ' and ', '&', ';']:
            if separator in authors_text:
                if separator == ' and ':
                    return [a.strip() for a in authors_text.split(' and ') if a.strip()]
                else:
                    return [a.strip() for a in authors_text.split(separator) if a.strip()]
        
        # 如果没有分隔符，返回单个作者
        return [authors_text.strip()] if authors_text.strip() else []
    
    @retry_on_failure(max_retries=3, delay=2.0)
    async def fetch_papers(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        从American Economic Review获取论文列表
        
        Args:
            start_date: 开始日期，用于过滤
            end_date: 结束日期，用于过滤
            max_results: 最大返回结果数
            
        Returns:
            论文列表，每个论文为字典格式
        """
        logger.info(f"Fetching papers from American Economic Review - max_results: {max_results}")
        
        papers = []
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        # 确定要爬取的年份范围
        current_year = datetime.now().year
        years_to_fetch = []
        
        if start_date and end_date:
            # 根据日期范围确定年份
            for year in range(start_date.year, end_date.year + 1):
                years_to_fetch.append(year)
        else:
            # 默认爬取最近2年的论文
            years_to_fetch = [current_year, current_year - 1]
        
        # 遍历年份和期号
        for year in years_to_fetch:
            if len(papers) >= max_results:
                break
                
            volume = self._calculate_volume(year)
            
            # AER每年通常有12期（月刊）
            for issue in range(1, 13):
                if len(papers) >= max_results:
                    break
                
                try:
                    url = self._get_issue_url(volume, issue)
                    logger.info(f"Fetching AER issue: Year {year}, Volume {volume}, Issue {issue} - URL: {url}")
                    
                    # 使用同步requests在异步上下文中
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None, 
                        lambda: requests.get(url, headers=headers, timeout=15)
                    )
                    
                    if response.status_code == 404:
                        # 该期可能不存在，跳过
                        logger.debug(f"Issue not found: {url}")
                        continue
                    
                    if response.status_code != 200:
                        logger.warning(f"Failed to fetch {url}: Status {response.status_code}")
                        continue
                    
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # 查找所有文章 - AER网站通常使用article标签或特定的div结构
                    articles = soup.find_all('article', class_='journal-article')
                    
                    # 如果找不到，尝试其他常见的选择器
                    if not articles:
                        articles = soup.find_all('div', class_='article')
                    if not articles:
                        articles = soup.find_all('div', class_='issue-item')
                    if not articles:
                        # 尝试更通用的选择器
                        articles = soup.find_all(['article', 'div'], class_=lambda x: x and ('article' in x.lower() if x else False))
                    
                    logger.info(f"Found {len(articles)} articles in issue {year}-{issue}")
                    
                    for article in articles:
                        try:
                            # 提取标题
                            title_elem = (
                                article.find('h3', class_='title') or
                                article.find('h2', class_='title') or
                                article.find('h3') or
                                article.find('a', class_='title')
                            )
                            
                            if not title_elem:
                                continue
                                
                            title = title_elem.get_text(strip=True)
                            
                            # 提取文章链接
                            article_link = None
                            if title_elem.name == 'a':
                                article_link = title_elem.get('href')
                            else:
                                link_elem = title_elem.find('a')
                                if link_elem:
                                    article_link = link_elem.get('href')
                            
                            if article_link and not article_link.startswith('http'):
                                article_link = self.base_url + article_link
                            
                            # 提取作者
                            authors = []
                            author_elem = (
                                article.find('div', class_='authors') or
                                article.find('p', class_='authors') or
                                article.find('span', class_='authors')
                            )
                            
                            if author_elem:
                                authors_text = author_elem.get_text(strip=True)
                                authors = self._parse_authors(authors_text)
                            
                            # 提取摘要
                            abstract = ""
                            abstract_elem = (
                                article.find('div', class_='abstract') or
                                article.find('p', class_='abstract') or
                                article.find('div', class_='description')
                            )
                            
                            if abstract_elem:
                                abstract = abstract_elem.get_text(strip=True)
                            
                            # 提取DOI
                            doi = ""
                            doi_elem = article.find('a', href=lambda x: x and 'doi.org' in x)
                            if doi_elem:
                                doi = doi_elem.get_text(strip=True)
                            
                            # 提取页码信息
                            pages = ""
                            pages_elem = (
                                article.find('span', class_='pages') or
                                article.find('div', class_='pages')
                            )
                            if pages_elem:
                                pages = pages_elem.get_text(strip=True)
                            
                            # 构建论文数据
                            # AER是月刊，使用月份1-12
                            published_date = datetime(year, issue, 1)
                            
                            paper_data = {
                                "title": title,
                                "abstract": abstract,
                                "authors": authors,
                                "published_date": published_date,
                                "doi": doi,
                                "keywords": [],
                                "issue": f"Vol. {volume}, No. {issue} ({year})",
                            }
                            
                            paper = self._generate_paper_data(**paper_data)
                            
                            # 设置正确的URL
                            if article_link:
                                paper['url'] = article_link
                            else:
                                paper['url'] = url
                            
                            # 添加额外信息
                            if pages:
                                paper['pages'] = pages
                            
                            papers.append(paper)
                            logger.debug(f"Added paper: {title[:50]}...")
                            
                        except Exception as e:
                            logger.error(f"Error parsing article: {e}")
                            continue
                    
                    # 添加随机延迟，避免被封
                    await asyncio.sleep(random.uniform(1.5, 3.0))
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"Network error fetching issue {issue}: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Error fetching issue {issue}: {e}")
                    continue
        
        # 根据日期范围过滤
        filtered_papers = self._filter_by_date_range(papers, start_date, end_date)
        
        # 限制结果数量
        final_papers = filtered_papers[:max_results]
        
        logger.info(f"Successfully fetched {len(final_papers)} papers from American Economic Review")
        return final_papers
