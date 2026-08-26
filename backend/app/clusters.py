"""主题聚类地图：基于本地 bge-m3 向量的全库语义聚类（KMeans + PCA 二维投影）。"""
import logging
import time
from collections import Counter

logger = logging.getLogger(__name__)

# 进程内缓存：向量数据变更不频繁，聚类结果按签名（论文数+最新向量行）缓存 30 分钟
_CACHE: dict = {"sig": None, "data": None, "at": 0.0}
_TTL_SECONDS = 1800


def _cluster_label(top_keywords: list[str], idx: int) -> str:
    return " · ".join(top_keywords[:3]) if top_keywords else f"主题簇 {idx + 1}"


def _momentum_tag(last12: int, prev12: int) -> str:
    """新兴/衰退标签：近一年 vs 前一年的频次比。"""
    if prev12 == 0:
        return "emerging" if last12 > 0 else "stable"
    ratio = last12 / prev12
    if ratio >= 1.3:
        return "emerging"
    if ratio <= 0.7:
        return "declining"
    return "stable"


async def _load_signature(db) -> tuple:
    """廉价指纹：有向量的论文数 + 最大特征行 id，任一变化即触发重算。"""
    from sqlalchemy import select as sa_select, func as sa_func
    from app.models import PaperFeatures

    row = await db.execute(
        sa_select(sa_func.count(PaperFeatures.id), sa_func.max(PaperFeatures.id))
        .where(PaperFeatures.embedding.isnot(None))
        .where(PaperFeatures.embedding != "")
    )
    cnt, mx = row.fetchone()
    return (cnt, mx)


async def _load_rows(db) -> list[dict]:
    """一次取齐聚类所需字段：向量 + 标题 + 关键词 + 发表时间 + 评分。"""
    from sqlalchemy import select as sa_select
    from app.models import Paper, PaperFeatures, PaperScore

    result = await db.execute(
        sa_select(
            PaperFeatures.paper_id,
            PaperFeatures.embedding,
            Paper.title,
            Paper.keywords_cn,
            Paper.published_at,
            PaperScore.final_score,
        )
        .join(Paper, Paper.id == PaperFeatures.paper_id)
        .outerjoin(PaperScore, PaperScore.paper_id == PaperFeatures.paper_id)
        .where(PaperFeatures.embedding.isnot(None))
        .where(PaperFeatures.embedding != "")
    )
    import json as _json

    rows = []
    for pid, emb, title, kws, pub, score in result.fetchall():
        try:
            vec = _json.loads(emb)
        except Exception:
            continue
        if not isinstance(vec, list) or not vec:
            continue
        rows.append({
            "id": pid,
            "vec": vec,
            "title": title or "",
            "keywords": [k for k in (kws or []) if k],
            "year": str(pub)[:4] if pub else "",
            "score": float(score) if score is not None else 0.0,
        })
    return rows


