"""
GLM AI 分析服务
使用 zai-sdk 库，支持深度思考模式
"""

import logging
from typing import Optional, Dict, Any, List
from app.config import settings

logger = logging.getLogger(__name__)

# GLM模型优先级（从高到低）
GLM_MODELS = [
    "glm-4.7",              # 最强模型，支持深度思考
    "glm-4.6v",             # 视觉模型
    "glm-4.5-air",          # 快速模型
    "glm-4.7-flash",        # 极速模型
    "glm-4.6v-flash",       # 视觉极速模型
]


class GLMAnalyzer:
    """GLM AI 分析器"""
    
    def __init__(self):
        self.api_key = settings.zhipu_api_key
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """初始化GLM客户端"""
        if not self.api_key:
            logger.warning("Zhipu API key not set. AI analysis will be limited.")
            return
        
        try:
            from zai import ZhipuAiClient
            self.client = ZhipuAiClient(api_key=self.api_key)
            logger.info("GLM client initialized successfully with zai-sdk")
        except ImportError:
            logger.error("zai-sdk package not installed. Please run: pip install zai-sdk")
        except Exception as e:
            logger.error(f"Failed to initialize GLM client: {e}")
    
    def _get_best_available_model(self) -> Optional[str]:
        """获取最佳可用模型"""
        if not self.client:
            return None
        
        # 返回优先级最高的模型
        return GLM_MODELS[0]
    
    async def analyze_trends(
        self,
        papers_data: List[Dict[str, Any]],
        keywords_data: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        分析论文趋势
        
        Args:
            papers_data: 论文数据列表
            keywords_data: 关键词趋势数据列表
            
        Returns:
            分析结果字典
        """
        if not self.client:
            logger.warning("GLM client not initialized, returning None")
            return None
        
        model = self._get_best_available_model()
        if not model:
            return None
        
        # 构建提示词
        prompt = self._build_analysis_prompt(papers_data, keywords_data)
        
        try:
            logger.info(f"Analyzing trends with model: {model}")
            
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的经济学研究趋势分析专家。请基于提供的数据，进行深入的趋势分析，并给出专业、有见地的分析报告。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                thinking={
                    "type": "enabled",    # 启用深度思考模式
                },
                max_tokens=65536,          # 最大输出 tokens
                temperature=1.0            # 控制输出的随机性
            )
            
            analysis_text = response.choices[0].message.content
            
            # 解析分析结果
            result = self._parse_analysis_result(analysis_text, model)
            
            logger.info("Trend analysis completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing trends: {e}")
            return None
    
    def _build_analysis_prompt(
        self,
        papers_data: List[Dict[str, Any]],
        keywords_data: List[Dict[str, Any]]
    ) -> str:
        """构建分析提示词"""
        
        # 统计数据
        total_papers = len(papers_data)
        
        # 关键词统计
        top_keywords = sorted(keywords_data, key=lambda x: x.get('paper_count', 0), reverse=True)[:20]
        
        # 期刊分布
        journals = {}
        for paper in papers_data:
            journal = paper.get('journal_name', 'Unknown')
            journals[journal] = journals.get(journal, 0) + 1
        
        # 时间分布
        years = {}
        for paper in papers_data:
            published_at = paper.get('published_at', '')
            if published_at:
                year = published_at[:4] if len(published_at) >= 4 else 'Unknown'
                years[year] = years.get(year, 0) + 1
        
        prompt = f"""
请基于以下经济学论文数据，进行全面深入的趋势分析：

## 数据概览
- 论文总数：{total_papers}篇
- 时间跨度：{min(years.keys()) if years else 'Unknown'} - {max(years.keys()) if years else 'Unknown'}
- 期刊数量：{len(journals)}个

## 期刊分布
{self._format_dict(journals, '期刊', '论文数')}

## 时间分布
{self._format_dict(years, '年份', '论文数')}

## 热门关键词（前20个）
{self._format_keywords(top_keywords)}

## 分析要求
请从以下几个维度进行深入分析：

1. **研究热点分析**
   - 当前最热门的研究方向是什么？
   - 这些热点反映了哪些经济学理论和实践问题？
   - 热点之间的关联性和演变趋势

2. **发展趋势预测**
   - 基于当前数据，预测未来可能的研究热点
   - 哪些新兴领域值得关注？
   - 可能出现的跨学科研究方向

3. **关键词关联分析**
   - 关键词之间的内在联系
   - 研究主题的聚类特征
   - 方法论和理论框架的演进

4. **期刊特色分析**
   - 不同期刊的研究偏好
   - 期刊定位和影响力
   - 投稿建议

5. **研究建议**
   - 对年轻研究者的建议
   - 潜在的研究机会
   - 值得关注的理论和方法

请用专业、准确、有见地的语言进行分析，并提供具体的数据支撑和案例说明。
"""
        
        return prompt
    
    def _format_dict(self, data: Dict, key_name: str, value_name: str) -> str:
        """格式化字典数据"""
        if not data:
            return f"暂无{key_name}数据"
        
        lines = []
        for key, value in sorted(data.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- {key}: {value}{value_name}")
        
        return '\n'.join(lines)
    
    def _format_keywords(self, keywords: List[Dict]) -> str:
        """格式化关键词数据"""
        if not keywords:
            return "暂无关键词数据"
        
        lines = []
        for i, kw in enumerate(keywords, 1):
            keyword = kw.get('topic', 'Unknown')
            count = kw.get('paper_count', 0)
            growth = kw.get('growth_rate', 0)
            growth_str = f"+{growth*100:.1f}%" if growth > 0 else f"{growth*100:.1f}%"
            lines.append(f"{i}. {keyword}: {count}篇 (增长率: {growth_str})")
        
        return '\n'.join(lines)
    
    def _parse_analysis_result(self, analysis_text: str, model: str) -> Dict[str, Any]:
        """解析分析结果"""
        from datetime import datetime
        return {
            "analysis": analysis_text,
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "status": "success"
        }


# 全局实例
glm_analyzer = GLMAnalyzer()
