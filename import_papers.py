#!/usr/bin/env python3
"""
直接导入爬取的论文到数据库
"""

import asyncio
import sys
import os

# 设置工作目录
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

from app.fetchers import (
    GuanliShijieFetcher,
    JingjiYanjiuFetcher,
    JingjixueJikanFetcher,
    ShijieJingjiFetcher,
    ZhongguoGongyeJingjiFetcher,
    AmericanEconomicReviewFetcher
)
from app.database import AsyncSessionLocal
from app.crud import PaperCRUD
from app.schemas import PaperCreate
from datetime import datetime

JOURNALS = {
    "管理世界": GuanliShijieFetcher,
    "经济研究": JingjiYanjiuFetcher,
    "经济学季刊": JingjixueJikanFetcher,
    "世界经济": ShijieJingjiFetcher,
    "中国工业经济": ZhongguoGongyeJingjiFetcher,
    "American Economic Review": AmericanEconomicReviewFetcher,
}


async def import_journal(journal_name: str, max_results: int = 50):
    """导入单个期刊的论文"""
    print(f"\n{'='*60}")
    print(f"正在爬取: {journal_name}")
    print('='*60)
    
    if journal_name not in JOURNALS:
        print(f"❌ 未知的期刊: {journal_name}")
        return 0
    
    fetcher_class = JOURNALS[journal_name]
    fetcher = fetcher_class()
    
    try:
        # 爬取论文（不限制日期）
        papers = await fetcher.fetch_papers(max_results=max_results)
        print(f"✓ 爬取到 {len(papers)} 篇论文")
        
        if not papers:
            return 0
        
        # 保存到数据库
        saved_count = 0
        skipped_count = 0
        error_count = 0
        
        async with AsyncSessionLocal() as db:
            for paper_data in papers:
                try:
                    # 检查是否已存在
                    existing = await PaperCRUD.get_paper_by_url(db, paper_data["url"])
                    if existing:
                        skipped_count += 1
                        continue
                    
                    # 处理DOI字段
                    if paper_data.get("doi") == "" or paper_data.get("doi") is None:
                        paper_data["doi"] = None
                    
                    # 创建论文
                    paper_create = PaperCreate(**paper_data)
                    paper = await PaperCRUD.create_paper(db, paper_create)
                    
                    # 创建基本特征（空）
                    await PaperCRUD.create_paper_features(
                        db,
                        paper.id,
                        summary="",
                        keywords=[],
                        embedding=None,
                        topic=None
                    )
                    
                    saved_count += 1
                    print(f"  ✓ {paper.title[:50]}...")
                    
                except Exception as e:
                    error_count += 1
                    print(f"  ✗ 保存失败: {str(e)[:60]}")
                    continue
            
            await db.commit()
        
        print(f"\n结果: 保存 {saved_count} 篇, 跳过 {skipped_count} 篇, 失败 {error_count} 篇")
        return saved_count
        
    except Exception as e:
        print(f"❌ 爬取失败: {str(e)}")
        return 0


async def import_all_journals():
    """导入所有期刊"""
    print("\n" + "="*60)
    print("PaperPulse 论文导入工具")
    print("="*60)
    
    total_saved = 0
    
    for journal_name in JOURNALS.keys():
        count = await import_journal(journal_name)
        total_saved += count
    
    print("\n" + "="*60)
    print(f"总计导入: {total_saved} 篇论文")
    print("="*60)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='导入论文到数据库')
    parser.add_argument('--journal', type=str, help='指定期刊名称')
    parser.add_argument('--all', action='store_true', help='导入所有期刊')
    parser.add_argument('--max-results', type=int, default=50, help='每期刊最大数量')
    
    args = parser.parse_args()
    
    if args.journal:
        asyncio.run(import_journal(args.journal, args.max_results))
    elif args.all:
        asyncio.run(import_all_journals())
    else:
        parser.print_help()
        print("\n示例:")
        print("  python import_papers.py --journal 管理世界")
        print("  python import_papers.py --all")
