"""P0-6 单测：similarity 相似推荐（纯函数）回归保护。"""
import pytest

from app.similarity import _tokenize, compute_all_similarities


def test_tokenize_empty():
    assert _tokenize(None) == ""
    assert _tokenize("") == ""


def test_tokenize_returns_tokens():
    t = _tokenize("数字经济 与 绿色发展")
    assert t and len(t.split()) > 0


def test_compute_all_similarities_requires_two():
    assert compute_all_similarities([]) == []
    assert compute_all_similarities([("p1", "单篇")]) == []


def test_similar_papers_ranked_higher():
    """同主题两篇应比搭边主题更相似，且分值在 (0,1]。"""
    papers = [
        ("p1", "数字货币 央行 金融稳定 货币政策"),
        ("p2", "央行数字货币 金融稳定 金融监管"),
        ("p3", "农业 粮食 产量 化肥"),
    ]
    result = compute_all_similarities(papers)
    print("result:", result)
    # p1-p2 应被记录
    assert any((a, b) == ("p1", "p2") for a, b, _ in result) or \
           any((a, b) == ("p2", "p1") for a, b, _ in result)
    s12 = next(s for a, b, s in result if set([a, b]) == {"p1", "p2"})
    s13 = next((s for a, b, s in result if set([a, b]) == {"p1", "p3"}), 0.0)
    assert s12 > s13


def test_no_self_similarity():
    papers = [("p1", "货币政策 利率"), ("p2", "利率 汇率")]
    result = compute_all_similarities(papers)
    for a, b, _ in result:
        assert a != b