#!/usr/bin/env python3
"""
清理数据库中的非论文条目和数据不完整的条目
"""

import sqlite3
import json
from datetime import datetime

def clean_database():
    """清理数据库"""
    db_file = 'backend/data/paperpulse.db'
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    print(f"{'='*80}")
    print(f"数据库清理脚本")
    print(f"{'='*80}")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 1. 删除非论文条目
    non_paper_keywords = [
        '征稿启事', '征稿', '征文', '征订', '稿约', '投稿须知', '投稿指南',
        '总目录', '目录', '索引', '内容提要', '总目次',
        '编辑部公告', '编辑部关于', '编辑部声明', '公告', '声明', '启事', '通知', '更正', '勘误', '补遗',
        '书评', '评介', '学院简介', '中心简介', '新书介绍', '新书评介',
        '会议纪要', '会议综述', '会议报道', '会议简报',
        '新闻', '消息', '简讯', '报道',
        '广告', '致谢名单', '致谢专家', '鸣谢', '致谢',
        '卷首语', '编者按', '导读', '操作指南', '使用指南', '手册',
        '人才招聘', '全球人才招聘', '招生', '培训', '课程', '讲座',
        '版权声明', '著作权', '授权声明',
        '欢迎订阅', '订阅杂志', '订购', '欢迎购买',
    ]
    
    cursor.execute("SELECT id, title FROM papers")
    papers = cursor.fetchall()
    
    non_paper_ids = []
    for paper_id, title in papers:
        for keyword in non_paper_keywords:
            if keyword in title:
                non_paper_ids.append(paper_id)
                print(f"删除非论文条目: {title[:60]}... (关键词: {keyword})")
                break
    
    if non_paper_ids:
        placeholders = ','.join('?' * len(non_paper_ids))
        cursor.execute(f"DELETE FROM papers WHERE id IN ({placeholders})", non_paper_ids)
        print(f"\n✅ 删除了 {len(non_paper_ids)} 个非论文条目\n")
    else:
        print(f"\n✅ 没有发现非论文条目\n")
    
    # 2. 删除数据不完整的条目（缺少作者或关键词）
    cursor.execute("""
        SELECT id, title
        FROM papers
        WHERE 
            (authors IS NULL OR authors = '[]' OR json_array_length(authors) = 0)
            OR (keywords_cn IS NULL OR keywords_cn = '[]' OR json_array_length(keywords_cn) = 0)
    """)
    
    incomplete_papers = cursor.fetchall()
    
    if incomplete_papers:
        print(f"发现 {len(incomplete_papers)} 个数据不完整的条目:")
        for i, (paper_id, title) in enumerate(incomplete_papers[:10], 1):
            print(f"  {i}. {title[:60]}...")
        
        if len(incomplete_papers) > 10:
            print(f"  ... 还有 {len(incomplete_papers) - 10} 个条目")
        
        incomplete_ids = [paper_id for paper_id, _ in incomplete_papers]
        placeholders = ','.join('?' * len(incomplete_ids))
        cursor.execute(f"DELETE FROM papers WHERE id IN ({placeholders})", incomplete_ids)
        print(f"\n✅ 删除了 {len(incomplete_papers)} 个数据不完整的条目\n")
    else:
        print(f"\n✅ 没有发现数据不完整的条目\n")
    
    # 3. 删除相关的 features 和 scores
    cursor.execute("DELETE FROM paper_features WHERE paper_id NOT IN (SELECT id FROM papers)")
    features_deleted = cursor.rowcount
    
    cursor.execute("DELETE FROM paper_scores WHERE paper_id NOT IN (SELECT id FROM papers)")
    scores_deleted = cursor.rowcount
    
    if features_deleted > 0 or scores_deleted > 0:
        print(f"✅ 删除了 {features_deleted} 个 paper_features 记录")
        print(f"✅ 删除了 {scores_deleted} 个 paper_scores 记录\n")
    
    # 提交事务
    conn.commit()
    
    # 4. 验证结果
    cursor.execute("SELECT COUNT(*) FROM papers")
    remaining_papers = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*) FROM papers
        WHERE authors IS NOT NULL AND authors != '[]' AND json_array_length(authors) > 0
    """)
    papers_with_authors = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*) FROM papers
        WHERE keywords_cn IS NOT NULL AND keywords_cn != '[]' AND json_array_length(keywords_cn) > 0
    """)
    papers_with_keywords = cursor.fetchone()[0]
    
    print(f"{'='*80}")
    print(f"清理完成统计:")
    print(f"  剩余论文总数: {remaining_papers}")
    print(f"  有作者的论文: {papers_with_authors}")
    print(f"  有关键词的论文: {papers_with_keywords}")
    print(f"{'='*80}\n")
    
    conn.close()

if __name__ == '__main__':
    clean_database()
