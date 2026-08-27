"""评分模块：全站唯一评分事实源（P0-1 统一）。

背景（PRODUCT_PLAN P0-1）：旧实现（0.5/0.3/0.2 + 0.1/天线性衰减）与
crud.PaperCRUD 的公式（0.35/0.35/0.30 + 180 天半衰期）并存，同一篇论文分数
取决于走哪条爬虫路径。本模块收敛为**单一入口**：直接委托 PaperCRUD 的静态
方法与常量，保证 scheduler（本模块）与 crud（PaperCRUD._xxx）结果完全一致。

保留原类接口（compute_recency_score / compute_venue_score / compute_trend_score /
compute_final_score）以兼容既有调用方，仅内部实现收敛。
"""
from datetime import datetime
from typing import Optional


class ScoringSystem:
    def __init__(self):
        # 注意：本类不自持任何权重/衰减参数，全部以 crud.PaperCRUD 为唯一事实源。
        pass

    @staticmethod
    def _crud():
        from app.crud import PaperCRUD
        return PaperCRUD

    def compute_recency_score(self, published_at: Optional[datetime]) -> float:
        """委托 PaperCRUD._recency_score：180 天半衰期指数衰减。"""
        return self._crud()._recency_score(published_at)

    def compute_venue_score(self, venue: Optional[str], source: Optional[str] = None) -> float:
        # 统一用期刊分级（arxiv 也走同一张白名单，收窄为单一分支）
        return self._crud()._venue_score(venue)

    def compute_trend_score(
        self,
        keywords: list,
        keyword_frequencies: dict,
        previous_frequencies: dict,
        topic_growth_rate: Optional[float] = None
    ) -> float:
        """委托 PaperCRUD._trend_score（tanh 平滑 0..1）。

        keyword_frequencies / previous_frequencies 参数自 P0 统一后不再参与
        公式（历史签名兼容保留）；趋势分只来自 topic_growth_rate，
        缺省时按增长率 0 取中性分。
        """
        return self._crud()._trend_score(topic_growth_rate if topic_growth_rate is not None else 0.0)

    def compute_final_score(
        self,
        recency_score: float,
        venue_score: float,
        trend_score: float
    ) -> float:
        # 委托 PaperCRUD._final_score：0.35/0.35/0.30 加权
        return self._crud()._final_score(recency_score, venue_score, trend_score)
