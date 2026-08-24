"""
统一AI趋势分析服务
所有 provider（智谱/OpenAI/硅基流动/自定义）一律通过 OpenAI 兼容接口调用。
提供重试/降级、结构化输出、模型优先级持久化功能。
数据策略：全量聚合 + 精选样本
"""

import json
import logging
import asyncio
import time
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from app.config import settings

logger = logging.getLogger(__name__)

# 内置 provider 的 OpenAI 兼容端点与 API Key 配置项
BUILTIN_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "key_setting": "zhipu_api_key",
    },
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "key_setting": "siliconflow_api_key",
    },
    "openai": {
        "base_url": None,  # OpenAI SDK 默认地址
        "key_setting": "openai_api_key",
    },
}

# 各内置 provider 的默认模型优先级（可通过设置页排序并持久化到 .env）
DEFAULT_MODELS: Dict[str, List[str]] = {
    "zhipu": ["glm-4.7", "glm-4.5-air", "glm-4.7-flash"],
    "siliconflow": ["Qwen/Qwen3-8B", "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B", "Qwen/Qwen3.5-4B"],
    "openai": ["gpt-4o", "gpt-4o-mini"],
}


def _build_openai_client(api_key: str, base_url: Optional[str] = None):
    """构造 OpenAI 兼容客户端。

    环境中存在 httpx 不支持的代理变量（如 ALL_PROXY=socks://...）时，
    OpenAI() 默认构造会直接抛 ValueError，此时降级为忽略环境代理的 http client。
    """
    from openai import OpenAI
    try:
        return OpenAI(api_key=api_key, base_url=base_url)
    except ValueError as e:
        if "proxy" not in str(e).lower():
            raise
        logger.warning(f"Ignoring unsupported proxy env for AI client: {e}")
        try:
            import httpx2 as http_lib
        except ImportError:
            import httpx as http_lib
        return OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_lib.Client(trust_env=False),
        )


