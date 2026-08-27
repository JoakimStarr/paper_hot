"""P0-6 单测：scoring 统一公式验证（P0-1 的回归保护）。

断言集中在：weight、half-life 衰减方向、趋势分 tanh 映射、final 加权、边界裁剪。
"""
import datetime
import pytest


def make_score_system():
    from app.scoring import ScoringSystem
    return ScoringSystem()


def test_final_score_weights():
    """0.35/0.35/0.30 加权：三项同为 1.0 → 恒等于 1.0。"""
    s = make_score_system()
    assert s.compute_final_score(1.0, 1.0, 1.0) == pytest.approx(1.0, abs=1e-6)
    # 只 recency=1 其余 0 → 0.35
    assert s.compute_final_score(1.0, 0.0, 0.0) == pytest.approx(0.35, abs=1e-4)
    # 三项 0.5→0.5
    assert s.compute_final_score(0.5, 0.5, 0.5) == pytest.approx(0.5, abs=1e-4)


def test_recency_half_life():
    """180 天半衰期：180 天前 → 约 0.5；今天 → ≈1.0；且单调递减。"""
    s = make_score_system()
    now = datetime.datetime(2026, 8, 25, 12, 0, 0)
    today = s.compute_recency_score(now)
    half = s.compute_recency_score(now - datetime.timedelta(days=180))
    older = s.compute_recency_score(now - datetime.timedelta(days=360))
    assert 0.99 <= today <= 1.0
    assert half == pytest.approx(0.5, abs=0.02)
    assert half > older


def test_recency_none_default():
    """published_at 缺失 → 0.3 中性兜底（与 PaperCRUD 一致，非 0）。"""
    s = make_score_system()
    assert s.compute_recency_score(None) == pytest.approx(0.3)


def test_trend_tanh():
    """趋势分 tanh 映射：g>0 抬升、g<0 压低、g=0 → 0.5。"""
    s = make_score_system()
    assert s.compute_trend_score([], {}, {}, topic_growth_rate=0) == pytest.approx(0.5, abs=1e-6)
    up = s.compute_trend_score([], {}, {}, topic_growth_rate=1.0)
    down = s.compute_trend_score([], {}, {}, topic_growth_rate=-0.5)
    assert up > 0.5
    assert 0 <= down < 0.5
    assert up > down


def test_final_not_clamped_raw_weighted():
    """compute_final_score 只加权不裁剪。"""
    s = make_score_system()
    # 2.0 三项 → 2.0（加权后仍 >1，说明不在本层裁剪）
    assert s.compute_final_score(2.0, 2.0, 2.0) == pytest.approx(2.0, abs=1e-4)
    assert s.compute_final_score(-1.0, -1.0, -1.0) == pytest.approx(-1.0, abs=1e-4)


def test_trend_score_neutral_fallback():
    """无增长率时趋势分取中性 0.5（签名兼容历史频率参数）。"""
    s = make_score_system()
    assert s.compute_trend_score([], {"kw": 5}, {}) == pytest.approx(0.5, abs=1e-6)