"""选题评估辩论（debate 技能）回归保护。

覆盖：
- skill 纯函数：五轮流式顺序、三角色 prompt 契约、历史轮次注入、评审 JSON 头契约
- 端点流式落库（TestDebateStreamPersist，仿 test_skills.TestValidateStreamPersist）：
  五轮 round 元帧顺序、裁决 JSON 头剥离、debate_scores 先于 done、apply_scores 落库。

与 validate 测试的关键差异：直接 patch `topic_mod.resolve_working_model`
（端点内部走模块级 resolve_working_model(body.model)），避免依赖本机 .env 的真实 AI key。
"""
import asyncio
import json as _json
from types import SimpleNamespace

import pytest

from app.skills import debate


def _mk_papers():
    return [
        {"id": "p1", "title": "耐心资本研究", "source": "经济研究", "published_at": "2026-01-01",
         "keywords": ["耐心资本"], "similarity": 0.82, "abstract": "摘要一"},
        {"id": "p2", "title": "数据要素市场研究", "source": "管理世界", "published_at": "2026-02-01",
         "keywords": ["数据要素"], "similarity": 0.61, "abstract": "摘要二"},
    ]


def _mk_stats():
    return {"top30_avg_similarity": 0.7, "max_similarity": 0.82,
            "recent_3m_count": 1, "keyword_overlap": [{"keyword": "耐心资本", "count": 5}]}


def _mk_comp():
    return {"top_authors": [{"name": "张三", "count": 4}],
            "journal_distribution": [{"journal": "经济研究", "count": 3}], "recent_1y_count": 12}


class TestDebateSkill:
    def test_round_sequence_and_labels(self):
        assert debate.ROUND_SEQUENCE == ["pro_1", "con_1", "pro_2", "con_2", "judge"]
        assert debate.ROLE_LABELS["pro_1"][1] == "pro"
        assert debate.ROLE_LABELS["con_2"][1] == "con"
        assert debate.ROLE_LABELS["judge"] == ("评审裁决", "judge")

    def test_build_messages_pro_round_contract(self):
        msgs = debate.build_messages("耐心资本对数据要素市场的影响", _mk_papers(), _mk_stats(), _mk_comp(),
                                     [], "pro_1")
        sys_prompt = msgs[0]["content"]
        assert "支持" in sys_prompt and "正方陈述" in sys_prompt
        assert "Script 证据" in sys_prompt and "max_similarity" in sys_prompt
        assert "[1]-[2]" in sys_prompt  # [n] 引用范围与召回论文数一致
        assert "[1] (0.820) 耐心资本研究" in sys_prompt
        assert "禁止" in sys_prompt
        assert "耐心资本对数据要素市场的影响" in sys_prompt

    def test_build_messages_con_round_takes_opposing_stance(self):
        msgs = debate.build_messages("t", _mk_papers(), _mk_stats(), _mk_comp(), [], "con_1")
        assert "反对/质疑" in msgs[0]["content"]

    def test_build_messages_injects_history(self):
        history = [("正方陈述", "这是正方第一轮的内容" * 300)]  # 超长触发截断
        msgs = debate.build_messages("t", _mk_papers(), _mk_stats(), _mk_comp(), history, "con_1")
        sys_prompt = msgs[0]["content"]
        assert "【正方陈述】" in sys_prompt
        assert "该轮过长已截断" in sys_prompt

    def test_judge_round_has_verdict_contract(self):
        msgs = debate.build_messages("t", _mk_papers(), _mk_stats(), _mk_comp(), [], "judge")
        sys_prompt = msgs[0]["content"]
        assert "```json" in sys_prompt and '"novelty"' in sys_prompt and '"gate"' in sys_prompt
        assert "## 评审条件" in sys_prompt
        assert "## 双方论点回顾" in sys_prompt

    def test_no_history_block_for_first_round(self):
        msgs = debate.build_messages("t", _mk_papers(), _mk_stats(), _mk_comp(), [], "pro_1")
        assert "已进行的辩论轮次" not in msgs[0]["content"]


def _frame(obj: dict) -> str:
    return "data: " + _json.dumps(obj, ensure_ascii=False) + "\n\n"


