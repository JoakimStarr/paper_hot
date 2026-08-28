"""选题灵感向导回归保护。

覆盖：
- 纯函数：_build_preferences_text 各分支；_normalize_candidates 字段兜底/钳制
- 核心生成：_generate_candidates（idea 空 → 400；LLM 失败/空候选 → 503；首轮/迭代轮；
  候选方向附带库内参考文献，monkeypatch 召回验证接线）
- 任务轮询：POST 提交生成任务（返回 task_id）→ GET 轮询 pending/done/404
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.routers.topic_ideas import (
    _build_preferences_text, _normalize_candidates, _generate_candidates,
    TopicIdeaPreferences, TopicIdeaGenerateRequest,
    generate_topic_ideas, get_generate_task,
)


# ---------- 纯函数：偏好文本 ----------

class TestBuildPreferencesText:
    def test_empty_none(self):
        assert _build_preferences_text(None) == ""

    def test_empty_object(self):
        # 默认 focus_china=True → 至少带「聚焦中国情境」一行，不抛异常
        text = _build_preferences_text(TopicIdeaPreferences())
        assert "聚焦中国情境" in text
        assert "身份" not in text

    def test_full_preferences(self):
        pref = TopicIdeaPreferences(
            identity="master", paper_type="empirical",
            subfields=["产业经济学"], methods=["因果识别"],
            data=["上市公司数据"], venue="cn_top",
            prefer_novelty=0.8, focus_china=True, extra="要突出政策评估",
        )
        text = _build_preferences_text(pref)
        assert "硕士论文" in text
        assert "实证研究" in text
        assert "产业经济学" in text
        assert "因果识别" in text
        assert "上市公司数据" in text
        assert "中文顶刊" in text
        assert "更强调新颖度" in text
        assert "聚焦中国情境" in text
        assert "政策评估" in text

    def test_novelty_buckets(self):
        assert "更强调可行性" in _build_preferences_text(TopicIdeaPreferences(prefer_novelty=0.1))
        assert "均衡" in _build_preferences_text(TopicIdeaPreferences(prefer_novelty=0.5))
        assert "更强调新颖度" in _build_preferences_text(TopicIdeaPreferences(prefer_novelty=0.9))

    def test_focus_china_false_omitted(self):
        assert "聚焦中国" not in _build_preferences_text(TopicIdeaPreferences(focus_china=False))


# ---------- 纯函数：候选规范化 ----------

class TestNormalizeCandidates:
    def test_dict_wrapped(self):
        raw = {"candidates": [{"title": "A"}, {"title": "B"}]}
        out = _normalize_candidates(raw)
        assert [c["title"] for c in out] == ["A", "B"]

    def test_non_list_returns_empty(self):
        assert _normalize_candidates("not-a-list") == []
        assert _normalize_candidates(None) == []

    def test_clamps_to_six(self):
        raw = [{"title": f"T{i}"} for i in range(10)]
        assert len(_normalize_candidates(raw)) == 6

    def test_skips_blank_title_and_non_dict(self):
        raw = [{"title": "  "}, "junk", {"title": "OK"}, 123]
        out = _normalize_candidates(raw)
        assert [c["title"] for c in out] == ["OK"]

    def test_field_defaults(self):
        out = _normalize_candidates([{"title": "X"}])[0]
        assert out["research_questions"] == []
        assert out["methods"] == []
        assert out["data"] == []
        assert out["keywords"] == []
        assert out["references"] == []
        assert out["assessment"] == {"novelty": 3, "feasibility": 3, "literature_support": 3, "comment": ""}

    def test_assessment_clamped(self):
        out = _normalize_candidates([{
            "title": "X",
            "assessment": {"novelty": 99, "feasibility": -3, "literature_support": "bad", "comment": "评"},
        }])[0]
        assert out["assessment"]["novelty"] == 5
        assert out["assessment"]["feasibility"] == 0
        assert out["assessment"]["literature_support"] == 0
        assert out["assessment"]["comment"] == "评"

    def test_questions_string_guarded(self):
        out = _normalize_candidates([{"title": "X", "research_questions": "not-a-list"}])[0]
        assert out["research_questions"] == []


# ---------- 核心生成 ----------

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


def _sample_candidate(title="数字普惠金融与制造业创新", extra_question=None):
    return {
        "title": title,
        "research_questions": [extra_question or "机制识别", "异质性分析"],
        "hypothesis": "假设",
        "why": "创新点",
        "angle": "DID",
        "methods": ["DID", "PSM"],
        "data": ["上市公司数据"],
        "subfield": "产业经济学",
        "keywords": ["数字普惠金融", "制造业创新"],
        "assessment": {"novelty": 4, "feasibility": 3, "literature_support": 4, "comment": "可行"},
    }


def _fake_refs():
    async def fake(db, topic, k=30):
        return [
            {"id": "ref1", "title": "参考论文A", "journal_name": "经济研究", "source": "test",
             "published_at": "2026-01-01", "keywords": [], "similarity": 0.85},
        ], "embedding"
    return fake


class TestGenerateCandidates:
    def test_idea_required(self):
        async def scenario(db):
            with pytest.raises(HTTPException) as ei:
                await _generate_candidates(db, TopicIdeaGenerateRequest(idea="   "), "local")
            return ei.value.status_code
        assert asyncio.run(_with_db(scenario)) == 400

    def test_llm_failure_503(self, monkeypatch):
        async def boom(messages, max_tokens=4096, temperature=0.4):
            raise ValueError("llm down")
        monkeypatch.setattr("app.routers.topic_ideas._llm_json", boom)

        async def scenario(db):
            with pytest.raises(HTTPException) as ei:
                await _generate_candidates(db, TopicIdeaGenerateRequest(idea="数字金融影响实体创新"), "local")
            return ei.value.status_code
        assert asyncio.run(_with_db(scenario)) == 503

    def test_empty_candidates_503(self, monkeypatch):
        async def fake_llm(messages, max_tokens=4096, temperature=0.4):
            return {"candidates": []}
        monkeypatch.setattr("app.routers.topic_ideas._llm_json", fake_llm)

        async def scenario(db):
            with pytest.raises(HTTPException) as ei:
                await _generate_candidates(db, TopicIdeaGenerateRequest(idea="数字金融影响实体创新"), "local")
            return ei.value.status_code
        assert asyncio.run(_with_db(scenario)) == 503

    def test_first_round_with_preferences_and_references(self, monkeypatch):
        captured = {}

        async def fake_llm(messages, max_tokens=4096, temperature=0.4):
            captured["user"] = messages[-1]["content"]
            return {"candidates": [_sample_candidate()]}

        monkeypatch.setattr("app.routers.topic_ideas._llm_json", fake_llm)
        monkeypatch.setattr("app.routers.topic_ideas._retrieve_similar_papers", _fake_refs())

        async def scenario(db):
            body = TopicIdeaGenerateRequest(
                idea="数字金融影响实体创新",
                preferences=TopicIdeaPreferences(identity="master", subfields=["产业经济学"]),
            )
            return await _generate_candidates(db, body, "local")
        res = asyncio.run(_with_db(scenario))
        assert res["round"] == 1
        assert len(res["candidates"]) == 1
        c = res["candidates"][0]
        assert c["id"] == "r1c0"
        assert c["keywords"] == ["数字普惠金融", "制造业创新"]
        assert c["references"][0]["id"] == "ref1"
        assert "硕士论文" in captured["user"]
        assert "数字金融影响实体创新" in captured["user"]

    def test_iteration_round_includes_feedback_and_previous(self, monkeypatch):
        captured = {}

        async def fake_llm(messages, max_tokens=4096, temperature=0.4):
            captured["user"] = messages[-1]["content"]
            return {"candidates": [_sample_candidate("聚焦制造业")]}

        monkeypatch.setattr("app.routers.topic_ideas._llm_json", fake_llm)
        monkeypatch.setattr("app.routers.topic_ideas._retrieve_similar_papers", _fake_refs())

        async def scenario(db):
            body = TopicIdeaGenerateRequest(
                idea="数字金融影响实体创新",
                feedback="聚焦制造业细分",
                previous_candidates=[{"title": "数字普惠金融与制造业创新", "research_questions": []}],
            )
            return await _generate_candidates(db, body, "local")
        res = asyncio.run(_with_db(scenario))
        assert res["round"] == 2
        assert "聚焦制造业细分" in captured["user"]
        assert "数字普惠金融与制造业创新" in captured["user"]

    def test_on_phase_callback_invoked_generating_then_recalling(self, monkeypatch):
        phases = []

        async def fake_llm(messages, max_tokens=4096, temperature=0.4):
            return {"candidates": [_sample_candidate()]}

        monkeypatch.setattr("app.routers.topic_ideas._llm_json", fake_llm)
        monkeypatch.setattr("app.routers.topic_ideas._retrieve_similar_papers", _fake_refs())

        async def scenario(db):
            return await _generate_candidates(
                db, TopicIdeaGenerateRequest(idea="数字金融影响实体创新"), "local",
                on_phase=phases.append,
            )
        asyncio.run(_with_db(scenario))
        assert phases == ["generating", "recalling"]


# ---------- 任务提交 + 轮询 ----------

class TestGenerateTask:
    def test_post_creates_pending_task(self, monkeypatch):
        monkeypatch.setattr("app.main.spawn_background_task", lambda coro: None)

        async def scenario(db):
            return await generate_topic_ideas(
                TopicIdeaGenerateRequest(idea="数字金融影响实体创新"), request=_uid(), db=db, token=True
            )
        res = asyncio.run(_with_db(scenario))
        assert res["status"] == "pending"
        assert res["phase"] == "generating"
        assert len(res["task_id"]) == 12

    def test_post_requires_idea(self, monkeypatch):
        monkeypatch.setattr("app.main.spawn_background_task", lambda coro: None)

        async def scenario(db):
            with pytest.raises(HTTPException) as ei:
                await generate_topic_ideas(
                    TopicIdeaGenerateRequest(idea="  "), request=_uid(), db=db, token=True
                )
            return ei.value.status_code
        assert asyncio.run(_with_db(scenario)) == 400

    def test_poll_pending_done_and_404(self):
        from app.routers import topic_ideas

        task_id = "t123456789ab"

        async def scenario(db):
            # 注入 pending 任务
            topic_ideas._generate_tasks[task_id] = {"status": "pending", "phase": "generating", "created_at": 0}
            pending = await get_generate_task(task_id, request=_uid(), token=True)
            # 模拟后台完成
            topic_ideas._generate_tasks[task_id].update(
                {"status": "done", "round": 1, "candidates": [_sample_candidate()], "phase": "recalling"}
            )
            done = await get_generate_task(task_id, request=_uid(), token=True)
            with pytest.raises(HTTPException) as ei:
                await get_generate_task("nonexistent", request=_uid(), token=True)
            return pending, done, ei.value.status_code

        pending, done, not_found = asyncio.run(_with_db(scenario))
        assert pending == {"status": "pending", "phase": "generating"}
        assert done["status"] == "done"
        assert done["round"] == 1
        assert done["phase"] == "recalling"
        assert done["candidates"][0]["title"] == "数字普惠金融与制造业创新"
        assert not_found == 404

