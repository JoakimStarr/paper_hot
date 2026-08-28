"""研究工作台懒召回与轻量状态接口回归保护。

- POST /topic-projects/{id}/recall-papers：按选题召回 top-10 并入文献集，
  已在文献集的论文去重跳过；失败返回 {"recalled": 0}。
- GET /topic-projects/{id}/status：轻量状态，只返回轮询所需字段，
  不携带 literature_review/proposal/overview 等大段 AI 文本。

与 test_recommend_papers.py 同款内存 SQLite（StaticPool）方案：
直接调用路由函数，`_retrieve_similar_papers` 统一 monkeypatch 为受控数据，
只验证接口自身的去重/写入/裁剪逻辑。
"""
import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Paper, ProjectPaper, TopicProject
from app.routers.workbench import get_project_status, recall_project_papers


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


async def _seed_project(db, project_id=1, user_id="local", papers=(), project_papers=()):
    db.add(TopicProject(id=project_id, user_id=user_id, title="数字经济与平台治理"))
    for p in papers:
        db.add(p)
    for uid, pid, sim in project_papers:
        db.add(ProjectPaper(user_id=uid, project_id=project_id, paper_id=pid, similarity=sim))
    await db.commit()


def _fake_retrieve(papers):
    """构造假的 _retrieve_similar_papers：返回受控的选题方向召回结果。"""

    async def fake(db, topic, k=30):
        return papers, "embedding"

    return fake


def _brief(pid: str, sim: float = 0.7) -> dict:
    """与 _retrieve_similar_papers 返回的 brief 同键（id/title/abstract/journal_name/source/published_at/keywords/similarity）。"""
    return {
        "id": pid, "title": f"论文{pid}", "abstract": "摘要", "journal_name": "经济研究",
        "source": "test", "published_at": "2026-01-01", "keywords": [], "similarity": sim,
    }


async def _project_paper_ids(db, project_id: int):
    return sorted(
        (await db.execute(select(ProjectPaper.paper_id).where(ProjectPaper.project_id == project_id)))
        .scalars().all()
    )


class TestRecallProjectPapers:
    def test_project_not_found(self):
        async def scenario(db):
            with pytest.raises(HTTPException) as ei:
                await recall_project_papers(999, request=_uid(), db=db, token=True)
            return ei.value.status_code
        assert asyncio.run(_with_db(scenario)) == 404

    def test_recall_inserts_all_when_project_empty(self, monkeypatch):
        """Scenario A：项目无文献集 → 召回全量写入。"""
        monkeypatch.setattr(
            "app.routers.workbench._retrieve_similar_papers",
            _fake_retrieve([_brief("p1"), _brief("p2"), _brief("p3")]),
        )

        async def scenario(db):
            await _seed_project(db, project_id=1, user_id="local",
                                papers=[_mk_paper("p1", "论文p1"), _mk_paper("p2", "论文p2"), _mk_paper("p3", "论文p3")])
            res = await recall_project_papers(1, request=_uid(), db=db, token=True)
            return res, await _project_paper_ids(db, 1)
        res, ids = asyncio.run(_with_db(scenario))
        assert res == {"recalled": 3}
        assert ids == ["p1", "p2", "p3"]

    def test_recall_skips_already_in_project(self, monkeypatch):
        """Scenario B：已存在 id 被跳过，recalled 只计新增。"""
        monkeypatch.setattr(
            "app.routers.workbench._retrieve_similar_papers",
            _fake_retrieve([_brief("p1"), _brief("p2"), _brief("p3")]),
        )

        async def scenario(db):
            await _seed_project(db, project_id=1, user_id="local",
                                papers=[_mk_paper("p1", "论文p1"), _mk_paper("p2", "论文p2"), _mk_paper("p3", "论文p3")],
                                project_papers=[("local", "p2", 0.5)])
            res = await recall_project_papers(1, request=_uid(), db=db, token=True)
            return res, await _project_paper_ids(db, 1)
        res, ids = asyncio.run(_with_db(scenario))
        assert res == {"recalled": 2}
        assert ids == ["p1", "p2", "p3"]  # p2 保持原相似度，未重复写入

    def test_recall_all_already_in_project(self, monkeypatch):
        monkeypatch.setattr(
            "app.routers.workbench._retrieve_similar_papers",
            _fake_retrieve([_brief("p1"), _brief("p2")]),
        )

        async def scenario(db):
            await _seed_project(db, project_id=1, user_id="local",
                                papers=[_mk_paper("p1", "论文p1"), _mk_paper("p2", "论文p2")],
                                project_papers=[("local", "p1", 0.5), ("local", "p2", 0.6)])
            return await recall_project_papers(1, request=_uid(), db=db, token=True)
        res = asyncio.run(_with_db(scenario))
        assert res == {"recalled": 0}

    def test_recall_failure_returns_zero(self, monkeypatch):
        async def boom(db, topic, k=30):
            raise RuntimeError("embedding 不可用")
        monkeypatch.setattr("app.routers.workbench._retrieve_similar_papers", boom)

        async def scenario(db):
            await _seed_project(db, project_id=1, user_id="local")
            return await recall_project_papers(1, request=_uid(), db=db, token=True)
        res = asyncio.run(_with_db(scenario))
        assert res == {"recalled": 0}


class TestGetProjectStatus:
    def test_status_returns_lightweight_fields_only(self):
        """Scenario C：只返回 id/status/ai_pending/ai_error/updated_at，无大段 AI 文本。"""
        async def scenario(db):
            db.add(TopicProject(id=1, user_id="local", title="数字经济与平台治理"))
            await db.flush()
            p = await db.get(TopicProject, 1)
            p.status = "validated"
            p.ai_pending = "literature_review"
            p.ai_error = None
            p.literature_review = "x" * 10000   # 大段 AI 文本不应出现在 status 响应里
            p.overview = "y" * 10000
            p.proposal = "z" * 10000
            await db.commit()
            await db.refresh(p)  # 拉取 server_default 的 updated_at
            return await get_project_status(1, request=_uid(), db=db, token=True)
        res = asyncio.run(_with_db(scenario))
        assert set(res) == {"id", "status", "ai_pending", "ai_error", "updated_at"}
        assert res["id"] == 1
        assert res["status"] == "validated"
        assert res["ai_pending"] == "literature_review"
        assert res["ai_error"] is None

    def test_status_not_found(self):
        async def scenario(db):
            with pytest.raises(HTTPException) as ei:
                await get_project_status(999, request=_uid(), db=db, token=True)
            return ei.value.status_code
        assert asyncio.run(_with_db(scenario)) == 404
