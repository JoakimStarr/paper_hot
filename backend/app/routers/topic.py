"""研究空白识别与选题验证接口（产品定位：研究选题的决策副驾）。

P1 空白识别：基于关键词共现网络发现"各自高频但共现稀少"的组合，
  并可选调用 LLM 生成空白假设卡片（后台任务 + 轮询，模式对齐 ai.py 的 v2 报告）。
P2 选题验证：候选题目 -> embedding 召回近似论文 -> 拥挤度统计 -> LLM 综合评估（SSE 流式）。
  embedding 不可用时自动降级为 TF-IDF（复用 similarity.py 的分词/向量化方案）。

多用户预留：ResearchGapReport 表带 user_id 列（当前恒为 "local"），
后续接入账号体系时按用户隔离查询即可，无需迁移表结构。
"""
import asyncio
import json
import logging
import math
import time
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select as sa_select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.models import Paper, PaperFeatures, ResearchGapReport, TopicProject
from app.ai_service import ai_trend_service
from app.routers.deps import (
    verify_token, _parse_json_list,
    _get_ai_client, _resolve_model_provider, _stream_chat_response,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# 单用户占位标识：接入账号体系后替换为真实用户维度
LOCAL_USER = "local"


def _uid_from(request: Request) -> str:
    """从请求头取用户维度（x-user-id）；与 personal/producer 路由同约定。

    写入（创建选题/空白解读）与读取统一走这里，避免历史代码硬编码 "local"
    造成「前端随机 uid 存的数据在别处查询不到」的隔离割裂。
    """
    return (request.headers.get("x-user-id") if request else None) or LOCAL_USER


# 本进程启动时间（UTC naive，与 ResearchGapReport.created_at 的 func.now() 同口径，
# SQLite server_default 为 UTC）。后台任务跑在进程内存里，后端重启会让 running
# 状态的报告永远无法完成，用它判断并回收僵尸 running 报告。
from datetime import datetime, timedelta, timezone

_PROCESS_START = datetime.now(timezone.utc).replace(tzinfo=None)


async def _reap_zombie_running_report(db: AsyncSession, uid: str = LOCAL_USER) -> None:
    """回收僵尸 running 报告：created_at 早于本进程启动时间的 running 必属
    「后端重启导致后台任务丢失」，标记 failed 让前端停止无限等待。"""
    result = await db.execute(
        sa_select(ResearchGapReport)
        .where(ResearchGapReport.status == "running", ResearchGapReport.user_id == uid)
    )
    changed = False
    for report in result.scalars():
        if report.created_at and report.created_at < _PROCESS_START:
            report.status = "failed"
            report.error_message = "任务因后端重启而中断，请重新发起分析"
            changed = True
    if changed:
        await db.commit()
        logger.info("Reaped zombie running gap-analysis reports (created before process start)")


# ---------------------------------------------------------------------------
# P1：研究空白 LLM 解读（后台任务 + 轮询）
# ---------------------------------------------------------------------------

class GapAnalysisResponse(BaseModel):
    report_id: Optional[int] = None
    status: Optional[str] = None  # running / success / failed
    is_running: bool = False
    model: Optional[str] = None
    created_at: Optional[str] = None
    raw_analysis: Optional[str] = None
    gaps_snapshot: Optional[list] = None
    error_message: Optional[str] = None


class GapAnalyzeRequest(BaseModel):
    model: Optional[str] = None
    limit: int = 10


async def _fetch_gaps_from_db(db: AsyncSession, limit: int = 10) -> list:
    """研究空白计算（实现收敛在 app/stats.py，与 /network/gaps 同一实现）。"""
    from app.stats import compute_keyword_gaps
    return await compute_keyword_gaps(db, limit=limit)


@router.post("/network/gaps/analyze", response_model=GapAnalysisResponse)
async def start_gap_analysis(
    body: GapAnalyzeRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """触发 LLM 空白解读后台任务（不阻塞，前端轮询 /network/gaps/analysis）。"""
    uid = _uid_from(request)
    # 先回收僵尸 running（后端重启遗留），否则会被下面"正在跑"分支永远拦住
    await _reap_zombie_running_report(db, uid)

    # 已有正在跑的任务直接返回，避免重复计费
    running = await db.execute(
        sa_select(ResearchGapReport)
        .where(ResearchGapReport.status == "running", ResearchGapReport.user_id == uid)
        .order_by(ResearchGapReport.id.desc())
        .limit(1)
    )
    running_report = running.scalar_one_or_none()
    if running_report:
        return GapAnalysisResponse(
            report_id=running_report.id,
            status="running",
            is_running=True,
            model=running_report.model,
        )

    # 数据先行：没有空白数据就没必要启动 LLM
    gaps = await _fetch_gaps_from_db(db, limit=body.limit)
    if not gaps:
        raise HTTPException(status_code=400, detail="No research gap data available. Fetch papers first.")

    report = ResearchGapReport(
        user_id=uid,
        model=body.model,
        status="running",
        gaps_snapshot=gaps,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    from app.main import spawn_background_task
    spawn_background_task(_run_gap_analysis_background(report.id, model=body.model, limit=body.limit))

    return GapAnalysisResponse(
        report_id=report.id,
        status="running",
        is_running=True,
        model=report.model,
    )


async def _run_gap_analysis_background(report_id: int, model: Optional[str] = None, limit: int = 10):
    """后台任务：组装空白数据 + 近期趋势 -> LLM 生成空白假设卡片（markdown）。"""
    start_time = time.time()
    async with AsyncSessionLocal() as db:
        report = await db.get(ResearchGapReport, report_id)
        if not report:
            return
        try:
            gaps = report.gaps_snapshot or []
            if not gaps:
                gaps = await _fetch_gaps_from_db(db, limit=limit)

            # 补充每个词的近期热度（TopicTrend 表，年份桶粒度），让 LLM 的假设有数据支撑。
            # 注意：week_start 存的是「年份桶」（当年1月1日，因半数 CNKI 论文仅有年份精度），
            # 按自然周/月窗口过滤会在绝大多数月份恒返回空，这里取最近 3 个年份桶聚合。
            from app.models import TopicTrend
            topic_names = set()
            for g in gaps:
                topic_names.update([g.get("source", ""), g.get("target", "")])
            recent_buckets = (
                await db.execute(
                    sa_select(TopicTrend.week_start)
                    .distinct()
                    .order_by(TopicTrend.week_start.desc())
                    .limit(3)
                )
            ).scalars().all()
            trend_map = {}
            if topic_names and recent_buckets:
                trend_rows = await db.execute(
                    sa_select(TopicTrend.topic, sa_func.sum(TopicTrend.paper_count))
                    .where(
                        TopicTrend.topic.in_(topic_names),
                        TopicTrend.week_start.in_(recent_buckets),
                    )
                    .group_by(TopicTrend.topic)
                )
                trend_map = {topic: int(cnt or 0) for topic, cnt in trend_rows.all()}

            data_lines = []
            for g in gaps:
                src, tgt = g.get("source", ""), g.get("target", "")
                data_lines.append(
                    f"- 「{src}」(词频{g.get('source_count', 0)}，近3个统计年度{trend_map.get(src, 0)}篇) × "
                    f"「{tgt}」(词频{g.get('target_count', 0)}，近3个统计年度{trend_map.get(tgt, 0)}篇)："
                    f"共现{g.get('cooccurrence', 0)}次，空白分{g.get('gap_score', 0):.3f}"
                )
            data_text = "\n".join(data_lines)

            system_prompt = f"""你是一位资深的学术研究选题顾问。以下数据来自一个学术论文库的关键词共现分析：
每个组合都是「两个关键词各自高频出现、但很少在同一篇论文中共现」的潜在研究空白。

数据（按空白分降序，空白分越高表示交叉越稀少）：
{data_text}

请对以上研究空白逐一给出"空白假设卡片"，用 markdown 输出，每个组合包含：
1. **组合**：A × B
2. **数据依据**：引用上面的词频/共现/趋势数字
3. **空白假设**：为什么可能存在这个空白（方法壁垒？领域隔阂？数据可得性？）
4. **风险提示**：这是"真空白"（有研究价值）还是"伪需求"（没人做是因为不值得做）？判断依据是什么？
5. **建议切入角度**：如果要研究，第一步可以做什么

要求：
- 诚实评估，宁可说"这可能是伪空白"也不要强行吹捧
- 假设要具体到"什么方法×什么场景"，不要空泛
- 最后给一个总结：按研究价值排序你最推荐的 3 个组合，并说明理由"""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "请分析这些研究空白并输出空白假设卡片。"},
            ]

            provider, bare_model = _resolve_model_provider(model)
            client, provider = _get_ai_client(provider)
            if not bare_model:
                from app.routers.deps import _get_default_model
                bare_model = _get_default_model(provider)

            # 后台任务用非流式调用（简单可靠），SSE 只用于选题验证器。
            # sync 客户端调用经 to_thread 下放线程池，避免阻塞事件循环数分钟
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=bare_model,
                messages=messages,
                max_tokens=4096,
                temperature=0.4,
            )
            analysis_text = response.choices[0].message.content or ""

            report.raw_analysis = analysis_text
            report.model = f"{provider}/{bare_model}"
            report.status = "success"
            report.processing_time_ms = int((time.time() - start_time) * 1000)
            await db.commit()
            logger.info(f"Gap analysis {report_id} done in {report.processing_time_ms}ms")

        except Exception as e:
            logger.error(f"Gap analysis {report_id} failed: {e}")
            report.status = "failed"
            report.error_message = str(e)[:1000]
            await db.commit()


