from datetime import datetime, timedelta
from typing import Optional
import math
from app.fetchers import VenueDataFetcher


class ScoringSystem:
    def __init__(self):
        self.recency_decay_rate = 0.1
        self.venue_fetcher = VenueDataFetcher()
    
    def compute_recency_score(self, published_at: Optional[datetime]) -> float:
        if not published_at:
            return 0.5
        
        now = datetime.now(published_at.tzinfo) if published_at.tzinfo else datetime.now()
        days_old = (now - published_at).days
        
        score = math.exp(-self.recency_decay_rate * days_old)
        
        return min(max(score, 0.0), 1.0)
    
    def compute_venue_score(self, venue: Optional[str], source: str) -> float:
        if source.lower() == "arxiv":
            return self.venue_fetcher.get_venue_score(venue or "arxiv")
        
        return self.venue_fetcher.get_venue_score(venue)
    
    def compute_trend_score(
        self,
        keywords: list,
        keyword_frequencies: dict,
        previous_frequencies: dict,
        topic_growth_rate: Optional[float] = None
    ) -> float:
        """
        计算趋势分数
        
        优先使用主题增长率（从 TopicTrend 表获取），
        如果没有则回退到关键词频率计算
        
        使用 Sigmoid 函数平滑映射：
        score = 0.5 + 0.5 * tanh(growth_rate)
        
        示例：
        - growth_rate = 0（无增长）→ score = 0.5
        - growth_rate = 1（100%增长）→ score = 0.88
        - growth_rate = -0.5（下降50%）→ score = 0.27
        """
        # 优先使用主题增长率（更准确）
        if topic_growth_rate is not None:
            # 使用 tanh 函数平滑映射到 0-1 范围
            score = 0.5 + 0.5 * math.tanh(topic_growth_rate)
            return min(max(score, 0.0), 1.0)
        
        # 回退到关键词频率计算（旧逻辑）
        if not keywords:
            return 0.5
        
        growth_rates = []
        for keyword in keywords:
            current_freq = keyword_frequencies.get(keyword, 0)
            previous_freq = previous_frequencies.get(keyword, 0)
            
            if previous_freq > 0:
                growth_rate = (current_freq - previous_freq) / previous_freq
                growth_rates.append(growth_rate)
        
        if not growth_rates:
            return 0.5
        
        avg_growth = sum(growth_rates) / len(growth_rates)
        
        # 使用新的 Sigmoid 映射
        score = 0.5 + 0.5 * math.tanh(avg_growth)
        
        return min(max(score, 0.0), 1.0)
    
    def compute_final_score(
        self,
        recency_score: float,
        venue_score: float,
        trend_score: float
    ) -> float:
        final_score = (
            0.5 * recency_score +
            0.3 * venue_score +
            0.2 * trend_score
        )
        
        return min(max(final_score, 0.0), 1.0)
    
    def compute_should_read_score(
        self,
        final_score: float,
        has_summary: bool,
        topic_relevance: Optional[float] = None
    ) -> float:
        score = final_score
        
        if has_summary:
            score *= 1.1
        
        if topic_relevance is not None:
            score = score * 0.7 + topic_relevance * 0.3
        
        return min(max(score, 0.0), 1.0)
