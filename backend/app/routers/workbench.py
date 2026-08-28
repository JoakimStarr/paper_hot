"""研究工作台（Workbench）：项目详情 / 文献集 / 统一 AI 操作。

选题中心重构的产物：以 TopicProject 为项目核心，串联
选题定义 → 验证 → 文献管理 → 数据/方法 → 写作输出 五步向导。

- GET  /topic-projects/{id}                 项目详情（全字段 + 文献集）
- GET  /topic-projects/{id}/papers          文献集列表
- POST /topic-projects/{id}/papers          加入论文
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
    verify_token, _parse_json_list, _isoformat_utc,
    _get_ai_client, _resolve_model_provider, _get_default_model,
)
from app.routers.topic import _retrieve_similar_papers, _generate_proposal_content, _project_out
from app.routers.producer import _suggest_journal_content

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


# ---------------------------------------------------------------- 统一 AI 操作

_AI_ACTIONS = {"generate_topics", "overview", "data_insights", "literature_review"}


class AIActionRequest(BaseModel):
    action: str
    idea_text: Optional[str] = None   # generate_topics 专用：一句话想法


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
    spawn_background_task(_run_ai_action(project_id, action, idea_text=body.idea_text))
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


async def _llm_json(messages: list, max_tokens: int = 4096, temperature: float = 0.4):
    """非流式 LLM 调用并解析 JSON（默认模型）。

    max_tokens 默认 4096：当前默认模型为推理模型（glm-5.2），
    token 预算会被 reasoning_content 大量占用，过小会导致 content 为空、
    finish_reason=length 而解析失败。
    """
    provider, bare_model = _resolve_model_provider(None)
    client, provider = _get_ai_client(provider)
    if not bare_model:
        bare_model = _get_default_model(provider)
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=bare_model, messages=messages,
        max_tokens=max_tokens, temperature=temperature,
    )
    return _extract_json(response.choices[0].message.content or "")


async def _run_ai_action(project_id: int, action: str, idea_text: Optional[str] = None):
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
                p.data_insights = await _ai_data_insights(db, p)
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
    provider, bare_model = _resolve_model_provider(None)
    client, provider = _get_ai_client(provider)
    if not bare_model:
        bare_model = _get_default_model(provider)
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=bare_model, messages=messages, max_tokens=3072, temperature=0.4,
    )
    return (response.choices[0].message.content or "").strip()


async def _ai_data_insights(db: AsyncSession, p: TopicProject) -> dict:
    """数据与方法线索：从文献集提取数据来源与研究方法（JSON）。"""
    papers = await _load_project_papers(db, p.id, p.user_id)
    papers_text = _build_papers_text(papers, limit=15)
    if not papers_text:
        return {"data_sources": [], "methods": [], "advice": "项目文献集为空，无法提取数据与方法线索。"}

    system_prompt = f"""以下是该选题相关论文的摘要与关键词。请提取这些研究所用的数据来源与研究方法。
选题：{p.title}
论文列表：
{papers_text}

输出 JSON 对象：
{{"data_sources": [{{"name": "数据库/数据源名称", "papers": ["编号1"], "usage": "用于什么研究"}}],
  "methods": [{{"name": "方法名称", "papers": ["编号"], "note": "要点"}}],
  "advice": "结合常见公开数据库给该选题的数据可得性建议（3-5 句，必须非空）"}}

要求：
1. papers 数组里的编号对应论文列表的 [n]；多个编号如 ["1","3"]
2. 数据来源若摘要里没有明确点名（如只说"上市公司数据""省级面板"），也要推断出具体可获得的库（CSMAR/Wind/CFPS/CHFS/投入产出表等）并在 usage 标注「推断」
3. data_sources 与 methods 尽量非空；完全没有依据时才给空数组"""
    return await _llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请提取数据与方法线索。"},
        ],
        max_tokens=4096, temperature=0.3,
    )


async def _ai_literature_review(db: AsyncSession, p: TopicProject) -> str:
    """文献综述：基于项目文献集生成结构化综述（markdown，复用综述结构）。"""
    papers = await _load_project_papers(db, p.id, p.user_id)
    papers_text = _build_papers_text(papers, limit=20)
    if not papers_text:
        return "（项目文献集为空。请先在「文献管理」中添加论文，或在验证步骤召回。)"
    system_prompt = f"""你是一位学术文献综述专家。请基于项目收集的论文，为选题生成一份结构化文献综述。
选题：{p.title}
相关论文（{len(papers[:20])} 篇，方括号为编号，按相关度排序）：
{papers_text}

请用 markdown 输出，包含：
## 研究脉络
梳理该方向从早期到近期的研究演进，说明主线脉络与发展阶段。
## 方法演进
文献采用的研究方法从简单到复杂的演进路径（概念界定、计量方法、数据来源等）。
## 争议点
现有文献存在哪些分歧与争议（结论冲突、方法派别、测度差异等）。
## 研究空白
基于上述脉络，指出尚待填补的空隙。
## 可进一步研究
给出 2-3 个可行切入点。

要求：引用文献用 [编号] 标注，结论必须有文献支撑；每个部分 2-4 段。"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "请生成这份文献综述。"},
    ]
    provider, bare_model = _resolve_model_provider(None)
    client, provider = _get_ai_client(provider)
    if not bare_model:
        bare_model = _get_default_model(provider)
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=bare_model, messages=messages, max_tokens=4096, temperature=0.4,
    )
    return (response.choices[0].message.content or "").strip()


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