@router.get("/network/gaps/analysis", response_model=GapAnalysisResponse)
async def get_gap_analysis(request: Request = None, db: AsyncSession = Depends(get_db)):
    """查询最新一次空白解读（供前端轮询：running 时继续等，success 时渲染）。"""
    uid = _uid_from(request)
    # 轮询入口顺带回收僵尸 running，前端刷新后即可拿到 failed 而非无限转圈
    await _reap_zombie_running_report(db, uid)

    result = await db.execute(
        sa_select(ResearchGapReport)
        .where(ResearchGapReport.user_id == uid)
        .order_by(ResearchGapReport.id.desc())
        .limit(1)
    )
    report = result.scalar_one_or_none()
    if not report:
        return GapAnalysisResponse()

    from app.routers.deps import _isoformat_utc
    return GapAnalysisResponse(
        report_id=report.id,
        status=report.status,
        is_running=(report.status == "running"),
        model=report.model,
        created_at=_isoformat_utc(report.created_at),
        raw_analysis=report.raw_analysis,
        gaps_snapshot=report.gaps_snapshot,
        error_message=report.error_message,
    )


# ---------------------------------------------------------------------------
# P2：选题验证器（embedding 召回 + LLM 流式评估）
# ---------------------------------------------------------------------------

class ValidateRequest(BaseModel):
    topic: str
    model: Optional[str] = None


