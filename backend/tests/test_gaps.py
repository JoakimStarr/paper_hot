"""P0-6 单测：研究空白识别（stats.py 纯函数部分）回归保护。

断言集中在：共现统计正确性、空白分随共现饱和度下降、热门词参与排序、以及
高分空白取自"各自高频但少共现"的组合。
"""
from app.stats import _gap_score, _cooc_from_paper_keywords


def test_cooc_from_paper_keywords_counts_frequency_and_pairs():
    """词频与两两共现统计正确（A-B 共现与 B-A 同，升序 pair）。"""
    papers = [
        ["A", "B"],
        ["A", "B"],
        ["A", "C"],
    ]
    kwc, cooc = _cooc_from_paper_keywords(papers)
    assert kwc["A"] == 3
    assert kwc["B"] == 2
    assert kwc["C"] == 1
    assert cooc[("A", "B")] == 2
    assert cooc[("A", "C")] == 1
    assert ("B", "A") not in cooc  # 统一升序键


def test_cooc_ignores_empty_keyword_lists():
    """空列表不产生共现/词频；非空列表正常统计。"""
    kwc, cooc = _cooc_from_paper_keywords([[], ["X"], ["Y", "Z"]])
    assert kwc["X"] == 1
    assert cooc.get(("Y", "Z"), 0) == 1
    assert sum(cooc.values()) == 1
    assert "A" not in kwc


def test_gap_score_drops_with_confound_cooccurrence():
    """越共现的 pair 空白分越低：同 freq 下共现多 < 共现少。"""
    gap_high = _gap_score(cnt_a=50, cnt_b=50, co=0, max_count=100)          # 共现 0 → 空白最高
    gap_low = _gap_score(cnt_a=50, cnt_b=50, co=49, max_count=100)          # 共现 49/50 → 饱和≈1
    gap_zero_freq = _gap_score(cnt_a=0, cnt_b=50, co=0, max_count=100)      # 冷词 → 0
    assert gap_high > gap_low >= 0
    assert 0.0 <= gap_high - gap_low  # 单调：共现越多分越低
    assert gap_zero_freq == 0.0


def test_gap_score_promotes_hot_low_cooc():
    """两词都高频但共现 0 → 进入空白候选并且比值高于高共现组合。"""
    gxy = _gap_score(20, 20, 5, max_count=20)   # 热度高、饱和度 5/20 → 空白大
    gpq = _gap_score(6, 6, 6, max_count=20)     # 共现 6/6 饱和 1 → 空白 0
    assert gxy > 0
    assert gpq == 0.0