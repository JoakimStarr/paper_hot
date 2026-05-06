#!/usr/bin/env python3
"""
知网经济学TOP50期刊论文爬取工具
使用 DrissionPage 浏览器自动化
支持将数据保存到 SQLite 数据库

正确的知网搜索流程：
1. 打开知网搜索页面 https://kns.cnki.net/kns8s/AdvSearch
2. 点击"文献来源"筛选条件
3. 输入期刊名称
4. 设置年份为2025
5. 点击搜索
6. 翻页获取更多结果

一键执行命令:
    python crawl_cnki_papers.py

可选参数:
    python crawl_cnki_papers.py --journal "经济研究" --max-results 30
    python crawl_cnki_papers.py --headless --max-journals 10
    python crawl_cnki_papers.py --save-to-db
"""

import asyncio
import argparse
import json
import sys
import os
import re
import time
import random
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from DrissionPage import ChromiumOptions, Chromium


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


class CNKICrawler:
    """知网论文爬虫 - 正确的知网搜索流程"""
    
    def __init__(self, headless: bool = False, use_system_user: bool = True):
        self.headless = headless
        self.use_system_user = use_system_user
        self.browser = None
        self.tab = None
        
    def init_browser(self):
        """初始化浏览器"""
        co = ChromiumOptions()
        
        if self.headless:
            co.headless(True)
        
        if self.use_system_user:
            co.use_system_user_path()
        
        # 设置 User-Agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        co.set_user_agent(random.choice(user_agents))
        co.set_argument("--window-size", "1400,900")
        co.set_argument("--disable-blink-features", "AutomationControlled")
        
        self.browser = Chromium(co)
        self.tab = self.browser.latest_tab
        print("✓ 浏览器初始化成功")
        
    def close_browser(self):
        """关闭浏览器"""
        if self.browser:
            self.browser.quit()
            print("✓ 浏览器已关闭")
            
    def check_captcha(self) -> bool:
        """检查是否有验证码"""
        try:
            indicators = ["验证码", "captcha", "验证", "verification", "安全验证", "请点击", "拖动滑块"]
            page_text = self.tab.html.lower()
            
            for indicator in indicators:
                if indicator in page_text:
                    return True
            
            # 检查验证码图片元素
            captcha_selectors = [
                'img[src*="captcha"]',
                '.verify-img',
                '.captcha-img',
                '[class*="captcha"]',
            ]
            for selector in captcha_selectors:
                try:
                    if self.tab.ele(selector, timeout=1):
                        return True
                except:
                    pass
                    
            return False
        except:
            return False
            
    def handle_captcha(self, timeout: int = 300) -> bool:
        """处理验证码"""
        if not self.check_captcha():
            return True
            
        print("\n" + "="*60)
        print("⚠️  检测到验证码！")
        print("请在浏览器窗口中完成验证码验证")
        print(f"超时时间: {timeout}秒")
        print("="*60 + "\n")
        
        # 显示提示
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
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            time.sleep(3)
            if not self.check_captcha():
                print("✓ 验证码已通过")
                return True
            remaining = int(timeout - (time.time() - start_time))
            if remaining % 30 == 0 and remaining > 0:
                print(f"等待验证码完成... 剩余 {remaining}秒")
        
        print("✗ 验证码处理超时")
        return False

    def open_advanced_search(self):
        """打开知网高级搜索页面"""
        print("  打开知网高级搜索页面...")
        self.tab.get("https://kns.cnki.net/kns8s/AdvSearch")
        time.sleep(3)
        
        # 处理可能的验证码
        self.handle_captcha()
        
    def set_journal_filter(self, journal_name: str):
        """设置文献来源筛选"""
        print(f"  设置文献来源: {journal_name}")
        
        try:
            # 点击"文献来源"下拉或输入框
            # 知网新版界面可能需要点击筛选条件
            
            # 尝试找到文献来源输入框
            # 新版知网界面可能有不同的选择器
            journal_input_selectors = [
                'input[placeholder*="文献来源"]',
                'input[placeholder*="期刊"]',
                '.journal-filter input',
                '[data-field="LY"] input',
                'input[name="publish_from"]',
            ]
            
            journal_input = None
            for selector in journal_input_selectors:
                try:
                    journal_input = self.tab.ele(selector, timeout=2)
                    if journal_input:
                        break
                except:
                    continue
            
            if journal_input:
                journal_input.clear()
                journal_input.input(journal_name)
                print(f"    ✓ 已输入期刊名称: {journal_name}")
                time.sleep(1)
            else:
                # 如果找不到输入框，尝试使用JavaScript设置
                print("    尝试使用JavaScript设置期刊...")
                js_code = f"""
                var inputs = document.querySelectorAll('input');
                for(var i=0; i<inputs.length; i++) {{
                    if(inputs[i].placeholder && inputs[i].placeholder.includes('来源')) {{
                        inputs[i].value = '{journal_name}';
                        inputs[i].dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inputs[i].dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                }}
                return false;
                """
                result = self.tab.run_js(js_code)
                if result:
                    print(f"    ✓ 已通过JS设置期刊名称")
                time.sleep(1)
                
        except Exception as e:
            print(f"    ✗ 设置文献来源出错: {e}")
            
    def set_year_filter(self, year: int = 2025):
        """设置年份筛选"""
        print(f"  设置年份: {year}年至今")
        
        try:
            # 尝试找到年份选择器
            year_selectors = [
                'input[placeholder*="年份"]',
                '.year-filter input',
                '[data-field="YE"] input',
            ]
            
            year_input = None
            for selector in year_selectors:
                try:
                    year_input = self.tab.ele(selector, timeout=2)
                    if year_input:
                        break
                except:
                    continue
            
            if year_input:
                year_input.clear()
                year_input.input(str(year))
                print(f"    ✓ 已设置年份: {year}")
                time.sleep(1)
            else:
                # 尝试使用JavaScript
                js_code = f"""
                var inputs = document.querySelectorAll('input');
                for(var i=0; i<inputs.length; i++) {{
                    if(inputs[i].placeholder && (inputs[i].placeholder.includes('年份') || inputs[i].placeholder.includes('年度'))) {{
                        inputs[i].value = '{year}';
                        inputs[i].dispatchEvent(new Event('input', {{ bubbles: true }}));
                        return true;
                    }}
                }}
                return false;
                """
                self.tab.run_js(js_code)
                
        except Exception as e:
            print(f"    ✗ 设置年份出错: {e}")
            
    def click_search(self):
        """点击搜索按钮"""
        print("  点击搜索按钮...")
        
        try:
            # 尝试多种搜索按钮选择器
            search_btn_selectors = [
                'button:contains("搜索")',
                'button.search-btn',
                '.search-btn',
                'input[type="submit"]',
                'button[type="submit"]',
                '.btn-search',
                '[class*="search"] button',
            ]
            
            search_btn = None
            for selector in search_btn_selectors:
                try:
                    search_btn = self.tab.ele(selector, timeout=2)
                    if search_btn:
                        break
                except:
                    continue
            
            if search_btn:
                search_btn.click()
                print("    ✓ 已点击搜索")
                time.sleep(5)  # 等待搜索结果加载
                
                # 处理验证码
                self.handle_captcha()
                return True
            else:
                # 尝试使用JavaScript点击
                js_code = """
                var buttons = document.querySelectorAll('button');
                for(var i=0; i<buttons.length; i++) {
                    if(buttons[i].textContent.includes('搜索') || buttons[i].textContent.includes('检索')) {
                        buttons[i].click();
                        return true;
                    }
                }
                return false;
                """
                result = self.tab.run_js(js_code)
                if result:
                    print("    ✓ 已通过JS点击搜索")
                    time.sleep(5)
                    self.handle_captcha()
                    return True
                else:
                    print("    ✗ 未找到搜索按钮")
                    return False
                    
        except Exception as e:
            print(f"    ✗ 点击搜索出错: {e}")
            return False
            
    def has_next_page(self) -> bool:
        """检查是否有下一页"""
        try:
            # 尝试多种下一页按钮选择器
            next_selectors = [
                '.next-page:not(.disabled)',
                '.pagination .next:not(.disabled)',
                'a:contains("下一页")',
                'button:contains("下一页")',
                '[class*="next"]',
            ]
            
            for selector in next_selectors:
                try:
                    next_btn = self.tab.ele(selector, timeout=2)
                    if next_btn:
                        # 检查是否禁用
                        class_attr = next_btn.attr("class") or ""
                        if "disabled" not in class_attr and "disable" not in class_attr:
                            return True
                except:
                    continue
                    
            return False
        except:
            return False
            
    def go_to_next_page(self) -> bool:
        """跳转到下一页"""
        try:
            print("  跳转到下一页...")
            
            next_selectors = [
                '.next-page',
                '.pagination .next',
                'a:contains("下一页")',
            ]
            
            for selector in next_selectors:
                try:
                    next_btn = self.tab.ele(selector, timeout=2)
                    if next_btn:
                        next_btn.click()
                        time.sleep(4)
                        self.handle_captcha()
                        return True
                except:
                    continue
                    
            # 尝试JavaScript翻页
            js_code = """
            var buttons = document.querySelectorAll('a, button');
            for(var i=0; i<buttons.length; i++) {
                if(buttons[i].textContent.includes('下一页') || buttons[i].title.includes('下一页')) {
                    buttons[i].click();
                    return true;
                }
            }
            return false;
            """
            result = self.tab.run_js(js_code)
            if result:
                time.sleep(4)
                self.handle_captcha()
                return True
                
            return False
        except Exception as e:
            print(f"    翻页出错: {e}")
            return False
        
    def extract_papers_from_page(self) -> List[Dict]:
        """从当前页面提取论文列表"""
        papers = []
        
        try:
            # 等待结果加载
            print("  等待搜索结果加载...")
            time.sleep(3)
            
            # 尝试多种结果表格选择器
            table_selectors = [
                '.result-table-list',
                '.search-result-list',
                '[class*="result"] table',
                '.article-list',
            ]
            
            table_found = False
            for selector in table_selectors:
                try:
                    self.tab.wait.ele_displayed(f"css:{selector}", timeout=10)
                    table_found = True
                    break
                except:
                    continue
            
            if not table_found:
                print("    未找到结果表格，尝试直接提取...")
            
            # 提取论文行
            row_selectors = [
                '.result-table-list tbody tr',
                '.search-result-list .item',
                '[class*="result"] tr',
                '.article-item',
            ]
            
            rows = []
            for selector in row_selectors:
                try:
                    rows = self.tab.eles(f"css:{selector}")
                    if rows:
                        break
                except:
                    continue
            
            print(f"    找到 {len(rows)} 篇论文")
            
            for row in rows:
                try:
                    paper = self._extract_paper_from_row(row)
                    if paper and paper.get("title"):
                        papers.append(paper)
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"    提取论文列表出错: {e}")
            
        return papers
        
    def _extract_paper_from_row(self, row) -> Dict:
        """从单行提取论文信息"""
        paper = {
            "title": "",
            "authors": [],
            "journal": "",
            "date": "",
            "citations": 0,
            "url": "",
        }
        
        try:
            # 提取标题 - 尝试多种选择器
            title_selectors = [
                '.name a',
                '.title a',
                'a[title]',
                'h3 a',
                '.article-title',
            ]
            
            for selector in title_selectors:
                try:
                    title_elem = row.ele(f"css:{selector}", timeout=1)
                    if title_elem:
                        paper["title"] = title_elem.text.strip()
                        href = title_elem.attr("href")
                        if href:
                            paper["url"] = href if href.startswith("http") else f"https://kns.cnki.net{href}"
                        break
                except:
                    continue
            
            # 提取作者
            author_selectors = [
                '.author',
                '.authors',
                '[class*="author"]',
            ]
            
            for selector in author_selectors:
                try:
                    author_elem = row.ele(f"css:{selector}", timeout=1)
                    if author_elem:
                        authors_text = author_elem.text
                        paper["authors"] = [a.strip() for a in authors_text.replace("；", ";").split(";") if a.strip()]
                        break
                except:
                    continue
            
            # 提取期刊来源
            source_selectors = [
                '.source',
                '.journal',
                '[class*="source"]',
            ]
            
            for selector in source_selectors:
                try:
                    source_elem = row.ele(f"css:{selector}", timeout=1)
                    if source_elem:
                        paper["journal"] = source_elem.text.strip()
                        break
                except:
                    continue
            
            # 提取日期
            date_selectors = [
                '.date',
                '.time',
                '[class*="date"]',
            ]
            
            for selector in date_selectors:
                try:
                    date_elem = row.ele(f"css:{selector}", timeout=1)
                    if date_elem:
                        paper["date"] = date_elem.text.strip()
                        break
                except:
                    continue
            
            # 提取被引次数
            cite_selectors = [
                '.cite',
                '.cited',
                '[class*="cite"]',
            ]
            
            for selector in cite_selectors:
                try:
                    cite_elem = row.ele(f"css:{selector}", timeout=1)
                    if cite_elem:
                        cite_text = cite_elem.text.replace("被引：", "").replace("被引:", "").strip()
                        try:
                            paper["citations"] = int(cite_text) if cite_text else 0
                        except:
                            pass
                        break
                except:
                    continue
                    
        except Exception as e:
            pass
            
        return paper
        
    def extract_paper_detail(self, url: str) -> Dict:
        """提取论文详情"""
        detail = {"abstract": "", "keywords": [], "doi": ""}
        
        if not url:
            return detail
            
        try:
            print(f"    获取详情: {url[:60]}...")
            self.tab.get(url)
            time.sleep(random.uniform(2, 4))
            
            if not self.handle_captcha():
                return detail
            
            # 提取摘要
            abstract_selectors = [
                '.abstract-text',
                '.abstract p',
                '[class*="abstract"] p',
                '#abstract',
            ]
            
            for selector in abstract_selectors:
                try:
                    abstract_elem = self.tab.ele(f"css:{selector}", timeout=3)
                    if abstract_elem:
                        detail["abstract"] = abstract_elem.text.strip()
                        break
                except:
                    continue
            
            # 提取关键词
            keyword_selectors = [
                '.keywords a',
                '.keyword a',
                '[class*="keyword"] a',
            ]
            
            for selector in keyword_selectors:
                try:
                    keyword_elems = self.tab.eles(f"css:{selector}", timeout=3)
                    if keyword_elems:
                        detail["keywords"] = [elem.text.strip() for elem in keyword_elems if elem.text]
                        break
                except:
                    continue
            
            # 提取DOI
            try:
                doi_elem = self.tab.ele('css:.doi, [class*="doi"]', timeout=2)
                if doi_elem:
                    doi_text = doi_elem.text
                    if "DOI" in doi_text.upper():
                        detail["doi"] = doi_text.replace("DOI:", "").replace("DOI：", "").strip()
            except:
                pass
                
        except Exception as e:
            print(f"    提取详情出错: {e}")
            
        return detail
        
    def crawl_journal(self, journal_name: str, max_results: int = 20) -> List[Dict]:
        """爬取单个期刊的论文"""
        print(f"\n{'='*60}")
        print(f"📚 正在爬取期刊: {journal_name}")
        print(f"{'='*60}")
        
        papers = []
        
        try:
            # 1. 打开高级搜索页面
            self.open_advanced_search()
            
            # 2. 设置文献来源（期刊名）
            self.set_journal_filter(journal_name)
            
            # 3. 设置年份（2025年至今）
            self.set_year_filter(2025)
            
            # 4. 点击搜索
            if not self.click_search():
                print("  ✗ 搜索失败")
                return papers
            
            # 5. 提取多页结果
            page_num = 1
            max_pages = (max_results // 10) + 2  # 估算需要的页数
            
            while len(papers) < max_results and page_num <= max_pages:
                print(f"\n  处理第 {page_num} 页...")
                
                # 提取当前页的论文
                page_papers = self.extract_papers_from_page()
                
                if not page_papers:
                    print("    本页未找到论文，结束爬取")
                    break
                
                print(f"    本页找到 {len(page_papers)} 篇论文")
                
                # 获取每篇论文的详情
                for i, paper in enumerate(page_papers):
                    if len(papers) >= max_results:
                        break
                    
                    print(f"    处理第 {len(papers)+1}/{max_results} 篇: {paper.get('title', '')[:40]}...")
                    
                    # 获取详情
                    if paper.get("url"):
                        detail = self.extract_paper_detail(paper["url"])
                        paper.update(detail)
                        
                        # 返回列表页
                        self.tab.back()
                        time.sleep(random.uniform(2, 3))
                    
                    papers.append(paper)
                    
                    # 随机延迟
                    time.sleep(random.uniform(2, 5))
                
                # 检查是否需要翻页
                if len(papers) >= max_results:
                    break
                    
                if self.has_next_page():
                    if not self.go_to_next_page():
                        break
                    page_num += 1
                else:
                    print("    没有更多页面")
                    break
                    
        except Exception as e:
            print(f"  ✗ 爬取过程出错: {e}")
            import traceback
            traceback.print_exc()
            
        print(f"\n  ✓ 期刊 {journal_name} 爬取完成，共 {len(papers)} 篇论文")
        return papers
        
    def crawl_multiple_journals(self, journals: List[str], max_results: int = 20) -> Dict[str, List[Dict]]:
        """爬取多个期刊"""
        results = {}
        
        for journal in journals:
            papers = self.crawl_journal(journal, max_results)
            results[journal] = papers
            
            # 期刊间延迟
            if journal != journals[-1]:  # 不是最后一个期刊
                delay = random.uniform(5, 10)
                print(f"\n  等待 {delay:.1f} 秒后爬取下一个期刊...")
                time.sleep(delay)
            
        return results


def parse_date(date_text: str) -> Optional[datetime]:
    """解析日期文本为datetime对象"""
    if not date_text:
        return None
    
    patterns = [
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
        (r'(\d{4})年(\d{1,2})月(\d{1,2})日', lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
        (r'(\d{4})年(\d{1,2})月', lambda m: datetime(int(m.group(1)), int(m.group(2)), 1)),
        (r'(\d{4})-(\d{1,2})', lambda m: datetime(int(m.group(1)), int(m.group(2)), 1)),
    ]
    
    for pattern, converter in patterns:
        match = re.search(pattern, date_text)
        if match:
            try:
                return converter(match)
            except:
                pass
    
    return None


def convert_to_db_format(papers: List[Dict], journal_name: str) -> List[Dict]:
    """将爬取的论文数据转换为数据库格式"""
    db_papers = []
    
    for paper in papers:
        published_at = parse_date(paper.get("date", ""))
        
        db_paper = {
            "title": paper.get("title", ""),
            "abstract": paper.get("abstract", ""),
            "authors": paper.get("authors", []),
            "url": paper.get("url", ""),
            "source": "cnki",
            "venue": journal_name,
            "published_at": published_at,
            "discipline": "经济学",
            "journal_name": journal_name,
            "journal_issue": "",
            "economics_subfield": None,
            "doi": paper.get("doi") if paper.get("doi") else None,
            "keywords_cn": paper.get("keywords", []),
        }
        
        db_papers.append(db_paper)
    
    return db_papers


async def save_to_database(results: Dict[str, List[Dict]]):
    """将爬取结果保存到数据库"""
    from app.database import AsyncSessionLocal
    from app.crud import PaperCRUD
    from app.schemas import PaperCreate
    from app.scoring import ScoringSystem
    
    print("\n" + "="*60)
    print("💾 正在保存到数据库...")
    print("="*60)
    
    scoring_system = ScoringSystem()
    total_saved = 0
    total_skipped = 0
    
    async with AsyncSessionLocal() as db:
        for journal_name, papers in results.items():
            if not papers:
                continue
                
            print(f"\n  保存 {journal_name} 的 {len(papers)} 篇论文...")
            
            db_papers = convert_to_db_format(papers, journal_name)
            
            for paper_data in db_papers:
                try:
                    # 检查是否已存在
                    existing = await PaperCRUD.get_paper_by_url(db, paper_data["url"])
                    if existing:
                        total_skipped += 1
                        continue
                    
                    # 创建论文记录
                    paper_create = PaperCreate(**paper_data)
                    paper = await PaperCRUD.create_paper(db, paper_create)
                    
                    # 计算分数
                    recency_score = scoring_system.compute_recency_score(paper.published_at)
                    venue_score = scoring_system.compute_venue_score(paper.venue, paper.source)
                    trend_score = 0.5
                    final_score = scoring_system.compute_final_score(
                        recency_score, venue_score, trend_score
                    )
                    
                    # 保存分数
                    await PaperCRUD.create_paper_score(
                        db, paper.id, recency_score, venue_score, trend_score, final_score
                    )
                    
                    total_saved += 1
                    
                except Exception as e:
                    print(f"    保存论文出错: {e}")
                    continue
        
        await db.commit()
    
    print(f"\n✓ 数据库保存完成: 新增 {total_saved} 篇, 跳过 {total_skipped} 篇")
    return total_saved, total_skipped


def save_results_to_file(results: Dict, output_file: str):
    """保存结果到文件"""
    output_path = Path(output_file)
    
    if output_file.endswith('.json'):
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    elif output_file.endswith('.csv'):
        import csv
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = None
            for journal, papers in results.items():
                for paper in papers:
                    row = {
                        '期刊': journal,
                        '标题': paper.get('title', ''),
                        '作者': ';'.join(paper.get('authors', [])),
                        '发表日期': paper.get('date', ''),
                        '被引次数': paper.get('citations', 0),
                        '摘要': paper.get('abstract', ''),
                        '关键词': ';'.join(paper.get('keywords', [])),
                        'DOI': paper.get('doi', ''),
                        '链接': paper.get('url', ''),
                    }
                    if writer is None:
                        writer = csv.DictWriter(f, fieldnames=row.keys())
                        writer.writeheader()
                    writer.writerow(row)
    else:
        with open(output_path, 'w', encoding='utf-8') as f:
            for journal, papers in results.items():
                f.write(f"\n{'='*60}\n")
                f.write(f"期刊: {journal}\n")
                f.write(f"{'='*60}\n\n")
                
                for i, paper in enumerate(papers, 1):
                    f.write(f"[{i}] {paper.get('title', '')}\n")
                    f.write(f"    作者: {', '.join(paper.get('authors', []))}\n")
                    f.write(f"    日期: {paper.get('date', '')}\n")
                    f.write(f"    被引: {paper.get('citations', 0)}\n")
                    f.write(f"    关键词: {', '.join(paper.get('keywords', []))}\n")
                    f.write(f"    链接: {paper.get('url', '')}\n\n")
    
    print(f"\n💾 结果已保存到: {output_path.absolute()}")


def print_summary(results: Dict):
    """打印摘要"""
    print("\n" + "="*60)
    print("📊 爬取结果摘要")
    print("="*60)
    
    total = 0
    for journal, papers in results.items():
        count = len(papers)
        total += count
        print(f"  {journal}: {count} 篇")
    
    print("-"*60)
    print(f"  总计: {total} 篇论文")
    print("="*60)


async def main():
    parser = argparse.ArgumentParser(
        description='知网经济学TOP50期刊论文爬取工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python crawl_cnki_papers.py                          # 爬取所有期刊（每期刊10篇）
  python crawl_cnki_papers.py -j "经济研究" -n 30       # 爬取经济研究30篇
  python crawl_cnki_papers.py --headless -m 5           # 无头模式，爬取前5个期刊
  python crawl_cnki_papers.py --save-to-db              # 保存到数据库
  python crawl_cnki_papers.py -j "经济研究" --save-to-db -n 20
        """
    )
    
    parser.add_argument('-j', '--journal', type=str, help='指定期刊名称（如：经济研究）')
    parser.add_argument('-n', '--max-results', type=int, default=10, help='每个期刊最大爬取数量（默认10）')
    parser.add_argument('-m', '--max-journals', type=int, help='最大爬取期刊数量')
    parser.add_argument('--headless', action='store_true', help='无头模式（不显示浏览器窗口）')
    parser.add_argument('-o', '--output', type=str, default='cnki_papers.json', help='输出文件路径')
    parser.add_argument('--list-journals', action='store_true', help='列出所有支持的期刊')
    parser.add_argument('--save-to-db', action='store_true', help='保存到数据库')
    parser.add_argument('--no-file', action='store_true', help='不保存到文件（仅用于--save-to-db时）')
    
    args = parser.parse_args()
    
    # 列出期刊
    if args.list_journals:
        print("\n支持的期刊列表（按优先级排序）:")
        print("="*60)
        sorted_journals = sorted(
            CNKI_TOP50_JOURNALS.items(),
            key=lambda x: x[1].get("priority", 0),
            reverse=True
        )
        for i, (name, config) in enumerate(sorted_journals, 1):
            print(f"{i:2d}. {name} (优先级: {config['priority']})")
        return
    
    # 确定要爬取的期刊
    if args.journal:
        if args.journal not in CNKI_TOP50_JOURNALS:
            print(f"✗ 不支持的期刊: {args.journal}")
            print(f"请使用 --list-journals 查看支持的期刊列表")
            return
        journals_to_crawl = [args.journal]
    else:
        sorted_journals = sorted(
            CNKI_TOP50_JOURNALS.items(),
            key=lambda x: x[1].get("priority", 0),
            reverse=True
        )
        journals_to_crawl = [name for name, _ in sorted_journals]
        
        if args.max_journals:
            journals_to_crawl = journals_to_crawl[:args.max_journals]
    
    print("\n" + "="*60)
    print("知网经济学TOP50期刊论文爬取工具")
    print("="*60)
    print(f"模式: {'无头' if args.headless else '可视'}")
    print(f"期刊数: {len(journals_to_crawl)}")
    print(f"每期刊: {args.max_results} 篇")
    if not args.no_file:
        print(f"输出文件: {args.output}")
    if args.save_to_db:
        print(f"数据库: /home/joakim/Project/paper_hot/backend/paperpulse.db")
    print("="*60)
    
    # 创建爬虫
    crawler = CNKICrawler(headless=args.headless)
    
    try:
        # 初始化浏览器
        print("\n🚀 正在启动浏览器...")
        crawler.init_browser()
        
        # 开始爬取
        print(f"\n📖 开始爬取 {len(journals_to_crawl)} 个期刊...")
        results = crawler.crawl_multiple_journals(journals_to_crawl, args.max_results)
        
        # 打印摘要
        print_summary(results)
        
        # 保存到文件
        if not args.no_file:
            save_results_to_file(results, args.output)
        
        # 保存到数据库
        if args.save_to_db:
            await save_to_database(results)
        
        print("\n✅ 爬取完成！")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断")
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        crawler.close_browser()


if __name__ == "__main__":
    asyncio.run(main())
