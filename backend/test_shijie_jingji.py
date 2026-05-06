import asyncio
import sys
sys.path.insert(0, '/home/joakim/Project/paper_hot/backend')

from app.fetchers import ShijieJingjiFetcher
from datetime import datetime, timedelta

async def test_shijie_jingji():
    print("测试世界经济期刊爬取器...")
    
    fetcher = ShijieJingjiFetcher()
    papers = await fetcher.fetch_papers(
        start_date=datetime.now() - timedelta(days=365),
        max_results=20
    )
    
    print(f"\n成功获取 {len(papers)} 篇论文\n")
    
    if papers:
        print("=" * 80)
        for i, paper in enumerate(papers[:5], 1):
            print(f"\n论文 {i}:")
            print(f"标题: {paper['title']}")
            print(f"作者: {', '.join(paper['authors'])}")
            print(f"期号: {paper.get('issue', 'N/A')}")
            print(f"摘要: {paper['abstract'][:100]}...")
            print(f"URL: {paper['url']}")
            print("-" * 80)
    else:
        print("未获取到论文，请检查网络连接或网站是否可访问")

if __name__ == "__main__":
    asyncio.run(test_shijie_jingji())
