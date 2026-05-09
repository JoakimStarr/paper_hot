#!/usr/bin/env python3
"""
将 papers_history.json 和 paper_details_history.json 中的数据导入数据库
"""

import json
import re
import asyncio
from datetime import datetime
from pathlib import Path
import sys

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models import Paper, PaperFeatures, PaperScore
from app.config import settings


async def import_papers():
    """导入论文数据到数据库"""
    
    # 加载数据
    papers_file = Path('backend/data/papers_history.json')
    details_file = Path('backend/data/paper_details_history.json')
    
    if not papers_file.exists():
        print(f"错误: 文件 {papers_file} 不存在")
        return
    
    with open(papers_file, 'r', encoding='utf-8') as f:
        papers_data = json.load(f)
    
    details_data = {}
    if details_file.exists():
        with open(details_file, 'r', encoding='utf-8') as f:
            details_data = json.load(f)
    
    print(f"开始导入数据...")
    print(f"论文数据最后更新: {papers_data.get('last_updated', '未知')}")
    print(f"详情数据最后更新: {details_data.get('last_updated', '未知')}")
    
    # 创建数据库引擎
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # 统计信息
    total_papers = 0
    imported_papers = 0
    skipped_papers = 0
    error_papers = 0
    
    async with async_session() as session:
        # 遍历所有期刊
        for journal_name, years in papers_data.get('papers', {}).items():
            print(f"\n处理期刊: {journal_name}")
            
            for year, issues in years.items():
                print(f"  处理年份: {year}")
                
                for issue, issue_data in issues.items():
                    if 'papers' not in issue_data:
                        continue
                    
                    papers = issue_data['papers']
                    total_papers += len(papers)
                    
                    for paper in papers:
                        title = paper.get('title', '')
                        url = paper.get('url', '')
                        
                        if not url:
                            skipped_papers += 1
                            continue
                        
                        try:
                            # 检查是否已存在
                            from sqlalchemy import select
                            result = await session.execute(
                                select(Paper).where(Paper.url == url)
                            )
                            existing = result.scalar_one_or_none()
                            
                            if existing:
                                skipped_papers += 1
                                continue
                            
                            # 获取详情数据
                            details = details_data.get('details', {}).get(url, {}).get('data', {})
                            
                            # 验证必需字段：作者和关键词
                            authors = details.get('authors', [])
                            keywords = details.get('keywords', [])
                            
                            if not authors or len(authors) == 0:
                                print(f"    跳过（无作者）: {title[:40]}...")
                                skipped_papers += 1
                                continue
                            
                            if not keywords or len(keywords) == 0:
                                print(f"    跳过（无关键词）: {title[:40]}...")
                                skipped_papers += 1
                                continue
                            
                            # 解析年份和期数
                            year_int = int(year)
                            journal_issue = f"{year}年第{issue}期"
                            
                            # 根据期数设置发布日期
                            issue_num = int(issue)
                            month = min(issue_num, 12)
                            published_at = datetime(year_int, month, 1)
                            
                            # 创建论文记录
                            db_paper = Paper(
                                title=details.get('title', title),
                                abstract=details.get('abstract', ''),
                                authors=authors,
                                url=url,
                                doi=details.get('doi') or None,
                                source='CNKI',
                                venue=journal_name,
                                published_at=published_at,
                                discipline='经济学',
                                journal_name=journal_name,
                                journal_issue=journal_issue,
                                keywords_cn=keywords
                            )
                            
                            session.add(db_paper)
                            await session.flush()
                            
                            imported_papers += 1
                            
                            if imported_papers % 50 == 0:
                                print(f"    已导入 {imported_papers} 篇论文...")
                        
                        except Exception as e:
                            print(f"    错误: {title[:40]}... - {str(e)}")
                            error_papers += 1
        
        # 提交事务
        await session.commit()
    
    # 打印统计信息
    print(f"\n{'='*80}")
    print(f"导入统计:")
    print(f"  总论文数: {total_papers}")
    print(f"  成功导入: {imported_papers}")
    print(f"  跳过（已存在）: {skipped_papers}")
    print(f"  错误: {error_papers}")
    print(f"{'='*80}\n")
    
    await engine.dispose()


if __name__ == '__main__':
    print(f"{'='*80}")
    print(f"数据导入脚本")
    print(f"{'='*80}\n")
    
    asyncio.run(import_papers())
    
    print("导入完成！")
