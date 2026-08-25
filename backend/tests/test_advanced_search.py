"""P1-9 研究级检索：高级语法解析器单测。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import select

from app.crud import (
    _ADVANCED_SEARCH_RE,
    _build_advanced_search_condition,
    _tokenize_advanced_search,
)
from app.models import Paper


def _compile(condition):
    """把条件编译成 SQLite SQL 文本与绑定参数，便于断言结构。"""
    compiled = select(Paper.id).where(condition).compile(
        dialect=None, compile_kwargs={"literal_binds": False}
    )
    return str(compiled), compiled.params


class TestAdvancedSearchDetection:
    def test_plain_query_not_matched(self):
        assert _ADVANCED_SEARCH_RE.search("数字经济") is None
        assert _ADVANCED_SEARCH_RE.search("carbon tax") is None

    def test_markers_detected(self):
        for q in ['"数字普惠金融"', "author:张三", "a AND b", "a OR b", "a NOT b"]:
            assert _ADVANCED_SEARCH_RE.search(q), q


class TestTokenizer:
    def test_phrase_and_words(self):
        tokens = _tokenize_advanced_search('"数字 金融" 数字经济')
        # (phrase-group, word-group, empty) 三元组形式
        kinds = [k for k, _, _ in [(t[0], t[1], t[2]) for t in tokens]]
        assert any(t[0] for t in tokens)          # 引号短语捕获组
        assert any(t[2] == "数字经济" for t in tokens)

    def test_author_prefix(self):
        tokens = _tokenize_advanced_search("author:张三")
        assert any(t[1] == "author:张三" for t in tokens)


class TestConditionBuild:
    def test_simple_and(self):
        sql, params = _compile(_build_advanced_search_condition("数字经济 实证"))
        assert str(sql).count("LIKE") >= 4  # 两词 x (title+abstract)，另有关键词子查询
        assert "json_each" in str(sql).lower()
        assert any("%数字经济%" in str(v) for v in params.values())

    def test_quoted_phrase_single_pattern(self):
        sql, params = _compile(_build_advanced_search_condition('"数字普惠金融"'))
        assert any("%数字普惠金融%" in str(v) for v in params.values())

    def test_not_excludes(self):
        sql, _ = _compile(_build_advanced_search_condition("金融 NOT 房地产"))
        assert "NOT" in str(sql).upper()

    def test_or_groups(self):
        sql, _ = _compile(_build_advanced_search_condition("数字经济 OR 绿色金融"))
        assert " OR " in str(sql).upper()

    def test_author_filter(self):
        sql, params = _compile(_build_advanced_search_condition("author:张三"))
        assert "json_each.value = " in str(sql)
        assert "张三" not in str(sql)  # 参数绑定而非字符串拼接
        assert "张三" in [str(v) for v in params.values()]

    def test_operators_only_returns_none(self):
        assert _build_advanced_search_condition("AND OR NOT") is None
        assert _build_advanced_search_condition("") is None