def _compute_clusters(rows: list[dict], k: int = 18) -> dict:
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    import numpy as np

    mat = np.array([r["vec"] for r in rows], dtype=np.float32)
    effective_k = max(4, min(k, len(rows) // 40 or 4))

    km = KMeans(n_clusters=effective_k, n_init=10, random_state=42)
    labels = km.fit_predict(mat)
    coords = PCA(n_components=2, random_state=42).fit_transform(mat)

    # 归一化到 0~100 便于前端渲染
    x_min, x_max = coords[:, 0].min(), coords[:, 0].max()
    y_min, y_max = coords[:, 1].min(), coords[:, 1].max()
    nx = (coords[:, 0] - x_min) / ((x_max - x_min) or 1.0) * 100
    ny = (coords[:, 1] - y_min) / ((y_max - y_min) or 1.0) * 100

    groups: dict[int, list[int]] = {}
    for i, lb in enumerate(labels):
        groups.setdefault(int(lb), []).append(i)

    clusters_out = []
    for cid, idxs in groups.items():
        members = [rows[i] for i in idxs]
        kw_counter: Counter = Counter()
        for r in members:
            kw_counter.update(r["keywords"])
        top_kw = [w for w, _ in kw_counter.most_common(6)]
        years = sorted(y[:4] for y in (r["year"] for r in members) if y)

        clusters_out.append({
            "id": cid,
            "label": _cluster_label(top_kw, cid),
            "top_keywords": top_kw,
            "size": len(idxs),
            "cx": round(float(nx[idxs].mean()), 2),
            "cy": round(float(ny[idxs].mean()), 2),
            "year_range": f"{years[0]}–{years[-1]}" if years else "",
            "representative_papers": [
                {"id": p["id"], "title": p["title"], "score": round(p["score"], 3)}
                for p in sorted(members, key=lambda r: (-r["score"], r["title"]))[:5]
            ],
            "points": [
                {"id": p["id"], "title": p["title"], "x": float(nx[i]), "y": float(ny[i])}
                for i, p in zip(idxs, members)
            ],
        })

    clusters_out.sort(key=lambda c: c["size"], reverse=True)
    for rank, c in enumerate(clusters_out, start=1):
        c["rank"] = rank
    return {"total": len(rows), "k": len(clusters_out), "clusters": clusters_out}


async def build_topic_clusters(db, k: int = 18) -> dict:
    sig = await _load_signature(db)
    now = time.time()
    if _CACHE["data"] and _CACHE["sig"] == sig and now - _CACHE["at"] < _TTL_SECONDS:
        return _CACHE["data"]

    rows = await _load_rows(db)
    if len(rows) < 20:
        return {"total": len(rows), "k": 0, "clusters": []}

    data = _compute_clusters(rows, k=k)
    _CACHE.update({"sig": sig, "data": data, "at": now})
    logger.info(f"topic clusters built: {data['k']} clusters / {data['total']} papers")
    return data


async def compute_keyword_trends(db, top: int = 12, keywords: list[str] | None = None) -> dict:
    """关键词年度演化 + 新兴/衰退动量（全库统计）。

    - yearly: 每个关键词的逐年论文数
    - 动量：近 12 个月 vs 前 12 个月；比值 ≥1.3 新兴、≤0.7 衰退
    """
    from sqlalchemy import select as sa_select
    from app.models import Paper
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(days=365)
    prev_cut = cutoff - timedelta(days=365)

    result = await db.execute(
        sa_select(Paper.keywords_cn, Paper.published_at)
        .where(Paper.keywords_cn.isnot(None))
    )
    yearly: dict[str, dict[str, int]] = {}
    last12: Counter = Counter()
    prev12: Counter = Counter()

    for raw, pub in result.fetchall():
        if not pub:
            continue
        year = str(pub)[:4]
        dt = pub if isinstance(pub, datetime) else None
        fresh = dt is not None and dt >= cutoff
        aging = dt is not None and prev_cut <= dt < cutoff
        for kw in raw or []:
            kw = (kw or "").strip()
            if not kw:
                continue
            yearly.setdefault(kw, {})
            yearly[kw][year] = yearly[kw].get(year, 0) + 1
            if fresh:
                last12[kw] += 1
            elif aging:
                prev12[kw] += 1

    years = sorted({y for d in yearly.values() for y in d})

    def _series(name: str) -> dict:
        yd = yearly.get(name, {})
        l12, p12 = last12.get(name, 0), prev12.get(name, 0)
        return {
            "name": name,
            "yearly": [{"year": y, "count": yd.get(y, 0)} for y in years],
            "total": sum(yd.values()),
            "last12": l12,
            "prev12": p12,
            "trend": _momentum_tag(l12, p12),
        }

    if keywords:
        wanted = [k.strip() for k in keywords if k.strip() in yearly]
        series = [_series(k) for k in wanted]
    else:
        # 默认取「近一年最热」的 top 个关键词，图表更有当下意义
        hottest = [kw for kw, _ in last12.most_common(top)]
        if len(hottest) < top:
            extra = sorted(yearly, key=lambda k: sum(yearly[k].values()), reverse=True)
            for kw in extra:
                if kw not in hottest:
                    hottest.append(kw)
                if len(hottest) >= top:
                    break
        series = [_series(k) for k in hottest[:top]]

    series.sort(key=lambda s: s["last12"], reverse=True)
    return {"years": years, "series": series}
