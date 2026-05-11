"""
统一AI趋势分析服务
提供重试/降级、结构化输出、监控功能
数据策略：全量聚合 + 精选样本
"""

import logging
import time
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)


class AITrendService:
    def __init__(self):
        self.glm_initialized = False
        self.glm_client = None
        self._init_glm()

    def _init_glm(self):
        if not settings.zhipu_api_key:
            logger.warning("Zhipu API key not set. GLM AI analysis will be unavailable.")
            return
        try:
            from zai import ZhipuAiClient
            self.glm_client = ZhipuAiClient(api_key=settings.zhipu_api_key)
            self.glm_initialized = True
            logger.info("GLM client initialized successfully")
        except ImportError:
            logger.error("zai-sdk package not installed. Please run: pip install zai-sdk")
        except Exception as e:
            logger.error(f"Failed to initialize GLM client: {e}")

    def is_available(self) -> bool:
        return self.glm_initialized

    def reload(self):
        self.glm_initialized = False
        self.glm_client = None
        self._init_glm()

    def get_model_status(self) -> List[Dict]:
        result = []
        for idx, model in enumerate(self.GLM_MODELS):
            result.append({
                "name": model,
                "priority": idx + 1,
                "available": self.glm_initialized,
            })
        return result

    def update_models(self, model_list: List[str]):
        self.GLM_MODELS = list(model_list)

    GLM_MODELS = [
        "glm-4.7",
        "glm-4.5-air",
        "glm-4.7-flash",
    ]

    async def analyze_trends(
        self,
        analysis_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self.is_available():
            logger.warning("AI service not available")
            return None

        start_time = time.time()
        last_error = None

        for model in self.GLM_MODELS:
            for attempt in range(2):
                try:
                    result = await self._call_glm_with_model(
                        model=model,
                        analysis_data=analysis_data,
                    )
                    if result:
                        elapsed_ms = int((time.time() - start_time) * 1000)
                        result["processing_time_ms"] = elapsed_ms
                        result["model"] = model
                        logger.info(f"AI analysis completed with model={model}, "
                                   f"tokens={result.get('tokens_used', 0)}, "
                                   f"time={elapsed_ms}ms")
                        return result
                except Exception as e:
                    last_error = e
                    logger.warning(f"Attempt {attempt + 1} with model {model} failed: {e}")
                    await asyncio.sleep(1 * (attempt + 1))
                    continue

        logger.error(f"All AI analysis attempts failed. Last error: {last_error}")
        return None

    async def _call_glm_with_model(
        self,
        model: str,
        analysis_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self.glm_client:
            return None

        prompt = self._build_structured_prompt(analysis_data)

        response = await asyncio.to_thread(
            self.glm_client.chat.completions.create,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的经济学研究趋势分析专家。请基于提供的全量统计数据进行分析，并严格按照JSON格式输出结果。所有统计数据均来自数据库全量聚合，覆盖100%论文数据。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"},
            thinking={"type": "enabled"},
            max_tokens=8192,
            temperature=0.7
        )

        analysis_text = response.choices[0].message.content

        tokens_used = 0
        if hasattr(response, 'usage') and response.usage:
            tokens_used = getattr(response.usage, 'total_tokens', 0)

        parsed = self._parse_structured_result(analysis_text, model, tokens_used)
        return parsed

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

        return f"""请基于以下经济学论文全量统计数据进行分析，并严格按照以下JSON格式返回结果，不要包含其他任何内容：

{{
  "summary": "整体分析摘要（100字以内）",
  "hot_topics": [
    {{
      "topic": "热点主题名称",
      "description": "该热点的具体描述",
      "related_keywords": ["相关关键词1", "相关关键词2"],
      "significance": "重要性分析"
    }}
  ],
  "development_trends": [
    {{
      "trend": "趋势名称",
      "direction": "up/down/stable",
      "description": "趋势描述",
      "evidence": "数据支撑"
    }}
  ],
  "keyword_insights": [
    {{
      "cluster": "关键词聚类名称",
      "keywords": ["关键词1", "关键词2"],
      "insight": "洞察分析"
    }}
  ],
  "journal_insights": [
    {{
      "journal": "期刊名称",
      "focus": "研究偏好",
      "suggestion": "投稿建议"
    }}
  ],
  "recommendations": [
    {{
      "area": "研究方向",
      "description": "研究建议",
      "opportunity_level": "high/medium/low"
    }}
  ]
}}

## 数据概览（全量统计）
- 论文总数：{total_papers}篇
- 期刊数量：{len(journal_dist)}个
- 时间跨度：{year_dist[0]['year'] if year_dist else 'Unknown'} - {year_dist[-1]['year'] if year_dist else 'Unknown'}

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

请确保：
1. 只返回JSON，不要包含任何markdown代码块标记或其他说明文字
2. 每个数组至少包含2-3个项目
3. 分析要基于全量统计数据，有具体数据支撑
4. 特别关注子领域分布、关键词共现关系和年度变迁趋势
5. 结合各年度热门关键词变迁分析研究热点的演化
6. 中文输出"""

    def _parse_structured_result(
        self, analysis_text: str, model: str, tokens_used: int
    ) -> Optional[Dict[str, Any]]:
        import json
        import re

        text = analysis_text.strip()
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            text = json_match.group()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from GLM response, falling back to text")
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
