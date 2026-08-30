"""Agent 新增工具的回归保护：get_paper_detail / similar_papers / paper_references / my_library。

与 test_workbench_recall.py 同款内存 SQLite（StaticPool）方案，直接调用工具处理函数：
- 论文定位：paper_id 精确 > 标题精确 > 标题模糊（唯一命中采纳，多命中返回候选）；
- similar_papers 读取预计算的 PaperSimilarity 对（双向 a/b）；
- paper_references：outgoing 读 references_cn 条目，incoming 复用 find_citing_papers 反向匹配；
- my_library 依赖注入的 args["_user_id"]，缺失时拒绝查询（防止跨用户读取）。
"""
import json
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Paper, PaperSimilarity, Favorite, ReadingHistory
from app.agent import _t_get_paper_detail, _t_similar_papers, _t_paper_references, _t_my_library


def _mk_paper(pid: str, title: str, **kw) -> Paper:
    return Paper(
        id=pid, title=title, abstract=kw.get("abstract", f"{title} 的摘要"),
        url=f"https://example.com/{pid}", source="test",
        journal_name=kw.get("journal", "经济研究"), keywords_cn=kw.get("keywords", ["关键词"]),
        published_at=datetime(2026, 1, 1),
        references_cn=kw.get("refs"),
    )


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


def test_get_paper_detail_by_title_and_truncation():
    long_abstract = "很" * 1200

    async def scenario(db):
        db.add(_mk_paper("p1", "目标论文", abstract=long_abstract))
        await db.commit()

        res = await _t_get_paper_detail(db, {"title": "目标论文"})
        assert res["papers"][0]["id"] == "p1"
        assert res["papers"][0]["abstract"].endswith("…（摘要过长已截断）")
        assert len(res["papers"][0]["abstract"]) < 900

        miss = await _t_get_paper_detail(db, {"title": "不存在的论文"})
        assert "note" in miss  # 未找到 → 诚实提示，模型不得编造

        noargs = await _t_get_paper_detail(db, {})
        assert "error" in noargs

    import asyncio
    asyncio.run(_with_db(scenario))


def test_resolve_paper_fuzzy_ambiguity():
    async def scenario(db):
        db.add(_mk_paper("p1", "数字金融与小微企业融资研究"))
        db.add(_mk_paper("p2", "数字金融与区域创新研究"))
        await db.commit()

        res = await _t_similar_papers(db, {"title": "数字金融"})
        assert "candidates" in res and len(res["candidates"]) == 2

    import asyncio
    asyncio.run(_with_db(scenario))


def test_similar_papers_bidirectional_pair():
    async def scenario(db):
        db.add(_mk_paper("p1", "论文甲"))
        db.add(_mk_paper("p2", "论文乙"))
        db.add(PaperSimilarity(paper_id_a="p2", paper_id_b="p1", similarity_score=0.77))
        await db.commit()

        res = await _t_similar_papers(db, {"title": "论文甲"})
        assert res["papers"][0]["id"] == "p2"
        assert res["papers"][0]["similarity"] == 0.77

        none = await _t_similar_papers(db, {"title": "论文乙"})  # 乙在 pair 中也存在
        assert none["papers"][0]["id"] == "p1"

        db.add(_mk_paper("p3", "论文丙"))
        await db.commit()
        empty = await _t_similar_papers(db, {"title": "论文丙"})
        assert empty["papers"] == [] and "note" in empty

    import asyncio
    asyncio.run(_with_db(scenario))


def test_paper_references_outgoing_and_incoming():
    async def scenario(db):
        refs = [{"index": 1, "text": "某经典文献原文", "url": "https://ref.example/1"}]
        db.add(_mk_paper("p1", "引用他人的论文", refs=refs))
        # p2 的参考文献里引用了 p1（URL 精确匹配）
        db.add(_mk_paper("p2", "后续论文", refs=[{"index": 1, "text": "引用了引用他人的论文", "url": "https://example.com/p1"}]))
        await db.commit()

        out = await _t_paper_references(db, {"title": "引用他人的论文"})
        assert out["direction"] == "outgoing" and out["total"] == 1
        assert out["references"][0]["text"] == "某经典文献原文"

        inc = await _t_paper_references(db, {"title": "引用他人的论文", "direction": "incoming"})
        assert inc["total"] == 1
        assert inc["papers"][0]["id"] == "p2"

        # p2 自己的 outgoing：有一条引用条目
        out_p2 = await _t_paper_references(db, {"title": "后续论文", "direction": "outgoing"})
        assert out_p2["total"] == 1 and "p1" not in [x.get("id") for x in out_p2["references"]]

        # 无任何参考文献数据的论文 → 诚实返回空
        db.add(_mk_paper("p3", "没有参考文献的论文"))
        await db.commit()
        empty_out = await _t_paper_references(db, {"title": "没有参考文献的论文", "direction": "outgoing"})
        assert empty_out["total"] == 0 and empty_out["references"] == []

    import asyncio
    asyncio.run(_with_db(scenario))


def test_my_library_requires_user_and_reads_records():
    async def scenario(db):
        db.add(_mk_paper("p1", "收藏的论文"))
        db.add(_mk_paper("p2", "读过的论文"))
        db.add(Favorite(user_id="u1", paper_id="p1"))
        db.add(ReadingHistory(user_id="u1", paper_id="p2"))
        db.add(Favorite(user_id="other", paper_id="p2"))
        await db.commit()

        denied = await _t_my_library(db, {})
        assert "error" in denied  # 无 user_id → 拒绝

        favs = await _t_my_library(db, {"_user_id": "u1"})
        assert favs["kind"] == "favorites" and favs["count"] == 1
        assert favs["papers"][0]["id"] == "p1"

        hist = await _t_my_library(db, {"_user_id": "u1", "kind": "history"})
        assert hist["papers"][0]["id"] == "p2"

        empty = await _t_my_library(db, {"_user_id": "nobody"})
        assert empty["count"] == 0

    import asyncio
    asyncio.run(_with_db(scenario))
