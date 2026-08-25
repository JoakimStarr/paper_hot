"""产出环节（P2-11）：综述生成 + 期刊适配建议。

让选题闭环的最后一步落地：输入一个选题 -> 从论文库检索相关论文 -> AI 生成结构化
文献综述；并依据期刊分布给出投稿适配建议。AI 不可用时优雅降级为纯数据检索结果。
"""
import asyncio
import json
import logging
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select as sa_select, desc as sa_desc, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db, AsyncSessionLocal
from app.models import Paper, PaperFeatures, ReviewReport
from app.ai_service import ai_trend_service
from app.routers.deps import (
    verify_token, _get_ai_client, _resolve_model_provider, _get_default_model,
    _isoformat_utc,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# 常用中文经管顶刊画像（内置，供期刊适配参考）
JOURNAL_PROFILES = {
    "经济研究": "经济学综合理论顶刊，看重选题的理论价值与政策含义，喜欢大问题、宏大叙事",
    "管理世界": "管理学综合顶刊，重管理实践与政策导向，接受实证与案例，青睐与现实政策紧密相关的话题",
    "中国工业经济": "产业经济学顶刊，重产业组织、公司金融、创新与数字化转型，实证要求高",
    "金融研究": "金融学顶刊，重金融市场、公司金融、资产定价，计量严谨",
    "数量经济技术经济研究": "计量方法前沿阵地，重方法创新与数据可得性，适合方法驱动选题",
    "南开管理评论": "管理学老牌期刊，重战略、组织、营销，理论与实证并重",
    "改革": "偏改革转型与制度经济，重政策与现实问题契合",
    "国际经济": "国际经济学方向，重开放宏观、国际贸易与投资",
    "中国农村经济": "农业与农村经济，重三农问题、乡村振兴实证",
    "财经研究": "财经类综合，金融与管理交叉，性价比高的投稿选择",
}


class ReviewRequest(BaseModel):
    topic: str
    model: Optional[str] = None


class ReviewResponse(BaseModel):
    review_id: Optional[int] = None
    status: str = "running"
    topic: Optional[str] = None
    content: Optional[str] = None
    papers: Optional[list] = None
    model: Optional[str] = None
    created_at: Optional[str] = None


async def _retrieve_papers(db: AsyncSession, topic: str, limit: int = 25) -> List[dict]:
    """按选题关键词从论文库检索相关论文（标题/摘要/关键词命中 + 综合评分排序）。"""
    # 论文库无真实全文检索，用关键词覆盖检索 + 标题命中，取综合评分 top
    kws = [k for k in _tokenize_query(topic)]
    result = await db.execute(
        sa_select(Paper)
        .options(selectinload(Paper.scores))
        .order_by(sa_desc(Paper.published_at))
        .limit(2000)
    )
    scored = []
    for p in result.scalars():
        title = (p.title or "").lower()
        abstract = (p.abstract or "").lower()
        kws_cn = p.keywords_cn or []
        hits = 0
        for k in kws:
            kk = k.lower()
            if kk in title or kk in abstract or any(kk in (w or "") for w in kws_cn):
                hits += 1
        if hits:
            score = p.scores.final_score if p.scores else 0.0
            scored.append((hits, score, p))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    out = []
    for hits, score, p in scored[:limit]:
        out.append({
            "id": p.id,
            "title": p.title,
            "abstract": (p.abstract or "")[:400],
            "authors": p.authors or [],
            "journal_name": p.journal_name,
            "published_at": _isoformat_utc(p.published_at),
            "keywords_cn": p.keywords_cn or [],
            "hits": hits,
            "final_score": score,
        })
    return out


def _tokenize_query(topic: str) -> List[str]:
    """简单切分选题为检索词：按分隔符拆，过滤单字与停用词。"""
    import re
    stops = {"的", "与", "和", "对", "在", "研究", "基于", "视角", "及其", "理论",
             "影响", "机制", "作用", "关系", "路径", "我国", "中国", "分析"}
    parts = re.split(r"[，。；、,.;\s·×/()（）\"']", topic)
    words = []
    for part in parts:
        part = part.strip()
        if len(part) >= 2 and part not in stops:
            words.append(part)
    return words


@router.post("/producer/review", response_model=ReviewResponse)
async def generate_review(
    body: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """生成综述：后台任务检索论文 -> LLM 生成结构化综述（非流式，前端轮询状态）。"""
    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")

    report = ReviewReport(user_id="local", topic=topic, status="running")
    db.add(report)
    await db.commit()
    await db.refresh(report)

    from app.main import spawn_background_task
    spawn_background_task(_run_review_background(report.id, topic=body.topic, model=body.model))
    return ReviewResponse(review_id=report.id, status="running", topic=topic)


async def _run_review_background(review_id: int, topic: str, model: Optional[str] = None):
    from datetime import datetime as _dt
    start = _dt.utcnow()
    async with AsyncSessionLocal() as db:
        report = await db.get(ReviewReport, review_id)
        if not report:
            return
        try:
            papers = await _retrieve_papers(db, topic)
            if not papers:
                report.status = "failed"
                report.error_message = "未检索到相关论文，请调整选题表述后重试"
                await db.commit()
                return

            papers_text = "\n".join([
                f"- 《{p['title']}》(期刊: {p['journal_name'] or '未知'}，{str(p['published_at'])[:10] if p['published_at'] else '?'}) "
                f"关键词: {', '.join(p['keywords_cn'][:5]) or '无'} | 摘要: {(p['abstract'] or '')[:150]}"
                for p in papers[:20]
            ])

            system_prompt = f"""你是一位学术文献综述专家。请基于以下从论文库检索到的、与选题相关的论文，生成一份结构化的文献综述。
选题：{topic}

检索到的相关论文（{len(papers)}篇，按相关度排序）：
{papers_text}

请用 markdown 输出，包含以下部分：
## 研究脉络
梳理该选题方向从早期到近期的研究演进，说明主线脉络与发展阶段。
## 方法演进
文献中采用的研究方法从简单到复杂的演进路径（概念界定、计量方法、数据来源等）。
## 争议点
现有文献中存在哪些分歧与争议（结论冲突、方法派别、测度差异等）。
## 研究空白
基于上述脉络，指出尚待填补的空隙，这正是新研究的切入机会。

要求：
1. 引用文献时用【编号】标注（对应检索列表序号，从1开始），结论必须有文献支撑
2. 每个部分 2-5 段，结构清晰、观点明确
3. 最后给一段「可进一步研究」的建议，指出 2-3 个可行切入点"""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "请生成这份文献综述。"},
            ]

            provider, bare_model = _resolve_model_provider(model)
            client, provider = _get_ai_client(provider)
            if not bare_model:
                bare_model = _get_default_model(provider)

            response = await asyncio.to_thread(
                client.chat.completions.create, messages=messages, model=bare_model,
                max_tokens=4096, temperature=0.4,
            )
            content = (response.choices[0].message.content or "").strip()

            report.content = content
            report.papers_json = papers[:25]
            report.model = f"{provider}/{bare_model}"
            report.status = "success"
            await db.commit()
            logger.info(f"Review {review_id} done for topic '{topic}' in "
                        f"{( _dt.utcnow() - start).total_seconds():.1f}s")
        except Exception as e:
            logger.error(f"Review {review_id} failed: {e}")
            report.status = "failed"
            report.error_message = str(e)[:1000]
            await db.commit()


