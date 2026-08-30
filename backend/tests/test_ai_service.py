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