class AITrendService:
    SYSTEM_PROMPT = (
        "你是一个专业的经济学研究趋势分析专家。请基于提供的全量统计数据进行分析，"
        "并严格按照JSON格式输出结果。所有统计数据均来自数据库全量聚合，覆盖100%论文数据。"
        "你的每个结论都必须引用具体数字（篇数、占比、增长率、年度对比），避免空泛表述。"
    )

    def __init__(self):
        self.clients: Dict[str, Any] = {}       # provider -> OpenAI 兼容客户端
        self.models: Dict[str, List[str]] = {}  # provider -> 模型优先级列表
        self._init_clients()
        self._load_model_order()

    # ---------- 初始化 ----------

    def _init_clients(self):
        self.clients = {}
        try:
            from openai import OpenAI  # noqa: F401
        except ImportError:
            logger.error("openai package not installed. Please run: pip install openai")
            return

        for name, conf in BUILTIN_PROVIDERS.items():
            api_key = getattr(settings, conf["key_setting"], None)
            if not api_key:
                logger.info(f"AI provider '{name}' API key not set, skipped")
                continue
            base_url = conf["base_url"]
            override = getattr(settings, f"{name}_base_url", None)
            if override:
                base_url = override
            try:
                self.clients[name] = _build_openai_client(api_key, base_url)
                logger.info(f"AI provider '{name}' initialized (base_url={base_url})")
            except Exception as e:
                logger.error(f"Failed to initialize AI provider '{name}': {e}")

        for provider in settings.get_custom_providers():
            name = provider.get("name", "")
            base_url = provider.get("base_url", "")
            api_key = provider.get("api_key", "")
            if not name or name in BUILTIN_PROVIDERS:
                logger.warning(f"Skip custom provider with invalid name: {name!r}")
                continue
            if not (base_url and api_key):
                continue
            try:
                self.clients[name] = _build_openai_client(api_key, base_url)
                logger.info(f"Custom AI provider '{name}' initialized")
            except Exception as e:
                logger.error(f"Failed to initialize custom provider '{name}': {e}")

    def _load_model_order(self):
        """加载各 provider 的模型优先级；内置 provider 未配置时使用默认列表。"""
        self.models = {}
        for name in BUILTIN_PROVIDERS:
            raw = getattr(settings, f"{name}_models", None)
            models = settings.get_json_list(raw) or DEFAULT_MODELS[name]
            self.models[name] = list(models)
        for provider in settings.get_custom_providers():
            name = provider.get("name", "")
            if name:
                self.models[name] = list(provider.get("models", []) or [])

    def is_available(self) -> bool:
        return bool(self.clients)

    def reload(self):
        self._init_clients()
        self._load_model_order()

    # ---------- provider / model 查询 ----------

    def custom_provider_names(self) -> List[str]:
        return [p.get("name") for p in settings.get_custom_providers() if p.get("name")]

    def provider_order(self) -> List[str]:
        """降级尝试顺序：内置 provider 在前，自定义 provider 在后。"""
        names = list(BUILTIN_PROVIDERS)
        names += [n for n in self.custom_provider_names() if n not in names]
        return names

    def get_client(self, provider: Optional[str] = None) -> Tuple[Any, str]:
        """获取指定 provider 的客户端；provider 为空时按默认优先级返回第一个可用的。"""
        if provider:
            client = self.clients.get(provider)
            if not client:
                raise KeyError(provider)
            return client, provider
        for name in self.provider_order():
            if name in self.clients:
                return self.clients[name], name
        raise KeyError(None)

    def get_model_status(self) -> List[Dict]:
        result = []
        priority = 0
        for provider in self.provider_order():
            available = provider in self.clients
            for model in self.models.get(provider, []):
                priority += 1
                result.append({
                    "name": f"{provider}/{model}",
                    "priority": priority,
                    "available": available,
                    "provider": provider,
                })
        return result

    def update_models(self, model_list: List[str]):
        """按前端提交的 'provider/model' 完整顺序更新并持久化模型优先级。

        仅处理内置 provider；自定义 provider 的模型列表由 /settings 接口保存。
        """
        by_provider: Dict[str, List[str]] = {}
        for full_name in model_list:
            provider, _, bare = full_name.partition("/")
            if provider and bare:
                by_provider.setdefault(provider, []).append(bare)

        for provider, models in by_provider.items():
            if provider in BUILTIN_PROVIDERS and models and self.models.get(provider) != models:
                self.models[provider] = models
                settings.__class__.update_setting(
                    f"{provider}_models", json.dumps(models, ensure_ascii=False)
                )
                logger.info(f"Model priority for '{provider}' updated and persisted: {models}")

    def _resolve_model(self, model: str) -> Tuple[Optional[str], str]:
        """将 'provider/model' 解析为 (provider, bare_model)；无前缀时返回 (None, model)。"""
        for name in self.custom_provider_names():
            if model.startswith(f"{name}/"):
                return name, model[len(name) + 1:]
        for name in BUILTIN_PROVIDERS:
            if model.startswith(f"{name}/"):
                return name, model[len(name) + 1:]
        return None, model

    # ---------- 分析入口 ----------

    async def analyze_trends(
        self,
        analysis_data: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.is_available():
            logger.warning("AI service not available")
            return None

        start_time = time.time()

        if model:
            provider, bare_model = self._resolve_model(model)
            if provider is None:
                # 兼容裸模型名：在各 provider 的模型列表中查找
                for name in self.provider_order():
                    if bare_model in self.models.get(name, []):
                        provider = name
                        break
            if provider is None or provider not in self.clients:
                logger.warning(f"Cannot resolve an available provider for model: {model}")
                return None
            result = await self._run_with_model(provider, bare_model, analysis_data)
            if result:
                result["processing_time_ms"] = int((time.time() - start_time) * 1000)
                result["model"] = f"{provider}/{bare_model}"
            return result

        last_error = None
        # 优先尝试全局默认模型（'provider/model'），失败后回退到普通优先级顺序
        default_model_used = await self._try_default_model(analysis_data, start_time)
        if default_model_used:
            return default_model_used

        for provider in self.provider_order():
            if provider not in self.clients:
                continue
            for bare_model in self.models.get(provider, []):
                for attempt in range(2):
                    try:
                        result = await self._call_model(provider, bare_model, analysis_data)
                        if result:
                            elapsed_ms = int((time.time() - start_time) * 1000)
                            result["processing_time_ms"] = elapsed_ms
                            result["model"] = f"{provider}/{bare_model}"
                            logger.info(
                                f"AI analysis completed with {provider}/{bare_model}, "
                                f"tokens={result.get('tokens_used', 0)}, time={elapsed_ms}ms"
                            )
                            return result
                    except Exception as e:
                        last_error = e
                        logger.warning(
                            f"Attempt {attempt + 1} with {provider}/{bare_model} failed: {e}"
                        )
                        await asyncio.sleep(1 * (attempt + 1))

        logger.error(f"All AI analysis attempts failed. Last error: {last_error}")
        return None

    async def _run_with_model(
        self,
        provider: str,
        bare_model: str,
        analysis_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """仅用指定 provider+model 运行分析，2次重试，失败返回 None（不降级到其他模型）。"""
        for attempt in range(2):
            try:
                return await self._call_model(provider, bare_model, analysis_data)
            except Exception as e:
                logger.warning(
                    f"Attempt {attempt + 1} with specified model {provider}/{bare_model} failed: {e}"
                )
                await asyncio.sleep(1 * (attempt + 1))
        return None

    async def _try_default_model(
        self,
        analysis_data: Dict[str, Any],
        start_time: float,
    ) -> Optional[Dict[str, Any]]:
        """按全局 default_model（'provider/model'）尝试分析；未设置或不可用/失败时返回 None。"""
        full = settings.default_model
        if not full:
            return None
        try:
            provider, bare_model = self._resolve_model(full)
        except Exception:
            return None
        if not provider or provider not in self.clients:
            logger.warning(f"default_model '{full}' has no available provider, skipping")
            return None
        if bare_model not in self.models.get(provider, []) and not self._model_exists(full):
            logger.warning(f"default_model '{full}' not in known model list, skipping")
            return None
        result = await self._run_with_model(provider, bare_model, analysis_data)
        if result:
            elapsed_ms = int((time.time() - start_time) * 1000)
            result["processing_time_ms"] = elapsed_ms
            result["model"] = f"{provider}/{bare_model}"
            logger.info(f"AI analysis completed with default_model {provider}/{bare_model}, "
                        f"tokens={result.get('tokens_used', 0)}, time={elapsed_ms}ms")
            return result
        return None

    def _model_exists(self, full_model: str) -> bool:
        """判断某完整模型名（provider/model）是否已被配置（内置或自定义 provider 的模型列表）。"""
        return any(full_model in self.models.get(name, []) or
                   full_model.startswith(f"{name}/") and full_model[len(name) + 1:] in self.models.get(name, [])
                   for name in self.provider_order())

    async def _call_model(
        self,
        provider: str,
        model: str,
        analysis_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        client = self.clients[provider]
        prompt = self._build_structured_prompt(analysis_data)
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 8192,
            "temperature": 0.4,
        }
        # 智谱的 OpenAI 兼容接口支持 JSON 输出模式，可提升结构化稳定性
        if provider == "zhipu":
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await asyncio.to_thread(client.chat.completions.create, **kwargs)
        except Exception as e:
            if "response_format" in kwargs and "response_format" in str(e):
                kwargs.pop("response_format")
                response = await asyncio.to_thread(client.chat.completions.create, **kwargs)
            else:
                raise

        message = response.choices[0].message
        content = getattr(message, "content", None) or ""
        # 思考型模型可能将结果放入 reasoning_content 而 content 为空
        if not content.strip():
            content = getattr(message, "reasoning_content", None) or ""
        if not content.strip():
            raise ValueError(f"Model {provider}/{model} returned empty content")

        tokens_used = 0
        if getattr(response, "usage", None):
            tokens_used = getattr(response.usage, "total_tokens", 0) or 0

        return self._parse_structured_result(content, f"{provider}/{model}", tokens_used)

    # ---------- Prompt 与结果解析 ----------

    def _build_structured_prompt(self, data: Dict[str, Any]) -> str:
        total_papers = data.get("total_papers", 0)
        journal_dist = data.get("journal_dist", [])
        year_dist = data.get("year_dist", [])
        subfield_dist = data.get("subfield_dist", [])
        keyword_freq = data.get("keyword_freq", [])
        cooccurrence = data.get("cooccurrence", [])
        subfield_keywords = data.get("subfield_keywords", {})
        year_keywords = data.get("year_keywords", {})
        top_papers = data.get("top_papers", [])
        keywords_trend = data.get("keywords_trend", [])
        author_freq = data.get("author_freq", [])

        journal_lines = []
        for j in journal_dist[:20]:
            journal_lines.append(f"- {j['name']}: {j['count']}篇")

        year_lines = []
        for y in year_dist:
            year_lines.append(f"- {y['year']}: {y['count']}篇")

        subfield_lines = []
        for sf in subfield_dist:
            sf_name = sf['subfield']
            sf_count = sf['count']
            sf_pct = f"{sf_count / total_papers * 100:.1f}%" if total_papers > 0 else "0%"
            top_kws = subfield_keywords.get(sf_name, [])
            kw_str = ", ".join([k['keyword'] for k in top_kws[:3]]) if top_kws else "暂无"
            subfield_lines.append(f"- {sf_name}: {sf_count}篇 ({sf_pct}), 热门词: {kw_str}")

        keyword_lines = []
        for i, kw in enumerate(keyword_freq[:30], 1):
            keyword_lines.append(f"{i}. {kw['keyword']}: {kw['count']}篇")

        trend_lines = []
        for i, kw in enumerate(keywords_trend[:20], 1):
            keyword = kw.get('topic', 'Unknown')
            count = kw.get('paper_count', 0)
            growth = kw.get('growth_rate', 0)
            growth_str = f"+{growth*100:.1f}%" if growth > 0 else f"{growth*100:.1f}%"
            trend_lines.append(f"{i}. {keyword}: {count}篇 (增长率: {growth_str})")

        cooccurrence_lines = []
        for co in cooccurrence[:15]:
            cooccurrence_lines.append(f"- {co['kw1']} × {co['kw2']}: {co['count']}篇")

        year_keyword_lines = []
        for yr in sorted(year_keywords.keys()):
            top_kws = year_keywords[yr][:3]
            kw_str = ", ".join([k['keyword'] for k in top_kws])
            year_keyword_lines.append(f"- {yr}: {kw_str}")

        top_papers_lines = []
        for paper in top_papers[:20]:
            title = paper.get('title', 'Unknown')[:60]
            abstract = (paper.get('abstract', '') or '')[:150]
            subfield = paper.get('economics_subfield', '')
            kws = paper.get('keywords', [])
            kw_str = ", ".join(kws[:3]) if kws else ""
            top_papers_lines.append(f"- 《{title}》 [{subfield}] 关键词: {kw_str} | 摘要: {abstract}")

        author_lines = []
        for a in author_freq[:15]:
            author_lines.append(f"- {a['author']}: {a['count']}篇")

        first_year = year_dist[0]['year'] if year_dist else 'Unknown'
        last_year = year_dist[-1]['year'] if year_dist else 'Unknown'
        today = datetime.now().strftime('%Y-%m-%d')

        return f"""请基于以下经济学论文全量统计数据进行分析，并严格按照以下JSON格式返回结果，不要包含其他任何内容：

{{
  "summary": "整体分析摘要（150字以内，必须包含2-3个关键数字，如总量、增速、占比）",
  "hot_topics": [
    {{
      "topic": "热点主题名称",
      "description": "该热点的具体描述",
      "evidence": "数据依据：引用篇数、占比或增长率等具体数字",
      "related_keywords": ["相关关键词1", "相关关键词2"],
      "significance": "学术与实践意义"
    }}
  ],
  "development_trends": [
    {{
      "trend": "趋势名称",
      "direction": "up/down/stable",
      "description": "趋势描述",
      "evidence": "数据支撑：引用年度变迁、增长率等具体数字"
    }}
  ],
  "keyword_insights": [
    {{
      "cluster": "关键词聚类名称",
      "keywords": ["关键词1", "关键词2"],
      "insight": "基于共现关系的洞察分析"
    }}
  ],
  "journal_insights": [
    {{
      "journal": "期刊名称",
      "focus": "研究偏好（结合该刊载文数据）",
      "suggestion": "投稿建议"
    }}
  ],
  "recommendations": [
    {{
      "area": "研究方向",
      "description": "研究建议：说明切入点、可行性与预期贡献",
      "related_keywords": ["切入关键词1", "切入关键词2"],
      "opportunity_level": "high/medium/low"
    }}
  ]
}}

## 分析背景
- 分析日期：{today}
- 数据范围：{first_year}-{last_year}年收录的{total_papers}篇经济学论文（数据库全量聚合）
- 期刊数量：{len(journal_dist)}个

## 子领域分布（全量，含热门关键词）
{chr(10).join(subfield_lines) if subfield_lines else '暂无子领域数据'}

## 期刊分布（前20）
{chr(10).join(journal_lines)}

## 时间分布（全量）
{chr(10).join(year_lines)}

## 各年度热门关键词变迁
{chr(10).join(year_keyword_lines) if year_keyword_lines else '暂无年度关键词数据'}

## 关键词频次排名（前30，全量统计）
{chr(10).join(keyword_lines) if keyword_lines else '暂无关键词数据'}

## 关键词增长趋势（前20，含增长率）
{chr(10).join(trend_lines) if trend_lines else '暂无趋势数据'}

## 关键词共现（前15对，全量统计）
{chr(10).join(cooccurrence_lines) if cooccurrence_lines else '暂无共现数据'}

## 高产作者（前15）
{chr(10).join(author_lines) if author_lines else '暂无作者数据'}

## 最新论文样本（前20篇标题+关键词+摘要+子领域）
{chr(10).join(top_papers_lines)}

## 分析要求
1. 只返回JSON，不要包含任何markdown代码块标记或其他说明文字
2. 每个结论必须引用具体数据（篇数、占比、增长率、年度对比），禁止"较多""明显"等无数字的空泛表述
3. hot_topics 给出3-5个，按热度从高到低排序
4. development_trends 给出3-5个，direction 依据年度变迁数据判断，证据中注明对比的年份与数字
5. keyword_insights 给出2-4组，必须基于共现对与聚类的实际组合
6. journal_insights 给出2-4个，结合期刊载文量说明研究偏好，建议要具体可操作
7. recommendations 给出3-5个，优先挖掘「增长率高但总文献量尚少」的研究空白，说明切入点
8. 结合各年度热门关键词变迁分析研究热点的演化路径，并与最新论文样本相互印证
9. 中文输出"""

    def _parse_structured_result(
        self, analysis_text: str, model: str, tokens_used: int
    ) -> Optional[Dict[str, Any]]:
        import re

        text = analysis_text.strip()
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            text = json_match.group()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from AI response, falling back to text")
            return {
                "summary": text[:200] if text else "分析生成失败",
                "raw_analysis": text,
                "hot_topics": [],
                "development_trends": [],
                "keyword_insights": [],
                "journal_insights": [],
                "recommendations": [],
                "model": model,
                "tokens_used": tokens_used,
                "status": "partial"
            }

        return {
            "summary": parsed.get("summary", "")[:500],
            "raw_analysis": json.dumps(parsed, ensure_ascii=False, indent=2),
            "hot_topics": parsed.get("hot_topics", []),
            "development_trends": parsed.get("development_trends", []),
            "keyword_insights": parsed.get("keyword_insights", []),
            "journal_insights": parsed.get("journal_insights", []),
            "recommendations": parsed.get("recommendations", []),
            "model": model,
            "tokens_used": tokens_used,
            "status": "success"
        }


ai_trend_service = AITrendService()
