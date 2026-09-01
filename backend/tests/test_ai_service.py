"""ai_service 纯逻辑回归（无需真实 API key）：模型名解析 / 可用模型筛选。"""
import pytest

from app.ai_service import ai_trend_service


class TestModelResolution:
    def test_resolve_model_with_provider_prefix(self):
        # 'provider/model' -> (provider, bare)；多段 model 名保留
        assert ai_trend_service._resolve_model("zhipu/glm-4.5") == ("zhipu", "glm-4.5")
        assert ai_trend_service._resolve_model("siliconflow/Qwen/Qwen2.5-7B") == ("siliconflow", "Qwen/Qwen2.5-7B")

    def test_resolve_model_without_prefix(self):
        # 无前缀：provider 为 None，整体当 bare（回落默认 provider）
        provider, bare = ai_trend_service._resolve_model("glm-4.5")
        assert provider is None and bare == "glm-4.5"

    def test_resolve_model_custom_provider_name(self):
        # 自定义 provider 名（阿里云百练等）应优先匹配
        name = "阿里云百练"
        provider, bare = ai_trend_service._resolve_model(f"{name}/deepseek-v4-flash-0731")
        assert provider == name and bare == "deepseek-v4-flash-0731"

    def test_get_model_status_returns_entries(self):
        # 状态列表字段契约（前端模型下拉依赖 name/provider/available）
        status = ai_trend_service.get_model_status()
        for m in status:
            assert m.get("name") and m.get("provider")
            assert m.get("available") is True


# ---------- embed_texts 分批容错（P0-2 回归） ----------

class _FakeEmbeddingItem:
    def __init__(self, index, embedding):
        self.index = index
        self.embedding = embedding


class _FakeEmbeddings:
    """第 fail_batch 批抛异常（按调用顺序），其余批正常返回。"""

    def __init__(self, fail_batch):
        self.fail_batch = fail_batch
        self.calls = []

    def create(self, model, input, **kwargs):
        self.calls.append(input)
        if len(self.calls) - 1 == self.fail_batch:
            raise RuntimeError("simulated batch failure")
        return type("Resp", (), {
            "data": [_FakeEmbeddingItem(i, [float(i), 0.0]) for i in range(len(input))]
        })


def _fake_client():
    return type("C", (), {
        "base_url": "https://api.zhipu.ai/v1",  # 非 localhost -> REMOTE_EMBED_BATCH=20
        "embeddings": None,
    })()


def test_embed_texts_partial_batch_tolerance(monkeypatch):
    """单批失败时仍返回部分成功向量（不再整体返回 None，修复 P0-2）。"""
    from app.ai_service import ai_trend_service
    from app.config import settings

    monkeypatch.setattr(settings, "embedding_model", "zhipu/embedding-3")
    fake_emb = _FakeEmbeddings(fail_batch=1)
    client = _fake_client()
    client.embeddings = fake_emb
    monkeypatch.setattr(ai_trend_service, "clients", {"zhipu": client})

    texts = [f"t{i}" for i in range(30)]  # 30 条 -> 2 批（20+10），第 2 批失败
    vectors = ai_trend_service.embed_texts(texts)

    assert vectors is not None
    assert len(vectors) == 30
    assert sum(1 for v in vectors if v is not None) == 20  # 第 1 批成功
    assert vectors[0] == [0.0, 0.0]  # 成功批内容正确
    assert vectors[20] is None  # 失败批位置为 None


def test_embed_texts_all_batches_fail_returns_none_slots(monkeypatch):
    """所有批都失败时返回全 None 列表（调用方逐条降级），不抛异常。"""
    from app.ai_service import ai_trend_service
    from app.config import settings

    monkeypatch.setattr(settings, "embedding_model", "zhipu/embedding-3")
    fake_emb = _FakeEmbeddings(fail_batch=0)
    client = _fake_client()
    client.embeddings = fake_emb
    monkeypatch.setattr(ai_trend_service, "clients", {"zhipu": client})

    vectors = ai_trend_service.embed_texts(["a", "b"])
    assert vectors is not None and len(vectors) == 2
    assert all(v is None for v in vectors)
