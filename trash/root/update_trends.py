#!/usr/bin/env python3
"""
更新主题趋势数据
"""

import asyncio
import sys
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models import Paper, PaperFeatures, TopicTrend
from app.config import settings
from app.crud import PaperCRUD
from datetime import datetime


async def update_trends():
    """更新趋势数据"""
    
    print(f"{'='*80}")
    print(f"更新主题趋势数据")
    print(f"{'='*80}\n")
    
    # 创建数据库引擎
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # 检查论文数量
        from sqlalchemy import select, func
        result = await session.execute(select(func.count(Paper.id)))
        paper_count = result.scalar()
        print(f"数据库中论文总数: {paper_count}")
        
        # 检查有主题的论文数量
        result = await session.execute(
            select(func.count(Paper.id))
            .join(PaperFeatures)
            .where(PaperFeatures.topic.isnot(None))
        )
        paper_with_topic = result.scalar()
        print(f"有主题的论文数: {paper_with_topic}")
        
        if paper_with_topic == 0:
            print("\n⚠️  没有论文有主题标签，无法生成趋势数据")
            print("请先运行 AI 处理来为主题打标签")
            return
        
        # 更新趋势数据
        print(f"\n开始更新趋势数据...")
        keyword_count = await PaperCRUD.update_keyword_trends(session, months_back=12)
        await session.commit()
        
        print(f"✅ 更新了 {keyword_count} 个关键词趋势记录")
        
        # 验证结果
        result = await session.execute(select(func.count(TopicTrend.id)))
        trend_count = result.scalar()
        print(f"\n数据库中趋势记录总数: {trend_count}")
        
        # 显示前10个趋势
        result = await session.execute(
            select(TopicTrend)
            .order_by(TopicTrend.growth_rate.desc())
            .limit(10)
        )
        trends = result.scalars().all()
        
        print(f"\n前10个热门趋势:")
        for i, trend in enumerate(trends, 1):
            print(f"{i}. {trend.topic}: {trend.paper_count}篇, 增长率 {trend.growth_rate*100:.1f}%")
    
    await engine.dispose()
    
    print(f"\n{'='*80}")
    print(f"✅ 趋势数据更新完成！")
    print(f"{'='*80}\n")


if __name__ == '__main__':
    asyncio.run(update_trends())
