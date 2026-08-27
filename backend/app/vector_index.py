"""FAISS 向量索引（选题验证器两阶段检索的召回加速，可选依赖）。

替代「每请求全量拉库 + JSON 解析 + numpy 暴力余弦」的召回方式：
- 进程内缓存 FAISS IndexFlatIP（向量已归一化，内积 = 余弦），TTL 过期自动重建，
  避免每次请求重新解析全库 embedding
- faiss-cpu 未安装或构建失败时，search() 返回空，调用方自动降级为原 numpy 暴力余弦，
  不影响功能

设计约束：
- faiss / numpy 仅在函数内 import（重依赖懒加载，符合项目约定）
- 异步构建：索引构建读 DB，在 async 上下文内完成；asyncio.Lock 串行化重建
"""
import asyncio
import json
import logging
import time
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# 索引缓存 TTL：爬虫/backfill 后最多延迟该时长才看到新向量
_INDEX_TTL_SECONDS = 300

_index_lock = asyncio.Lock()
_index_cache = {"ts": 0.0, "ids": [], "index": None}


async def _build_index(db) -> Tuple[Optional[object], List[str]]:
    """从 paper_features 全量构建归一化余弦索引。

    返回 (faiss_index, ids)：ids[i] 与索引中第 i 个向量对应（paper_id）。
    faiss 不可用或没有向量时返回 (None, [])。
    """
    import numpy as np
    from sqlalchemy import select as sa_select
    from app.models import PaperFeatures

    rows = (
        await db.execute(
            sa_select(
                PaperFeatures.paper_id,
                PaperFeatures.embedding,
            )
            .where(PaperFeatures.embedding.isnot(None))
        )
    ).all()
    if not rows:
        return None, []

    ids: List[str] = []
    vecs: List[object] = []
    for pid, emb in rows:
        try:
            v = np.asarray(json.loads(emb), dtype=np.float32)
            norm = np.linalg.norm(v)
            if norm == 0:
                continue
            vecs.append(v / norm)
            ids.append(pid)
        except Exception:
            continue
    if not vecs:
        return None, []

    try:
        import faiss
    except ImportError:
        logger.warning("faiss-cpu not installed, vector recall falls back to numpy brute force")
        return None, []

    mat = np.vstack(vecs).astype(np.float32)
    index = faiss.IndexFlatIP(mat.shape[1])
    index.add(mat)
    logger.info(f"FAISS index built: {len(ids)} vectors, dim={mat.shape[1]}")
    return index, ids


async def search(db, query_vec: List[float], k: int) -> Tuple[List[str], List[float]]:
    """余弦召回 top-k。返回 (paper_ids, scores) 按相似度降序。

    faiss 不可用/构建失败时返回 ([], [])，由调用方降级为 numpy 暴力余弦。
    """
    async with _index_lock:
        if _index_cache["index"] is None or time.time() - _index_cache["ts"] > _INDEX_TTL_SECONDS:
            index, ids = await _build_index(db)
            _index_cache["index"] = index
            _index_cache["ids"] = ids
            _index_cache["ts"] = time.time()
        index, ids = _index_cache["index"], _index_cache["ids"]

    if index is None or not ids:
        return [], []

    import numpy as np

    q = np.asarray(query_vec, dtype=np.float32).reshape(1, -1)
    norm = np.linalg.norm(q)
    if norm == 0:
        return [], []
    q = q / norm

    k = min(k, len(ids))
    scores, idx = index.search(q, k)
    order = idx[0]
    hit_ids = [ids[i] for i in order if i >= 0]
    hit_scores = [float(s) for s in scores[0][: len(hit_ids)]]
    return hit_ids, hit_scores
