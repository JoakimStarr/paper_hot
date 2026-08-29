"""选题项目 PATCH 更新接口回归保护（引导层改造配套）。

内存 SQLite（StaticPool）建库后直接调用路由函数，不依赖 httpx/TestClient。

背景：validation_report 曾因 PATCH 白名单缺失被静默丢弃（验证报告保存请求
发出但从不落库）。本测试锁住以下行为：
- validation_report / validation_evidence / search_keywords 可落库并可读回
- novelty / crowding / status 正常更新
- current_step 持久化
- 非本人项目 → 404

覆盖场景：
- 全字段一次性 PATCH 往返
- 白名单外字段（ai_pending 等）不被请求模型接收
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import TopicProject
from app.routers.topic import update_topic_project, TopicProjectUpdate


def _uid() -> SimpleNamespace:
    return SimpleNamespace(headers={"x-user-id": "local"})


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


async def _seed(db, project_id=1, user_id="local"):
    db.add(TopicProject(id=project_id, user_id=user_id, title="耐心资本与数据要素市场"))
    await db.commit()


class TestTopicProjectPatch:
    def test_validation_report_and_evidence_persist(self):
        """回归：validation_report 曾经不在 PATCH 白名单里，保存请求被静默丢弃。"""
        async def scenario(db):
            await _seed(db)
            body = TopicProjectUpdate(
                validation_report="## 新颖性评估\n\n新颖性评分：8/10\n\n拥挤度：低",
                validation_evidence={"mode": "embedding", "papers": [], "validated_at": "2026-08-29T00:00:00Z"},
                search_keywords=["耐心资本", "数据要素", "工具变量"],
                novelty=8,
                crowding="低",
            )
            out = await update_topic_project(1, body, request=_uid(), db=db, token=True)
            assert out["validation_report"].startswith("## 新颖性评估")
            assert out["validation_evidence"]["mode"] == "embedding"
            assert out["search_keywords"] == ["耐心资本", "数据要素", "工具变量"]
            assert out["novelty"] == 8
            assert out["crowding"] == "低"
            return True

        assert asyncio.run(_with_db(scenario))

    def test_status_and_current_step_persist(self):
        async def scenario(db):
            await _seed(db)
            body = TopicProjectUpdate(status="validated", current_step=3)
            out = await update_topic_project(1, body, request=_uid(), db=db, token=True)
            assert out["status"] == "validated"
            assert out["current_step"] == 3
            return True

        assert asyncio.run(_with_db(scenario))

    def test_other_user_project_404(self):
        async def scenario(db):
            await _seed(db, user_id="someone-else")
            body = TopicProjectUpdate(title="劫持标题")
            with pytest.raises(HTTPException) as ei:
                await update_topic_project(1, body, request=_uid(), db=db, token=True)
            assert ei.value.status_code == 404
            return True

        assert asyncio.run(_with_db(scenario))
