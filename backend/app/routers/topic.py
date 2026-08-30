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
from app.skills import validate as validate_skill
from app.routers.deps import _stream_llm_content
from app.routers.deps import (
    resolve_working_model,
    verify_token, _parse_json_list,
    _get_ai_client, _resolve_model_provider, _get_default_model, _stream_chat_response,
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


def _make_role_model_resolver(models: Optional[dict], fallback: tuple):
    """按角色解析 'provider/model'（辩论/答辩共用）。

    返回 resolver(role) -> (client, provider, bare_model)：
    显式指定优先（失败回落全局默认），未指定直接用 fallback；结果按角色缓存。
    """
    cache: dict = {}

    def resolve(role: str) -> tuple:
        cached = cache.get(role)
        if cached is not None:
            return cached
        picked = (models or {}).get(role)
        if picked:
            try:
                p_provider, p_bare = _resolve_model_provider(picked)
                p_client, p_provider = _get_ai_client(p_provider)
                if not p_bare:
                    p_bare = _get_default_model(p_provider)
                cache[role] = (p_client, p_provider, p_bare)
                return cache[role]
            except HTTPException:
                logger.warning(f"role model {role}={picked} 不可用，回落全局默认")
        cache[role] = fallback
        return cache[role]

    return resolve


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
                    f"#{len(data_lines) + 1} 「{src}」(词频{g.get('source_count', 0)}，近3个统计年度{trend_map.get(src, 0)}篇) × "
                    f"「{tgt}」(词频{g.get('target_count', 0)}，近3个统计年度{trend_map.get(tgt, 0)}篇)："
                    f"共现{g.get('cooccurrence', 0)}次，空白分{g.get('gap_score', 0):.3f}"
                )
            data_text = "\n".join(data_lines)

            system_prompt = f"""你是一位资深的学术研究选题顾问。以下数据来自一个学术论文库的关键词共现分析：
每个组合都是「两个关键词各自高频出现、但很少在同一篇论文中共现」的潜在研究空白。
注意：「共现稀疏」不等于「从未共同出现」——共现次数可能是很小的正数（如 3 次、13 次），也可能是 0。

数据（按空白分降序，空白分越高表示交叉越稀少；每行行首的 #编号 唯一标识该组合）：
{data_text}

请对以上研究空白逐一给出"空白假设卡片"，用 markdown 输出，每个组合包含：
1. **组合**：A × B
2. **数据依据**：引用上面的词频/共现/趋势数字
3. **空白假设**：为什么可能存在这个空白（方法壁垒？领域隔阂？数据可得性？）
4. **风险提示**：这是"真空白"（有研究价值）还是"伪需求"（没人做是因为不值得做）？判断依据是什么？
5. **建议切入角度**：如果要研究，第一步可以做什么

要求：
- 数据引用必须逐字对应该行的 #编号 与数字，严禁把一个组合的数字写到另一个组合上（如把「A×C」的共现数写到「B×C」）
- 共现次数 > 0 的组合，严禁使用「没有出现过」「从未共同出现」「零共现」等表述，必须写「共现仅 N 次，远低于两词热度下的预期水平」；仅当共现 = 0 时才可说「未检索到共现」
- 诚实评估，宁可说"这可能是伪空白"也不要强行吹捧
- 假设要具体到"什么方法×什么场景"，不要空泛
- 最后给一个总结：按研究价值排序你最推荐的 3 个组合，并说明理由"""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "请分析这些研究空白并输出空白假设卡片。"},
            ]

            client, provider, bare_model = resolve_working_model(model)

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
    # 提供时：流结束后服务端直接把评分/报告/状态落库到该项目（技能层回写）
    project_id: Optional[int] = None
    # Agent 工具模式：报告生成前允许模型调用定量工具（topic_crowding/keyword_gaps 等）查询数据
    use_tools: bool = False


class DebateRequest(BaseModel):
    topic: str
    model: Optional[str] = None
    # 提供时：裁决分数（novelty/crowding/feasibility/gate）落库到该项目
    project_id: Optional[int] = None
    # 每方辩论轮数（1-3，服务端钳制）；总轮数 = rounds_per_side*2 + 1（评审）
    rounds_per_side: int = 2
    # 按角色指定模型（可选键 pro/con/judge，值 'provider/model'）；缺省键跟随 model/全局默认
    models: Optional[dict] = None


