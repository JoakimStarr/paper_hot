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

from fastapi import APIRouter, Depends, HTTPException
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

# 本进程启动时间（UTC naive，与 ResearchGapReport.created_at 同口径）。
# 后台任务跑在进程内存里，后端重启会让 running 状态的报告永远无法完成，
# 用它判断并回收僵尸 running 报告。
from datetime import datetime as _datetime
_PROCESS_START = _datetime.utcnow()


async def _reap_zombie_running_report(db: AsyncSession) -> None:
    """回收僵尸 running 报告：created_at 早于本进程启动时间的 running 必属
    「后端重启导致后台任务丢失」，标记 failed 让前端停止无限等待。"""
    result = await db.execute(
        sa_select(ResearchGapReport)
        .where(ResearchGapReport.status == "running", ResearchGapReport.user_id == LOCAL_USER)
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
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """触发 LLM 空白解读后台任务（不阻塞，前端轮询 /network/gaps/analysis）。"""
    # 先回收僵尸 running（后端重启遗留），否则会被下面"正在跑"分支永远拦住
    await _reap_zombie_running_report(db)

    # 已有正在跑的任务直接返回，避免重复计费
    running = await db.execute(
        sa_select(ResearchGapReport)
        .where(ResearchGapReport.status == "running", ResearchGapReport.user_id == LOCAL_USER)
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
        user_id=LOCAL_USER,
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

            # 补充每个词的近 6 个月趋势（TopicTrend 表），让 LLM 的假设有数据支撑
            from app.models import TopicTrend
            from datetime import datetime, timedelta
            since = datetime.utcnow() - timedelta(days=180)
            topic_names = set()
            for g in gaps:
                topic_names.update([g.get("source", ""), g.get("target", "")])
            trend_rows = await db.execute(
                sa_select(TopicTrend.topic, sa_func.sum(TopicTrend.paper_count))
                .where(TopicTrend.topic.in_(topic_names), TopicTrend.week_start >= since)
                .group_by(TopicTrend.topic)
            )
            trend_map = {topic: int(cnt or 0) for topic, cnt in trend_rows.all()}

            data_lines = []
            for g in gaps:
                src, tgt = g.get("source", ""), g.get("target", "")
                data_lines.append(
                    f"- 「{src}」(词频{g.get('source_count', 0)}，近6月{trend_map.get(src, 0)}篇) × "
                    f"「{tgt}」(词频{g.get('target_count', 0)}，近6月{trend_map.get(tgt, 0)}篇)："
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

            # 后台任务用非流式调用（简单可靠），SSE 只用于选题验证器
            response = client.chat.completions.create(
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
async def get_gap_analysis(db: AsyncSession = Depends(get_db)):
    """查询最新一次空白解读（供前端轮询：running 时继续等，success 时渲染）。"""
    # 轮询入口顺带回收僵尸 running，前端刷新后即可拿到 failed 而非无限转圈
    await _reap_zombie_running_report(db)

    result = await db.execute(
        sa_select(ResearchGapReport)
        .where(ResearchGapReport.user_id == LOCAL_USER)
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
                vectors = ai_trend_service.embed_texts(texts)
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

    返回 (papers: list[dict], mode: "embedding" | "tfidf")
    """
    result = await db.execute(
        sa_select(
            PaperFeatures.paper_id, PaperFeatures.embedding, PaperFeatures.keywords,
            Paper.title, Paper.abstract, Paper.source, Paper.published_at,
        )
        .join(Paper, Paper.id == PaperFeatures.paper_id)
        .where(PaperFeatures.embedding.isnot(None))
        .limit(5000)
    )
    rows = result.all()

    # ---- 路线 1：embedding 召回 ----
    if rows:
        try:
            query_vec = ai_trend_service.embed_texts([topic])
            if query_vec and query_vec[0]:
                candidates = [(r[0], json.loads(r[1])) for r in rows if r[1]]
                top = _cosine_top_k(query_vec[0], candidates, k=k)
                score_map = dict(top)
                picked = [r for r in rows if r[0] in score_map]
                picked.sort(key=lambda r: score_map.get(r[0], 0), reverse=True)
                # 列序对齐 _paper_brief（[paper_id, keywords, title, abstract, source, published_at]）：
                # SELECT 里 embedding 列插在最前，这里归一化掉，避免 title/abstract/source 错位
                norm = [(r[0], r[2], r[3], r[4], r[5], r[6]) for r in picked]
                papers = [_paper_brief(nr, score_map.get(nr[0], 0.0)) for nr in norm]
                return papers, "embedding"
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
        .limit(5000)
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
    from datetime import datetime, timedelta
    three_months_ago = datetime.utcnow() - timedelta(days=90)
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


# ---------------------------------------------------------------------------
# P6：选题库（决策层）——把「验证过的选题」沉淀为可跟踪项目
# ---------------------------------------------------------------------------

class TopicProjectCreate(BaseModel):
    title: str
    source_gap: Optional[str] = None
    source_paper_id: Optional[int] = None
    validation_report: Optional[str] = None
    novelty: Optional[int] = None
    crowding: Optional[str] = None
    feasibility: Optional[int] = None


class TopicProjectUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    novelty: Optional[int] = None
    crowding: Optional[str] = None
    feasibility: Optional[int] = None


class TopicProjectOut(BaseModel):
    id: int
    title: str
    source_gap: Optional[str] = None
    source_paper_id: Optional[int] = None
    novelty: Optional[int] = None
    crowding: Optional[str] = None
    feasibility: Optional[int] = None
    status: str
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
        "source_paper_id": p.source_paper_id,
        "novelty": p.novelty,
        "crowding": p.crowding,
        "feasibility": p.feasibility,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("/topic-projects")
async def list_topic_projects(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """选题库列表：按状态过滤（可选），时间倒序。"""
    stmt = sa_select(TopicProject).where(TopicProject.user_id == LOCAL_USER)
    if status:
        stmt = stmt.where(TopicProject.status == status)
    stmt = stmt.order_by(TopicProject.updated_at.desc())
    result = await db.execute(stmt)
    return [_project_out(p) for p in result.scalars().all()]


@router.post("/topic-projects", status_code=201)
async def create_topic_project(
    body: TopicProjectCreate,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """保存一个选题到选题库（从验证器/空白页沉淀）。"""
    if not (body.title or "").strip():
        raise HTTPException(status_code=400, detail="Title is required")
    p = TopicProject(
        user_id=LOCAL_USER,
        title=body.title.strip(),
        source_gap=body.source_gap,
        source_paper_id=body.source_paper_id,
        validation_report=body.validation_report,
        novelty=body.novelty,
        crowding=body.crowding,
        feasibility=body.feasibility,
        status="validated",
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _project_out(p)


@router.patch("/topic-projects/{project_id}")
async def update_topic_project(
    project_id: int,
    body: TopicProjectUpdate,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """更新选题状态/评分（决策流转：to_validate->validated->subscribed->abandoned）。"""
    p = await db.get(TopicProject, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Topic project not found")
    allowed_status = {"to_validate", "validated", "subscribed", "abandoned"}
    if body.status is not None:
        if body.status not in allowed_status:
            raise HTTPException(status_code=400, detail=f"Invalid status, must be one of {sorted(allowed_status)}")
        p.status = body.status
    for field in ("title", "novelty", "crowding", "feasibility"):
        value = getattr(body, field, None)
        if value is not None:
            setattr(p, field, value)
    await db.commit()
    await db.refresh(p)
    return _project_out(p)


@router.delete("/topic-projects/{project_id}", status_code=204)
async def delete_topic_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """删除一个选题（从选题库移除）。"""
    p = await db.get(TopicProject, project_id)
    if not p:
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

    papers_text = "\n".join([
        f"- [{p['similarity']:.3f}] {p['title']} ({p['source']}, {p['published_at'][:10] if p['published_at'] else '?'})"
        f" 关键词: {', '.join(p['keywords'][:5]) or '无'}"
        for p in papers[:30]
    ]) or "（未召回近似论文：该题目的表述在库内近乎无匹配）"

    stats_text = (
        f"召回模式: {mode}\n"
        f"Top30 平均相似度: {stats['top30_avg_similarity']}\n"
        f"最高相似度: {stats.get('max_similarity', 0)}\n"
        f"近似论文中近 3 个月发表: {stats['recent_3m_count']} 篇\n"
        f"近似论文高频关键词: {', '.join([k['keyword'] for k in stats['keyword_overlap'][:8]]) or '无'}"
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

要求：诚实、量化、不客套。如果证据显示这个选题已经非常拥挤，直接说。如果检索证据不足以下结论，明确说明置信度低。"""

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
                    "id": p["id"],
                    "title": p["title"],
                    "source": p["source"],
                    "published_at": p["published_at"],
                    "keywords": p["keywords"],
                    "similarity": p["similarity"],
                }
                for p in papers[:30]
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
