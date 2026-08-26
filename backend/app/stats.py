"""论文库统计核心（单一实现）：关键词词频、共现、研究空白。

被 routers/network.py、routers/ai.py、routers/topic.py 共用，替代原先三处各自实现。
数据源统一为 papers.keywords_cn（全量完整；paper_features.keywords 有 409 篇缺失）。
"""
import logging
from typing import List

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def iter_paper_keywords(db: AsyncSession, limit: int = 0) -> List[List[str]]:
    """取每篇论文的关键词列表（papers.keywords_cn，按发表时间倒序）。

    limit>0 时只取最近 N 篇（网络图语义）；limit=0 取全库（研究空白语义）。
    走 ORM select 以获得 UnicodeJSON 的 list 类型转换（text 查询只会返回字符串）。
    """
    from sqlalchemy import select as sa_select
    from app.models import Paper

    stmt = (
        sa_select(Paper.keywords_cn)
        .where(Paper.keywords_cn.isnot(None))
        .order_by(Paper.published_at.desc())
    )
    if limit > 0:
        stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    out: List[List[str]] = []
    for (raw,) in result.fetchall():
        kws = raw if isinstance(raw, list) else []
        kws = [k for k in (kws or []) if k]
        out.append(kws)
    return out


def _cooc_from_paper_keywords(paper_keywords: List[List[str]]) -> tuple:
    """从"每篇论文的关键词列表"统计词频与两两共现（内存计算，万级论文足够快）。"""
    keyword_count = {}
    cooc = {}
    for keywords in paper_keywords:
        for kw in keywords:
            keyword_count[kw] = keyword_count.get(kw, 0) + 1
        for i in range(len(keywords)):
            for j in range(i + 1, len(keywords)):
                pair = tuple(sorted([keywords[i], keywords[j]]))
                cooc[pair] = cooc.get(pair, 0) + 1
    return keyword_count, cooc


async def keyword_cooccurrence(db: AsyncSession, limit: int = 15) -> list:
    """关键词两两共现 top-N（SQL 聚合，供 AI 分析数据采集使用）。"""
    result = await db.execute(sa_text("""
        SELECT a.value AS kw1, b.value AS kw2, COUNT(*) AS cnt
        FROM papers p, json_each(p.keywords_cn) a, json_each(p.keywords_cn) b
        WHERE p.keywords_cn IS NOT NULL AND a.value < b.value
        GROUP BY a.value, b.value
        ORDER BY cnt DESC
        LIMIT :lim
    """), {"lim": limit})
    return [{"kw1": r[0], "kw2": r[1], "count": r[2]} for r in result.fetchall()]


def _gap_score(cnt_a: int, cnt_b: int, co: int, max_count: int = 100) -> float:
    """单个空白组合的评分（纯函数，供单测与 compute_keyword_gaps 复用）。

    空白分 = 词A热度 × 词B热度 × (1 - 共现饱和度)
      - 词热度：count / max_count（两词都必须热，排除长尾噪声）
      - 共现饱和度：cooc / min(count_A, count_B)（共现天花板是较冷一词的频次）
    空白分高 = 两个方向各自活跃，但几乎没人在同一篇论文里把它们结合起来。
    """
    if max_count <= 0 or cnt_a <= 0 or cnt_b <= 0:
        return 0.0
    saturation = co / min(cnt_a, cnt_b) if min(cnt_a, cnt_b) > 0 else 1.0
    return (cnt_a / max_count) * (cnt_b / max_count) * (1.0 - saturation)


async def compute_keyword_gaps(db: AsyncSession, limit: int = 10) -> list:
    """研究空白识别（供 /network/gaps 与 topic.py 的 LLM 解读复用）。

    空白分 = 词A热度 × 词B热度 × (1 - 共现饱和度)；纯计算委托 _gap_score。
    """
    paper_keywords = await iter_paper_keywords(db, limit=0)
    keyword_count, cooc = _cooc_from_paper_keywords(paper_keywords)
    if not keyword_count:
        return []

    # 只在高频词之间找空白（词频过低无统计意义）
    hot = sorted(keyword_count.items(), key=lambda x: x[1], reverse=True)[:60]
    max_count = hot[0][1] if hot else 1

    gaps = []
    for i in range(len(hot)):
        for j in range(i + 1, len(hot)):
            (kw_a, cnt_a), (kw_b, cnt_b) = hot[i], hot[j]
            pair = tuple(sorted([kw_a, kw_b]))
            co = cooc.get(pair, 0)
            score = _gap_score(cnt_a, cnt_b, co, max_count)
            gaps.append({
                "source": kw_a,
                "target": kw_b,
                "source_count": cnt_a,
                "target_count": cnt_b,
                "cooccurrence": co,
                "gap_score": round(score, 4),
            })

    gaps.sort(key=lambda g: g["gap_score"], reverse=True)
    return gaps[:limit]


async def keyword_network(db: AsyncSession) -> dict:
    """关键词共现网络：全库聚合（此前仅统计最近 N 篇导致计数失真，已改为全库）。

    节点取词频 top80、边取共现 top400，裁剪在本函数内完成。
    """
    paper_keywords = await iter_paper_keywords(db)
    keyword_count, cooc = _cooc_from_paper_keywords(paper_keywords)

    nodes_map = {}
    for kw, cnt in keyword_count.items():
        nodes_map[kw] = {"id": kw, "name": kw, "count": cnt, "group": "keyword"}

    nodes = sorted(nodes_map.values(), key=lambda x: x["count"], reverse=True)[:80]
    node_ids = {n["id"] for n in nodes}
    links = [
        {"source": a, "target": b, "value": v}
        for (a, b), v in cooc.items()
        if a in node_ids and b in node_ids
    ]
    links.sort(key=lambda x: x["value"], reverse=True)
    return {"nodes": nodes, "links": links[:400]}