class TestDebateStreamPersist:
    """端到端：五轮流式回放、裁决 JSON 头剥离、debate_scores 先于 done、apply_scores 落库。"""

    def test_stream_five_rounds_and_persists_scores(self, monkeypatch):
        from app.database import Base
        from app.models import TopicProject
        from app.routers import topic as topic_mod
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from sqlalchemy.pool import StaticPool

        async def scenario(db):
            db.add(TopicProject(id=1, user_id="local", title="测试选题"))
            await db.commit()

            papers = _mk_papers()
            async def fake_retrieve(db_, t, k=30):
                return papers, "embedding"
            monkeypatch.setattr(topic_mod, "_retrieve_similar_papers", fake_retrieve)
            monkeypatch.setattr(topic_mod, "_crowding_stats", lambda p: _mk_stats())
            async def fake_comp(db_, ids):
                return _mk_comp()
            monkeypatch.setattr(topic_mod, "_competition_map", fake_comp)

            class _FakeClient:
                pass
            monkeypatch.setattr(topic_mod, "resolve_working_model",
                                lambda m: (_FakeClient(), "fake", "fake-model"))

            # 按轮次回放：裁决轮输出 JSON 头（跨 chunk）+ 正文 + done，论证轮直接 content + done
            def _round_events(user_text: str):
                if "评审裁决" in user_text:
                    head_obj = {"novelty": 7, "crowding": "中", "feasibility": 6, "gate": "caution"}
                    head_text = "```json\n" + _json.dumps(head_obj, ensure_ascii=False) + "\n```\n"
                    body_md = "## 双方论点回顾\n正方观点…\n## 裁决依据\n…\n## 评审条件\n若数据可得则做。\n## 结论\ncaution"
                    return [
                        {"content": head_text[: len(head_text) // 2]},
                        {"content": head_text[len(head_text) // 2:]},   # 判定在此触发
                        {"content": body_md},
                        {"done": True},
                    ]
                return [{"content": f"第 {user_text} 的论证内容。"}, {"done": True}]

            async def fake_llm_stream(client, model, messages, on_event=None, **kw):
                for ev in _round_events(messages[-1]["content"]):
                    if on_event:
                        on_event(ev)
                    yield "data: " + _json.dumps(ev, ensure_ascii=False) + "\n\n"
            monkeypatch.setattr(topic_mod, "_stream_llm_content", fake_llm_stream)

            body = topic_mod.DebateRequest(topic="测试选题", project_id=1)
            req = SimpleNamespace(headers={"x-user-id": "local"})
            resp = await topic_mod.debate_topic(body, request=req, db=db, token=True)

            frames = []
            async for chunk in resp.body_iterator:
                chunk = chunk if isinstance(chunk, str) else chunk.decode()
                for line in chunk.split("\n"):
                    if line.startswith("data: "):
                        frames.append(_json.loads(line[6:]))

            # 首帧是召回论文元载荷，随后五轮 round 元帧顺序固定
            assert frames[0]["papers"] and frames[0]["mode"] == "embedding"
            rounds = [f["round"] for f in frames if "round" in f]
            assert rounds == ["pro_1", "con_1", "pro_2", "con_2", "judge"]

            # JSON 头剥离：任何 content 帧不得含 ```json
            assert not any("```json" in (f.get("content") or "") for f in frames)
            content_texts = [f.get("content") or "" for f in frames]
            assert any("## 评审条件" in c for c in content_texts), "裁决正文必须转发"

            # 时序硬约束：debate_scores 先于评审轮（最后一个）done 帧
            scores_idx = next(i for i, f in enumerate(frames) if "debate_scores" in f)
            done_idx = max(i for i, f in enumerate(frames) if f.get("done"))
            assert scores_idx < done_idx, "debate_scores 必须先于 done 帧"
            assert frames[scores_idx]["debate_scores"] == {
                "novelty": 7, "crowding": "中", "feasibility": 6, "gate": "caution"}

            # 裁决分数落库（apply_scores 复用 validate 状态流转；gate 无存储列，已随 debate_scores 帧透传）
            p = await db.get(TopicProject, 1)
            assert p.novelty == 7 and p.crowding == "中" and p.feasibility == 6
            assert p.status == "validated"
            return True

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

        async def _run():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with Session() as db:
                    return await scenario(db)
            finally:
                await engine.dispose()

        assert asyncio.run(_run())

    def test_stream_without_project_id_does_not_persist(self, monkeypatch):
        """无 project_id：只流式输出，不落库。"""
        from app.database import Base
        from app.routers import topic as topic_mod
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from sqlalchemy.pool import StaticPool

        async def scenario(db):
            papers = _mk_papers()
            async def fake_retrieve(db_, t, k=30):
                return papers, "tfidf"
            monkeypatch.setattr(topic_mod, "_retrieve_similar_papers", fake_retrieve)
            monkeypatch.setattr(topic_mod, "_crowding_stats", lambda p: _mk_stats())
            async def fake_comp(db_, ids):
                return _mk_comp()
            monkeypatch.setattr(topic_mod, "_competition_map", fake_comp)

            class _FakeClient:
                pass
            monkeypatch.setattr(topic_mod, "resolve_working_model",
                                lambda m: (_FakeClient(), "fake", "fake-model"))

            async def fake_llm_stream(client, model, messages, on_event=None, **kw):
                if "评审裁决" in messages[-1]["content"]:
                    evs = [{"content": '```json\n{"novelty": 9, "crowding": "低", "feasibility": 8, "gate": "pass"}\n```\n## 结论\npass'},
                           {"done": True}]
                else:
                    evs = [{"content": "论证内容"}, {"done": True}]
                for ev in evs:
                    if on_event:
                        on_event(ev)
                    yield "data: " + _json.dumps(ev, ensure_ascii=False) + "\n\n"
            monkeypatch.setattr(topic_mod, "_stream_llm_content", fake_llm_stream)

            body = topic_mod.DebateRequest(topic="测试选题")
            req = SimpleNamespace(headers={"x-user-id": "local"})
            resp = await topic_mod.debate_topic(body, request=req, db=db, token=True)
            frames = []
            async for chunk in resp.body_iterator:
                chunk = chunk if isinstance(chunk, str) else chunk.decode()
                for line in chunk.split("\n"):
                    if line.startswith("data: "):
                        frames.append(_json.loads(line[6:]))
            rounds = [f["round"] for f in frames if "round" in f]
            assert rounds == ["pro_1", "con_1", "pro_2", "con_2", "judge"]
            assert any("debate_scores" in f for f in frames)
            return True

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

        async def _run():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with Session() as db:
                    return await scenario(db)
            finally:
                await engine.dispose()

        assert asyncio.run(_run())
