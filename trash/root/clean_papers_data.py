#!/usr/bin/env python3
"""
清理 papers_history.json 中的非论文条目
并更新发布日期格式（基于期数）
"""

import json
import re
from datetime import datetime
from pathlib import Path
from collections import Counter

# 非论文过滤关键词（与 cnki_paper_captcha.py 保持一致）
SKIP_KEYWORDS = [
    '征稿启事', '征稿', '征文', '征订', '稿约', '投稿须知', '投稿指南',
    '总目录', '目录', '索引', '内容提要',
    '编辑部公告', '编辑部关于', '编辑部声明', '公告', '声明', '启事', '通知', '更正', '勘误', '补遗',
    '书评', '评介', '学院简介', '中心简介', '新书介绍', '新书评介',
    '会议纪要', '会议综述', '会议报道', '会议简报',
    '新闻', '消息', '简讯', '报道',
    '广告', '致谢名单', '致谢专家', '鸣谢',
    '卷首语', '编者按', '导读', '操作指南', '使用指南', '手册',
    '人才招聘', '全球人才招聘', '招生', '培训', '课程', '讲座',
    '版权声明', '著作权', '授权声明',
    '欢迎订阅', '订阅杂志', '订购', '欢迎购买',
]


def is_non_paper(title: str) -> tuple[bool, str]:
    """判断是否为非论文条目"""
    for keyword in SKIP_KEYWORDS:
        if keyword in title:
            return True, keyword
    return False, ''


def clean_papers_history():
    """清理 papers_history.json"""
    data_file = Path('backend/data/papers_history.json')
    
    if not data_file.exists():
        print(f"错误: 文件 {data_file} 不存在")
        return
    
    # 加载数据
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"开始清理数据...")
    print(f"原始数据最后更新时间: {data.get('last_updated', '未知')}")
    
    # 统计信息
    total_before = 0
    total_after = 0
    removed_items = []
    keyword_stats = Counter()
    
    # 清理数据
    papers_data = data.get('papers', {})
    for journal_name, years in papers_data.items():
        for year, issues in years.items():
            for issue, issue_data in issues.items():
                if 'papers' not in issue_data:
                    continue
                
                papers = issue_data['papers']
                total_before += len(papers)
                
                # 过滤非论文条目
                cleaned_papers = []
                for paper in papers:
                    title = paper.get('title', '')
                    is_non, keyword = is_non_paper(title)
                    
                    if is_non:
                        removed_items.append({
                            'journal': journal_name,
                            'year': year,
                            'issue': issue,
                            'title': title,
                            'keyword': keyword
                        })
                        keyword_stats[keyword] += 1
                    else:
                        cleaned_papers.append(paper)
                
                # 更新数据
                issue_data['papers'] = cleaned_papers
                total_after += len(cleaned_papers)
    
    # 更新最后更新时间
    data['last_updated'] = datetime.now().isoformat()
    
    # 保存清理后的数据
    backup_file = data_file.with_suffix('.json.backup')
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n备份文件已保存到: {backup_file}")
    
    # 保存清理后的数据
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"清理后的数据已保存到: {data_file}")
    
    # 打印统计信息
    print(f"\n{'='*80}")
    print(f"清理统计:")
    print(f"  清理前总数: {total_before}")
    print(f"  清理后总数: {total_after}")
    print(f"  删除条目数: {total_before - total_after}")
    print(f"  删除比例: {(total_before - total_after) / total_before * 100:.2f}%")
    
    print(f"\n删除条目关键词统计:")
    for keyword, count in keyword_stats.most_common():
        print(f"  {keyword}: {count}次")
    
    print(f"\n删除的条目详情 (前20个):")
    for item in removed_items[:20]:
        print(f"  [{item['journal']}] {item['year']}年第{item['issue']}期: {item['title'][:60]}... (关键词: {item['keyword']})")
    
    if len(removed_items) > 20:
        print(f"  ... 还有 {len(removed_items) - 20} 个条目")
    
    print(f"{'='*80}\n")


def update_published_dates():
    """更新数据库中的发布日期（基于期数）"""
    import sqlite3
    from datetime import datetime
    
    db_file = Path('backend/paperpulse.db')
    
    if not db_file.exists():
        print(f"错误: 数据库文件 {db_file} 不存在")
        return
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # 查询所有论文
    cursor.execute("""
        SELECT id, journal_issue, published_at 
        FROM papers 
        WHERE journal_issue IS NOT NULL
    """)
    
    papers = cursor.fetchall()
    print(f"\n开始更新数据库中的发布日期...")
    print(f"需要更新的论文数: {len(papers)}")
    
    updated_count = 0
    for paper_id, journal_issue, published_at in papers:
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
    
    conn.commit()
    conn.close()
    
    print(f"更新完成: {updated_count} 条记录")
    print(f"{'='*80}\n")


if __name__ == '__main__':
    print(f"{'='*80}")
    print(f"数据清理脚本")
    print(f"{'='*80}\n")
    
    # 清理 papers_history.json
    clean_papers_history()
    
    # 更新数据库中的发布日期
    update_published_dates()
    
    print("所有任务完成！")
