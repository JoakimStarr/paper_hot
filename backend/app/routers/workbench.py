"""研究工作台（Workbench）：项目详情 / 文献集 / 统一 AI 操作。

选题中心重构的产物：以 TopicProject 为项目核心，串联
选题定义 → 验证 → 文献管理 → 数据/方法 → 写作输出 五步向导。

- GET  /topic-projects/{id}                 项目详情（全字段 + 文献集）
- GET  /topic-projects/{id}/status          轻量状态（id/status/ai_pending/ai_error/updated_at，轮询用）
- GET  /topic-projects/{id}/papers          文献集列表
- POST /topic-projects/{id}/papers          加入论文
- POST /topic-projects/{id}/recall-papers   按选题懒召回 top-10 论文并入文献集
- PATCH/DELETE /topic-projects/{id}/papers/{paper_id}   更新/移除
- POST /topic-projects/{id}/search-papers   检索候选论文（embedding 召回）
- POST /topic-projects/{id}/ai              统一 AI 操作（后台任务 + ai_pending 轮询）
- POST /topic-projects/{id}/proposal        立项书（结果存回项目）
- POST /topic-projects/{id}/journal         期刊适配（结果存回项目）

AI 长任务一律走 spawn_background_task + project.ai_pending 标记：
前端轮询项目详情直到 ai_pending 清空；失败时 ai_error 携带原因。
"""
import asyncio
import json
import logging
import re
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select as sa_select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.models import TopicProject, ProjectPaper, Paper
from app.routers.deps import (
    resolve_working_model,
    verify_token, _parse_json_list, _isoformat_utc,
    _get_ai_client, _resolve_model_provider, _get_default_model,
)
from app.routers.topic import _retrieve_similar_papers, _generate_proposal_content, _project_out
from app.routers.producer import _suggest_journal_content
from app.skills import method_playbook
from app.skills import lit_review as lit_review_skill

logger = logging.getLogger(__name__)
router = APIRouter()

LOCAL_USER = "local"


def _uid_from(request: Request) -> str:
    return (request.headers.get("x-user-id") if request else None) or LOCAL_USER


async def _load_project(db: AsyncSession, project_id: int, uid: str) -> TopicProject:
    p = await db.get(TopicProject, project_id)
    if not p or p.user_id not in (uid, LOCAL_USER):
        raise HTTPException(status_code=404, detail="Project not found")
    return p


def _paper_entry(pp: ProjectPaper, paper: Paper) -> dict:
    """ProjectPaper + Paper -> 文献集条目。"""
    authors = paper.authors if isinstance(paper.authors, list) else _parse_json_list(paper.authors)
    return {
        "id": pp.id,
        "paper_id": pp.paper_id,
        "similarity": round(float(pp.similarity), 4) if pp.similarity is not None else None,
        "read_status": pp.read_status or "to_read",
        "note": pp.note,
        "title": paper.title,
        "journal": paper.journal_name,
        "authors": authors or [],
        "published_at": str(paper.published_at)[:10] if paper.published_at else None,
        "keywords": (paper.keywords_cn or [])[:8],
        "abstract": (paper.abstract or "")[:500],
    }


async def _load_project_papers(db: AsyncSession, project_id: int, uid: str) -> List[dict]:
    """按相似度降序加载项目文献集（join Paper 补标题/期刊/摘要等）。"""
    rows = await db.execute(
        sa_select(ProjectPaper, Paper)
        .join(Paper, Paper.id == ProjectPaper.paper_id)
        .where(ProjectPaper.project_id == project_id, ProjectPaper.user_id == uid)
        .order_by(sa_func.coalesce(ProjectPaper.similarity, 0).desc())
    )
    return [_paper_entry(pp, paper) for pp, paper in rows.all()]


