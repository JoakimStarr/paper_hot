"""相关文献推荐接口（POST /topic-projects/{id}/recommend-papers）回归保护。

内存 SQLite（StaticPool 共享单连接）建库后直接调用路由函数，不依赖 httpx/TestClient。
聚合推荐会走 `_retrieve_similar_papers`（选题方向召回，真实实现会触发 embedding/AI），
测试里统一 monkeypatch 为受控数据，只验证推荐接口自身的合并/排除/排序逻辑。

覆盖场景：
- 项目不存在 / 非本人项目 → 404
- 文献集为空：退化为纯选题方向召回；无数据时 → no_results
- 选题方向召回 + 参考文献相似召回融合（同篇取最大相似度，via_title 归属正确）
- 已在文献集的论文被排除
- paper_id 单种子召回 / 非法 paper_id 降级
- limit 边界钳制
"""
import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Paper, TopicProject, ProjectPaper, PaperSimilarity
from app.routers.workbench import recommend_project_papers, RecommendRequest


def _uid() -> SimpleNamespace:
    return SimpleNamespace(headers={"x-user-id": "local"})


def _mk_paper(pid: str, title: str) -> Paper:
    return Paper(
        id=pid, title=title, abstract=f"{title} 的摘要",
        url=f"https://example.com/{pid}", source="test",
        journal_name="经济研究", keywords_cn=[title],
        published_at=datetime(2026, 1, 1),
    )


