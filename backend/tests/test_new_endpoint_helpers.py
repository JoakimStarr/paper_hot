"""#14 新增端点纯函数回归保护（不依赖 DB / LLM）。

覆盖重构后抽出的可测逻辑：
- papers.py._rule_relevance_score      （/papers/{id}/relevance 规则兜底分支）
- network.py._aggregate_research_map   （/network/keyword-map 共现/年度/期刊聚合）
- topic.py._crowding_stats             （/topic-validator/validate 拥挤度信号）
"""
from types import SimpleNamespace

from app.routers.papers import _rule_relevance_score
from app.routers.network import _aggregate_research_map
from app.routers.topic import _crowding_stats


# ---------- papers.py: 相关性规则兜底 ----------

class TestRuleRelevanceScore:
    def test_exact_keyword_overlap(self):
        score, overlap = _rule_relevance_score("数字经济 平台经济", ["数字经济", "共同富裕"])
        assert overlap == ["数字经济"]
        # len(paper_kws)=2 → 得分 = min(1, 1/2) = 0.5
        assert score == 0.5

    def test_full_overlap_clamps_to_one(self):
        # 两个关键词都与选题重合 → 2/2 = 1.0
        score, _ = _rule_relevance_score("通货膨胀货币政策", ["通货膨胀", "货币"])
        assert score == 1.0

    def test_no_overlap_zero(self):
        score, overlap = _rule_relevance_score("气候金融", ["房地产", "城市化"])
        assert score == 0.0
        assert overlap == []

    def test_short_keyword_prefix_match(self):
        # kw[:6] in topic 命中前缀逻辑
        score, overlap = _rule_relevance_score("数字普惠金融的发展", ["数字普惠金融"])
        assert overlap == ["数字普惠金融"]
        assert score > 0

    def test_empty_keywords_no_crash(self):
        score, overlap = _rule_relevance_score("金融", [])
        assert score == 0.0
        assert overlap == []


# ---------- network.py: keyword-map 聚合 ----------

def _paper(kws=None, published=None, journal=None, venue=None):
    return SimpleNamespace(
        keywords_cn=kws or [],
        published_at=published,
        journal_name=journal,
        venue=venue,
    )


class TestAggregateResearchMap:
    def test_cooccur_counts_and_excludes_self(self):
        papers = [
            _paper(["数字经济", "平台", "监管"], "2026-01-10", "经济研究", None),
            _paper(["数字经济", "平台"], "2025-06-01", "管理世界", None),
            _paper(["其它", "平台"], "2025-01-01", None, "管理世界"),
        ]
        cooccur, yearly, journals = _aggregate_research_map("数字经济", papers)
        # 平台在 3 篇里被统计（p3 含平台，如实计入），监管仅 1 次；不含"数字经济"自身
        assert cooccur["平台"] == 3
        assert cooccur["监管"] == 1
        assert "数字经济" not in cooccur
        assert yearly == {"2026": 1, "2025": 2}
        assert journals["经济研究"] == 1
        assert journals["管理世界"] == 2  # journal_name + venue 兜底

    def test_excludes_broad_term_containing_keyword(self):
        # 查询"经济"时，"经济研究"（含子串）应被剔除
        papers = [_paper(["经济研究", "房价"], "2026-01-01", "AJ", None)]
        cooccur, _, _ = _aggregate_research_map("经济", papers)
        assert "经济研究" not in cooccur
        assert cooccur["房价"] == 1

    def test_empty_input(self):
        cooccur, yearly, journals = _aggregate_research_map("词", [])
        assert cooccur == {} and yearly == {} and journals == {}


# ---------- topic.py: 拥挤度统计 ----------

class TestCrowdingStats:
    def test_avg_similarity_and_keyword_overlap(self):
        now = "2026-08-01T00:00:00Z"
        papers = [
            {"similarity": 0.8, "published_at": now, "keywords": ["碳排放", "碳市场"]},
            {"similarity": 0.4, "published_at": now, "keywords": ["碳排放"]},
        ]
        stats = _crowding_stats(papers)
        assert stats["top30_avg_similarity"] == 0.6
        assert stats["max_similarity"] == 0.8
        assert stats["recent_3m_count"] == 2
        kw = {k["keyword"]: k["count"] for k in stats["keyword_overlap"]}
        assert kw["碳排放"] == 2 and kw["碳市场"] == 1

    def test_empty_papers(self):
        stats = _crowding_stats([])
        assert stats["top30_avg_similarity"] == 0.0
        assert stats["recent_3m_count"] == 0

    def test_old_published_not_counted_recent(self):
        papers = [{"similarity": 0.5, "published_at": "2020-01-01T00:00:00Z", "keywords": ["k"]}]
        stats = _crowding_stats(papers)
        assert stats["recent_3m_count"] == 0

    def test_invalid_published_at_does_not_break(self):
        papers = [{"similarity": 0.5, "published_at": "not-a-date", "keywords": ["k"]}]
        stats = _crowding_stats(papers)
        assert stats["recent_3m_count"] == 0
        assert stats["top30_avg_similarity"] == 0.5