def _build_papers_text(papers: List[dict], limit: int = 15) -> str:
    """文献集 -> 编号文本（供 LLM prompt，编号 [n] 与前端引用对齐）。"""
    if not papers:
        return ""
    lines = []
    for i, x in enumerate(papers[:limit], start=1):
        lines.append(
            f"[{i}] {x['title']}（{x['journal'] or '未知'}，{x['published_at'] or '?'}）"
            f"关键词: {', '.join(x['keywords'][:5]) or '无'} | 摘要: {x['abstract'] or '无'}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------- 项目详情

class ProjectDetailOut(BaseModel):
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
    validation_report: Optional[str] = None
    validation_evidence: Optional[dict] = None
    search_keywords: Optional[list] = None
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
    papers: list = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@router.get("/topic-projects/{project_id}", response_model=ProjectDetailOut)
async def get_project(
    project_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """项目详情：全字段 + 文献集。前端各步骤的轮询都打这里（含 ai_pending 状态）。"""
    uid = _uid_from(request)
    p = await _load_project(db, project_id, uid)
    papers = await _load_project_papers(db, project_id, p.user_id)
    out = _project_out(p)
    out["ai_error"] = p.ai_error
    out["papers"] = papers
    return out


@router.get("/topic-projects/{project_id}/status")
async def get_project_status(
    project_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """轻量项目状态：AI 长任务执行期间前端高频轮询打这里。

    只返回 id/status/ai_pending/ai_error/updated_at，不携带
    literature_review/proposal/overview 等大段 AI 文本，避免每次轮询全量序列化。
    """
    uid = _uid_from(request)
    p = await _load_project(db, project_id, uid)
    return {
        "id": p.id,
        "status": p.status,
        "ai_pending": p.ai_pending,
        "ai_error": p.ai_error,
        "updated_at": _isoformat_utc(p.updated_at),
    }


# ---------------------------------------------------------------- 文献集

class PaperAddRequest(BaseModel):
    paper_id: str
    similarity: Optional[float] = None


class PaperPatchRequest(BaseModel):
    read_status: Optional[str] = None    # to_read | reading | read
    note: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    limit: int = 12


@router.get("/topic-projects/{project_id}/papers")
async def list_project_papers(
    project_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    uid = _uid_from(request)
    await _load_project(db, project_id, uid)
    return await _load_project_papers(db, project_id, uid)


@router.post("/topic-projects/{project_id}/papers", status_code=201)
async def add_project_paper(
    project_id: int,
    body: PaperAddRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    uid = _uid_from(request)
    p = await _load_project(db, project_id, uid)
    paper_id = (body.paper_id or "").strip()
    if not paper_id:
        raise HTTPException(status_code=400, detail="paper_id is required")
    exists = await db.get(Paper, paper_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Paper not found")
    try:
        pp = ProjectPaper(
            user_id=p.user_id, project_id=p.id,
            paper_id=paper_id, similarity=body.similarity,
        )
        db.add(pp)
        await db.commit()
        await db.refresh(pp)
        paper = await db.get(Paper, paper_id)
        return _paper_entry(pp, paper)
    except Exception as e:
        await db.rollback()
        logger.warning(f"add paper {paper_id} to project {project_id} failed: {e}")
        raise HTTPException(status_code=409, detail="该论文已在文献集中")


@router.post("/topic-projects/{project_id}/recall-papers")
async def recall_project_papers(
    project_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """按选题懒召回 top-10 论文并入文献集（Step3 首次进入时调用）。

    创建项目时不再同步召回（见 create_topic_project），初始文献在这里按需生成。
    已在该项目文献集内的论文自动去重跳过；返回本次新增数量。
    """
    uid = _uid_from(request)
    p = await _load_project(db, project_id, uid)
    try:
        briefs, _mode = await _retrieve_similar_papers(db, p.title or "", k=10)
        existing = set(
            (await db.execute(
                sa_select(ProjectPaper.paper_id).where(ProjectPaper.project_id == p.id)
            )).scalars().all()
        )
        n = 0
        for b in briefs:
            pid = str(b["id"])
            if pid in existing:
                continue
            existing.add(pid)
            db.add(ProjectPaper(
                user_id=p.user_id, project_id=p.id,
                paper_id=pid, similarity=b.get("similarity"),
            ))
            n += 1
        await db.commit()
        return {"recalled": n}
    except Exception as e:
        await db.rollback()
        logger.warning(f"recall papers for project {project_id} failed: {e}")
        return {"recalled": 0}


@router.patch("/topic-projects/{project_id}/papers/{paper_id}")
async def update_project_paper(
    project_id: int,
    paper_id: str,
    body: PaperPatchRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    uid = _uid_from(request)
    p = await _load_project(db, project_id, uid)
    pp = (
        await db.execute(
            sa_select(ProjectPaper)
            .where(ProjectPaper.project_id == p.id, ProjectPaper.paper_id == paper_id)
        )
    ).scalar_one_or_none()
    if not pp:
        raise HTTPException(status_code=404, detail="Paper not in project")
    if body.read_status is not None:
        if body.read_status not in ("to_read", "reading", "read"):
            raise HTTPException(status_code=400, detail="read_status must be to_read/reading/read")
        pp.read_status = body.read_status
    if body.note is not None:
        pp.note = body.note
    await db.commit()
    await db.refresh(pp)
    paper = await db.get(Paper, pp.paper_id)
    return _paper_entry(pp, paper)


@router.delete("/topic-projects/{project_id}/papers/{paper_id}", status_code=204)
async def delete_project_paper(
    project_id: int,
    paper_id: str,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    uid = _uid_from(request)
    p = await _load_project(db, project_id, uid)
    pp = (
        await db.execute(
            sa_select(ProjectPaper)
            .where(ProjectPaper.project_id == p.id, ProjectPaper.paper_id == paper_id)
        )
    ).scalar_one_or_none()
    if not pp:
        raise HTTPException(status_code=404, detail="Paper not in project")
    await db.delete(pp)
    await db.commit()


@router.post("/topic-projects/{project_id}/search-papers")
async def search_project_papers(
    project_id: int,
    body: SearchRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """检索候选论文（embedding 召回，带是否已在文献集标记）。"""
    uid = _uid_from(request)
    p = await _load_project(db, project_id, uid)
    query = (body.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    k = min(max(int(body.limit or 12), 1), 30)
    papers, mode = await _retrieve_similar_papers(db, query, k=k)
    existing = set(
        (await db.execute(
            sa_select(ProjectPaper.paper_id).where(ProjectPaper.project_id == p.id)
        )).scalars().all()
    )
    out = []
    for b in papers:
        out.append({
            "id": b["id"],
            "title": b["title"],
            "abstract": (b.get("abstract") or "")[:200],
            "journal": b.get("journal_name"),
            "source": b.get("source"),
            "published_at": b.get("published_at"),
            "keywords": b.get("keywords", [])[:6],
            "similarity": b.get("similarity"),
            "in_project": str(b["id"]) in existing,
        })
    return {"mode": mode, "count": len(out), "papers": out}


class RecommendRequest(BaseModel):
    limit: int = 10
    paper_id: Optional[str] = None   # 传了则只以该篇文献为种子召回（文献管理「相似论文」）


@router.post("/topic-projects/{project_id}/recommend-papers")
async def recommend_project_papers(
    project_id: int,
    body: Optional[RecommendRequest] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """相关文献推荐：基于「选题方向 + 参考文献」召回相关论文，供用户决定是否加入引用。

    不传 paper_id（聚合推荐）：
      - 选题方向召回：以项目选题（title/source_ref）embedding 检索相关论文；
      - 参考文献召回：以文献集前 5 篇为种子，从 PaperSimilarity 表取相似论文；
      - 两者合并去重（同篇取最大相似度），排除已在文献集的，按相似度排序；
      - 文献集为空时退化为纯选题方向召回。
    传 paper_id（须在文献集内）：只以该篇为种子召回（文献管理「相似论文」展开用）。

    每篇带 via_title：参考文献召回为引出它的项目文献标题，选题方向召回的为 None
    （前端显示「基于选题方向」）。
    """
    uid = _uid_from(request)
    p = await _load_project(db, project_id, uid)
    papers = await _load_project_papers(db, project_id, p.user_id)
    paper_id = (body.paper_id or "").strip() if body else ""
    limit = min(max(int(body.limit) if body else 10, 1), 30)  # 注意：limit=0 也要钳到 1，不能用 `body.limit` 真值判断
    in_project = {x["paper_id"] for x in papers}

    from app.crud import PaperSimilarityCRUD

    best: dict = {}  # paper_id -> {"similarity": float, "via_title": str|None}

    def _add(pid: str, sim: float, via_title: Optional[str]) -> None:
        sim = float(sim or 0)
        cur = best.get(pid)
        if cur is None or sim > cur["similarity"]:
            best[pid] = {"similarity": sim, "via_title": via_title}

    # ---- 单篇「相似论文」：只以该篇文献为种子 ----
    if paper_id:
        if paper_id not in in_project:
            return {"mode": "no_results", "count": 0, "papers": []}
        seed = next((x for x in papers if x["paper_id"] == paper_id), None)
        if not seed:
            return {"mode": "no_results", "count": 0, "papers": []}
        similar_papers, score_map = await PaperSimilarityCRUD.get_similar_papers_with_scores(
            db, seed["paper_id"], limit=8
        )
        for sp in similar_papers:
            if sp.id in in_project:
                continue
            _add(sp.id, score_map.get(sp.id, 0), seed["title"])
        mode = "similarity"
    else:
        # ---- 聚合推荐：选题方向 + 参考文献 ----
        query = (p.title or "").strip() or (p.source_ref or p.source_gap or "").strip()
        # (a) 选题方向召回（via_title=None → 前端显示「基于选题方向」）
        topic_papers, _tmode = await _retrieve_similar_papers(db, query, k=10)
        for b in topic_papers:
            pid = b["id"]
            if pid in in_project:
                continue
            _add(pid, b.get("similarity"), None)
        # (b) 参考文献相似召回（无文献集时跳过，退化为纯方向推荐）
        if papers:
            for s in papers[:5]:
                similar_papers, score_map = await PaperSimilarityCRUD.get_similar_papers_with_scores(
                    db, s["paper_id"], limit=8
                )
                for sp in similar_papers:
                    if sp.id in in_project:
                        continue
                    _add(sp.id, score_map.get(sp.id, 0), s["title"])
        mode = "similarity" if any(v["via_title"] for v in best.values()) else "topic"

    if not best:
        return {"mode": "no_results", "count": 0, "papers": []}

    ranked = sorted(best.items(), key=lambda kv: kv[1]["similarity"], reverse=True)[:limit]
    result = await db.execute(
        sa_select(Paper).where(Paper.id.in_([pid for pid, _ in ranked]))
    )
    paper_by_id = {paper.id: paper for paper in result.scalars().all()}

    out = []
    for pid, info in ranked:
        paper = paper_by_id.get(pid)
        if not paper:
            continue
        out.append({
            "id": paper.id,
            "title": paper.title,
            "abstract": (paper.abstract or "")[:200],
            "journal": paper.journal_name,
            "source": paper.source,
            "published_at": str(paper.published_at)[:10] if paper.published_at else None,
            "keywords": (paper.keywords_cn or [])[:6],
            "similarity": round(float(info["similarity"]), 4),
            "via_title": info["via_title"],
            "in_project": False,
        })
    return {"mode": mode, "count": len(out), "papers": out}


# ---------------------------------------------------------------- 统一 AI 操作

_AI_ACTIONS = {"generate_topics", "overview", "data_insights", "literature_review"}


class AIActionRequest(BaseModel):
    action: str
    idea_text: Optional[str] = None   # generate_topics 专用：一句话想法
    model: Optional[str] = None       # 数据与方法等动作的模型覆盖（'provider/bare' 或裸模型名）


@router.post("/topic-projects/{project_id}/ai")
async def run_ai_action(
    project_id: int,
    body: AIActionRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """统一 AI 操作：置 ai_pending 后后台执行，前端轮询项目详情等待完成。"""
    uid = _uid_from(request)
    p = await _load_project(db, project_id, uid)
    action = (body.action or "").strip()
    if action not in _AI_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown action, must be one of {sorted(_AI_ACTIONS)}")
    if p.ai_pending:
        raise HTTPException(status_code=409, detail=f"已有任务「{p.ai_pending}」正在执行")
    p.ai_pending = action
    p.ai_error = None
    await db.commit()
    from app.main import spawn_background_task
    spawn_background_task(_run_ai_action(project_id, action, idea_text=body.idea_text, model=body.model))
    return {"status": "started", "action": action}


def _extract_json(text: str):
    """从 LLM 输出里稳健提取 JSON（容忍 markdown 代码块围栏、前后杂讯与嵌套结构）。

    策略：先去围栏，再尝试整段解析；失败则用括号配对找最外层 {...} 或 [...]。
    """
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    # 括号配对：找到第一个开括号后按深度匹配最外层闭合，跳过被括号包裹的内层
    for opener, closer in (("{", "}"), ("[", "]")):
        start = t.find(opener)
        if start < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(t)):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[start:i + 1])
                    except Exception:
                        break
    logger.warning("workbench _extract_json 解析失败，原始输出前 200 字符: %r", (text or "")[:200])
    raise ValueError("无法从 LLM 输出解析 JSON")


async def _llm_json(messages: list, max_tokens: int = 4096, temperature: float = 0.4, model: Optional[str] = None):
    """非流式 LLM 调用并解析 JSON。

    model：显式模型覆盖（Step4 模型设定）；为空时按 resolve_working_model 优先级
    （显式 > 全局 default_model > 首个可用候选）解析，保证 bare_model 非空。
    max_tokens 默认 4096：推理模型的 token 预算会被 reasoning_content 大量占用，
    过小会导致 content 为空、finish_reason=length 而解析失败。
    """
    client, provider, bare_model = resolve_working_model(model)
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=bare_model, messages=messages,
        max_tokens=max_tokens, temperature=temperature,
    )
    return _extract_json(response.choices[0].message.content or "")


async def _run_ai_action(project_id: int, action: str, idea_text: Optional[str] = None, model: Optional[str] = None):
    async with AsyncSessionLocal() as db:
        p = await db.get(TopicProject, project_id)
        if not p or p.ai_pending != action:
            return  # 项目已删或任务已被替换
        try:
            if action == "generate_topics":
                p.generated_topics = await _ai_generate_topics(db, p, idea_text)
            elif action == "overview":
                p.overview = await _ai_overview(db, p)
            elif action == "data_insights":
                p.data_insights = await _ai_data_insights(db, p, model=model)
            elif action == "literature_review":
                p.literature_review = await _ai_literature_review(db, p)
            p.ai_pending = None
            await db.commit()
            logger.info(f"workbench ai '{action}' done for project {project_id}")
        except Exception as e:
            logger.error(f"workbench ai '{action}' failed for project {project_id}: {e}")
            p.ai_pending = None
            p.ai_error = str(e)[:500]
            await db.commit()


async def _ai_generate_topics(db: AsyncSession, p: TopicProject, idea_text: Optional[str]) -> list:
    """把项目来源/一句话想法打磨成 3 个具体可研究选题（JSON 数组）。"""
    query = (idea_text or p.source_ref or p.title or "").strip()
    if not query:
        query = p.title
    papers, _mode = await _retrieve_similar_papers(db, query, k=8)
    papers_text = "\n".join([
        f"[{i + 1}] {b['title']}（{b.get('journal_name') or b.get('source') or '未知'}，"
        f"{str(b.get('published_at'))[:10] if b.get('published_at') else '?'}）"
        f"关键词: {', '.join(b.get('keywords', [])[:5]) or '无'} | 摘要: {(b.get('abstract') or '')[:200]}"
        for i, b in enumerate(papers)
    ]) or "（库内无相关论文）"

    system_prompt = f"""你是学术选题顾问。请把用户的初步想法打磨成 3 个具体可研究、可发表的学术选题。
用户想法/选题背景：{query}
库内相关论文（供参考，避免与已有研究重复）：
{papers_text}

输出 JSON 对象，格式：
{{"topics": [
  {{"title": "具体题目", "research_questions": ["研究问题1", "研究问题2"], "hypothesis": "初步假设", "why": "为什么值得做/创新点"}}
]}}

要求：
1. title 必须具体——含研究对象、作用机制、具体场景或数据（如「数字普惠金融对小微企业创新的影响：基于某省数据的证据」），
   禁止「交叉研究：A与B的结合」这类模板题目
2. 3 个题目要有区分度（不同机制/不同对象/不同数据）
3. research_questions 1-3 个，具体可检验"""

    data = await _llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请生成 3 个具体选题。"},
        ],
        max_tokens=4096, temperature=0.5,
    )
    topics = data.get("topics") if isinstance(data, dict) else data
    if not isinstance(topics, list):
        raise ValueError("generate_topics 返回格式异常")
    return topics[:3]


async def _ai_overview(db: AsyncSession, p: TopicProject) -> str:
    """已有研究盘点：文献集逐篇 方法/数据/结论 + 共识/争议/空白（markdown）。"""
    papers = await _load_project_papers(db, p.id, p.user_id)
    papers_text = _build_papers_text(papers, limit=15)
    if not papers_text:
        return "（项目文献集为空。请先在「文献管理」中添加论文，或在验证步骤召回。)"
    system_prompt = f"""你是一位严格的学术评审。以下是论文库中与该选题最相关的论文（编号对应项目文献集）：
选题：{p.title}
相关论文：
{papers_text}

请输出一份「已有研究盘点」（markdown），包含：
## 谁做了什么
逐篇列出：[n] 一句话概括其核心贡献
## 用的什么方法
汇总这些研究的主流方法（计量模型/识别策略）
## 用的什么数据
列出出现的数据库/数据来源（如 CFPS/CHFS/上市公司数据/投入产出表等）
## 结论共识与争议
哪些结论一致，哪些存在分歧
## 尚待填补的空白
基于以上盘点，指出可差异化切入的具体空白（2-3 个）

要求：引用必须带 [n] 编号，结论必须有文献支撑；信息不足就明说，不要编造。"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "请输出已有研究盘点。"},
    ]
    client, provider, bare_model = resolve_working_model(None)
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=bare_model, messages=messages, max_tokens=3072, temperature=0.4,
    )
    return (response.choices[0].message.content or "").strip()


async def _ai_data_insights(db: AsyncSession, p: TopicProject, model: Optional[str] = None) -> dict:
    """数据与方法线索：从文献集提取数据来源与研究方法（JSON）+ 命中的方法手册条目。"""
    papers = await _load_project_papers(db, p.id, p.user_id)
    papers_text = _build_papers_text(papers, limit=15)

    # 方法手册匹配（Script 侧确定性匹配）：标题 + 检索关键词 + 灵感快照关键词
    kw: list = [k for k in (p.search_keywords or []) if k]
    for g in (p.generated_topics or []):
        if isinstance(g, dict):
            kw.extend(g.get("keywords") or [])
    matched = method_playbook.match_project(p.title, kw)
    playbook_block = method_playbook.to_prompt_block(matched)

    if not papers_text:
        return {
            "data_sources": [],
            "methods": [],
            "advice": "项目文献集为空，无法提取数据与方法线索。",
            "matched_methods": [e["id"] for e in matched],
        }

    system_prompt = f"""以下是该选题相关论文的摘要与关键词。请提取这些研究所用的数据来源与研究方法。
选题：{p.title}
论文列表：
{papers_text}

{playbook_block}

输出 JSON 对象：
{{"data_sources": [{{"name": "数据库/数据源名称", "papers": ["编号1"], "usage": "用于什么研究"}}],
  "methods": [{{"name": "方法名称", "papers": ["编号"], "note": "要点"}}],
  "advice": "结合常见公开数据库给该选题的数据可得性建议（3-5 句，必须非空）"}}

要求：
1. papers 数组里的编号对应论文列表的 [n]；多个编号如 ["1","3"]
2. 数据来源若摘要里没有明确点名（如只说"上市公司数据""省级面板"），也要推断出具体可获得的库（CSMAR/Wind/CFPS/CHFS/投入产出表等）并在 usage 标注「推断」
3. data_sources 与 methods 尽量非空；完全没有依据时才给空数组
4. 若上方方法手册命中了与选题相关的条目，methods 应纳入对应方法并在 note 里引用条目名"""
    data = await _llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请提取数据与方法线索。"},
        ],
        max_tokens=4096, temperature=0.3, model=model,
    )
    if isinstance(data, dict):
        # matched_methods 由 Script 侧确定性产出，不依赖 LLM 是否遵守
        data["matched_methods"] = [e["id"] for e in matched]
    return data


async def _ai_literature_review(db: AsyncSession, p: TopicProject) -> str:
    """文献综述：基于项目文献集生成结构化综述（lit_review 技能统一五节契约）。"""
    papers = await _load_project_papers(db, p.id, p.user_id)
    papers_text = _build_papers_text(papers, limit=20)
    if not papers_text:
        return "（项目文献集为空。请先在「文献管理」中添加论文，或在验证步骤召回。)"
    messages = lit_review_skill.build_messages(
        topic=p.title,
        papers_text=papers_text,
        paper_count=len(papers[:20]),
        context_note="项目文献集",
    )
    client, provider, bare_model = resolve_working_model(None)
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=bare_model, messages=messages, max_tokens=4096, temperature=0.4,
    )
    return (response.choices[0].message.content or "").strip()


# ---------------------------------------------------------------- 方法手册（skills/method_playbook）

@router.get("/skills/method-playbook")
async def get_method_playbook():
    """方法手册全量条目（系统预置静态文本；前端按 data_insights.matched_methods 渲染命中卡）。"""
    return {"entries": method_playbook.PLAYBOOK}


# ---------------------------------------------------------------- 立项书 / 期刊适配（结果存回项目）

class ProjectProposalRequest(BaseModel):
    validation_report: Optional[str] = None


@router.post("/topic-projects/{project_id}/proposal")
async def project_proposal(
    project_id: int,
    body: ProjectProposalRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """生成立项书并存入项目（复用 topic-validator/proposal 核心逻辑）。"""
    uid = _uid_from(request)
    p = await _load_project(db, project_id, uid)
    content, model_name = await _generate_proposal_content(
        db, p.title, body.validation_report or p.validation_report
    )
    p.proposal = content
    # 立项书请求携带验证报告时顺带沉淀（兼容跳过 onPatch 的调用路径）
    if body.validation_report and not p.validation_report:
        p.validation_report = body.validation_report
    await db.commit()
    return {"proposal": content, "model": model_name}


@router.post("/topic-projects/{project_id}/journal")
async def project_journal(
    project_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """期刊适配并存入项目（复用 producer/journal 核心逻辑，综述作摘要上下文）。"""
    uid = _uid_from(request)
    p = await _load_project(db, project_id, uid)
    rec, suggestions, ai_used = await _suggest_journal_content(
        db, p.title, p.literature_review or None
    )
    p.journal_advice = rec
    await db.commit()
    return {"recommendations": rec, "suggestions": suggestions, "ai_used": ai_used}


# ---------------------------------------------------------------- 灵感推荐

# 个性化灵感推荐缓存（按用户，TTL 10 分钟；结果无副作用可安全共享）
_RECOMMEND_TTL = 600
_recommend_cache: dict[str, tuple[float, list]] = {}


@router.post("/topic-projects/recommend")
async def recommend_topics(
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """个性化选题灵感推荐：基于 关注子领域/关键词 + 最近阅读 + 库内研究空白，
    LLM 生成 4-6 个贴合用户的具体选题方向。结果按用户缓存 10 分钟。"""
    uid = _uid_from(request)
    now = time.time()
    hit = _recommend_cache.get(uid)
    if hit and now - hit[0] < _RECOMMEND_TTL:
        return {"recommendations": hit[1], "cached": True}

    # ---- 用户画像 ----
    from app.models import FollowedSubfield, FollowedKeyword, ReadingHistory, TopicTrend
    sf = (
        await db.execute(sa_select(FollowedSubfield.subfield).where(FollowedSubfield.user_id == uid))
    ).scalars().all()
    kw = (
        await db.execute(sa_select(FollowedKeyword.keyword).where(FollowedKeyword.user_id == uid))
    ).scalars().all()
    recent = (
        await db.execute(
            sa_select(Paper.title)
            .join(ReadingHistory, ReadingHistory.paper_id == Paper.id)
            .where(ReadingHistory.user_id == uid)
            .order_by(ReadingHistory.read_at.desc())
            .limit(6)
        )
    ).scalars().all()

    # 库内研究空白 + 热点（作为机会信号）
    from app.stats import compute_keyword_gaps
    try:
        gaps = await compute_keyword_gaps(db, limit=6)
        gap_text = "；".join(f"{g['source']}×{g['target']}" for g in gaps)
    except Exception:
        gap_text = ""
    hot_rows = (
        await db.execute(sa_select(TopicTrend.topic, sa_func.sum(TopicTrend.paper_count))
                         .group_by(TopicTrend.topic).order_by(sa_func.sum(TopicTrend.paper_count).desc()).limit(6))
    ).all()
    hot_text = "；".join(f"{t}({int(c or 0)}篇)" for t, c in hot_rows)

    profile_lines = []
    if sf:
        profile_lines.append("关注的子领域：" + "、".join(sf))
    if kw:
        profile_lines.append("关注的关键词：" + "、".join(kw))
    if recent:
        profile_lines.append("最近在读：" + "；".join(recent))
    if gap_text:
        profile_lines.append("库内研究空白：" + gap_text)
    if hot_text:
        profile_lines.append("库内热点方向：" + hot_text)

    system_prompt = f"""你是学术选题顾问，为经济管理研究者做个性化选题推荐。
用户画像：
{chr(10).join(profile_lines) or "（暂无画像，给出当前经济学研究的高价值通用方向）"}

请推荐 4-6 个具体的、可发表的选题方向。输出 JSON 数组（不要 markdown 代码块），每个元素：
{{"title": "具体选题题目", "why": "为什么适合这个用户/为什么值得做（结合画像）", "angle": "切入角度或数据方案"}}

要求：
1. title 必须具体——含研究对象、作用机制、场景或数据（如「数字普惠金融对小微企业创新的影响：基于某数据的证据」），禁止模板题目
2. 优先贴合用户画像（关注子领域/关键词/在读文献），再结合库内空白与热点机会
3. 角度有区分度（不同机制/对象/数据）"""
    data = await _llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请为我推荐选题方向。"},
        ],
        max_tokens=4096, temperature=0.6,
    )
    recs = data if isinstance(data, list) else (data.get("recommendations", []) if isinstance(data, dict) else [])
    if not isinstance(recs, list):
        raise ValueError("recommend 返回格式异常")
    recs = recs[:6]
    _recommend_cache[uid] = (now, recs)
    return {"recommendations": recs, "cached": False}