async def _with_db(fn):
    """内存库 + 单连接池：种子写入与请求读取共享同一数据。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as db:
            return await fn(db)
    finally:
        await engine.dispose()


async def _seed_project(db, project_id=1, user_id="local", papers=(), project_papers=(), similarities=()):
    db.add(TopicProject(id=project_id, user_id=user_id, title="数字经济与平台治理"))
    for p in papers:
        db.add(p)
    for uid, pid, sim in project_papers:
        db.add(ProjectPaper(user_id=uid, project_id=project_id, paper_id=pid, similarity=sim))
    for a, b, score in similarities:
        db.add(PaperSimilarity(paper_id_a=a, paper_id_b=b, similarity_score=score))
    await db.commit()


def _fake_retrieve(papers):
    """构造假的 _retrieve_similar_papers：返回受控的选题方向召回结果。"""

    async def fake(db, topic, k=30):
        return papers, "embedding"

    return fake


class TestRecommendPapersExceptions:
    def test_project_not_found(self):
        async def scenario(db):
            with pytest.raises(HTTPException) as ei:
                await recommend_project_papers(999, RecommendRequest(limit=10), request=_uid(), db=db, token=True)
            return ei.value.status_code
        assert asyncio.run(_with_db(scenario)) == 404

    def test_project_of_other_user(self):
        async def scenario(db):
            await _seed_project(db, project_id=1, user_id="alice")
            with pytest.raises(HTTPException) as ei:
                await recommend_project_papers(1, RecommendRequest(limit=10), request=_uid(), db=db, token=True)
            return ei.value.status_code
        assert asyncio.run(_with_db(scenario)) == 404


class TestRecommendPapersTopicFallback:
    """文献集为空时退化为纯选题方向推荐。"""

    def test_no_references_uses_topic_direction(self, monkeypatch):
        monkeypatch.setattr(
            "app.routers.workbench._retrieve_similar_papers",
            _fake_retrieve([
                {"id": "ta", "title": "方向相关论文A", "abstract": "A", "journal_name": "经济研究",
                 "source": "test", "published_at": "2026-01-01", "keywords": [], "similarity": 0.72},
            ]),
        )

        async def scenario(db):
            topic_paper = _mk_paper("ta", "方向相关论文A")
            await _seed_project(db, project_id=1, user_id="local", papers=[topic_paper])
            return await recommend_project_papers(1, RecommendRequest(limit=10), request=_uid(), db=db, token=True)
        res = asyncio.run(_with_db(scenario))
        assert res["mode"] == "topic"
        assert len(res["papers"]) == 1
        assert res["papers"][0]["id"] == "ta"
        assert res["papers"][0]["via_title"] is None  # 方向召回 → 前端显示「基于选题方向」

    def test_no_references_and_no_data_no_results(self, monkeypatch):
        monkeypatch.setattr(
            "app.routers.workbench._retrieve_similar_papers", _fake_retrieve([])
        )

        async def scenario(db):
            await _seed_project(db, project_id=1, user_id="local", papers=[])
            return await recommend_project_papers(1, RecommendRequest(limit=10), request=_uid(), db=db, token=True)
        res = asyncio.run(_with_db(scenario))
        assert res["mode"] == "no_results"
        assert res["papers"] == []


class TestRecommendPapersRanking:
    def test_merged_topic_and_reference(self, monkeypatch):
        """融合场景：同篇论文同时被方向召回与文献相似召回，取最大相似度与对应的 via_title。"""
        # 方向召回 ta=0.80, sa=0.30；文献相似召回 sa=0.95（经种子 s1）
        monkeypatch.setattr(
            "app.routers.workbench._retrieve_similar_papers",
            _fake_retrieve([
                {"id": "ta", "title": "方向相关论文A", "abstract": "A", "journal_name": "经济研究",
                 "source": "test", "published_at": "2026-01-01", "keywords": [], "similarity": 0.80},
                {"id": "sa", "title": "文献相似论文A", "abstract": "A", "journal_name": "经济研究",
                 "source": "test", "published_at": "2026-01-01", "keywords": [], "similarity": 0.30},
            ]),
        )

        async def scenario(db):
            seed1 = _mk_paper("s1", "数字经济")
            sim_a = _mk_paper("sa", "文献相似论文A")
            sim_b = _mk_paper("sb", "文献相似论文B")
            topic_only = _mk_paper("ta", "方向相关论文A")
            await _seed_project(
                db, project_id=1, user_id="local",
                papers=[seed1, sim_a, sim_b, topic_only],
                project_papers=[("local", "s1", 0.9)],
                similarities=[("s1", "sa", 0.95), ("s1", "sb", 0.60)],
            )
            return await recommend_project_papers(1, RecommendRequest(limit=10), request=_uid(), db=db, token=True)
        res = asyncio.run(_with_db(scenario))
        assert res["mode"] == "similarity"
        ids = [x["id"] for x in res["papers"]]
        assert ids == ["sa", "ta", "sb"]  # 0.95 > 0.80 > 0.60 降序
        by_id = {x["id"]: x for x in res["papers"]}
        # sa 同时被方向召回(0.30)与文献相似召回(0.95) → 取 0.95，via_title 为种子标题
        assert by_id["sa"]["similarity"] == 0.95
        assert by_id["sa"]["via_title"] == "数字经济"
        assert by_id["sb"]["similarity"] == 0.60
        assert by_id["sb"]["via_title"] == "数字经济"
        assert by_id["ta"]["similarity"] == 0.80
        assert by_id["ta"]["via_title"] is None  # 纯方向召回

    def test_ranks_by_max_similarity_and_excludes_in_project(self, monkeypatch):
        monkeypatch.setattr("app.routers.workbench._retrieve_similar_papers", _fake_retrieve([]))

        async def scenario(db):
            seed1 = _mk_paper("s1", "数字经济")
            seed2 = _mk_paper("s2", "平台经济")
            sim_a = _mk_paper("sa", "数字平台治理")
            sim_b = _mk_paper("sb", "数据要素")
            in_project_sim = _mk_paper("sx", "已在库的相似论文")
            await _seed_project(
                db, project_id=1, user_id="local",
                papers=[seed1, seed2, sim_a, sim_b, in_project_sim],
                project_papers=[("local", "s1", 0.9), ("local", "s2", 0.8), ("local", "sx", 0.6)],
                similarities=[
                    ("s1", "sa", 0.85), ("s2", "sa", 0.90),  # sa 被两种子召回，取最大 0.90
                    ("s1", "sb", 0.50),
                    ("s1", "sx", 0.95),                      # sx 已在文献集，必须排除
                ],
            )
            return await recommend_project_papers(1, RecommendRequest(limit=10), request=_uid(), db=db, token=True)
        res = asyncio.run(_with_db(scenario))
        assert res["mode"] == "similarity"
        ids = [x["id"] for x in res["papers"]]
        assert ids == ["sa", "sb"]  # 降序；sx 被排除
        by_id = {x["id"]: x for x in res["papers"]}
        assert by_id["sa"]["similarity"] == 0.90
        assert by_id["sa"]["via_title"] == "平台经济"  # 来自相似度更高的种子
        assert by_id["sb"]["via_title"] == "数字经济"
        assert by_id["sb"]["in_project"] is False

    def test_paper_id_scoped_single_seed(self):
        async def scenario(db):
            seed1 = _mk_paper("s1", "数字经济")
            seed2 = _mk_paper("s2", "平台经济")
            sim_a = _mk_paper("sa", "数字平台治理")
            sim_b = _mk_paper("sb", "数据要素")
            await _seed_project(
                db, project_id=1, user_id="local",
                papers=[seed1, seed2, sim_a, sim_b],
                project_papers=[("local", "s1", 0.9), ("local", "s2", 0.8)],
                similarities=[("s1", "sa", 0.85), ("s2", "sb", 0.95)],
            )
            return await recommend_project_papers(
                1, RecommendRequest(limit=10, paper_id="s1"), request=_uid(), db=db, token=True
            )
        res = asyncio.run(_with_db(scenario))
        # 只以 s1 为种子 → 只有 sa；sb 相似度更高但不属于 s1
        assert [x["id"] for x in res["papers"]] == ["sa"]
        assert res["papers"][0]["via_title"] == "数字经济"

    def test_paper_id_not_in_project_empty(self):
        async def scenario(db):
            seed1 = _mk_paper("s1", "数字经济")
            sim_a = _mk_paper("sa", "数字平台治理")
            await _seed_project(
                db, project_id=1, user_id="local",
                papers=[seed1, sim_a],
                project_papers=[("local", "s1", 0.9)],
                similarities=[("s1", "sa", 0.85)],
            )
            return await recommend_project_papers(
                1, RecommendRequest(limit=10, paper_id="ghost"), request=_uid(), db=db, token=True
            )
        res = asyncio.run(_with_db(scenario))
        assert res["mode"] == "no_results"
        assert res["papers"] == []

    def test_limit_clamped(self, monkeypatch):
        monkeypatch.setattr("app.routers.workbench._retrieve_similar_papers", _fake_retrieve([]))

        async def scenario(db):
            seed1 = _mk_paper("s1", "数字经济")
            sims = [_mk_paper(f"sa{i}", f"相似论文{i}") for i in range(5)]
            await _seed_project(
                db, project_id=1, user_id="local",
                papers=[seed1, *sims],
                project_papers=[("local", "s1", 0.9)],
                similarities=[("s1", f"sa{i}", 0.9 - i * 0.01) for i in range(5)],
            )
            zero = await recommend_project_papers(1, RecommendRequest(limit=0), request=_uid(), db=db, token=True)
            huge = await recommend_project_papers(1, RecommendRequest(limit=100), request=_uid(), db=db, token=True)
            return zero, huge
        zero, huge = asyncio.run(_with_db(scenario))
        assert len(zero["papers"]) == 1   # 0 → 钳到 1
        assert len(huge["papers"]) == 5   # 100 → 钳到 30，实际仅 5 条
