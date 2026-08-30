"""选题答辩（defense 技能）回归保护。

覆盖：
- skill 纯函数：轮序（candidate_0 + N 轮质询应答 + panel）、三角色 prompt 契约、
  质询维度轮换、合议 JSON 头（validate 4 轴 + verdict）、历史注入
- 端点流式落库（TestDefenseStreamPersist）：环节轮不转发 done 帧（仅合议轮一个 done）、
  verdict 随 defense_scores 透传、apply_scores 落库
"""
import asyncio
import json as _json
from types import SimpleNamespace

from app.skills import defense
from app.skills import validate as validate_skill


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


class TestDefenseSkill:
    def test_round_sequence(self):
        assert defense.build_round_sequence(1) == ["candidate_0", "examiner_1", "candidate_1", "panel"]
        assert defense.build_round_sequence(2) == ["candidate_0", "examiner_1", "candidate_1", "examiner_2", "candidate_2", "panel"]
        assert defense.build_round_sequence(3)[:2] == ["candidate_0", "examiner_1"]
        assert defense.build_round_sequence(3)[-1] == "panel"
        assert len(defense.build_round_sequence(3)) == 1 + 2 * 3 + 1
        assert defense.build_round_sequence(0) == defense.build_round_sequence(1)
        assert defense.build_round_sequence(9) == defense.build_round_sequence(3)

    def test_round_label(self):
        assert defense.round_label("candidate_0") == ("候选人自述", "candidate")
        assert defense.round_label("candidate_1")[0] == "候选人应答·第1轮"
        assert defense.round_label("examiner_1") == ("评委质询·第1问", "examiner")
        assert defense.round_label("examiner_3") == ("评委质询·第3问", "examiner")
        assert defense.round_label("panel") == ("合议裁定", "panel")

    def test_candidate_opening_mentions_design(self):
        msgs = defense.build_messages("t", _mk_papers(), _mk_stats(), _mk_comp(), [], "candidate_0")
        sys_prompt = msgs[0]["content"]
        assert "候选人" in sys_prompt and "研究设计" in sys_prompt
        assert "Script 证据" in sys_prompt and "max_similarity" in sys_prompt
        assert "[1] (0.820) 耐心资本研究" in sys_prompt

    def test_examiner_asks_targeted_question(self):
        msgs = defense.build_messages("t", _mk_papers(), _mk_stats(), _mk_comp(), [], "examiner_1")
        assert "答辩评委" in msgs[0]["content"]
        assert "新颖性" in msgs[0]["content"]  # 第 1 问维度
        msgs2 = defense.build_messages("t", _mk_papers(), _mk_stats(), _mk_comp(), [], "examiner_2")
        assert "识别策略" in msgs2[0]["content"]  # 第 2 问维度轮换

    def test_panel_has_verdict_contract(self):
        msgs = defense.build_messages("t", _mk_papers(), _mk_stats(), _mk_comp(), [], "panel")
        sys_prompt = msgs[0]["content"]
        assert "```json" in sys_prompt and '"verdict"' in sys_prompt
        assert '"通过|修改后通过|不通过"' in sys_prompt.replace('"verdict": "通过|修改后通过|不通过"', '"verdict": "通过|修改后通过|不通过"')
        assert "## 修改意见" in sys_prompt

    def test_history_injection(self):
        history = [("候选人自述", "我的研究设计是…" * 200)]
        msgs = defense.build_messages("t", _mk_papers(), _mk_stats(), _mk_comp(), history, "examiner_1")
        assert "【候选人自述】" in msgs[0]["content"]
        assert "该轮过长已截断" in msgs[0]["content"]

    def test_normalize_scores_accepts_verdict(self):
        assert validate_skill.normalize_scores(
            {"novelty": 7, "crowding": "中", "feasibility": 6, "gate": "caution", "verdict": "修改后通过"}
        )["verdict"] == "修改后通过"
        assert "verdict" not in validate_skill.normalize_scores({"verdict": "未知结论"})


class TestDefenseStreamPersist:
    """端到端：环节轮不转发 done、verdict 随 defense_scores 透传、apply_scores 落库。"""

    def test_stream_rounds_and_persists_scores(self, monkeypatch):
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

            def _round_events(user_text: str):
                if "合议裁定" in user_text:
                    head_obj = {"novelty": 8, "crowding": "中", "feasibility": 7, "gate": "caution", "verdict": "修改后通过"}
                    head_text = "```json\n" + _json.dumps(head_obj, ensure_ascii=False) + "\n```\n"
                    body_md = "## 质询焦点回顾\n…\n## 修改意见\n若补充稳健性检验则可推进。\n## 结论\n修改后通过"
                    return [{"content": head_text[: len(head_text) // 2]},
                            {"content": head_text[len(head_text) // 2:]},
                            {"content": body_md},
                            {"done": True}]
                return [{"content": f"{user_text} 的内容。"}, {"done": True}]

            async def fake_llm_stream(client, model, messages, on_event=None, **kw):
                for ev in _round_events(messages[-1]["content"]):
                    if on_event:
                        on_event(ev)
                    yield "data: " + _json.dumps(ev, ensure_ascii=False) + "\n\n"
            monkeypatch.setattr(topic_mod, "_stream_llm_content", fake_llm_stream)

            body = topic_mod.DefenseRequest(topic="测试选题", project_id=1, rounds_per_side=2)
            req = SimpleNamespace(headers={"x-user-id": "local"})
            resp = await topic_mod.defense_topic(body, request=req, db=db, token=True)

            frames = []
            async for chunk in resp.body_iterator:
                chunk = chunk if isinstance(chunk, str) else chunk.decode()
                for line in chunk.split("\n"):
                    if line.startswith("data: "):
                        frames.append(_json.loads(line[6:]))

            # 轮序
            rounds = [f["round"] for f in frames if "round" in f]
            assert rounds == ["candidate_0", "examiner_1", "candidate_1", "examiner_2", "candidate_2", "panel"]

            # 环节轮不转发 done，仅合议轮一个总 done（且必须是最后一个帧）
            done_frames = [f for f in frames if f.get("done")]
            assert len(done_frames) == 1 and done_frames[0] is frames[-1]

            # JSON 头剥离 + verdict 随 defense_scores 透传
            assert not any("```json" in (f.get("content") or "") for f in frames)
            content_texts = [f.get("content") or "" for f in frames]
            assert any("## 修改意见" in c for c in content_texts)
            scores_frame = next(f for f in frames if "defense_scores" in f)
            assert scores_frame["defense_scores"]["verdict"] == "修改后通过"
            scores_idx = frames.index(scores_frame)
            assert scores_idx < frames.index(done_frames[0]), "defense_scores 必须先于 done"

            # 落库：4 轴分数回填（verdict 无存储列，仅透传）
            p = await db.get(TopicProject, 1)
            assert p.novelty == 8 and p.crowding == "中" and p.feasibility == 7
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
