import asyncio
import sys
sys.path.insert(0, '/home/joakim/Project/paper_hot/backend')

from app.fetchers import JingjiYanjiuFetcher, GuanliShijieFetcher
from datetime import datetime, timedelta

async def test_fetchers():
    print("测试经济学期刊爬取器...")
    
    # 测试经济研究爬取器
    fetcher1 = JingjiYanjiuFetcher()
    papers1 = await fetcher1.fetch_papers(
        start_date=datetime.now() - timedelta(days=180),
        max_results=10
    )
    print(f"\n经济研究: 获取了 {len(papers1)} 篇论文")
    if papers1:
        print(f"第一篇论文: {papers1[0]['title']}")
    
    # 测试管理世界爬取器
    fetcher2 = GuanliShijieFetcher()
    papers2 = await fetcher2.fetch_papers(
        start_date=datetime.now() - timedelta(days=180),
        max_results=10
    )
    print(f"\n管理世界: 获取了 {len(papers2)} 篇论文")
    if papers2:
        print(f"第一篇论文: {papers2[0]['title']}")

if __name__ == "__main__":
    asyncio.run(test_fetchers())
