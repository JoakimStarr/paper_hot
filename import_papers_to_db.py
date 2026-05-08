#!/usr/bin/env python3
"""
将 paper_details_history.json 中的论文数据导入到数据库
"""

import json
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from app.crud import PaperCRUD
from app.database import AsyncSessionLocal


async def import_papers_from_json():
    """从 JSON 文件导入论文到数据库"""
    json_file = Path('backend/data/paper_details_history.json')
    
    if not json_file.exists():
        print(f"文件不存在: {json_file}")
        return
    
    print(f"正在读取 {json_file}...")
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    details = data.get('details', {})
    total = len(details)
    success = 0
    skipped = 0
    failed = 0
    
    print(f"共找到 {total} 篇论文，开始导入...")
    print("=" * 60)
    
    async with AsyncSessionLocal() as db:
        for i, (url, paper_entry) in enumerate(details.items(), 1):
            # 只导入状态为 1（成功获取）的论文
            if paper_entry.get('status') != 1:
                print(f"[{i}/{total}] 跳过（未成功获取）: {url[:60]}...")
                skipped += 1
                continue
            
            paper_data = paper_entry.get('data', {})
            if not paper_data:
                print(f"[{i}/{total}] 跳过（无数据）: {url[:60]}...")
                skipped += 1
                continue
            
            # 添加期刊名称到 paper_data
            journal_name = paper_entry.get('journal_name', '')
            paper_data['journal_name'] = journal_name
            
            # 从 DOI 或 URL 中提取年份
            year = 2026  # 默认年份
            doi = paper_data.get('doi', '')
            if doi:
                # 尝试从 DOI 中提取年份，如 10.19581/j.cnki.ciejournal.2026.03.001
                import re
                match = re.search(r'\.(\d{4})\.', doi)
                if match:
                    year = int(match.group(1))
            paper_data['year'] = year
            
            title = paper_data.get('title', '')[:50]
            print(f"[{i}/{total}] 导入: {title}...")
            
            try:
                result = await PaperCRUD.create_paper_from_cnki(db, paper_data)
                if result:
                    success += 1
                else:
                    skipped += 1  # 已存在
            except Exception as e:
                print(f"  ✗ 导入失败: {e}")
                failed += 1
            
            # 每 10 篇提交一次
            if i % 10 == 0:
                await db.commit()
                print(f"  已提交 {i} 篇论文")
        
        # 最后提交剩余的
        await db.commit()
    
    print("=" * 60)
    print(f"导入完成!")
    print(f"  成功: {success}")
    print(f"  跳过: {skipped}")
    print(f"  失败: {failed}")
    print(f"  总计: {total}")


if __name__ == '__main__':
    asyncio.run(import_papers_from_json())