@router.get("/topic-validator/status")
async def get_validator_status(db: AsyncSession = Depends(get_db)):
    """embedding 覆盖情况：已向量化论文数 / 总数（决定召回质量）。"""
    total_result = await db.execute(
        sa_select(sa_func.count(PaperFeatures.id)).where(PaperFeatures.embedding.isnot(None))
    )
    embedded = total_result.scalar() or 0
    all_result = await db.execute(sa_select(sa_func.count(PaperFeatures.id)))
    total = all_result.scalar() or 0
    return {"embedded_papers": embedded, "total_papers": total}


@router.post("/topic-validator/embeddings/backfill")
async def backfill_embeddings(
    batch_size: int = 100,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """后台补算缺失的论文摘要 embedding（分批，不阻塞请求）。"""
    # 预检：用配置的 embedding model 测试连通性
    from app.ai_service import ai_trend_service
    from app.config import settings
    embed_model = getattr(settings, "embedding_model", None)
    if not embed_model:
        raise HTTPException(
            status_code=503,
            detail="未配置 Embedding 模型。请在系统设置中设置 embedding_model（如 ollama/bge-m3）",
        )
    # 解析 provider 和模型名
    provider, bare_model = ai_trend_service._resolve_model(embed_model)
    if not provider or provider not in ai_trend_service.clients:
        raise HTTPException(
            status_code=503,
            detail=f"Embedding provider '{provider}' 未初始化，请检查 API Key 配置",
        )
    client = ai_trend_service.clients[provider]
    try:
        client.embeddings.create(model=bare_model, input=["test"])
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Embedding 服务 '{embed_model}' 连接失败：{e}",
        )
    from app.main import spawn_background_task
    spawn_background_task(_run_backfill_background(batch_size=min(batch_size, 500)))
    return {"status": "started", "batch_size": min(batch_size, 500)}


async def _run_backfill_background(batch_size: int = 100):
    """取 embedding 为空的 PaperFeatures（join 论文标题+摘要），分批调用 embedding API 写回。

    循环执行直到全库补齐：每次处理 batch_size 条，写回后继续取下一批。
    上限 max_rounds 防止异常场景无限循环；每轮之间留出写入间隔。
    """
    max_rounds = 60  # 每轮 batch_size(≤500) 条，上限覆盖数千篇全量
    for _round in range(max_rounds):
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(
                    sa_select(PaperFeatures.id, Paper.title, Paper.abstract)
                    .join(Paper, Paper.id == PaperFeatures.paper_id)
                    .where(PaperFeatures.embedding.is_(None))
                    .order_by(Paper.published_at.desc())
                    .limit(batch_size)
                )
                rows = result.all()
                if not rows:
                    logger.info("Embedding backfill: nothing to do")
                    return

                texts = [f"{r[1]}\n{(r[2] or '')[:2000]}" for r in rows]
                vectors = await ai_trend_service.embed_texts_async(texts)
                if vectors is None:
                    logger.warning("Embedding backfill skipped: embedding API unavailable")
                    return

                updated = 0
                for (feature_id, _, _), vec in zip(rows, vectors):
                    if not vec:
                        continue
                    feature = await db.get(PaperFeatures, feature_id)
                    if feature:
                        feature.embedding = json.dumps(vec)
                        updated += 1
                await db.commit()
                logger.info(f"Embedding backfill round {_round + 1}: {updated}/{len(rows)} embedded")
                if updated < len(rows):
                    logger.warning(f"Embedding backfill: {len(rows) - updated} rows failed this round, stopping")
                    return
            except Exception as e:
                logger.warning(f"Embedding backfill round {_round + 1} failed: {e}")
                return
        # round 之间休息，避免触发 embedding API 限流
        await asyncio.sleep(0.5)
    logger.warning("Embedding backfill: reached max rounds")


