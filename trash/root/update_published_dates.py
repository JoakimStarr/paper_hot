#!/usr/bin/env python3
"""
更新数据库中论文的发布日期（基于期数）
"""

import sqlite3
import re
from datetime import datetime
from pathlib import Path

def update_published_dates():
    """更新数据库中的发布日期"""
    db_file = Path('backend/data/paperpulse.db')
    
    if not db_file.exists():
        print(f"错误: 数据库文件 {db_file} 不存在")
        return
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # 查询所有论文
    cursor.execute("""
        SELECT id, journal_issue, published_at, title
        FROM papers 
        WHERE journal_issue IS NOT NULL
    """)
    
    papers = cursor.fetchall()
    print(f"\n开始更新数据库中的发布日期...")
    print(f"需要更新的论文数: {len(papers)}")
    
    updated_count = 0
    for paper_id, journal_issue, published_at, title in papers:
        if not journal_issue:
            continue
        
        # 从期数中提取期号
        issue_match = re.search(r'第(\d+)期', journal_issue)
        if issue_match:
            issue_num = int(issue_match.group(1))
            month = min(issue_num, 12)
            
            # 从原发布日期中提取年份
            old_date = datetime.fromisoformat(published_at)
            year = old_date.year
            
            # 更新发布日期
            new_date = datetime(year, month, 1)
            cursor.execute("""
                UPDATE papers 
                SET published_at = ? 
                WHERE id = ?
            """, (new_date.isoformat(), paper_id))
            
            updated_count += 1
            if updated_count % 100 == 0:
                print(f"  已更新 {updated_count} 条记录...")
    
    conn.commit()
    
    # 验证更新结果
    cursor.execute("""
        SELECT title, published_at, journal_issue 
        FROM papers 
        WHERE journal_issue IS NOT NULL
        ORDER BY published_at DESC 
        LIMIT 10
    """)
    
    print(f"\n更新后的前10篇论文:")
    for i, (title, published_at, journal_issue) in enumerate(cursor.fetchall(), 1):
        print(f"{i}. {title[:50]}...")
        print(f"   发布日期: {published_at}, 期数: {journal_issue}")
    
    # 按月份统计
    cursor.execute("""
        SELECT COUNT(*) as total, strftime('%Y-%m', published_at) as month 
        FROM papers 
        GROUP BY month 
        ORDER BY month DESC 
        LIMIT 15
    """)
    
    print(f"\n按月份统计:")
    for total, month in cursor.fetchall():
        print(f"  {month}: {total}篇")
    
    conn.close()
    
    print(f"\n更新完成: {updated_count} 条记录")
    print(f"{'='*80}\n")


if __name__ == '__main__':
    print(f"{'='*80}")
    print(f"更新发布日期脚本")
    print(f"{'='*80}\n")
    
    update_published_dates()
    
    print("所有任务完成！")
