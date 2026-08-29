"""全局 AI 悬浮助手（浮窗追问）：跨页面通用对话 + 会话管理 + 历史记录。

- 所有页面底部悬浮按钮，点击弹开对话窗；回答贴合当前页面上下文。
- 会话管理：每个对话一个 assistant_session，消息存 assistant_messages；
  支持历史列表 / 详情 / 删除，跨页面、跨浏览器会话保留。
- Agent 工具检索遵循 AGENT_ENABLED 开关：关闭时退化为普通对话（默认）。

接口：
  POST /assistant/sessions                    创建会话
  POST /assistant/chat                        流式对话（SSE，基于某会话继续）
  POST /assistant/sessions/{id}/messages      保存一轮消息（流结束后调用）
  GET  /assistant/sessions                    历史会话列表
  GET  /assistant/sessions/{id}               会话详情（含全部消息）
  DELETE /assistant/sessions/{id}             删除会话及其消息
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select as sa_select, desc as sa_desc, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.crud import PaperCRUD
from app.models import AssistantSession, AssistantMessage
from app.routers.deps import (
    verify_token, _parse_json_list, _isoformat_utc,
    _get_ai_client, _resolve_model_provider, _get_default_model,
    _stream_agent_chat_response,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# 各页面的一句话场景说明（注入 system prompt，帮助 AI 理解用户所处页面）
_PAGE_HINTS = {
    "paper": "用户正在浏览一篇论文的详情页，问题通常围绕这篇论文。",
    "trends": "用户正在查看领域热点趋势分析（研究趋势、选题机会）。",
    "topics": "用户正在使用选题中心（研究空白 / 选题验证 / 产出工作台）。",
    "search": "用户正在论文库检索页，问题通常围绕检索结果或检索策略。",
    "dashboard": "用户正在查看个人研究工作台（今日值得读 / 领域快讯 / 我的研究栈）。",
    "network": "用户正在查看论文 / 关键词 / 作者关系网络图。",
    "reading": "用户正在查看阅读历史。",
    "home": "用户正在论文发现首页。",
    "generic": "",
}

_ASSISTANT_SYSTEM = """你是一位学术论文助手，正通过全局悬浮窗为用户答疑。请结合「当前页面」上下文回答用户的问题，用中文，回答简洁、准确、有结构（可适当分点或小标题），不要冗长。若问题超出上下文范围，先诚实说明，再基于你的专业知识给出合理建议。"""


class SessionCreate(BaseModel):
    page: str = "generic"                     # paper/trends/topics/search/dashboard/network/reading/home/generic
    paper_id: Optional[str] = None
    context_text: Optional[str] = None


class ChatRequest(BaseModel):
    session_id: int
    messages: List[dict] = []                 # 本轮新增消息（通常只有一条 user）
    agent_enabled: Optional[bool] = None      # 请求级"数据库检索"开关；None 跟随全局 settings.agent_enabled
    model: Optional[str] = None               # 请求级模型（provider/model 或裸模型名）；None 用默认模型
    extra_context: Optional[str] = None       # 请求级页面补充上下文（如 network 选中节点摘要），随每次追问更新，不落库


class MessagesIn(BaseModel):
    messages: List[dict] = []                 # 需要保存的消息（[user, assistant]）


class SessionOut(BaseModel):
    id: int
    title: Optional[str] = None
    page: str = "generic"
    paper_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    message_count: int = 0


class SessionDetailOut(SessionOut):
    messages: List[dict] = []


def _uid(x_user_id: Optional[str]) -> str:
    return (x_user_id or "").strip() or "local"


def _make_title(text: str, max_len: int = 24) -> str:
    """把首条用户消息加工成会话标题：压空白、按句边界截断。"""
    t = " ".join(str(text or "").split())
    if not t:
        return ""
    for sep in ("。", "？", "！", "；", "？", "！", ". ", "? ", "! "):
        idx = t.find(sep)
        if 0 < idx < max_len:
            return t[:idx].strip()[:max_len]
    return t[:max_len]


def _build_system_prompt(page: str, paper, context_text: Optional[str]) -> str:
    parts = [_ASSISTANT_SYSTEM]
    hint = _PAGE_HINTS.get(page or "generic", "")
    if hint:
        parts.append(f"## 当前页面\n{hint}")
    if paper is not None:
        authors = ", ".join(_parse_json_list(paper.authors)) or "未知"
        keywords = ", ".join(_parse_json_list(paper.keywords_cn)) or "未知"
        parts.append(
            f"## 当前论文\n"
            f"- 标题：{paper.title}\n"
            f"- 作者：{authors}\n"
            f"- 期刊：{paper.journal_name or '未知'}\n"
            f"- 关键词：{keywords}\n"
            f"- 子领域：{paper.economics_subfield or '未知'}\n\n"
            f"## 论文摘要\n{paper.abstract or '无'}"
        )
    if context_text and context_text.strip():
        parts.append(f"## 页面补充上下文\n{context_text.strip()[:2000]}")
    return "\n\n".join(parts)


async def _load_session(db: AsyncSession, session_id: int, uid: str) -> AssistantSession:
    session = await db.get(AssistantSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id not in (uid, "local"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return session


async def _load_messages(db: AsyncSession, session_id: int) -> List[dict]:
    """加载会话历史（仅 role/content，用于拼 LLM 上下文，不含思考过程）。"""
    rows = await db.execute(
        sa_select(AssistantMessage.role, AssistantMessage.content)
        .where(AssistantMessage.session_id == session_id)
        .order_by(AssistantMessage.id)
    )
    return [{"role": r[0], "content": r[1]} for r in rows.all()]


async def _load_session_messages(db: AsyncSession, session_id: int) -> List[dict]:
    """加载会话消息（含 reasoning，供前端展示「查看思考过程」）。"""
    rows = await db.execute(
        sa_select(AssistantMessage.role, AssistantMessage.content, AssistantMessage.reasoning)
        .where(AssistantMessage.session_id == session_id)
        .order_by(AssistantMessage.id)
    )
    return [
        {"role": r[0], "content": r[1], "reasoning": r[2] or None}
        for r in rows.all()
    ]


def _session_to_out(s: AssistantSession, count: int) -> SessionOut:
    return SessionOut(
        id=s.id, title=s.title, page=s.page, paper_id=s.paper_id,
        created_at=_isoformat_utc(s.created_at), updated_at=_isoformat_utc(s.updated_at),
        message_count=count,
    )


# ---------------------------------------------------------------- 会话管理

@router.post("/assistant/sessions", response_model=SessionOut)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    uid = _uid(x_user_id)
    session = AssistantSession(
        user_id=uid,
        page=(body.page or "generic"),
        paper_id=body.paper_id,
        context_text=(body.context_text or None),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _session_to_out(session, 0)


@router.get("/assistant/sessions", response_model=List[SessionOut])
async def list_sessions(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    uid = _uid(x_user_id)
    rows = await db.execute(
        sa_select(AssistantSession)
        .where(AssistantSession.user_id == uid)
        .order_by(sa_desc(AssistantSession.updated_at))
        .limit(min(max(limit, 1), 200))
    )
    sessions = rows.scalars().all()
    counts = {r[0]: r[1] for r in (await db.execute(
        sa_select(AssistantMessage.session_id, sa_func.count())
        .where(AssistantMessage.session_id.in_([s.id for s in sessions] or [-1]))
        .group_by(AssistantMessage.session_id)
    )).all()}
    return [_session_to_out(s, counts.get(s.id, 0)) for s in sessions]


@router.get("/assistant/sessions/{session_id}", response_model=SessionDetailOut)
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    uid = _uid(x_user_id)
    session = await _load_session(db, session_id, uid)
    messages = await _load_session_messages(db, session_id)
    out = _session_to_out(session, len(messages)).model_dump()
    out["messages"] = messages
    return SessionDetailOut(**out)


@router.delete("/assistant/sessions/{session_id}")
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    uid = _uid(x_user_id)
    session = await _load_session(db, session_id, uid)
    from sqlalchemy import delete as sa_delete
    await db.execute(sa_delete(AssistantMessage).where(AssistantMessage.session_id == session_id))
    await db.delete(session)
    await db.commit()
    return {"ok": True}


@router.post("/assistant/sessions/{session_id}/messages")
async def save_messages(
    session_id: int,
    body: MessagesIn,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    uid = _uid(x_user_id)
    session = await _load_session(db, session_id, uid)
    msgs = body.messages or []
    for m in msgs:
        role = str(m.get("role") or "").strip()
        content = str(m.get("content") or "").strip()
        if not role or not content:
            continue
        reasoning = str(m.get("reasoning") or "").strip() or None
        db.add(AssistantMessage(session_id=session_id, role=role, content=content, reasoning=reasoning))
        # 用首条用户消息生成会话标题
        if role == "user" and not session.title:
            session.title = _make_title(content)
    await db.commit()
    return {"ok": True, "count": len(msgs)}


# ---------------------------------------------------------------- 流式对话

@router.post("/assistant/chat")
async def assistant_chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """基于某会话继续对话（SSE 流式）：加载会话上下文 + 历史消息 + 本轮新消息。"""
    uid = _uid(x_user_id)
    session = await _load_session(db, body.session_id, uid)

    paper = None
    if session.paper_id:
        try:
            paper = await PaperCRUD.get_paper_by_id(db, session.paper_id)
        except Exception as e:
            logger.warning(f"assistant: failed to load paper {session.paper_id}: {e}")
            paper = None

    # 请求级 extra_context 覆盖在会话级 context_text 之上（如 network 页选中节点后的结构摘要），
    # 让已存在会话无需重建也能感知最新页面状态
    merged_context = "\n\n".join(
        x for x in [session.context_text, body.extra_context] if x and x.strip()
    ).strip() or None
    system_prompt = _build_system_prompt(session.page, paper, merged_context)
    enabled = body.agent_enabled if body.agent_enabled is not None else settings.agent_enabled
    if enabled:
        # 工具行为规则保持精简：工具细节由 JSON schema 提供，提示词只约束行为，避免指令稀释
        system_prompt += (
            "\n\n## 工具使用规则\n"
            "1. 涉及论文库数据的问题（热点/趋势/相关论文/研究现状/数量/进展/作者），第一步必须调用工具检索后再回答，禁止用常识编造库内数字。\n"
            "2. 热点用 trending_topics，推荐/相关文献用 retrieve_context 或 search_papers，其余按需调用。\n"
            "3. 未调用工具就不要说「我查看了论文库/我检索了」。不检索就直接回答。\n"
            "4. 引用检索到的论文用 [编号] 标注（如 [1]）。\n"
            "5. 检索结果为空或无关时如实说明，不要编造。"
        )
    history = await _load_messages(db, session.id)
    # 长会话上下文压缩：只保留最近 _MAX_CTX 条，更早的以提示代替（避免撑爆模型上下文窗口）
    _MAX_CTX = 20
    if len(history) > _MAX_CTX:
        dropped = len(history) - _MAX_CTX
        history = history[-_MAX_CTX:]
        system_prompt += f"\n\n（注意：该会话早期有 {dropped} 条消息因过长被截断，仅保留最近 {_MAX_CTX} 条作为上下文）"
    new_msgs = [m for m in (body.messages or []) if str(m.get("role") or "") and str(m.get("content") or "").strip()]
    messages = [{"role": "system", "content": system_prompt}] + history + new_msgs

    try:
        provider, bare_model = _resolve_model_provider(body.model)
        client, provider = _get_ai_client(provider)
    except HTTPException:
        raise HTTPException(status_code=503, detail="AI API key not configured")
    if not bare_model:
        bare_model = _get_default_model(provider)

    return _stream_agent_chat_response(
        client, provider, messages, model=bare_model, surface="assistant_chat",
        agent_enabled=enabled,
    )