def _cosine_top_k(
    query_vec: List[float], candidates: List[Tuple[str, List[float]]], k: int = 30
) -> List[Tuple[str, float]]:
    """内存 cosine 召回（万级论文量级足够快，不引入向量数据库）。"""
    import numpy as np
    q = np.asarray(query_vec, dtype=np.float32)
    q_norm = np.linalg.norm(q)
    if q_norm == 0:
        return []
    q = q / q_norm

    ids: List[str] = []
    mat_rows: List[np.ndarray] = []
    for pid, vec in candidates:
        ids.append(pid)
        mat_rows.append(np.asarray(vec, dtype=np.float32))
    mat = np.vstack(mat_rows)
    norms = np.linalg.norm(mat, axis=1)
    norms[norms == 0] = 1.0
    sims = mat / norms[:, None] @ q
    order = np.argsort(-sims)[:k]
    return [(ids[i], float(sims[i])) for i in order]


async def _retrieve_similar_papers(db: AsyncSession, topic: str, k: int = 30):
    """候选题目 -> 近似论文召回。优先 embedding，失败降级 TF-IDF。

    两阶段检索（P0）：本地 bge-m3 召回 Top(4k, ≥100) -> 若配置了 rerank key，
    用硅基流动 bge-reranker-v2-m3 重排 -> 取 Top k；重排不可用时降级为 embedding 顺序。
    注意不再对候选集做 limit 硬截断——此前 limit(5000) 会让库内 5000 之后的论文
    永远无法被召回（库现有 5251 篇）。

    返回 (papers: list[dict], mode: "embedding+rerank" | "embedding" | "tfidf")
    """
    # ---- 路线 1：embedding 召回（FAISS 优先，降级 numpy 暴力余弦） ----
    try:
        query_vec = await ai_trend_service.embed_texts_async([topic])
        if query_vec and query_vec[0]:
            recall_k = max(k * 4, 100)  # 召回放宽，交给重排器精排
            papers = await _embedding_recall(db, query_vec[0], recall_k)
            if papers:
                # 两阶段：重排器对召回候选精排（失败降级为 embedding 顺序）
                reranked, ok = await _rerank_papers(topic, papers, k)
                if ok:
                    return reranked, "embedding+rerank"
                return papers[:k], "embedding"
    except Exception as e:
        logger.warning(f"Embedding retrieval failed, falling back to TF-IDF: {e}")

    # ---- 路线 2：TF-IDF 降级（复用 similarity.py 的 jieba 分词方案） ----
    from app.similarity import _tokenize
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    all_result = await db.execute(
        sa_select(
            PaperFeatures.paper_id, PaperFeatures.keywords,
            Paper.title, Paper.abstract, Paper.source, Paper.published_at,
        )
        .join(Paper, Paper.id == PaperFeatures.paper_id)
        .order_by(Paper.published_at.desc())
    )
    all_rows = all_result.all()
    if not all_rows:
        return [], "tfidf"

    corpus = [_tokenize(f"{r[2]} {(r[3] or '')[:500]}") for r in all_rows]
    vectorizer = TfidfVectorizer(tokenizer=lambda x: x.split(), token_pattern=None, max_features=10000)
    matrix = vectorizer.fit_transform(corpus + [_tokenize(topic)])
    sims = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
    order = sims.argsort()[::-1][:k]

    papers = []
    for i in order:
        r = all_rows[i]
        papers.append(_paper_brief(r, float(sims[i])))
    return papers, "tfidf"


async def _embedding_recall(db: AsyncSession, query_vec: list, recall_k: int):
    """embedding 召回候选：FAISS 索引优先，不可用时降级为全量 numpy 暴力余弦。

    返回按相似度降序的候选 brief 列表（不超过 recall_k 篇）；两者都不可用返回 None。
    """
    # ---- FAISS 优先（进程内缓存索引，避免每请求全量拉库+解析 embedding） ----
    from app.vector_index import search as faiss_search
    try:
        ids, scores = await faiss_search(db, query_vec, recall_k)
    except Exception as e:
        logger.warning(f"FAISS recall failed, falling back to brute force: {e}")
        ids, scores = [], []
    if ids:
        result = await db.execute(
            sa_select(
                PaperFeatures.paper_id, PaperFeatures.keywords,
                Paper.title, Paper.abstract, Paper.source, Paper.published_at,
            )
            .join(Paper, Paper.id == PaperFeatures.paper_id)
            .where(PaperFeatures.paper_id.in_(ids))
        )
        row_by_id = {r[0]: r for r in result.all()}
        score_map = dict(zip(ids, scores))
        papers = []
        for pid in ids:
            r = row_by_id.get(pid)
            if r:
                papers.append(_paper_brief(r, score_map.get(pid, 0.0)))
        if papers:
            return await _attach_journal_and_filter(db, papers)

    # ---- 降级：全量拉 embedding，内存暴力余弦 ----
    rows = (
        await db.execute(
            sa_select(
                PaperFeatures.paper_id, PaperFeatures.embedding, PaperFeatures.keywords,
                Paper.title, Paper.abstract, Paper.source, Paper.published_at,
            )
            .join(Paper, Paper.id == PaperFeatures.paper_id)
            .where(PaperFeatures.embedding.isnot(None))
        )
    ).all()
    if not rows:
        return None
    candidates = [(r[0], json.loads(r[1])) for r in rows if r[1]]
    if not candidates:
        return None
    top = _cosine_top_k(query_vec, candidates, k=recall_k)
    score_map = dict(top)
    picked = [r for r in rows if r[0] in score_map]
    picked.sort(key=lambda r: score_map.get(r[0], 0), reverse=True)
    # 列序对齐 _paper_brief（[paper_id, keywords, title, abstract, source, published_at]）：
    # SELECT 里 embedding 列插在最前，这里归一化掉，避免 title/abstract/source 错位
    norm = [(r[0], r[2], r[3], r[4], r[5], r[6]) for r in picked]
    return await _attach_journal_and_filter(db, [_paper_brief(nr, score_map.get(nr[0], 0.0)) for nr in norm])


