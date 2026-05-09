"""
统一AI趋势分析服务
提供重试/降级、结构化输出、监控功能
"""

import logging
import time
import asyncio
from typing import Optional, Dict, Any, List, Tuple
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

    GLM_MODELS = [
        "glm-4.7",
        "glm-4.5-air",
        "glm-4.7-flash",
    ]

    async def analyze_trends(
        self,
        papers_data: List[Dict[str, Any]],
        keywords_data: List[Dict[str, Any]]
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
                        papers_data=papers_data,
                        keywords_data=keywords_data
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
        papers_data: List[Dict[str, Any]],
        keywords_data: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not self.glm_client:
            return None

        prompt = self._build_structured_prompt(papers_data, keywords_data)

        response = await asyncio.to_thread(
            self.glm_client.chat.completions.create,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的经济学研究趋势分析专家。请基于提供的数据进行分析，并严格按照JSON格式输出结果。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
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

    def _build_structured_prompt(
        self,
        papers_data: List[Dict[str, Any]],
        keywords_data: List[Dict[str, Any]]
    ) -> str:
        total_papers = len(papers_data)

        journals = {}
        for paper in papers_data:
            journal = paper.get('journal_name', 'Unknown')
            journals[journal] = journals.get(journal, 0) + 1

        years = {}
        for paper in papers_data:
            published_at = paper.get('published_at', '')
            if published_at:
                year = published_at[:4] if len(published_at) >= 4 else 'Unknown'
                years[year] = years.get(year, 0) + 1

        top_keywords = sorted(keywords_data, key=lambda x: x.get('paper_count', 0), reverse=True)[:20]

        keyword_lines = []
        for i, kw in enumerate(top_keywords, 1):
            keyword = kw.get('topic', 'Unknown')
            count = kw.get('paper_count', 0)
            growth = kw.get('growth_rate', 0)
            growth_str = f"+{growth*100:.1f}%" if growth > 0 else f"{growth*100:.1f}%"
            keyword_lines.append(f"{i}. {keyword}: {count}篇 (增长率: {growth_str})")

        journal_lines = []
        for key, value in sorted(journals.items(), key=lambda x: x[1], reverse=True):
            journal_lines.append(f"- {key}: {value}篇")

        year_lines = []
        for key, value in sorted(years.items(), key=lambda x: x[1], reverse=True):
            year_lines.append(f"- {key}: {value}篇")

        return f"""请基于以下经济学论文数据进行分析，并严格按照以下JSON格式返回结果，不要包含其他任何内容：

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

## 数据概览
- 论文总数：{total_papers}篇
- 期刊数量：{len(journals)}个
- 时间跨度：{min(years.keys()) if years else 'Unknown'} - {max(years.keys()) if years else 'Unknown'}

## 期刊分布
{chr(10).join(journal_lines)}

## 时间分布
{chr(10).join(year_lines)}

## 热门关键词（前20个）
{chr(10).join(keyword_lines)}

请确保：
1. 只返回JSON，不要包含任何markdown代码块标记或其他说明文字
2. 每个数组至少包含2-3个项目
3. 分析要基于数据，有具体支撑
4. 中文输出"""

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