"""技能层（skills）回归保护：registry 契约 / validate 解析与回填 / 方法手册匹配 / 综述模板。

第二期技能化的关键行为锁：
- validate：```json 头解析 + 剥离 + 字段钳制；无头/损坏头降级为纯 markdown；
  apply_scores 状态流转克制（仅 to_validate -> validated，不覆盖用户手动状态）
- method_playbook：条目结构完整（三元组 + 诊断 + 代码）、关键词匹配、prompt 块
- lit_review：五节契约统一，两个调用方（workbench/producer）共用同一模板
"""
import asyncio
import json as _json
from types import SimpleNamespace

import pytest

from app.skills import lit_review, method_playbook, validate
from app.skills.registry import get_skill, list_skills


class TestRegistry:
    def test_three_skills_registered(self):
        names = {s["name"] for s in list_skills()}
        assert {"validate", "method_playbook", "lit_review"} <= names

    def test_get_skill(self):
        assert get_skill("validate") is validate
        assert get_skill("nope") is None

    def test_modules_have_contract_metadata(self):
        for s in list_skills():
            assert s["description"]


class TestValidate:
    def test_split_json_head_parses_and_strips(self):
        raw = '```json\n{"novelty": 8, "crowding": "低", "feasibility": 6, "gate": "caution"}\n```\n## 新颖性评估\n正文'
        scores, md = validate.split_json_head(raw)
        assert scores == {"novelty": 8, "crowding": "低", "feasibility": 6, "gate": "caution"}
        assert md.startswith("## 新颖性评估")
        assert "```" not in md

    def test_split_json_head_clamps_invalid_values(self):
        raw = '```json\n{"novelty": 15, "crowding": "极高", "feasibility": 0, "gate": "maybe"}\n```\n正文'
        scores, md = validate.split_json_head(raw)
        # 字段全非法 → 视为无有效头（None），原文降级放行
        assert scores is None
        assert "正文" in md

    def test_split_json_head_fallback_without_head(self):
        scores, md = validate.split_json_head("## 新颖性评估\n旧格式纯 markdown")
        assert scores is None
        assert "旧格式" in md

    def test_split_json_head_malformed_json(self):
        scores, md = validate.split_json_head('```json\n{not-json}\n```\n正文')
        assert scores is None
        assert "正文" in md

    def test_build_messages_contains_contract(self):
        papers = [{"id": "p1", "title": "耐心资本研究", "source": "经济研究",
                   "published_at": "2026-01-01", "keywords": ["耐心资本"], "similarity": 0.82}]
        stats = {"mode": "embedding", "top30_avg_similarity": 0.7, "max_similarity": 0.82,
                 "recent_3m_count": 1, "keyword_overlap": [{"keyword": "耐心资本", "count": 5}]}
        competition = {"top_authors": [{"name": "张三", "count": 4}], "journal_distribution": [], "recent_1y_count": 12}
        msgs = validate.build_messages("耐心资本对数据要素市场的影响", papers, stats, competition)
        sys_prompt = msgs[0]["content"]
        # 预承诺评分标准 / Script 证据 / 输出契约 / 未找到的证据 声明
        assert "预承诺" in sys_prompt
        assert "Script 证据" in sys_prompt
        assert "max_similarity" in sys_prompt
        assert "未找到的证据" in sys_prompt
        assert "```json" in sys_prompt
        assert "耐心资本对数据要素市场的影响" in sys_prompt
        assert "[1] (0.820) 耐心资本研究" in sys_prompt

    def test_apply_scores_transitions_status_only_from_to_validate(self):
        class P:
            def __init__(self):
                self.novelty = None
                self.crowding = None
                self.feasibility = None
                self.gate = None
                self.verdict = None
                self.status = "to_validate"

        p = P()
        touched = validate.apply_scores(p, {"novelty": 8, "crowding": "低", "feasibility": 6, "gate": "pass"})
        assert p.novelty == 8 and p.crowding == "低" and p.feasibility == 6
        assert p.gate == "pass" and "gate" in touched
        assert p.status == "validated" and "status" in touched

        # verdict 落库（答辩合议）
        pv = P()
        validate.apply_scores(pv, {"novelty": 7, "verdict": "修改后通过"})
        assert pv.verdict == "修改后通过" and pv.gate is None

        # 用户已手动置 subscribed / abandoned 时不覆盖
        for st in ("subscribed", "abandoned"):
            p2 = P()
            p2.status = st
            validate.apply_scores(p2, {"novelty": 9})
            assert p2.status == st

        # 空评分：只推进状态，不写空值
        p3 = P()
        touched3 = validate.apply_scores(p3, {})
        assert p3.novelty is None and p3.status == "validated" and touched3 == ["status"]