async def _attach_journal_and_filter(db: AsyncSession, papers: list):
    """给召回候选补 journal_name 并按受信期刊去噪。

    库内混入大量非 TOP50 的无关期刊，会让召回/拥挤度统计把低质论文混进来。
    过滤后若为空则保留原结果（兜底不中断功能）。
    """
    if not papers:
        return papers
    ids = [p["id"] for p in papers if p.get("id")]
    if ids:
        jrows = (await db.execute(
            sa_select(Paper.id, Paper.journal_name).where(Paper.id.in_(ids))
        )).all()
        jmap = {r[0]: r[1] for r in jrows}
        for p in papers:
            p["journal_name"] = jmap.get(p.get("id"))
    from app.journal_filter import filter_trusted_papers
    return filter_trusted_papers(papers)


async def _rerank_papers(topic: str, papers: list, k: int):
    """对召回候选做重排精排（硅基流动 bge-reranker-v2-m3）。

    返回 (papers, ok)：ok=True 时 papers 为按重排分数降序的前 k 篇（similarity 为重排分），
    ok=False 时 papers 为原顺序前 k 篇（调用方走 embedding 顺序降级）。
    """
    if not papers:
        return papers, False
    docs = [f"{p['title']}\n{p['abstract'] or ''}" for p in papers]
    try:
        results = await ai_trend_service.rerank_async(topic, docs, top_n=k)
    except Exception as e:
        logger.warning(f"Rerank stage failed: {e}")
        results = None
    if not results:
        return papers[:k], False
    out = []
    for r in results:
        idx = r.get("index")
        if idx is not None and 0 <= idx < len(papers):
            p = dict(papers[idx])
            p["similarity"] = round(float(r.get("relevance_score") or p["similarity"]), 4)
            out.append(p)
    return out, True


def _paper_brief(row, score: float) -> dict:
    """行数据 -> 验证器用的论文摘要卡片（字段精简，控制 prompt 长度）。

    published_at 兼容 datetime / str 两种取值（SQLite 不同查询路径类型可能不一致）。
    """
    from datetime import datetime, timezone
    raw = row[5]
    if isinstance(raw, datetime):
        published = raw.isoformat() if raw.tzinfo else raw.replace(tzinfo=timezone.utc).isoformat()
    elif raw:
        published = str(raw)
        if published.endswith("Z"):
            # 兼容 'YYYY-MM-DDTHH:MM:SSZ'：ISO 规范 Z 后缀 → +00:00
            published = published[:-1] + "+00:00"
    else:
        published = None
    return {
        "id": row[0],
        "title": row[2],
        "abstract": (row[3] or "")[:300],
        "source": row[4],
        "published_at": published,
        "keywords": (row[1] or [])[:8] if isinstance(row[1], list) else [],
        "similarity": round(float(score), 4),
    }


