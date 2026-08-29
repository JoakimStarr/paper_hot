"""参考文献条目解析纯函数测试。

用例覆盖：知网引文格式（作者在后）、GB/T 7714（作者在前）、外文条目、
无类型标记条目、无年份条目；以及真实库内 references_cn 数据的解析覆盖率
（backend/data/paperpulse.db 存在时运行，否则跳过）。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cnki_crawler.parsing import (  # noqa: E402
    _is_cnki_detail_url,
    _norm_title,
    _parse_ref_meta,
    _ref_title_keys,
)

CASES = [
    # 知网参考文献页签格式：序号.题名[类型].作者.来源,年(期)（作者在后）
    ("[1] 数据要素成为中国经济增长新动能的机制探析[J]. 刘涛雄;张亚迪;戎珂;周迪.经济研究,2024(10)",
     (2024, "经济研究"), "数据要素成为中国经济增长新动能的机制探析"),
    ("[2] 企业裂变创业研究——基于理论成熟度阶梯的述评[J]. 李鸿磊;王凤彬.管理世界,2025(05)",
     (2025, "管理世界"), "企业裂变创业研究——基于理论成熟度阶梯的述评"),
    # GB/T 7714：作者在前
    ("1. 张三. 中国经济增长研究[J]. 经济研究, 2020(3): 12-25.",
     (2020, "经济研究"), "中国经济增长研究"),
    ("Acemoglu D. Institutions[J]. AER, 2001, 91(5):1369.",
     (2001, "AER"), "Acemoglu D. Institutions"),
    # 学位论文 / 图书（图书带冒号 → 不认作来源）
    ("[3] 博士论文[D]. 王五.北京大学,2019.", (2019, "北京大学"), "博士论文"),
    ("李四. 转型经济学[M]. 北京: 商务印书馆, 2018.", (2018, None), "转型经济学"),
    # 外文条目（来源与年份之间是句点）
    ("[1] The short-run employment effects of public infrastructure investment[J]. "
     "Alexander Matusche.European Economic Review.2025",
     (2025, "European Economic Review"),
     "The short-run employment effects of public infrastructure investment"),
    # 无类型标记（真实库内常见）：序号.题名.作者.来源,年(期)
    ("[4] 公共数据开放对县域城乡融合发展的影响研究. 黄林秀;李丹丹.宏观经济研究,2026(06)",
     (2026, "宏观经济研究"), "公共数据开放对县域城乡融合发展的影响研究"),
    # 无年份（录用定稿等）→ 不解析，宁可跳过
    ("[1] 公共数据开放与家庭收入结构优化. 冯诗棠;李勇刚;杨祝三.软科学",
     (None, None), "公共数据开放与家庭收入结构优化"),
]


@pytest.mark.parametrize("text,meta,title", CASES)
def test_parse_ref_meta_and_title(text, meta, title):
    assert _parse_ref_meta(text) == meta
    assert _norm_title(title) in _ref_title_keys(text)


def test_norm_title_strips_punct():
    assert _norm_title("中国 经济-增长研究") == "中国经济增长研究"


def test_title_keys_empty_for_blank():
    assert _ref_title_keys("") == set()
    assert _ref_title_keys(None) == set()


def test_is_cnki_detail_url():
    assert _is_cnki_detail_url("https://kns.cnki.net/kcms2/article/abstract?v=abc&uniplatform=NZKPT")
    assert _is_cnki_detail_url("https://kns.cnki.net/kcms/detail/detail.aspx?dbcode=CJFD&filename=X")
    assert not _is_cnki_detail_url("")
    assert not _is_cnki_detail_url(None)
    assert not _is_cnki_detail_url("https://www.cnki.net/")
    assert not _is_cnki_detail_url("https://example.com/kcms2/article/abstract?v=1")


def test_real_db_reference_coverage():
    """真实库内 references_cn 数据的解析覆盖率（DB 缺失时跳过）。"""
    db_file = Path(__file__).resolve().parents[1] / 'backend' / 'data' / 'paperpulse.db'
    if not db_file.exists():
        pytest.skip("paperpulse.db 不存在")
    import sqlite3

    con = sqlite3.connect(f'file:{db_file}?mode=ro', uri=True)
    try:
        rows = con.execute("SELECT references_cn FROM papers WHERE references_cn IS NOT NULL").fetchall()
        titles = {_norm_title(r[0]) for r in con.execute("SELECT title FROM papers").fetchall() if r[0]}
    finally:
        con.close()
    if not rows:
        pytest.skip("库内无参考文献数据")
    refs = [it for (rc,) in rows for it in (json.loads(rc) if rc else [])]
    assert refs, "参考文献数据为空"

    n_url, n_cnki, n_year, n_journal, n_title, n_title_hit = 0, 0, 0, 0, 0, 0
    for r in refs:
        text, url = r.get('text') or '', r.get('url')
        if url:
            n_url += 1
            if _is_cnki_detail_url(url):
                n_cnki += 1
        year, journal = _parse_ref_meta(text)
        if year:
            n_year += 1
        if journal:
            n_journal += 1
        keys = _ref_title_keys(text)
        if keys:
            n_title += 1
            if keys & titles:
                n_title_hit += 1

    total = len(refs)
    assert n_url == total, "真实数据里参考文献应全部带链接"
    assert n_cnki == total, "真实数据里应全部是可导航的知网详情页链接"
    assert n_year / total > 0.9, f"年份解析覆盖率偏低: {n_year}/{total}"
    assert n_journal / total > 0.9, f"来源解析覆盖率偏低: {n_journal}/{total}"
    assert n_title == total, "题名判重键应全部能抽出"
