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

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import select as sa_select, desc as sa_desc, func as sa_func, or_ as sa_or
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db, AsyncSessionLocal
from app.skills import lit_review as lit_review_skill
from app.models import Paper, ReviewReport
from app.ai_service import ai_trend_service
from app.routers.deps import (
    resolve_working_model,
    verify_token, _get_ai_client, _resolve_model_provider, _get_default_model,
    _isoformat_utc,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _uid(x_user_id: Optional[str]) -> str:
    return (x_user_id or "").strip() or "local"

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
    """按选题从论文库检索相关论文（FAISS+rerank 两阶段，与选题验证器同一套检索）。

    输出结构兼容原实现（id/title/abstract/authors/journal_name/published_at/
    keywords_cn/hits/final_score），并额外带 similarity；按受信期刊去噪，
    过滤后为空则保留原结果（不中断功能）。
    """
    from app.routers.topic import _retrieve_similar_papers
    from app.journal_filter import filter_trusted_papers

    briefs, _mode = await _retrieve_similar_papers(db, topic, k=limit)
    if not briefs:
        return []

    ids = [b["id"] for b in briefs if b.get("id")]
    if not ids:
        return []

    result = await db.execute(
        sa_select(Paper).options(selectinload(Paper.scores)).where(Paper.id.in_(ids))
    )
    by_id = {p.id: p for p in result.scalars()}

    out = []
    for b in briefs:
        p = by_id.get(b["id"])
        if not p:
            continue
        out.append({
            "id": p.id,
            "title": p.title,
            "abstract": (p.abstract or "")[:400],
            "authors": p.authors or [],
            "journal_name": p.journal_name,
            "published_at": _isoformat_utc(p.published_at),
            "keywords_cn": p.keywords_cn or [],
            "hits": 1,
            "final_score": p.scores.final_score if p.scores else 0.0,
            "similarity": b.get("similarity", 0.0),
        })

    # 受信期刊去噪：过滤库内混入的无关期刊；全被过滤则保留原结果
    return filter_trusted_papers(out)


@router.post("/producer/review", response_model=ReviewResponse)
async def generate_review(
    body: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """生成综述：后台任务检索论文 -> LLM 生成结构化综述（非流式，前端轮询状态）。"""
    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")

    # P0 遗留#8：按 x-user-id 隔离综述历史，不再写死 "local"
    report = ReviewReport(user_id=_uid(x_user_id), topic=topic, status="running")
    db.add(report)
    await db.commit()
    await db.refresh(report)

    from app.main import spawn_background_task
    spawn_background_task(_run_review_background(report.id, topic=body.topic, model=body.model))
    return ReviewResponse(review_id=report.id, status="running", topic=topic)


async def _run_review_background(review_id: int, topic: str, model: Optional[str] = None):
    from datetime import datetime as _dt, timezone as _tz
    start = _dt.now(_tz.utc)
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
                f"[{i+1}] 《{p['title']}》(期刊: {p['journal_name'] or '未知'}，{str(p['published_at'])[:10] if p['published_at'] else '?'}) "
                f"关键词: {', '.join(p['keywords_cn'][:5]) or '无'} | 摘要: {(p['abstract'] or '')[:150]}"
                for i, p in enumerate(papers[:20])
            ])

            # 综述 prompt 收敛到 skills.lit_review（与工作台综述同一五节契约）
            messages = lit_review_skill.build_messages(
                topic=topic,
                papers_text=papers_text,
                paper_count=len(papers[:20]),
                context_note="从论文库检索到的",
            )

            client, provider, bare_model = resolve_working_model(model)

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
                        f"{(_dt.now(_tz.utc) - start).total_seconds():.1f}s")
        except Exception as e:
            logger.error(f"Review {review_id} failed: {e}")
            report.status = "failed"
            report.error_message = str(e)[:1000]
            await db.commit()


@router.get("/producer/review/{review_id}", response_model=ReviewResponse)
async def get_review(
    review_id: int,
    db: AsyncSession = Depends(get_db),
    x_user_id: str = Header(default=None),
):
    report = await db.get(ReviewReport, review_id)
    if not report:
        raise HTTPException(status_code=404, detail="Review not found")
    # 仅本人（或历史遗留的 local 记录）可读
    uid = _uid(x_user_id)
    if report.user_id not in (uid, "local"):
        raise HTTPException(status_code=403, detail="Forbidden")
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
    x_user_id: str = Header(default=None),
):
    uid = _uid(x_user_id)
    result = await db.execute(
        sa_select(ReviewReport)
        .where(sa_or(ReviewReport.user_id == uid, ReviewReport.user_id == "local"))
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


async def _suggest_journal_content(
    db: AsyncSession, topic: str,
    abstract: Optional[str] = None, model: Optional[str] = None,
) -> tuple:
    """期刊适配建议核心（供 /producer/journal 与研究工作台复用）。

    返回 (recommendations_text, suggestions, ai_used)；AI 不可用/失败时降级规则推荐。
    """
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
        return recommendation_block, fallback, False

    try:
        client, provider, bare_model = resolve_working_model(model)
        system_prompt = f"""你是学术期刊投稿顾问。用户给出一个研究选题，请结合论文库中该方向的期刊分布与内置期刊画像，推荐 2-3 个投稿目标。

内置期刊画像：
{profiles_text}

论文库该方向的实际期刊分布：
{dist_text}

选题：{topic}
{'摘要：' + abstract if abstract else ''}

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
        return text, fallback, True
    except Exception as e:
        logger.warning(f"Journal suggestion LLM failed, using rule fallback: {e}")
        return recommendation_block, fallback, False


@router.post("/producer/journal")
async def suggest_journal(
    body: JournalRequest,
    db: AsyncSession = Depends(get_db),
):
    """期刊适配建议：依据论文库期刊分布 + 内置期刊画像 + LLM 推荐 2-3 个投稿目标。"""
    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")

    recommendations, fallback, ai_used = await _suggest_journal_content(
        db, topic, body.abstract, body.model
    )
    return {"topic": topic, "recommendations": recommendations, "suggestions": fallback, "ai_used": ai_used}


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