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
    rows = await db.execute(
        sa_select(AssistantMessage.role, AssistantMessage.content)
        .where(AssistantMessage.session_id == session_id)
        .order_by(AssistantMessage.id)
    )
    return [{"role": r[0], "content": r[1]} for r in rows.all()]


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
    messages = await _load_messages(db, session_id)
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
        db.add(AssistantMessage(session_id=session_id, role=role, content=content))
        # 用首条用户消息生成会话标题
        if role == "user" and not session.title:
            session.title = content[:50]
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

    system_prompt = _build_system_prompt(session.page, paper, session.context_text)
    enabled = body.agent_enabled if body.agent_enabled is not None else settings.agent_enabled
    if enabled:
        system_prompt += (
            "\n\n## 工具使用规则（强制）\n"
            "只要问题涉及论文库数据——热点/趋势/相关论文/研究现状/文献数量/某个方向进展/作者，"
            "**必须先调用工具检索论文库，再基于检索结果回答，禁止用常识编造库内统计数字**。\n"
            "- `trending_topics`：热点/热门趋势/升温方向（返回论文库真实统计，保持其排序）\n"
            "- `search_papers`：按关键词/期刊/年份检索（返回标题/期刊/关键词/评分）\n"
            "- `retrieve_context`：语义召回最相关的论文（返回标题/摘要/[编号]，适合「研究到哪了」）\n"
            "- `paper_trend`：关键词逐年发文趋势；`author_papers`：按作者查论文；"
            "`keyword_gaps`：研究空白组合；`subfield_distribution`：子领域分布\n\n"
            "引用具体论文时用 [编号] 标注（如 [1][3]）。检索结果为空或与问题无关时如实说明；"
            "严禁未检索就给出「XX方向是热点」之类的断言。"
        )
    history = await _load_messages(db, session.id)
    new_msgs = [m for m in (body.messages or []) if str(m.get("role") or "") and str(m.get("content") or "").strip()]
    messages = [{"role": "system", "content": system_prompt}] + history + new_msgs

    try:
        provider, bare_model = _resolve_model_provider(None)
        client, provider = _get_ai_client(provider)
    except HTTPException:
        raise HTTPException(status_code=503, detail="AI API key not configured")
    if not bare_model:
        bare_model = _get_default_model(provider)

    return _stream_agent_chat_response(
        client, provider, messages, model=bare_model, surface="assistant_chat",
        agent_enabled=enabled,
    )