@router.get("/producer/review/{review_id}", response_model=ReviewResponse)
async def get_review(
    review_id: int,
    db: AsyncSession = Depends(get_db),
):
    report = await db.get(ReviewReport, review_id)
    if not report:
        raise HTTPException(status_code=404, detail="Review not found")
    return ReviewResponse(
        review_id=report.id,
        status=report.status,
        topic=report.topic,
        content=report.content,
        papers=report.papers_json,
        model=report.model,
        created_at=_isoformat_utc(report.created_at),
    )


@router.get("/producer/reviews")
async def list_reviews(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    result = await db.execute(
        sa_select(ReviewReport)
        .order_by(sa_desc(ReviewReport.created_at))
        .limit(limit)
    )
    return [
        {
            "id": r.id, "topic": r.topic, "status": r.status,
            "model": r.model, "created_at": _isoformat_utc(r.created_at),
        }
        for r in result.scalars()
    ]


class JournalRequest(BaseModel):
    topic: str
    abstract: Optional[str] = None
    model: Optional[str] = None


@router.post("/producer/journal")
async def suggest_journal(
    body: JournalRequest,
    db: AsyncSession = Depends(get_db),
):
    """期刊适配建议：依据论文库期刊分布 + 内置期刊画像 + LLM 推荐 2-3 个投稿目标。"""
    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")

    # 论文库该方向的期刊分布（检索相关论文统计期刊频次）
    papers = await _retrieve_papers(db, topic, limit=30)
    journal_counts: dict = {}
    for p in papers:
        j = p.get("journal_name")
        if j:
            journal_counts[j] = journal_counts.get(j, 0) + 1
    journal_dist = sorted(journal_counts.items(), key=lambda x: -x[1])[:10]

    profiles_text = "\n".join([
        f"- {name}: {profile}"
        for name, profile in JOURNAL_PROFILES.items()
    ])

    dist_text = "\n".join([
        f"- {name}: {cnt}篇相关论文" for name, cnt in journal_dist
    ]) or "（论文库暂无该方向的明确期刊分布）"

    # 即便 AI 不可用，也有规则推理兜底
    fallback = _rule_journal_suggestion(topic, journal_dist)
    recommendation_block = _render_recommendation(fallback[0] if fallback else None)

    if not ai_trend_service.is_available():
        return {"topic": topic, "recommendations": recommendation_block, "suggestions": fallback, "ai_used": False}

    try:
        provider, bare_model = _resolve_model_provider(body.model)
        client, provider = _get_ai_client(provider)
        if not bare_model:
            bare_model = _get_default_model(provider)
        system_prompt = f"""你是学术期刊投稿顾问。用户给出一个研究选题，请结合论文库中该方向的期刊分布与内置期刊画像，推荐 2-3 个投稿目标。

内置期刊画像：
{profiles_text}

论文库该方向的实际期刊分布：
{dist_text}

选题：{topic}
{'摘要：' + body.abstract if body.abstract else ''}

请用 markdown 输出，每个推荐期刊一个小节：
## 推荐期刊名
- 契合理由：为什么你的方法论/话题/数据适合这个期刊
- 投稿策略：目标栏目、篇幅、侧重点建议
- 备选说明：若投不中还退到哪个期刊

要求：结合期刊画像与论文库分布，理由具体不空泛。"""
        response = await asyncio.to_thread(
            client.chat.completions.create, messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "请给出期刊适配建议。"},
            ], model=bare_model, max_tokens=2048, temperature=0.3,
        )
        text = (response.choices[0].message.content or "").strip()
        return {"topic": topic, "recommendations": text, "suggestions": fallback, "ai_used": True}
    except Exception as e:
        logger.warning(f"Journal suggestion LLM failed, using rule fallback: {e}")
        return {"topic": topic, "recommendations": recommendation_block, "suggestions": fallback, "ai_used": False}