class DefenseRequest(BaseModel):
    topic: str
    model: Optional[str] = None
    # 提供时：合议分数（novelty/crowding/feasibility/gate）落库到该项目
    project_id: Optional[int] = None
    # 质询轮数（1-3，服务端钳制）；总环节 = candidate_0 + rounds_per_side*2 + panel
    rounds_per_side: int = 2
    # 按角色指定模型（可选键 candidate/examiner/panel，值 'provider/model'）
    models: Optional[dict] = None


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
    validation_report: Optional[str] = None
    validation_evidence: Optional[dict] = None
    search_keywords: Optional[list] = None
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
    gate: Optional[str] = None
    verdict: Optional[str] = None
    status: str
    validation_report: Optional[str] = None   # 验证报告 markdown（选题库回看决策依据）
    validation_evidence: Optional[dict] = None
    debate_transcript: Optional[dict] = None  # 辩论/答辩完整记录快照
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
        "gate": p.gate,
        "verdict": p.verdict,
        "status": p.status,
        "validation_report": p.validation_report,
        "validation_evidence": p.validation_evidence,
        "debate_transcript": p.debate_transcript,
        "search_keywords": p.search_keywords or [],
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

    创建保持轻量快速：不再同步做 embedding 召回。初始文献改为懒加载，
    用户首次进入 Step3（文献管理）时通过 POST /topic-projects/{id}/recall-papers 召回。
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
        # 状态机修正：只有携带验证报告的创建（旧验证器沉淀路径）才算已验证；
        # 普通新建从「验证中」开始，由 validate 技能推动 to_validate -> validated
        status="validated" if (body.validation_report or "").strip() else "to_validate",
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)

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
        "validation_report", "validation_evidence", "search_keywords",
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
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """选题验证器（validate 技能）：两阶段召回 -> 预承诺评分标准 -> Script 证据 -> LLM 流式评估（SSE）。

    输出以 ```json 头开始（novelty/crowding/feasibility/gate），后端在流中缓冲剥离该头：
    - 剥离后的 markdown 实时转发给前端（前端看不到 JSON 噪声）；
    - 带 project_id 时流结束后服务端直接把评分/报告/状态落库（技能层回写）；
    - 无 JSON 头时降级为旧版纯 markdown 流程（前端正则解析仍生效）。
    """
    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    papers, mode = await _retrieve_similar_papers(db, topic, k=30)
    stats = _crowding_stats(papers)
    stats["mode"] = mode
    # P2-12b：竞争地图（谁在做 / 发到哪 / 近一年多少篇）
    try:
        competition = await _competition_map(db, [p["id"] for p in papers])
    except Exception as comp_err:
        logger.warning(f"competition map failed: {comp_err}")
        competition = {"top_authors": [], "journal_distribution": [], "recent_1y_count": 0}
    stats["competition"] = competition

    # prompt 构造收敛到 skills.validate（预承诺评分标准 + Script 证据块 + 输出契约）
    messages = validate_skill.build_messages(topic, papers, stats, competition, use_tools=body.use_tools)

    try:
        client, provider, bare_model = resolve_working_model(body.model)
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

    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    async def composed_stream():
        yield _sse(_papers_payload())

        # JSON 头缓冲状态：判定期 content 暂缓下发（改写在 on_event 回调里完成）
        buf = {"text": "", "decided": False, "scores": None, "md": []}

        def on_event(ev: dict) -> None:
            """_stream_llm_content 转发前回调：剥离 JSON 头、累积正文供落库。"""
            c = ev.get("content")
            if not c:
                return
            if not buf["decided"]:
                buf["text"] += c
                # 每帧尝试解析：JSON 对象完整（无论围栏是否闭合）即剥离
                scores, rest = validate_skill.split_json_head(buf["text"])
                if scores is not None:
                    buf["decided"] = True
                    buf["scores"] = scores
                    buf["md"].append(rest)
                    ev["content"] = rest  # 判定完成：本帧改写为剥头后的剩余正文
                elif validate_skill.head_in_progress(buf["text"]):
                    ev["content"] = ""  # 头仍在流式中，继续缓冲（空 content 帧前端忽略）
                else:
                    buf["decided"] = True
                    buf["md"].append(buf["text"])
                    ev["content"] = buf["text"]  # 不是 JSON 头：放行原文（旧格式降级）
            else:
                buf["md"].append(c)

        # 推理模型（如 glm-5.2）的 reasoning_content 会大量占用 token 预算，
        # 4096 会导致正文为空（与 workbench._llm_json 同因），验证报告放宽到 8192
        if body.use_tools:
            # Agent 工具模式：模型可在写报告前调用定量工具查询论文库
            # （工具集刻意不含返回论文列表的工具，[n] 引用编号始终对齐基础召回）
            from app.routers.deps import _stream_agent_chat_response

            async def _agent_frames():
                async for chunk in _stream_agent_chat_response(
                    client, provider, messages, model=bare_model,
                    surface="topic_validator", agent_enabled=True,
                ):
                    text = chunk.decode("utf-8", "ignore") if isinstance(chunk, (bytes, bytearray)) else str(chunk)
                    for line in text.split("\n"):
                        line = line.strip()
                        if not line.startswith("data: "):
                            continue
                        try:
                            frame = json.loads(line[6:])
                        except Exception:
                            continue
                        if not isinstance(frame, dict):
                            continue
                        c = frame.get("content")
                        if c:
                            if not buf["decided"]:
                                buf["text"] += c
                                scores, rest = validate_skill.split_json_head(buf["text"])
                                if scores is not None:
                                    buf["decided"] = True
                                    buf["scores"] = scores
                                    buf["md"].append(rest)
                                    if rest:
                                        yield _sse({"content": rest})
                                elif validate_skill.head_in_progress(buf["text"]):
                                    pass  # JSON 头仍在流式中，继续缓冲
                                else:
                                    buf["decided"] = True
                                    buf["md"].append(buf["text"])
                                    yield _sse({"content": buf["text"]})
                            else:
                                buf["md"].append(c)
                                yield _sse({"content": c})
                        else:
                            if '"done"' in line and not buf["decided"] and buf["text"]:
                                # done 前放行缓冲正文
                                buf["decided"] = True
                                scores, rest = validate_skill.split_json_head(buf["text"])
                                buf["md"].append(rest)
                                if rest:
                                    yield _sse({"content": rest})
                            yield line + "\n\n"

            llm_gen = _agent_frames()
        else:
            llm_gen = _stream_llm_content(client, bare_model, messages, on_event=on_event, max_tokens=8192)
        async for frame in llm_gen:
            if not buf["decided"] and '"done"' in frame:
                # done 帧前放行全部缓冲正文，保证 content 先于 done 到达前端
                buf["decided"] = True
                buf["scores"], rest = validate_skill.split_json_head(buf["text"])
                buf["md"].append(rest)
                if rest:
                    yield _sse({"content": rest})
            yield frame

        # ---- 服务端落库：评分回填 + 报告正文 + 状态推进（仅限 to_validate） ----
        if body.project_id:
            try:
                uid = _uid_from(request)
                logger.info(f"validate persist begin: project={body.project_id}, uid={uid}")
                p = await db.get(TopicProject, body.project_id)
                if p and p.user_id == uid:
                    md = "".join(buf["md"]).strip()
                    if md:
                        p.validation_report = md
                    if buf["scores"] is not None:
                        validate_skill.apply_scores(p, buf["scores"])
                    if md or buf["scores"] is not None:
                        await db.commit()
                        logger.info(f"validate persisted for project {body.project_id}: "
                                    f"novelty={getattr(p, 'novelty', None)}, crowding={getattr(p, 'crowding', None)}")
            except Exception as e:
                logger.warning(f"validate server-side persist failed: {e}")

    return StreamingResponse(composed_stream(), media_type="text/event-stream")


