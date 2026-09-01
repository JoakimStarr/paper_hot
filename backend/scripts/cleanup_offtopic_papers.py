"""清理跑题 / 低质论文（可重跑，默认 dry-run）。

判据（三档，见 build_targets）：
  一档：cnki_subject 属非经济类学科（医药卫生、数学、高等教育、公安、体育…）
  二档：期刊总篇数 <= JOURNAL_MAX_PAPERS 且刊名含明显非经济关键词
  三档：标题重复（保留 id 最小的一条）

注意：papers 表无外键级联，删除论文必须同步清理 11 张关联表，否则留下孤儿行。
      topic_projects.source_paper_id / assistant_sessions.paper_id 置 NULL 而非删行，
      避免连带删掉用户的选题项目与会话。

用法（无需停服，分批小事务提交）：
    cd backend && ../venv/bin/python scripts/cleanup_offtopic_papers.py            # dry-run
    cd backend && ../venv/bin/python scripts/cleanup_offtopic_papers.py --apply     # 执行
"""
import argparse
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "paperpulse.db"
BATCH = 25  # 每批论文数：单事务足够小，不会把服务端写请求堵到 busy_timeout

# cnki_subject 命中任一关键词即视为经济/管理相关，否则判为跑题
ECON_SUBJECT_KEYWORDS = [
    "经济", "金融", "管理", "财政", "税收", "贸易", "会计", "审计", "统计",
    "保险", "证券", "投资", "市场", "企业", "农业", "工业", "信息", "旅游",
    "劳动", "人口", "城市", "区域", "环境", "资源", "价格",
]

# 刊名命中任一关键词且该刊总篇数极少 → 判为跑题期刊
OFFTOPIC_JOURNAL_KEYWORDS = [
    "医学", "医药", "卫生", "中医", "护理", "药学", "临床", "预防",
    "体育", "公安", "军事", "文学", "语言", "艺术", "音乐", "图书",
    "档案", "新闻", "传媒", "机械", "电子", "计算机", "自动化", "材料",
    "化工", "地质", "气象", "铁道", "纺织", "食品", "畜牧", "水产",
]
# 刊名命中任一关键词 → 视为经管相关，即使命中上面的跑题词也保留
# （例：中国林业经济 命中"林业"、金融理论与教学 命中"教学"、xx大学学报(社会科学版)）
ECON_JOURNAL_KEYWORDS = [
    "经济", "金融", "财政", "贸易", "会计", "管理", "营销", "市场",
    "企业", "社会科学", "商",
]
# 期刊总篇数 >= 该阈值 → 视为核心刊，一/二档一律不删。
#
# 原因：cnki_subject 取自 CNKI 详情页的「专题」字段（cnki_paper_captcha.py:1889），
# 按论文的**研究主题所属领域**打标，而非学科。因此顶刊上的跨学科论文会正常落到
# 非经济类目，例如经济学(季刊)：「医院生产函数与需求函数的估计」→ 医药卫生方针政策、
# 「幼儿园增建与儿童认知能力发展」→ 学前教育、《专利法》修订与专利质量」→ 民商法。
# 仅凭该字段判跑题会误杀 143 篇正经论文，故用核心刊阈值兜底。
# 三档（重复标题）是同文重复入库，与期刊无关，不受此保护。
CORE_JOURNAL_MIN_PAPERS = 20
JOURNAL_MAX_PAPERS = 3

# 按 paper_id 引用论文的表：删行
CASCADE_DELETE = [
    "favorites",
    "paper_analyses",
    "paper_chats",
    "paper_features",
    "paper_scores",
    "pinned_papers",
    "project_papers",
    "reading_history",
]
# 按单列引用论文的表：置 NULL，保留业务行本身
CASCADE_NULL = [
    ("assistant_sessions", "paper_id"),
    ("topic_projects", "source_paper_id"),
]


def build_targets(con):
    """返回 {paper_id: 判定档位}。"""
    rows = con.execute("SELECT id, cnki_subject, journal_name, TRIM(title) FROM papers").fetchall()
    journal_counts = Counter(r[2] for r in rows)

    def subject_is_offtopic(subject):
        """有学科标注，且不含任何经济类关键词 → 跑题。无标注返回 False（不做判断）。"""
        return bool(subject) and not any(k in subject for k in ECON_SUBJECT_KEYWORDS)

    def journal_is_econ(journal):
        """刊名含经管关键词 → 交叉学科刊（如"卫生经济研究""经营与管理"），一律保留。"""
        return any(k in journal for k in ECON_JOURNAL_KEYWORDS)

    def journal_is_offtopic(journal):
        """长尾刊（<=JOURNAL_MAX_PAPERS 篇）且刊名明显非经济。"""
        if journal_counts[journal] > JOURNAL_MAX_PAPERS:
            return False
        if journal_is_econ(journal):
            return False
        return any(k in journal for k in OFFTOPIC_JOURNAL_KEYWORDS)

    targets = {}
    for pid, subject, journal, title in rows:
        if journal_counts[journal] >= CORE_JOURNAL_MIN_PAPERS:
            continue  # 核心刊保护：CNKI 学科字段曾整刊抓错，不参与一/二档判定
        if subject_is_offtopic(subject) and not journal_is_econ(journal):
            targets[pid] = "一档:非经济学科"
        elif not subject and journal_is_offtopic(journal):
            # 无学科证据 + 刊名明显跑题，才判二档（如"西部旅游"刊上的经济类标题）
            targets[pid] = "二档:长尾非经济期刊"
    # 重复标题：核心刊保护不适用。同一篇论文常被 CNKI 与期刊站各抓一次，
    # 优先保留 CNKI 那条（cnki_subject / journal_issue 等元数据更全），其余删。
    seen = set()
    for pid, title in con.execute(
        "SELECT id, TRIM(title) FROM papers "
        "ORDER BY TRIM(title), (source = 'CNKI') DESC, created_at, id"
    ):
        if title in seen:
            targets.setdefault(pid, "三档:重复标题")
        seen.add(title)
    return targets


