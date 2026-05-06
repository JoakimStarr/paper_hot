#!/usr/bin/env python3
"""
PaperPulse 期刊爬虫运行脚本

使用方法:
    python crawl.py --journal 管理世界          # 爬取单期刊
    python crawl.py --all                       # 爬取所有期刊
    python crawl.py --journal 管理世界 --save   # 爬取并保存到数据库
"""

import argparse
import asyncio
import sys
import os
from datetime import datetime
from typing import Dict, List, Any

# 设置工作目录为backend目录，确保使用正确的数据库
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

from backend.app.fetchers import (
    GuanliShijieFetcher,
    JingjiYanjiuFetcher,
    JingjixueJikanFetcher,
    ShijieJingjiFetcher,
    ZhongguoGongyeJingjiFetcher,
    AmericanEconomicReviewFetcher
)

# 期刊配置
JOURNALS = {
    "管理世界": GuanliShijieFetcher,
    "经济研究": JingjiYanjiuFetcher,
    "经济学季刊": JingjixueJikanFetcher,
    "世界经济": ShijieJingjiFetcher,
    "中国工业经济": ZhongguoGongyeJingjiFetcher,
    "AER": AmericanEconomicReviewFetcher,
    "American Economic Review": AmericanEconomicReviewFetcher,
}


class Colors:
    """终端颜色"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """打印标题"""
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{text.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")


def print_progress(current: int, total: int, journal_name: str):
    """打印进度"""
    percent = (current / total) * 100
    bar_length = 30
    filled = int(bar_length * current / total)
    bar = '█' * filled + '░' * (bar_length - filled)
    print(f"\r{Colors.CYAN}进度: [{bar}] {percent:.1f}% ({current}/{total}) - {journal_name}{Colors.ENDC}", end='', flush=True)


def print_result(journal_name: str, count: int, success: bool = True):
    """打印结果"""
    status = f"{Colors.GREEN}✓ 成功{Colors.ENDC}" if success else f"{Colors.FAIL}✗ 失败{Colors.ENDC}"
    print(f"\n{status} {Colors.BOLD}{journal_name}{Colors.ENDC}: 获取 {Colors.CYAN}{count}{Colors.ENDC} 篇论文")


async def crawl_journal(journal_name: str, max_results: int = 50) -> List[Dict[str, Any]]:
    """爬取单个期刊"""
    if journal_name not in JOURNALS:
        print(f"{Colors.FAIL}错误: 未知的期刊 '{journal_name}'{Colors.ENDC}")
        print(f"支持的期刊: {', '.join(JOURNALS.keys())}")
        return []
    
    fetcher_class = JOURNALS[journal_name]
    fetcher = fetcher_class()
    
    try:
        papers = await fetcher.fetch_papers(max_results=max_results)
        return papers
    except Exception as e:
        print(f"{Colors.FAIL}爬取 {journal_name} 时出错: {str(e)}{Colors.ENDC}")
        return []


async def crawl_all_journals(max_results: int = 50) -> Dict[str, List[Dict[str, Any]]]:
    """爬取所有期刊"""
    results = {}
    journals = list(JOURNALS.keys())
    
    print_header("开始爬取所有期刊")
    print(f"共 {len(journals)} 个期刊\n")
    
    for i, journal_name in enumerate(journals, 1):
        print_progress(i, len(journals), journal_name)
        papers = await crawl_journal(journal_name, max_results)
        results[journal_name] = papers
        print_result(journal_name, len(papers), len(papers) > 0)
    
    return results


def print_summary(results: Dict[str, List[Dict[str, Any]]]):
    """打印汇总结果"""
    print_header("爬取结果汇总")
    
    total_papers = 0
    successful_journals = 0
    
    for journal_name, papers in results.items():
        count = len(papers)
        total_papers += count
        if count > 0:
            successful_journals += 1
            print(f"{Colors.GREEN}✓{Colors.ENDC} {journal_name:20s}: {Colors.CYAN}{count:3d}{Colors.ENDC} 篇")
        else:
            print(f"{Colors.FAIL}✗{Colors.ENDC} {journal_name:20s}: {Colors.WARNING}{count:3d}{Colors.ENDC} 篇")
    
    print(f"\n{Colors.BOLD}总计:{Colors.ENDC}")
    print(f"  - 成功期刊: {Colors.GREEN}{successful_journals}{Colors.ENDC} / {len(results)}")
    print(f"  - 总论文数: {Colors.CYAN}{total_papers}{Colors.ENDC}")


def save_to_database(papers: List[Dict[str, Any]], journal_name: str):
    """保存论文到数据库"""
    try:
        from backend.app.database import AsyncSessionLocal
        from backend.app.crud import PaperCRUD
        from backend.app.schemas import PaperCreate
        import asyncio
        
        async def _save():
            async with AsyncSessionLocal() as db:
                saved_count = 0
                for paper_data in papers:
                    try:
                        # 检查是否已存在
                        existing = await PaperCRUD.get_paper_by_url(db, paper_data["url"])
                        if existing:
                            continue
                        
                        # 创建论文
                        paper_create = PaperCreate(**paper_data)
                        await PaperCRUD.create_paper(db, paper_create)
                        saved_count += 1
                    except Exception as e:
                        print(f"  保存论文失败: {str(e)[:50]}")
                
                await db.commit()
                return saved_count
        
        saved = asyncio.run(_save())
        print(f"{Colors.GREEN}✓ 已保存 {saved} 篇论文到数据库{Colors.ENDC}")
        
    except Exception as e:
        print(f"{Colors.FAIL}✗ 保存到数据库失败: {str(e)}{Colors.ENDC}")


def main():
    parser = argparse.ArgumentParser(
        description='PaperPulse 期刊爬虫',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python crawl.py --journal 管理世界              # 爬取管理世界
  python crawl.py --journal 经济研究 --save       # 爬取并保存
  python crawl.py --all                           # 爬取所有期刊
  python crawl.py --all --save                    # 爬取所有并保存
        """
    )
    
    parser.add_argument('--journal', type=str, help='指定要爬取的期刊名称')
    parser.add_argument('--all', action='store_true', help='爬取所有期刊')
    parser.add_argument('--save', action='store_true', help='保存到数据库')
    parser.add_argument('--max-results', type=int, default=50, help='每个期刊最大爬取数量 (默认: 50)')
    
    args = parser.parse_args()
    
    if not args.journal and not args.all:
        parser.print_help()
        print(f"\n{Colors.WARNING}请指定 --journal 或 --all{Colors.ENDC}")
        sys.exit(1)
    
    print_header("PaperPulse 期刊爬虫")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    if args.journal:
        # 爬取单期刊
        print(f"{Colors.BOLD}爬取期刊: {args.journal}{Colors.ENDC}\n")
        papers = asyncio.run(crawl_journal(args.journal, args.max_results))
        print_result(args.journal, len(papers), len(papers) > 0)
        
        if args.save and papers:
            print(f"\n正在保存到数据库...")
            save_to_database(papers, args.journal)
    
    elif args.all:
        # 爬取所有期刊
        results = asyncio.run(crawl_all_journals(args.max_results))
        print_summary(results)
        
        if args.save:
            print(f"\n{Colors.BOLD}正在保存到数据库...{Colors.ENDC}")
            for journal_name, papers in results.items():
                if papers:
                    print(f"\n保存 {journal_name}...")
                    save_to_database(papers, journal_name)
    
    print(f"\n{Colors.GREEN}完成!{Colors.ENDC}")
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


if __name__ == '__main__':
    main()
