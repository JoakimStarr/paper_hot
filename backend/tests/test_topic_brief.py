"""P0-6 单测：选题验证器两条纯函数（topic.py）回归保护。

- _paper_brief：行数据 -> 精简卡片，重点验证 published_at 的 datetime/str/Z 后缀
  兼容与 keywords 列表/非列表防护。
- _cosine_top_k：embedding 余弦召回，验证 top-k 排序与零向量防御。
"""
import datetime

from app.routers.topic import _paper_brief, _cosine_top_k


def _row(paper_id, keywords, title, abstract, source, published):
    return (paper_id, keywords, title, abstract, source, published)


def test_paper_brief_datetime_naive():
    """naive datetime（无 tzinfo）→ 补 UTC 的 ISO 字符串。"""
    r = _row("p1", ["k1", "k2"], "标题", "摘要内容", "CNKI", datetime.datetime(2026, 8, 1))
    out = _paper_brief(r, 0.85)
    assert out["id"] == "p1"
    assert out["title"] == "标题"
    assert out["abstract"] == "摘要内容"
    assert out["published_at"] == "2026-08-01T00:00:00+00:00"
    assert out["keywords"] == ["k1", "k2"]
    assert out["similarity"] == 0.85


def test_paper_brief_tz_aware():
    """带 tzinfo 的 datetime → 保留原时区的 ISO。"""
    r = _row("p2", ["k"], "t", "a", "arxiv", datetime.datetime(2026, 7, 15, tzinfo=datetime.timezone.utc))
    out = _paper_brief(r, 0.5)
    assert out["published_at"].startswith("2026-07-15")


def test_paper_brief_str_z_suffix():
    """ISO 字符串带 Z 后缀 → 转为 +00:00。"""
    r = _row("p3", [], "t", "a", "CNKI", "2026-06-01T10:00:00Z")
    out = _paper_brief(r, 0.1)
    assert out["published_at"] == "2026-06-01T10:00:00+00:00"


def test_paper_brief_empty_published():
    r = _row("p4", ["k"], "t", "a", "arxiv", None)
    out = _paper_brief(r, 0.0)
    assert out["published_at"] is None


def test_paper_brief_nonlist_keywords_guarded():
    """keywords 非 list（如 None/字符串）→ 安全置空，不抛异常。"""
    r = _row("p5", "not-a-list", "t", "a", "CNKI", None)
    out = _paper_brief(r, 0.2)
    assert out["keywords"] == []


def test_cosine_top_k_ranks_by_similarity():
    q = [1.0, 0.0]
    candidates = [
        ("far", [0.0, 1.0]),
        ("close", [1.0, 0.0]),
    ]
    top = _cosine_top_k(q, candidates, k=2)
    assert top[0][0] == "close"   # 与查询同向 → cos=1 最高
    assert top[1][0] == "far"

    close_score = dict(top)["close"]
    far_score = dict(top)["far"]
    assert close_score > far_score


def test_cosine_top_k_zero_query_returns_empty():
    q = [0.0, 0.0]
    candidates = [("a", [1.0, 0.0])]
    assert _cosine_top_k(q, candidates, k=5) == []


def test_cosine_top_k_k_limit():
    q = [1.0, 0.0, 0.0]
    candidates = [
        ("a", [1.0, 0.0, 0.0]),
        ("b", [0.9, 0.1, 0.0]),
        ("c", [0.0, 1.0, 0.0]),
    ]
    top = _cosine_top_k(q, candidates, k=2)
    assert len(top) == 2
    assert top[0][0] == "a"