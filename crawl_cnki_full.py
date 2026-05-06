#!/usr/bin/env python3
"""
CNKI 期刊导航完整爬取脚本
爬取知网经济与管理科学分类下的所有期刊论文
"""

import sys
import os
import subprocess

# 自动激活虚拟环境
# 尝试多个可能的虚拟环境路径
possible_venvs = [
    os.path.join(os.path.dirname(__file__), 'backend', '.venv'),
    os.path.join(os.path.dirname(__file__), 'backend', 'venv'),
    os.path.join(os.path.dirname(__file__), '.venv'),
    os.path.join(os.path.dirname(__file__), 'venv'),
]

VENV_PATH = None
for venv in possible_venvs:
    if os.path.exists(venv):
        VENV_PATH = venv
        break

if VENV_PATH:
    # 构建虚拟环境的 Python 路径
    if sys.platform == 'win32':
        venv_python = os.path.join(VENV_PATH, 'Scripts', 'python.exe')
    else:
        venv_python = os.path.join(VENV_PATH, 'bin', 'python')
    
    # 如果当前不是虚拟环境的 Python，则重新启动脚本
    if sys.executable != venv_python and os.path.exists(venv_python):
        print(f"正在激活虚拟环境: {VENV_PATH}")
        result = subprocess.run([venv_python] + sys.argv)
        sys.exit(result.returncode)
    else:
        print(f"✓ 虚拟环境已激活: {VENV_PATH}")
else:
    print(f"⚠ 未找到虚拟环境，使用系统 Python")

import asyncio
import json
import logging
from datetime import datetime

# 设置工作目录
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('cnki_crawl.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

from app.fetchers_cnki_navi import CNKINaviFetcher
from app.database import AsyncSessionLocal
from app.crud import PaperCRUD


async def save_papers_to_db(papers_data: list):
    """保存论文到数据库"""
    saved_count = 0
    skipped_count = 0
    
    async with AsyncSessionLocal() as db:
        for paper_data in papers_data:
            try:
                result = await PaperCRUD.create_paper_from_cnki(db, paper_data)
                if result:
                    saved_count += 1
                    logger.info(f"Saved: {paper_data['title'][:60]}...")
                else:
                    skipped_count += 1
            except Exception as e:
                logger.error(f"Error saving paper: {e}")
                continue
        
        await db.commit()
    
    return saved_count, skipped_count


async def main():
    """主函数"""
    print("="*70)
    print("CNKI 期刊导航完整爬取脚本")
    print("="*70)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-"*70)
    
    fetcher = CNKINaviFetcher(headless=False)
    all_papers = []
    
    try:
        # 步骤1: 获取期刊列表
        print("\n[步骤1/4] 获取期刊列表...")
        journals = fetcher.get_journals_list()
        print(f"✓ 成功获取 {len(journals)} 个期刊")
        
        if not journals:
            print("✗ 未获取到期刊列表，退出")
            return
        
        # 显示期刊列表
        print("\n期刊列表:")
        for i, (name, url) in enumerate(journals.items(), 1):
            print(f"  {i}. {name}")
        
        # 保存期刊列表
        with open('journals_list.json', 'w', encoding='utf-8') as f:
            json.dump(journals, f, ensure_ascii=False, indent=2)
        print(f"\n期刊列表已保存到 journals_list.json")
        
        # 步骤2: 爬取每个期刊的论文
        print("\n[步骤2/4] 开始爬取论文...")
        total_journals = len(journals)
        
        for idx, (journal_name, journal_url) in enumerate(journals.items(), 1):
            print(f"\n{'='*70}")
            print(f"[{idx}/{total_journals}] 爬取期刊: {journal_name}")
            print(f"{'='*70}")
            
            try:
                papers = fetcher.get_papers_from_journal(journal_name, journal_url)
                print(f"✓ 获取到 {len(papers)} 篇论文链接")
                
                # 步骤3: 获取每篇论文的详情
                print(f"\n[步骤3/4] 获取论文详情...")
                for i, paper_info in enumerate(papers, 1):
                    try:
                        print(f"  [{i}/{len(papers)}] {paper_info['title'][:50]}...", end=' ')
                        
                        detail = fetcher.get_paper_detail(paper_info['url'])
                        if detail:
                            paper_data = {
                                **detail,
                                'journal_name': journal_name,
                                'year': paper_info.get('year', datetime.now().year),
                                'source': 'CNKI',
                                'discipline': '经济学'
                            }
                            all_papers.append(paper_data)
                            print("✓")
                        else:
                            print("✗ (无详情)")
                        
                        # 随机延迟
                        fetcher._random_delay(2, 4)
                        
                    except Exception as e:
                        print(f"✗ (错误: {e})")
                        continue
                
                print(f"\n✓ 期刊 '{journal_name}' 完成，当前共 {len(all_papers)} 篇论文")
                
                # 期刊间延迟
                fetcher._random_delay(5, 8)
                
            except Exception as e:
                print(f"✗ 爬取期刊 '{journal_name}' 失败: {e}")
                continue
        
        # 步骤4: 保存数据
        print(f"\n{'='*70}")
        print("[步骤4/4] 保存数据...")
        print(f"{'='*70}")
        
        # 保存到JSON
        output_file = f'cnki_papers_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_papers, f, ensure_ascii=False, indent=2)
        print(f"✓ 论文数据已保存到 {output_file}")
        
        # 保存到数据库
        print(f"\n保存到数据库...")
        saved, skipped = await save_papers_to_db(all_papers)
        print(f"✓ 保存成功: {saved} 篇")
        print(f"✓ 跳过重复: {skipped} 篇")
        
        # 统计信息
        print(f"\n{'='*70}")
        print("爬取统计")
        print(f"{'='*70}")
        print(f"期刊数量: {total_journals}")
        print(f"论文总数: {len(all_papers)}")
        print(f"保存成功: {saved}")
        print(f"跳过重复: {skipped}")
        print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
        
    except KeyboardInterrupt:
        print("\n\n用户中断爬取")
        # 保存已爬取的数据
        if all_papers:
            output_file = f'cnki_papers_interrupted_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(all_papers, f, ensure_ascii=False, indent=2)
            print(f"已保存 {len(all_papers)} 篇论文到 {output_file}")
    
    except Exception as e:
        print(f"\n✗ 爬取过程出错: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        fetcher._close_browser()
        print("\n浏览器已关闭")


if __name__ == '__main__':
    asyncio.run(main())