class TestMethodPlaybook:
    def test_at_least_ten_entries_with_full_structure(self):
        assert len(method_playbook.PLAYBOOK) >= 10
        for e in method_playbook.PLAYBOOK:
            for key in ("id", "name", "aliases", "applies", "data_needs", "assumptions", "diagnostics", "code_hint"):
                assert e.get(key), f"entry {e.get('id')} missing {key}"
            assert isinstance(e["diagnostics"], list) and len(e["diagnostics"]) >= 3

    def test_match_by_chinese_and_english_aliases(self):
        ids = lambda hits: [e["id"] for e in hits]
        assert "iv" in ids(method_playbook.match_methods("基于工具变量的实证分析"))
        assert "did" in ids(method_playbook.match_methods("政策试点的双重差分估计"))
        assert "psm_did" in ids(method_playbook.match_methods("PSM-DID 稳健性"))
        assert "text_analysis" in ids(method_playbook.match_methods("年报文本情绪测度"))
        assert method_playbook.match_methods("完全无关的内容描述") == []

    def test_match_project_combines_title_and_keywords(self):
        hits = method_playbook.match_project("某政策效应研究", ["工具变量", "psm"])
        ids = {e["id"] for e in hits}
        assert {"iv", "psm_did"} <= ids

    def test_to_prompt_block(self):
        block = method_playbook.to_prompt_block(method_playbook.match_methods("工具变量"))
        assert "方法手册" in block and "工具变量法" in block
        assert method_playbook.to_prompt_block([]) == ""


class TestLitReview:
    def test_build_messages_unified_sections(self):
        msgs = lit_review.build_messages("数字金融与企业创新", "[1] 某论文", paper_count=1, context_note="项目文献集")
        sys_prompt = msgs[0]["content"]
        for section in ("研究脉络", "方法演进", "争议点", "研究空白", "可进一步研究"):
            assert f"## {section}" in sys_prompt
        assert "项目文献集" in sys_prompt
        assert "数字金融与企业创新" in sys_prompt
        assert "[1] 某论文" in sys_prompt
        assert msgs[1] == {"role": "user", "content": "请生成这份文献综述。"}

    def test_context_note_shapes_wording(self):
        msgs = lit_review.build_messages("t", "[1] x", context_note="从论文库检索到的")
        assert "从论文库检索到的" in msgs[0]["content"]


def _frame(obj: dict) -> str:
    return "data: " + _json.dumps(obj) + "\n\n"