def _crowding_stats(papers: list) -> dict:
    """拥挤度统计：给 LLM 的定量信号。"""
    if not papers:
        return {"top30_avg_similarity": 0.0, "recent_3m_count": 0, "keyword_overlap": {}}

    sims = [p["similarity"] for p in papers]
    from datetime import timedelta
    # 比较对象已被 strip 成 naive，此处保持 naive-UTC 同口径（utcnow 的无弃用等价写法）
    three_months_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)
    recent = 0
    kw_counts: dict = {}
    for p in papers:
        try:
            if p["published_at"] and datetime.fromisoformat(p["published_at"].replace("Z", "+00:00")).replace(tzinfo=None) >= three_months_ago:
                recent += 1
        except (ValueError, TypeError):
            pass
        for kw in p.get("keywords", []):
            kw_counts[kw] = kw_counts.get(kw, 0) + 1

    top_keywords = sorted(kw_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    return {
        "top30_avg_similarity": round(sum(sims) / len(sims), 4),
        "max_similarity": round(max(sims), 4),
        "recent_3m_count": recent,
        "keyword_overlap": [{"keyword": kw, "count": c} for kw, c in top_keywords],
    }


async def _competition_map(db: AsyncSession, paper_ids: list) -> dict:
    """竞争地图（P2-12b）：这个话题谁在做、发到哪、近一年多少篇。

    基于召回论文 id 反查 authors / venue / journal_name，聚合作者与期刊分布。
    """
    if not paper_ids:
        return {"top_authors": [], "journal_distribution": [], "recent_1y_count": 0}

    from sqlalchemy import select as sa_select
    from app.models import Paper

    result = await db.execute(
        sa_select(Paper.authors, Paper.venue, Paper.journal_name, Paper.published_at)
        .where(Paper.id.in_(list(paper_ids)[:60]))
    )
    author_counts: dict = {}
    journal_counts: dict = {}
    recent_1y = 0

    from datetime import datetime, timedelta, timezone
    one_year_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=365)
    for authors_raw, venue, journal_name, published_at in result.all():
        authors = authors_raw if isinstance(authors_raw, list) else []
        for a in authors or []:
            a = (a or "").strip()
            if a:
                author_counts[a] = author_counts.get(a, 0) + 1
        j = journal_name or venue
        if j:
            journal_counts[j] = journal_counts.get(j, 0) + 1
        if published_at:
            try:
                dt = published_at if isinstance(published_at, datetime) else datetime.fromisoformat(str(published_at))
                if dt.tzinfo:
                    dt = dt.replace(tzinfo=None)
                if dt >= one_year_ago:
                    recent_1y += 1
            except (ValueError, TypeError):
                pass

    top_authors = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    journals = sorted(journal_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    return {
        "top_authors": [{"name": n, "count": c} for n, c in top_authors],
        "journal_distribution": [{"journal": j, "count": c} for j, c in journals],
        "recent_1y_count": recent_1y,
    }


# ---------------------------------------------------------------------------
# P6：选题库（决策层）——把「验证过的选题」沉淀为可跟踪项目
# ---------------------------------------------------------------------------

class TopicProjectCreate(BaseModel):
    title: str
    source_gap: Optional[str] = None
    source_type: Optional[str] = "manual"       # gap | keyword | idea | manual
    source_ref: Optional[str] = None            # 来源引用（空白词对/热点词/一句话想法）
    source_paper_id: Optional[int] = None
    validation_report: Optional[str] = None
    novelty: Optional[int] = None
    crowding: Optional[str] = None
    feasibility: Optional[int] = None
    research_questions: Optional[list] = None
    current_step: Optional[int] = 1


class TopicProjectUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    novelty: Optional[int] = None
    crowding: Optional[str] = None
    feasibility: Optional[int] = None
    research_questions: Optional[list] = None
    current_step: Optional[int] = None
    generated_topics: Optional[list] = None
    overview: Optional[str] = None
    data_insights: Optional[dict] = None
    literature_review: Optional[str] = None
    proposal: Optional[str] = None
    journal_advice: Optional[str] = None


class TopicProjectOut(BaseModel):
    id: int
    title: str
    source_gap: Optional[str] = None
    source_type: Optional[str] = "manual"
    source_ref: Optional[str] = None
    source_paper_id: Optional[int] = None
    novelty: Optional[int] = None
    crowding: Optional[str] = None
    feasibility: Optional[int] = None
    status: str
    validation_report: Optional[str] = None   # 验证报告 markdown（选题库回看决策依据）
    research_questions: Optional[list] = None
    current_step: Optional[int] = 1
    generated_topics: Optional[list] = None
    overview: Optional[str] = None
    data_insights: Optional[dict] = None
    literature_review: Optional[str] = None
    proposal: Optional[str] = None
    journal_advice: Optional[str] = None
    ai_pending: Optional[str] = None
    ai_error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


def _project_out(p: TopicProject) -> dict:
    """TopicProject -> 前端展示 dict（时间格式化为 ISO 字符串）。"""
    return {
        "id": p.id,
        "title": p.title,
        "source_gap": p.source_gap,
        "source_type": p.source_type or "manual",
        "source_ref": p.source_ref,
        "source_paper_id": p.source_paper_id,
        "novelty": p.novelty,
        "crowding": p.crowding,
        "feasibility": p.feasibility,
        "status": p.status,
        "validation_report": p.validation_report,
        "research_questions": p.research_questions or [],
        "current_step": p.current_step or 1,
        "generated_topics": p.generated_topics or [],
        "overview": p.overview,
        "data_insights": p.data_insights,
        "literature_review": p.literature_review,
        "proposal": p.proposal,
        "journal_advice": p.journal_advice,
        "ai_pending": p.ai_pending,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("/topic-projects")
async def list_topic_projects(
    status: Optional[str] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """选题库列表：按状态过滤（可选），时间倒序。"""
    stmt = sa_select(TopicProject).where(TopicProject.user_id == _uid_from(request))
    if status:
        stmt = stmt.where(TopicProject.status == status)
    stmt = stmt.order_by(TopicProject.updated_at.desc())
    result = await db.execute(stmt)
    return [_project_out(p) for p in result.scalars().all()]


@router.post("/topic-projects", status_code=201)
async def create_topic_project(
    body: TopicProjectCreate,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """创建研究项目（从验证器/空白页/热点/一句话想法沉淀）。

    创建后自动用 embedding 召回与选题最相关的论文作为初始文献集（失败不阻塞创建）。
    """
    if not (body.title or "").strip():
        raise HTTPException(status_code=400, detail="Title is required")
    p = TopicProject(
        user_id=_uid_from(request),
        title=body.title.strip(),
        source_gap=body.source_gap,
        source_type=(body.source_type or "manual"),
        source_ref=body.source_ref,
        source_paper_id=body.source_paper_id,
        validation_report=body.validation_report,
        novelty=body.novelty,
        crowding=body.crowding,
        feasibility=body.feasibility,
        research_questions=body.research_questions,
        current_step=body.current_step or 1,
        status="validated",
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)

    # 初始文献集：embedding 召回 top-10 写入 project_papers（失败静默，不阻塞创建）
    from app.models import ProjectPaper
    try:
        query = p.title
        briefs, _mode = await _retrieve_similar_papers(db, query, k=10)
        for b in briefs:
            db.add(ProjectPaper(
                user_id=p.user_id, project_id=p.id,
                paper_id=str(b["id"]), similarity=b.get("similarity"),
            ))
        await db.commit()
    except Exception as e:
        logger.warning(f"auto recall initial papers failed for project {p.id}: {e}")
        await db.rollback()

    return _project_out(p)


@router.patch("/topic-projects/{project_id}")
async def update_topic_project(
    project_id: int,
    body: TopicProjectUpdate,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """更新选题状态/评分（决策流转：to_validate->validated->subscribed->abandoned）。"""
    p = await db.get(TopicProject, project_id)
    if not p or p.user_id != _uid_from(request):
        raise HTTPException(status_code=404, detail="Topic project not found")
    allowed_status = {"to_validate", "validated", "subscribed", "abandoned"}
    if body.status is not None:
        if body.status not in allowed_status:
            raise HTTPException(status_code=400, detail=f"Invalid status, must be one of {sorted(allowed_status)}")
        p.status = body.status
    for field in (
        "title", "novelty", "crowding", "feasibility",
        "research_questions", "current_step", "generated_topics",
        "overview", "data_insights", "literature_review",
        "proposal", "journal_advice",
    ):
        value = getattr(body, field, None)
        if value is not None:
            setattr(p, field, value)
    await db.commit()
    await db.refresh(p)
    return _project_out(p)


@router.delete("/topic-projects/{project_id}", status_code=204)
async def delete_topic_project(
    project_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """删除一个选题（从选题库移除）。"""
    p = await db.get(TopicProject, project_id)
    if not p or p.user_id != _uid_from(request):
        raise HTTPException(status_code=404, detail="Topic project not found")
    await db.delete(p)
    await db.commit()


@router.post("/topic-validator/validate")
async def validate_topic(
    body: ValidateRequest,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """选题验证器：候选题目 -> 召回近似论文 -> 拥挤度统计 -> LLM 流式评估（SSE）。"""
    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    papers, mode = await _retrieve_similar_papers(db, topic, k=30)
    stats = _crowding_stats(papers)
    # P2-12b：竞争地图（谁在做 / 发到哪 / 近一年多少篇）
    try:
        competition = await _competition_map(db, [p["id"] for p in papers])
    except Exception as comp_err:
        logger.warning(f"competition map failed: {comp_err}")
        competition = {"top_authors": [], "journal_distribution": [], "recent_1y_count": 0}
    stats["competition"] = competition

    papers_text = "\n".join([
        f"[{i+1}] ({p['similarity']:.3f}) {p['title']} ({p['source']}, {p['published_at'][:10] if p['published_at'] else '?'})"
        f" 关键词: {', '.join(p['keywords'][:5]) or '无'}"
        for i, p in enumerate(papers[:30])
    ]) or "（未召回近似论文：该题目的表述在库内近乎无匹配）"

    stats_text = (
        f"召回模式: {mode}\n"
        f"Top30 平均相似度: {stats['top30_avg_similarity']}\n"
        f"最高相似度: {stats.get('max_similarity', 0)}\n"
        f"近似论文中近 3 个月发表: {stats['recent_3m_count']} 篇\n"
        f"近似论文高频关键词: {', '.join([k['keyword'] for k in stats['keyword_overlap'][:8]]) or '无'}\n"
        f"竞争地图——活跃作者: {', '.join(a['name'] for a in competition['top_authors']) or '无'}\n"
        f"竞争地图——期刊分布: {', '.join(j['journal'] for j in competition['journal_distribution']) or '无'}\n"
        f"竞争地图——近一年发表: {competition['recent_1y_count']} 篇"
    )

    system_prompt = f"""你是一位严格的学术选题评审专家。用户提出了一个候选研究选题，你需要基于论文库的检索证据评估它。

候选选题：{topic}

检索到的近似论文（按相似度降序）：
{papers_text}

定量统计：
{stats_text}

请用 markdown 输出一份选题验证报告，包含以下部分：
## 新颖性评估
基于最高相似度和近似论文列表，判断该选题与现有文献的重合程度。给出新颖性评分（1-10，10 最新颖）和依据。
## 竞争拥挤度
基于平均相似度、近 3 个月发表量和高频关键词，判断这个方向是否已经很拥挤。给出拥挤度（低/中/高）和依据。
## 机会窗口
综合以上分析，现在是进入这个方向的好时机吗？是蓝海、红海还是正在升温的方向？
## 风险与盲区
检索证据可能遗漏什么（关键词表述差异、跨领域文献）？用户需要警惕什么？
## 建议切入角度
如果要做，如何与已召回的这些论文差异化？给出 2-3 个具体切入点。

要求：诚实、量化、不客套。如果证据显示这个选题已经非常拥挤，直接说。如果检索证据不足以下结论，明确说明置信度低。

引用要求：涉及具体论文的判断/依据时，用方括号编号标注对应论文，如 [1]、[2][5]。编号即上面论文列表的序号。若某结论不依赖具体论文，则无需标注。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请验证选题：「{topic}」"},
    ]

    try:
        provider, bare_model = _resolve_model_provider(body.model)
        client, provider = _get_ai_client(provider)
    except HTTPException:
        raise HTTPException(status_code=503, detail="AI API key not configured")

    # 先发射一条论文元消息：前端据此渲染召回卡片（召回可见化），再进入 LLM 流。
    def _papers_payload() -> dict:
        return {
            "papers": [
                {
                    "n": i + 1,  # 与 prompt 里的 [n] 编号对齐，前端据此把引用渲染成论文链接
                    "id": p["id"],
                    "title": p["title"],
                    "source": p["source"],
                    "published_at": p["published_at"],
                    "keywords": p["keywords"],
                    "similarity": p["similarity"],
                }
                for i, p in enumerate(papers[:30])
            ],
            "mode": mode,
            "stats": stats,
        }

    async def composed_stream():
        yield f"data: {json.dumps(_papers_payload())}\n\n"
        # 逐个转发 LLM 流事件（原始 SSE 行原样透传）
        llm_resp = _stream_chat_response(client, provider, messages, model=bare_model)
        async for chunk in llm_resp.body_iterator:
            yield chunk

    return StreamingResponse(composed_stream(), media_type="text/event-stream")


class ProposalRequest(BaseModel):
    topic: str
    validation_report: Optional[str] = None
    model: Optional[str] = None


async def _generate_proposal_content(
    db: AsyncSession, topic: str,
    validation_report: Optional[str] = None,
    model: Optional[str] = None,
) -> tuple:
    """选题立项书生成核心（供 /topic-validator/proposal 与研究工作台复用）。

    返回 (content, model_name)。模型未配置时抛 HTTPException(503)。
    """
    import asyncio as _asyncio

    papers, _mode = await _retrieve_similar_papers(db, topic, k=15)

    # 库内数据线索：相关论文用到的关键词与期刊分布，供"可用数据"部分参考
    try:
        competition = await _competition_map(db, [p["id"] for p in papers])
    except Exception:
        competition = {"top_authors": [], "journal_distribution": [], "recent_1y_count": 0}

    related_text = "\n".join([
        f"- {p['title']} ({p['source']}, {p['published_at'][:10] if p['published_at'] else '?'})"
        for p in papers[:15]
    ]) or "（库内无强相关论文）"

    system_prompt = f"""你是严谨的学术研究计划顾问。请为以下选题生成一页「选题立项书」（markdown）。

选题：{topic}

{'验证报告摘要（供参考）：' + validation_report[:1500] if validation_report else ''}
{'竞争情报——活跃作者: ' + ', '.join(a['name'] for a in competition['top_authors']) + '；主要发表期刊: ' + ', '.join(j['journal'] for j in competition['journal_distribution']) if competition['top_authors'] else ''}

库内最相关论文：
{related_text}

请严格按以下结构输出：
# 选题立项书：{topic}
## 一、研究问题与假设
核心研究问题（1-3 个）、理论假说或待检验命题
## 二、数据来源建议
具体到可获得的数据库/统计年鉴/调查数据（如 CFPS/CHFS/上市公司数据库等），说明匹配的样本与变量
## 三、可用数据评估
结合论文库中相似研究使用的数据，判断该选题的数据可得性与获取成本（高/中/低）
## 四、方法论设计
推荐 1-2 种识别策略/模型（如 DID、IV、RDD、面板固定效应等），说明理由与关键设定
## 五、研究步骤与时间安排
4-6 步的研究路线图
## 六、预期贡献与创新点
理论贡献与实践贡献各 1-2 条

要求：具体、可执行，不写空话。"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请为选题「{topic}」生成立项书。"},
    ]

    provider, bare_model = _resolve_model_provider(model)
    client, provider = _get_ai_client(provider)
    if not bare_model:
        from app.routers.deps import _get_default_model
        bare_model = _get_default_model(provider)

    response = await _asyncio.to_thread(
        client.chat.completions.create,
        model=bare_model,
        messages=messages,
        max_tokens=3072,
        temperature=0.4,
    )
    return (response.choices[0].message.content or "").strip(), f"{provider}/{bare_model}"


@router.post("/topic-validator/proposal")
async def generate_proposal(
    body: ProposalRequest,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """选题立项书（P2-12a）：验证通过后一键/自动生成一页立项书。

    包含：研究问题、数据来源建议、可用数据、方法论、研究设计与预期贡献。
    """
    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")
    try:
        content, model_name = await _generate_proposal_content(db, topic, body.validation_report, body.model)
        return {"topic": topic, "proposal": content, "model": model_name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proposal generation failed: {str(e)}")
