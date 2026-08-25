"""数据质量清理脚本（一次性/可重跑）

背景：models.py 的 UnicodeJSON 曾用 impl=JSON，导致 list/dict 在入库时被
SQLAlchemy 底层再编码一次，存成双重 JSON 字符串（'"[\"a\", \"b\"]"'）。
影响：papers.authors / papers.keywords_cn / paper_features.keywords 共 2484+ 篇
论文被双重编码，统计聚合层（stats.py / json_each SQL）读不到这批关键词。

本脚本做三件事：
1. 解码双重编码的作者/关键词为正常 JSON 数组（幂等，可重复执行）
2. 清理标题中的"附视频"后缀
3. 修正 CNKI 早期解析 bug 产生的拼接作者名（findall 式切分错误）

用法（先停服）：
    cd backend && ../venv/bin/python scripts/cleanup_data_quality.py
"""
import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "paperpulse.db"

# 已人工核实的拼接作者名修正（论文标题 → 正确作者列表）
AUTHOR_FIXES = {
    "习近平全球问题论述开拓了马克思主义世界经济理论新境界": ["裴长洪", "倪江飞"],
    "质量共性技术促进科技创新和产业创新深度融合的功能与路径研究": ["张蕾蕾", "高勇", "徐畅"],
    "央行沟通情感识别、通胀预期形成机制与央行信誉优化": ["刘达禹", "李莹莹", "丁一兵", "李子"],
}


def decode_to_list(value):
    """将存储值解码为 Python list；兼容单层/双重编码。"""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, str):
        # 双重编码：内层仍是 JSON 文本
        try:
            inner = json.loads(parsed)
            if isinstance(inner, list):
                return inner
        except (json.JSONDecodeError, TypeError):
            pass
        return parsed
    return parsed


def encode(value):
    """统一编码为单层 JSON 文本（ensure_ascii=False）。"""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def main():
    if not DB_PATH.exists():
        print(f"数据库不存在: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout=15000")
    cur = conn.cursor()

    # ---- 1. papers.authors / keywords_cn 解码 ----
    rows = cur.execute(
        "SELECT id, title, authors, keywords_cn FROM papers"
    ).fetchall()

    fix_authors = 0
    fix_keywords = 0
    fix_title = 0
    fix_garbled = 0
    for pid, title, authors, keywords in rows:
        new_title = title.replace("附视频", "").strip() if title else title
        if new_title != title:
            fix_title += 1

        new_authors = decode_to_list(authors)
        new_keywords = decode_to_list(keywords)

        # 拼接作者名修正（按清洗后标题匹配）
        if new_title in AUTHOR_FIXES and new_authors != AUTHOR_FIXES[new_title]:
            print(f"  修正作者: {new_title[:40]}... {new_authors} -> {AUTHOR_FIXES[new_title]}")
            new_authors = AUTHOR_FIXES[new_title]
            fix_garbled += 1

        # 仅在确实变化时更新
        if encode(new_authors) != authors or encode(new_keywords) != keywords or new_title != title:
            cur.execute(
                "UPDATE papers SET authors=?, keywords_cn=?, title=? WHERE id=?",
                (encode(new_authors), encode(new_keywords), new_title, pid),
            )
            if encode(new_authors) != authors:
                fix_authors += 1
            if encode(new_keywords) != keywords:
                fix_keywords += 1

    # ---- 2. paper_features.keywords 解码 ----
    feat_rows = cur.execute("SELECT id, keywords FROM paper_features").fetchall()
    fix_feat = 0
    for fid, kw in feat_rows:
        new_kw = decode_to_list(kw)
        if new_kw is not None and encode(new_kw) != kw:
            cur.execute("UPDATE paper_features SET keywords=? WHERE id=?", (encode(new_kw), fid))
            fix_feat += 1

    conn.commit()

    print(f"\n=== 清理结果 ===")
    print(f"papers 作者解码/修正: {fix_authors} 篇")
    print(f"papers 关键词解码:    {fix_keywords} 篇")
    print(f"标题去'附视频':        {fix_title} 篇")
    print(f"拼接作者名修正:       {fix_garbled} 篇")
    print(f"paper_features 关键词: {fix_feat} 条")

    # ---- 3. 校验 ----
    cur.execute("SELECT COUNT(*) FROM papers WHERE json_type(authors) != 'array' OR json_type(keywords_cn) != 'array'")
    remain = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM papers WHERE title LIKE '%附视频%'")
    remain_title = cur.fetchone()[0]
    print(f"\n残留非数组 authors/keywords: {remain}")
    print(f"残留'附视频'标题: {remain_title}")

    conn.close()
    print("完成。")


if __name__ == "__main__":
    main()
