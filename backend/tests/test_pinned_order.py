"""置顶排序回归保护（PaperCRUD.get_papers pinned_ids）。

背景：case(tuple(whens)) 未解包生成器，置顶 ≥2 篇时 (cond, val) 元组被当作
SQL 参数绑定 → 列表 500（"type 'tuple' is not supported"）。
本测试锁住：多枚置顶时列表正常返回且置顶论文按置顶时间倒序恒排最前。
"""
import asyncio
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Paper, PaperScore, PinnedPaper
from app.crud import PaperCRUD


async def _with_db(fn):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as db:
            return await fn(db)
    finally:
        await engine.dispose()


def _mk_paper(pid: str, title: str) -> Paper:
    return Paper(
        id=pid, title=title, abstract=f"{title} 摘要",
        url=f"https://example.com/{pid}", source="test",
        published_at=datetime(2026, 1, 1),
    )


async def _seed(db):
    import random
    for i, (pid, title) in enumerate((("a", "论文A"), ("b", "论文B"), ("c", "论文C"))):
        db.add(_mk_paper(pid, title))
        # 列表查询 INNER JOIN paper_scores，种子必须带评分行
        db.add(PaperScore(paper_id=pid, final_score=0.9 - i * 0.1))
    # 置顶顺序（created_at 倒序 = 最新置顶在前）：b 最先置顶，其次 a
    db.add(PinnedPaper(user_id="local", paper_id="b"))
    db.add(PinnedPaper(user_id="local", paper_id="a"))
    await db.commit()


def test_two_pins_do_not_crash_and_order_first():
    """置顶 2 篇：不触发 tuple 绑定 500，且置顶论文排最前。"""

    async def scenario(db):
        await _seed(db)
        papers, total = await PaperCRUD.get_papers(
            db, page=1, page_size=10,
            pinned_ids=["a", "b"],  # created_at 倒序已由路由排好
        )
        assert total == 3
        ids = [p.id for p in papers]
        assert ids[:2] == ["a", "b"], f"置顶论文应按传入顺序排最前，实际 {ids}"
        assert "c" in ids
        return True

    assert asyncio.run(_with_db(scenario))


def test_empty_pins_normal_order():
    async def scenario(db):
        await _seed(db)
        papers, total = await PaperCRUD.get_papers(db, page=1, page_size=10, pinned_ids=[])
        assert total == 3
        return True

    assert asyncio.run(_with_db(scenario))