def dry_run(con, targets):
    by_tier = Counter(targets.values())
    print(f"命中 {len(targets)} 篇 / 全库 {con.execute('SELECT COUNT(*) FROM papers').fetchone()[0]} 篇")
    for tier, n in sorted(by_tier.items()):
        print(f"  {tier:22s} {n:5d} 篇")

    print("\n各关联表待清理行数：")
    ids = list(targets)
    ph = ",".join("?" * len(ids))
    for table in CASCADE_DELETE:
        n = con.execute(f"SELECT COUNT(*) FROM {table} WHERE paper_id IN ({ph})", ids).fetchone()[0]
        print(f"  DELETE {table:20s} {n:5d} 行")
    for table, col in CASCADE_NULL:
        n = con.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {col} IN ({ph})", ids
        ).fetchone()[0]
        print(f"  NULL   {table}.{col:24s} {n:5d} 行")
    n = con.execute(
        f"SELECT COUNT(*) FROM paper_similarities WHERE paper_id_a IN ({ph}) OR paper_id_b IN ({ph})",
        ids + ids,
    ).fetchone()[0]
    print(f"  DELETE {'paper_similarities':20s} {n:5d} 行")

    print("\n样例（每档随机 5 条）：")
    for tier in sorted(by_tier):
        sample = [pid for pid, t in targets.items() if t == tier][:5]
        ph5 = ",".join("?" * len(sample))
        for journal, title in con.execute(
            f"SELECT journal_name, title FROM papers WHERE id IN ({ph5})", sample
        ):
            print(f"  [{tier}] {journal} | {title[:45]}")


def apply(con, targets, db_path):
    backup = db_path.with_name(
        f"{db_path.stem}.bak-{datetime.now():%Y%m%d_%H%M%S}{db_path.suffix}"
    )
    print(f"备份中 → {backup}")
    con.execute(f"VACUUM INTO '{backup}'")
    print(f"备份完成（{backup.stat().st_size / 1e6:.1f} MB）\n")

    ids = list(targets)
    con.execute("PRAGMA busy_timeout=30000")
    deleted = Counter()
    for i in range(0, len(ids), BATCH):
        chunk = ids[i : i + BATCH]
        ph = ",".join("?" * len(chunk))
        con.execute("BEGIN")
        try:
            for table in CASCADE_DELETE:
                deleted[table] += con.execute(
                    f"DELETE FROM {table} WHERE paper_id IN ({ph})", chunk
                ).rowcount
            deleted["paper_similarities"] += con.execute(
                f"DELETE FROM paper_similarities WHERE paper_id_a IN ({ph}) OR paper_id_b IN ({ph})",
                chunk + chunk,
            ).rowcount
            for table, col in CASCADE_NULL:
                deleted[f"{table}.{col}"] += con.execute(
                    f"UPDATE {table} SET {col} = NULL WHERE {col} IN ({ph})", chunk
                ).rowcount
            deleted["papers"] += con.execute(
                f"DELETE FROM papers WHERE id IN ({ph})", chunk
            ).rowcount
            con.commit()
        except Exception:
            con.rollback()
            raise
        print(f"  批次 {i // BATCH + 1}/{-(-len(ids) // BATCH)} 完成", flush=True)

    con.execute("PRAGMA optimize")
    print("\n已删除/更新：")
    for table, n in sorted(deleted.items()):
        print(f"  {table:28s} {n:6d} 行")
    print(f"\n剩余论文：{con.execute('SELECT COUNT(*) FROM papers').fetchone()[0]} 篇")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正执行删除（默认仅 dry-run）")
    args = ap.parse_args()

    if not DB_PATH.exists():
        sys.exit(f"数据库不存在：{DB_PATH}")

    con = sqlite3.connect(DB_PATH, timeout=30)
    targets = build_targets(con)
    if not targets:
        print("没有命中的论文，无需清理。")
        return
    dry_run(con, targets)
    if not args.apply:
        print("\n[dry-run] 未做任何改动。确认无误后加 --apply 执行。")
        return
    print("\n=== 执行删除 ===")
    apply(con, targets, DB_PATH)


if __name__ == "__main__":
    main()