@router.post("/topic-validator/debate")
async def debate_topic(
    body: DebateRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """选题评估辩论（debate 技能）：正方/反方各 rounds_per_side 轮交锋 + 评审裁决（SSE 全流式）。

    轮序（build_round_sequence）：pro_1 -> con_1 -> ... -> pro_N -> con_N -> judge。
    每一轮前发 {"round": round_name, "model": "provider/bare"} 元帧（前端据此开新气泡桶
    并标注模型），正文逐字流式转发。每轮按角色取模型：models.pro/con/judge 显式指定时
    用对应模型，缺省/失败回落 body.model 或全局默认。

    帧约定：论证轮只转发 content/reasoning/usage/error，**不转发轮内 done 帧**
    （前端 streamChat 遇 done 即 break，转发会截断后续轮次）；评审轮最后发一个总 done。

    裁决轮输出以 ```json 头开始（novelty/crowding/feasibility/gate，口径与 validate 一致）：
    - 后端在流中缓冲剥离该头（复用 validate_skill.split_json_head），markdown 正文实时转发；
    - 帧顺序硬约束：{"debate_scores": {...}} 必须在 done 帧之前发出（前端 streamChat 遇 done 即 break）；
    - 带 project_id 时流结束后 apply_scores 落库（技能层回写）。
    """
    from app.skills import debate as debate_skill

    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    papers, mode = await _retrieve_similar_papers(db, topic, k=30)
    stats = _crowding_stats(papers)
    stats["mode"] = mode
    try:
        competition = await _competition_map(db, [p["id"] for p in papers])
    except Exception as comp_err:
        logger.warning(f"debate competition map failed: {comp_err}")
        competition = {"top_authors": [], "journal_distribution": [], "recent_1y_count": 0}

    try:
        client, provider, bare_model = resolve_working_model(body.model)
    except HTTPException:
        raise HTTPException(status_code=503, detail="AI API key not configured")

    resolve_role_model = _make_role_model_resolver(body.models, (client, provider, bare_model))

    rounds_per_side = max(1, min(int(body.rounds_per_side or 2), 3))
    round_sequence = debate_skill.build_round_sequence(rounds_per_side)

    # 首帧论文元消息：编号与 prompt 里的 [n] 对齐，前端据此渲染召回卡片
    def _papers_payload() -> dict:
        return {
            "papers": [
                {
                    "n": i + 1,
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

    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    async def composed_stream():
        yield _sse(_papers_payload())

        history: list = []  # [(轮次标签, 该轮全文), ...] 注入下一轮上下文
        debate_scores = None
        # 完整记录快照（随项目一起落库，重进步骤恢复）
        transcript_rounds: list = []
        # 裁决轮 JSON 头缓冲状态（同 validate 端点 :945-969）
        buf = {"text": "", "decided": False, "scores": None, "md": []}

        def on_judge(ev: dict) -> None:
            c = ev.get("content")
            if not c:
                return
            if not buf["decided"]:
                buf["text"] += c
                scores, rest = validate_skill.split_json_head(buf["text"])
                if scores is not None:
                    buf["decided"] = True
                    buf["scores"] = scores
                    buf["md"].append(rest)
                    ev["content"] = rest
                elif validate_skill.head_in_progress(buf["text"]):
                    ev["content"] = ""
                else:
                    buf["decided"] = True
                    buf["md"].append(buf["text"])
                    ev["content"] = buf["text"]
            else:
                buf["md"].append(c)

        for round_name in round_sequence:
            label, _side = debate_skill.round_label(round_name)
            # 每轮按角色取模型：pro/con 用各自模型，judge 用评审模型
            role = _side
            r_client, r_provider, r_bare = resolve_role_model(role)
            model_str = f"{r_provider}/{r_bare}"
            yield _sse({"round": round_name, "model": model_str})

            messages = debate_skill.build_messages(
                topic, papers, stats, competition, history, round_name, rounds_per_side
            )

            if round_name == "judge":
                async for frame in _stream_llm_content(
                    r_client, r_bare, messages, on_event=on_judge, max_tokens=8192
                ):
                    # 硬约束：debate_scores 必须先于 done 到达（前端 streamChat 遇 done 即 break）
                    if not buf["decided"] and '"done"' in frame and buf["text"]:
                        buf["decided"] = True
                        buf["scores"], rest = validate_skill.split_json_head(buf["text"])
                        buf["md"].append(rest)
                        if rest:
                            yield _sse({"content": rest})
                    if buf["scores"] is not None and debate_scores is None:
                        debate_scores = buf["scores"]
                        yield _sse({"debate_scores": debate_scores})
                    yield frame
                transcript_rounds.append({
                    "id": round_name, "label": label, "model": model_str,
                    "text": "".join(buf["md"]),
                })
            else:
                round_text: list = []

                def on_arg(ev: dict) -> None:
                    c = ev.get("content")
                    if c:
                        round_text.append(c)

                # 论证轮：转发 content/reasoning/usage/error，但**丢弃轮内 done 帧**——
                # streamChat 遇 done 即 break，若每轮都发 done，前端在第 1 轮后就会断开，
                # 后续轮次（含反方/评审）全部收不到（"反方没内容"的根因）。
                # max_tokens 放宽到 16384：多轮对抗任务推理长，给正文留足预算。
                async for frame in _stream_llm_content(
                    r_client, r_bare, messages, on_event=on_arg, max_tokens=16384
                ):
                    if '"done"' in frame:
                        continue
                    yield frame
                # 空轮兜底：模型只输出思考没输出正文时，注入提示帧避免空气泡（下一轮 meta 之前）
                text = "".join(round_text)
                if not text:
                    text = "\n\n> ⚠️ 本轮模型未输出正文，已跳过。"
                    yield _sse({"content": text})
                history.append((label, text))
                transcript_rounds.append({
                    "id": round_name, "label": label, "model": model_str, "text": text,
                })

        # ---- 服务端落库：完整记录快照 + 裁决分数回填（重进步骤时随项目一起恢复） ----
        if body.project_id and transcript_rounds:
            try:
                uid = _uid_from(request)
                p = await db.get(TopicProject, body.project_id)
                if p and p.user_id == uid:
                    if debate_scores is not None:
                        validate_skill.apply_scores(p, debate_scores)
                    p.debate_transcript = {
                        "surface": "debate",
                        "rounds_per_side": rounds_per_side,
                        "rounds": transcript_rounds,
                        "scores": debate_scores,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await db.commit()
                    logger.info(f"debate transcript persisted for project {body.project_id}: "
                                f"rounds={len(transcript_rounds)}, novelty={getattr(p, 'novelty', None)}")
            except Exception as e:
                logger.warning(f"debate server-side persist failed: {e}")

    return StreamingResponse(composed_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/topic-validator/defense")
async def defense_topic(
    body: DefenseRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """选题答辩（defense 技能）：候选人自述 -> 评委质询/候选人应答交替 -> 合议裁定（SSE 全流式）。

    轮序（build_round_sequence）：candidate_0 -> examiner_1 -> candidate_1 -> ...
    -> examiner_N -> candidate_N -> panel。每一轮前发 {"round", "model"} 元帧，
    正文逐字流式转发，每轮按角色取模型（models.candidate/examiner/panel）。

    合议轮输出 ```json 头（validate 4 轴 + verdict: 通过|修改后通过|不通过）：
    - 后端缓冲剥离 JSON 头，markdown 正文实时转发；
    - 帧顺序硬约束：{"defense_scores": {...}} 先于 done（前端 streamChat 遇 done 即 break）；
    - 论证环节不转发轮内 done 帧（同 debate，避免截断后续环节）；合议轮最后发总 done；
    - 带 project_id 时 apply_scores 落库。
    """
    from app.skills import defense as defense_skill

    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    papers, mode = await _retrieve_similar_papers(db, topic, k=30)
    stats = _crowding_stats(papers)
    stats["mode"] = mode
    try:
        competition = await _competition_map(db, [p["id"] for p in papers])
    except Exception as comp_err:
        logger.warning(f"defense competition map failed: {comp_err}")
        competition = {"top_authors": [], "journal_distribution": [], "recent_1y_count": 0}

    try:
        client, provider, bare_model = resolve_working_model(body.model)
    except HTTPException:
        raise HTTPException(status_code=503, detail="AI API key not configured")

    resolve_role_model = _make_role_model_resolver(body.models, (client, provider, bare_model))

    rounds_per_side = max(1, min(int(body.rounds_per_side or 2), 3))
    round_sequence = defense_skill.build_round_sequence(rounds_per_side)

    def _papers_payload() -> dict:
        return {
            "papers": [
                {
                    "n": i + 1,
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

    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    async def composed_stream():
        yield _sse(_papers_payload())

        history: list = []  # [(环节标签, 该轮全文), ...]
        defense_scores = None
        transcript_rounds: list = []
        buf = {"text": "", "decided": False, "scores": None, "md": []}

        def on_panel(ev: dict) -> None:
            c = ev.get("content")
            if not c:
                return
            if not buf["decided"]:
                buf["text"] += c
                scores, rest = validate_skill.split_json_head(buf["text"])
                if scores is not None:
                    buf["decided"] = True
                    buf["scores"] = scores
                    buf["md"].append(rest)
                    ev["content"] = rest
                elif validate_skill.head_in_progress(buf["text"]):
                    ev["content"] = ""
                else:
                    buf["decided"] = True
                    buf["md"].append(buf["text"])
                    ev["content"] = buf["text"]
            else:
                buf["md"].append(c)

        for round_name in round_sequence:
            label, role = defense_skill.round_label(round_name)
            r_client, r_provider, r_bare = resolve_role_model(role)
            model_str = f"{r_provider}/{r_bare}"
            yield _sse({"round": round_name, "model": model_str})

            messages = defense_skill.build_messages(
                topic, papers, stats, competition, history, round_name, rounds_per_side
            )

            if round_name == "panel":
                async for frame in _stream_llm_content(
                    r_client, r_bare, messages, on_event=on_panel, max_tokens=8192
                ):
                    if not buf["decided"] and '"done"' in frame and buf["text"]:
                        buf["decided"] = True
                        buf["scores"], rest = validate_skill.split_json_head(buf["text"])
                        buf["md"].append(rest)
                        if rest:
                            yield _sse({"content": rest})
                    if buf["scores"] is not None and defense_scores is None:
                        defense_scores = buf["scores"]
                        yield _sse({"defense_scores": defense_scores})
                    yield frame
                transcript_rounds.append({
                    "id": round_name, "label": label, "model": model_str,
                    "text": "".join(buf["md"]),
                })
            else:
                round_text: list = []

                def on_round(ev: dict) -> None:
                    c = ev.get("content")
                    if c:
                        round_text.append(c)

                # 环节轮：不转发轮内 done 帧（同 debate 根因修复），max_tokens 放宽给推理留预算
                async for frame in _stream_llm_content(
                    r_client, r_bare, messages, on_event=on_round, max_tokens=16384
                ):
                    if '"done"' in frame:
                        continue
                    yield frame
                text = "".join(round_text)
                if not text:
                    text = "\n\n> ⚠️ 本环节模型未输出正文，已跳过。"
                    yield _sse({"content": text})
                history.append((label, text))
                transcript_rounds.append({
                    "id": round_name, "label": label, "model": model_str, "text": text,
                })

        # ---- 服务端落库：完整记录快照 + 合议分数回填（verdict 随 JSON 头透传，无存储列） ----
        if body.project_id and transcript_rounds:
            try:
                uid = _uid_from(request)
                p = await db.get(TopicProject, body.project_id)
                if p and p.user_id == uid:
                    if defense_scores is not None:
                        validate_skill.apply_scores(p, defense_scores)
                    p.debate_transcript = {
                        "surface": "defense",
                        "rounds_per_side": rounds_per_side,
                        "rounds": transcript_rounds,
                        "scores": defense_scores,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await db.commit()
                    logger.info(f"defense transcript persisted for project {body.project_id}: "
                                f"rounds={len(transcript_rounds)}, novelty={getattr(p, 'novelty', None)}")
            except Exception as e:
                logger.warning(f"defense server-side persist failed: {e}")

    return StreamingResponse(composed_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class DebateContinueRequest(BaseModel):
    topic: str
    model: Optional[str] = None
    project_id: Optional[int] = None
    history: list = []          # 已完成轮次 [{id,label,model,text}]
    role: str = "assistant"     # pro | con | judge | assistant
    prompt: str = ""            # 用户追问或预置指令
    models: Optional[dict] = None


@router.post("/topic-validator/debate/continue")
async def debate_continue(
    body: DebateContinueRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """辩论继续追问（单轮流式）：基于已完成轮次追加一轮，可指定角色或自由追问。"""
    from app.skills import debate as debate_skill

    topic = (body.topic or "").strip()
    prompt = (body.prompt or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    papers, mode = await _retrieve_similar_papers(db, topic, k=30)
    stats = _crowding_stats(papers)
    stats["mode"] = mode
    try:
        competition = await _competition_map(db, [p["id"] for p in papers])
    except Exception:
        competition = {"top_authors": [], "journal_distribution": [], "recent_1y_count": 0}

    try:
        client, provider, bare_model = resolve_working_model(body.model)
    except HTTPException:
        raise HTTPException(status_code=503, detail="AI API key not configured")
    resolve_role_model = _make_role_model_resolver(body.models, (client, provider, bare_model))

    role = body.role if body.role in ("pro", "con", "judge", "assistant") else "assistant"
    # 角色 -> 模型键：pro/con/judge 用各自模型，assistant 用评审模型
    model_key = {"pro": "pro", "con": "con", "judge": "judge", "assistant": "judge"}[role]
    r_client, r_provider, r_bare = resolve_role_model(model_key)
    messages = debate_skill.build_followup_messages(topic, papers, stats, competition, body.history, role, prompt)

    label = {"pro": "正方再回应", "con": "反方再回应", "judge": "评委再点评", "assistant": "继续追问"}[role]

    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    async def composed_stream():
        yield _sse({"round": "followup", "model": f"{r_provider}/{r_bare}", "role": role})
        round_text: list = []

        def on_round(ev: dict) -> None:
            c = ev.get("content")
            if c:
                round_text.append(c)

        async for frame in _stream_llm_content(r_client, r_bare, messages, on_event=on_round, max_tokens=16384):
            yield frame

        # 落库：追加到辩论记录
        if body.project_id:
            try:
                uid = _uid_from(request)
                p = await db.get(TopicProject, body.project_id)
                if p and p.user_id == uid:
                    t = p.debate_transcript or {}
                    rounds = list(t.get("rounds") or [])
                    rounds.append({"id": "followup", "label": label, "model": f"{r_provider}/{r_bare}",
                                   "text": "".join(round_text)})
                    p.debate_transcript = {
                        "surface": "debate",
                        "rounds_per_side": t.get("rounds_per_side", 2),
                        "rounds": rounds,
                        "scores": t.get("scores"),
                        "created_at": t.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    }
                    await db.commit()
            except Exception as e:
                logger.warning(f"debate continue persist failed: {e}")

    return StreamingResponse(composed_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class DefenseContinueRequest(BaseModel):
    topic: str
    model: Optional[str] = None
    project_id: Optional[int] = None
    history: list = []
    role: str = "assistant"     # candidate | examiner | panel | assistant
    prompt: str = ""
    models: Optional[dict] = None


@router.post("/topic-validator/defense/continue")
async def defense_continue(
    body: DefenseContinueRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """答辩继续追问（单轮流式）：基于已完成环节追加一轮，可指定角色或自由追问。"""
    from app.skills import defense as defense_skill

    topic = (body.topic or "").strip()
    prompt = (body.prompt or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    papers, mode = await _retrieve_similar_papers(db, topic, k=30)
    stats = _crowding_stats(papers)
    stats["mode"] = mode
    try:
        competition = await _competition_map(db, [p["id"] for p in papers])
    except Exception:
        competition = {"top_authors": [], "journal_distribution": [], "recent_1y_count": 0}

    try:
        client, provider, bare_model = resolve_working_model(body.model)
    except HTTPException:
        raise HTTPException(status_code=503, detail="AI API key not configured")
    resolve_role_model = _make_role_model_resolver(body.models, (client, provider, bare_model))

    role = body.role if body.role in ("candidate", "examiner", "panel", "assistant") else "assistant"
    model_key = {"candidate": "candidate", "examiner": "examiner", "panel": "panel", "assistant": "panel"}[role]
    r_client, r_provider, r_bare = resolve_role_model(model_key)
    messages = defense_skill.build_followup_messages(topic, papers, stats, competition, body.history, role, prompt)

    label = {"candidate": "候选人再回应", "examiner": "评委再质询", "panel": "合议补充", "assistant": "继续追问"}[role]

    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    async def composed_stream():
        yield _sse({"round": "followup", "model": f"{r_provider}/{r_bare}", "role": role})
        round_text: list = []

        def on_round(ev: dict) -> None:
            c = ev.get("content")
            if c:
                round_text.append(c)

        async for frame in _stream_llm_content(r_client, r_bare, messages, on_event=on_round, max_tokens=16384):
            yield frame

        if body.project_id:
            try:
                uid = _uid_from(request)
                p = await db.get(TopicProject, body.project_id)
                if p and p.user_id == uid:
                    t = p.debate_transcript or {}
                    rounds = list(t.get("rounds") or [])
                    rounds.append({"id": "followup", "label": label, "model": f"{r_provider}/{r_bare}",
                                   "text": "".join(round_text)})
                    p.debate_transcript = {
                        "surface": "defense",
                        "rounds_per_side": t.get("rounds_per_side", 2),
                        "rounds": rounds,
                        "scores": t.get("scores"),
                        "created_at": t.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    }
                    await db.commit()
            except Exception as e:
                logger.warning(f"defense continue persist failed: {e}")

    return StreamingResponse(composed_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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

    client, provider, bare_model = resolve_working_model(model)

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