def _rule_journal_suggestion(topic: str, journal_dist) -> list:
    """无 AI 时的规则兜底：优先推荐库内该方向分布最多的期刊，再补充画像里最通用的一档。"""
    suggestions = []
    if journal_dist:
        top = journal_dist[0]
        suggestions.append({
            "journal": top[0],
            "reason": f"论文库内与「{topic}」相关文献多发表于该刊（{top[1]}篇），领域契合度高、接收偏好最接近。",
        })
    else:
        suggestions.append({
            "journal": "经济研究或管理世界",
            "reason": "论文库暂无该方向明确分布，优先考虑全国综合顶刊，兴趣覆盖面广。",
        })
    suggestions.append({
        "journal": "数量经济技术经济研究",
        "reason": "若研究含较强计量方法成分，该刊对方法规范与数据可得性要求高、题材包容度好。",
    })
    return suggestions[:2]


def _render_recommendation(sugg) -> str:
    if not sugg:
        return ""
    return f"## {sugg['journal']}\n- 契合理由：{sugg.get('reason', '')}"


# ---------- 引用导出：GB/T 7714 与 BibTeX ----------

def _authors_text(authors) -> str:
    if not authors:
        return ""
    return ", ".join(a for a in authors if a)


def _to_gbt7714(p: dict, idx: int = 0) -> str:
    """论文卡片/快照 -> GB/T 7714 引用条目（作者. 题名[J]. 刊名, 年(期).）"""
    authors = _authors_text(p.get("authors") or [])
    title = (p.get("title") or "").strip()
    journal = (p.get("journal_name") or "").strip()
    year = ""
    published = p.get("published_at")
    if published:
        year = str(published)[:4]
    issue = p.get("journal_issue") or ""
    suffix = f"{year}{('(' + issue + ')') if issue else ''}" if (year or issue) else ""
    if suffix:
        suffix = f", {suffix}"
    return f"{authors}. {title}[J]. {journal}{suffix}。"


def _to_bibtex(p: dict) -> str:
    """论文卡片/快照 -> BibTeX 条目（@article）。"""
    from datetime import datetime as _dtt
    authors = _authors_text(p.get("authors") or [])
    title = (p.get("title") or "").strip()
    journal = (p.get("journal_name") or "").strip()
    year = ""
    published = p.get("published_at")
    if published:
        year = str(published)[:4]
    key = "paper{}{}".format(year, (p.get("id") or "")[:6].replace("-", ""))
    a = (_authors_text(p.get("authors") or []) or "Anonymous").strip()
    first = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]", "", (a.split(",")[0] if "," in a else a).strip())
    bt_key = f"{first or 'author'}{year}"
    lines = [
        "@article{" + f"{bt_key},",
        f"  title = {{{title}}},",
        f"  author = {{{authors}}},",
        f"  journal = {{{journal}}},",
        f"  year = {{{year}}},",
    ]
    if published:
        lines.append(f"  month = {{{_dtt.strptime(str(published)[:7], '%Y-%m').strftime('%b')}}},")
    lines.append("}")
    return "\n".join(lines)


class CitationRequest(BaseModel):
    papers: List[dict] = []   # 论文快照列表（详见 _retrieve_papers 的 dict 结构）
    format: str = "gbt7714"   # gbt7714 | bibtex


@router.post("/producer/citations")
async def export_citations(
    body: CitationRequest,
    token: bool = Depends(verify_token),
):
    """批量导出引用：GB/T 7714 或 BibTeX。输入论文快照，返回文本列表。"""
    fmt = (body.format or "gbt7714").strip().lower()
    items = body.papers or []
    if not items:
        return {"format": fmt, "citations": [], "total": 0}
    if fmt == "bibtex":
        citations = [_to_bibtex(p) for p in items]
    else:
        citations = [_to_gbt7714(p, i) for i, p in enumerate(items)]
    return {"format": fmt, "citations": citations, "total": len(citations)}