class TestValidateStreamPersist:
    """端到端验证 SSE 缓冲逻辑：JSON 头跨 chunk 剥离、reasoning 透传、服务端落库。"""

    def test_stream_strips_head_and_persists(self, monkeypatch):
        from app.database import Base
        from app.models import TopicProject
        from app.routers import topic as topic_mod
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from sqlalchemy.pool import StaticPool

        async def scenario(db):
            db.add(TopicProject(id=1, user_id="local", title="测试选题"))
            await db.commit()

            async def fake_retrieve(db_, t, k=30):
                return [], "none"
            monkeypatch.setattr(topic_mod, "_retrieve_similar_papers", fake_retrieve)
            monkeypatch.setattr(
                topic_mod, "_crowding_stats",
                lambda papers: {"top30_avg_similarity": 0.5, "max_similarity": 0.5,
                                 "recent_3m_count": 0, "keyword_overlap": []},
            )

            async def fake_comp(db_, ids):
                return {"top_authors": [], "journal_distribution": [], "recent_1y_count": 3}
            monkeypatch.setattr(topic_mod, "_competition_map", fake_comp)
            monkeypatch.setattr(topic_mod, "_resolve_model_provider", lambda m: ("fake", "fake-model"))

            class _FakeClient:
                pass
            monkeypatch.setattr(topic_mod, "_get_ai_client", lambda p: (_FakeClient(), p))

            head_obj = {"novelty": 8, "crowding": "低", "feasibility": 6, "gate": "caution"}
            head_text = "```json\n" + _json.dumps(head_obj) + "\n```\n"
            body_md = "## 新颖性评估\n新颖性评分：8/10 正文依据"
            events = [
                {"content": head_text[: len(head_text) // 2]},   # 头前半（跨 chunk）
                {"reasoning": "思考过程"},
                {"content": head_text[len(head_text) // 2:]},    # 头后半（判定在此触发）
                {"content": body_md},
                {"done": True},
            ]

            async def fake_llm_stream(client, model, messages, on_event=None, **kw):
                # 模拟 _stream_llm_content：回调改写事件后序列化为 SSE 帧
                for ev in events:
                    if on_event:
                        on_event(ev)
                    yield "data: " + _json.dumps(ev) + "\n\n"
            monkeypatch.setattr(topic_mod, "_stream_llm_content", fake_llm_stream)

            body = topic_mod.ValidateRequest(topic="测试选题", project_id=1)
            req = SimpleNamespace(headers={"x-user-id": "local"})
            resp = await topic_mod.validate_topic(body, request=req, db=db, token=True)

            # 解析 SSE 帧（json.dumps 转义中文，须解析后断言）
            frames = []
            async for chunk in resp.body_iterator:
                chunk = chunk if isinstance(chunk, str) else chunk.decode()
                for line in chunk.split("\n"):
                    if line.startswith("data: "):
                        frames.append(_json.loads(line[6:]))
            blob = _json.dumps(frames, ensure_ascii=False)
            assert not any("```json" in (f.get("content") or "") for f in frames), "JSON 头必须剥离，不透传给前端"
            content_texts = [f.get("content") or "" for f in frames]
            assert any("## 新颖性评估" in c for c in content_texts), "剥头后的正文必须转发"
            assert any(f.get("reasoning") for f in frames), "reasoning 帧原样透传"
            assert any(f.get("done") for f in frames), "done 帧原样透传"
            # 时序：正文必须先于 done 帧到达前端
            assert any("新颖性评估" in c for c in content_texts[: content_texts.index(body_md) + 1]) \
                if body_md in content_texts else True
            done_idx = next(i for i, f in enumerate(frames) if f.get("done"))
            body_idx = next(i for i, f in enumerate(frames) if "新颖性评估" in (f.get("content") or ""))
            assert body_idx < done_idx, "正文必须先于 done 帧"

            p = await db.get(TopicProject, 1)
            assert p.novelty == 8 and p.crowding == "低" and p.feasibility == 6
            assert p.status == "validated"
            assert p.validation_report.startswith("## 新颖性评估")
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

    def test_stream_headless_output_flushes_before_done(self, monkeypatch):
        """弱模型不输出 JSON 头时：缓冲正文必须在 done 帧前整体放行（降级路径）。"""
        from app.database import Base
        from app.models import TopicProject
        from app.routers import topic as topic_mod
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from sqlalchemy.pool import StaticPool

        async def scenario(db):
            db.add(TopicProject(id=1, user_id="local", title="测试选题"))
            await db.commit()

            async def fake_retrieve(db_, t, k=30):
                return [], "none"
            monkeypatch.setattr(topic_mod, "_retrieve_similar_papers", fake_retrieve)
            monkeypatch.setattr(
                topic_mod, "_crowding_stats",
                lambda papers: {"top30_avg_similarity": 0.5, "max_similarity": 0.5,
                                 "recent_3m_count": 0, "keyword_overlap": []},
            )

            async def fake_comp(db_, ids):
                return {"top_authors": [], "journal_distribution": [], "recent_1y_count": 3}
            monkeypatch.setattr(topic_mod, "_competition_map", fake_comp)
            monkeypatch.setattr(topic_mod, "_resolve_model_provider", lambda m: ("fake", "fake-model"))

            class _FakeClient:
                pass
            monkeypatch.setattr(topic_mod, "_get_ai_client", lambda p: (_FakeClient(), p))

            body_md = "## 新颖性评估\n" + "正文" * 100  # 400 字，无任何反引号，不足以触发长度判定
            events = [{"content": body_md}, {"done": True}]

            async def fake_llm_stream(client, model, messages, on_event=None, **kw):
                for ev in events:
                    if on_event:
                        on_event(ev)
                    yield "data: " + _json.dumps(ev) + "\n\n"
            monkeypatch.setattr(topic_mod, "_stream_llm_content", fake_llm_stream)

            body = topic_mod.ValidateRequest(topic="测试选题", project_id=1)
            req = SimpleNamespace(headers={"x-user-id": "local"})
            resp = await topic_mod.validate_topic(body, request=req, db=db, token=True)

            frames = []
            async for chunk in resp.body_iterator:
                chunk = chunk if isinstance(chunk, str) else chunk.decode()
                for line in chunk.split("\n"):
                    if line.startswith("data: "):
                        frames.append(_json.loads(line[6:]))
            # 时序：缓冲的正文必须在 done 帧之前放行（此前实现恰在这里丢正文）
            done_idx = next(i for i, f in enumerate(frames) if f.get("done"))
            body_idx = next(i for i, f in enumerate(frames) if "新颖性评估" in (f.get("content") or ""))
            assert body_idx < done_idx, "缓冲正文必须先于 done 帧"

            # 降级路径：报告落库，但不强制写评分/状态（前端正则兜底）
            p = await db.get(TopicProject, 1)
            assert p.validation_report.startswith("## 新颖性评估")
            assert p.novelty is None
            assert p.status == "to_validate"
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
