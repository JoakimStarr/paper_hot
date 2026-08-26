"""个人化轻量体系（P1-10）：本地 userId + 收藏/阅读历史/关注子领域。

不引入账号体系：前端在 localStorage 生成 userId，随请求头 x-user-id 传入；
后端以该值隔离数据（缺省回退 "local"，行为与旧版一致）。

驱动：
- 收藏：替代原前端 localStorage 实现书签（换设备不丢）
- 阅读历史：已读/未读标记、"我的研究栈"
- 关注子领域：研究工作台推荐与领域快讯
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select as sa_select, delete as sa_delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Favorite, PinnedPaper, MAX_PINNED_PAPERS, HiddenPreference, ReadingHistory, FollowedSubfield, Paper
from app.routers.deps import verify_token, _paper_to_card, _isoformat_utc

logger = logging.getLogger(__name__)
router = APIRouter()


def _user_id(x_user_id: Optional[str]) -> str:
    """取值：优先请求头会话 userId；缺失回退 "local"（保持向后兼容）。"""
    return (x_user_id or "").strip() or "local"


class FollowedSubfieldsRequest(BaseModel):
    subfields: List[str]


async def _paper_ids_by_status(db: AsyncSession, user_id: str, model, limit: int = 200):
    result = await db.execute(
        sa_select(model.paper_id)
        .where(model.user_id == user_id)
        .order_by(model.id.desc())
        .limit(limit)
    )
    return [row[0] for row in result.all()]


@router.get("/personal/me")
async def get_me(
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """汇总个人数据：收藏子领域 + 已读论文数（供研究工作台与详情页初始化）。"""
    uid = _user_id(x_user_id)

    subfields = await db.execute(
        sa_select(FollowedSubfield.subfield).where(FollowedSubfield.user_id == uid)
    )
    read_count = await db.execute(
        sa_select(ReadingHistory.id).where(ReadingHistory.user_id == uid)
    )
    fav_count = await db.execute(
        sa_select(Favorite.id).where(Favorite.user_id == uid)
    )
    return {
        "user_id": uid,
        "followed_subfields": [r[0] for r in subfields.all()],
        "read_count": len(read_count.all()),
        "favorite_count": len(fav_count.all()),
    }


# ---------- 收藏 ----------

@router.get("/personal/favorites")
async def get_favorites(
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """收藏列表（论文卡片，时间倒序）。"""
    uid = _user_id(x_user_id)
    ids = await _paper_ids_by_status(db, uid, Favorite)
    if not ids:
        return {"papers": [], "total": 0}
    result = await db.execute(
        sa_select(Paper).options(
            selectinload(Paper.features),
            selectinload(Paper.scores),
        ).where(Paper.id.in_(ids))
    )
    papers = result.scalars().all()
    return {"papers": [_paper_to_card(p) for p in papers], "total": len(papers)}


class PaperIdRequest(BaseModel):
    paper_id: str


@router.post("/personal/favorites/toggle")
async def toggle_favorite(
    body: PaperIdRequest,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """切换收藏：已收藏则移除，未收藏则添加。返回 { bookmarked: bool }。"""
    uid = _user_id(x_user_id)
    pid = (body.paper_id or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="paper_id is required")
    exists = await db.execute(
        sa_select(Favorite.id).where(Favorite.user_id == uid, Favorite.paper_id == pid)
    )
    if exists.scalar_one_or_none():
        await db.execute(
            sa_delete(Favorite).where(Favorite.user_id == uid, Favorite.paper_id == pid)
        )
        await db.commit()
        return {"bookmarked": False}
    db.add(Favorite(user_id=uid, paper_id=pid))
    await db.commit()
    return {"bookmarked": True}


# ---------- 手动置顶（P2 置顶改造）----------

@router.get("/personal/pins")
async def get_pins(
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """置顶论文 id 列表（最新置顶在前），供前端渲染置顶徽章与列表置顶置序。"""
    uid = _user_id(x_user_id)
    ids = await _paper_ids_by_status(db, uid, PinnedPaper)
    return {"paper_ids": ids}


@router.post("/personal/pins/toggle")
async def toggle_pin(
    body: PaperIdRequest,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """切换手动置顶：已置顶则取消，未置顶则置顶。返回 { pinned: bool }。"""
    uid = _user_id(x_user_id)
    pid = (body.paper_id or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="paper_id is required")
    exists = await db.execute(
        sa_select(PinnedPaper.id).where(PinnedPaper.user_id == uid, PinnedPaper.paper_id == pid)
    )
    if exists.scalar_one_or_none():
        await db.execute(
            sa_delete(PinnedPaper).where(PinnedPaper.user_id == uid, PinnedPaper.paper_id == pid)
        )
        await db.commit()
        return {"pinned": False}
    # 置顶上限（MAX_PINNED_PAPERS）：已达上限时拒绝新增，避免置顶了却不排最前的静默问题
    count = await db.execute(
        sa_select(func.count()).select_from(PinnedPaper).where(PinnedPaper.user_id == uid)
    )
    if count.scalar_one() >= MAX_PINNED_PAPERS:
        raise HTTPException(status_code=400, detail="MAX_PINNED_PAPERS")
    db.add(PinnedPaper(user_id=uid, paper_id=pid))
    await db.commit()
    return {"pinned": True}


# ---------- 不感兴趣/内容屏蔽（P2）----------

class HiddenPreferenceRequest(BaseModel):
    entity_type: str  # subfield | journal | keyword | author
    entity_value: str


async def _load_hidden_preferences(db: AsyncSession, user_id: str) -> dict:
    """把某用户的屏蔽项聚合成 hidden 字典（供各列表查询过滤，全局生效）。"""
    result = await db.execute(
        sa_select(HiddenPreference.entity_type, HiddenPreference.entity_value)
        .where(HiddenPreference.user_id == user_id)
        .order_by(HiddenPreference.id.desc())
    )
    hidden: dict = {}
    for etype, evalue in result.all():
        hidden.setdefault(etype, []).append(evalue)
    return hidden


@router.get("/personal/preferences")
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """当前用户的"不感兴趣"屏蔽项列表（contrib 过滤与管理工作台渲染用）。"""
    uid = _user_id(x_user_id)
    result = await db.execute(
        sa_select(HiddenPreference.entity_type, HiddenPreference.entity_value)
        .where(HiddenPreference.user_id == uid)
        .order_by(HiddenPreference.id.desc())
    )
    items = [{"entity_type": et, "entity_value": ev} for et, ev in result.all()]
    return {"items": items}


@router.post("/personal/preferences")
async def add_preference(
    body: HiddenPreferenceRequest,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """新增一条屏蔽项（幂等：已存在则忽略）。entity_type 限定白名单。"""
    uid = _user_id(x_user_id)
    etype = (body.entity_type or "").strip()
    evalue = (body.entity_value or "").strip()
    if etype not in ("subfield", "journal", "keyword", "author"):
        raise HTTPException(status_code=400, detail="invalid entity_type")
    if not evalue:
        raise HTTPException(status_code=400, detail="entity_value is required")
    exists = await db.execute(
        sa_select(HiddenPreference.id).where(
            HiddenPreference.user_id == uid,
            HiddenPreference.entity_type == etype,
            HiddenPreference.entity_value == evalue,
        )
    )
    if not exists.scalar_one_or_none():
        db.add(HiddenPreference(user_id=uid, entity_type=etype, entity_value=evalue))
        await db.commit()
    return {"added": True}


@router.delete("/personal/preferences")
async def remove_preference(
    entity_type: str,
    entity_value: str,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """删除一条屏蔽项。"""
    uid = _user_id(x_user_id)
    await db.execute(
        sa_delete(HiddenPreference).where(
            HiddenPreference.user_id == uid,
            HiddenPreference.entity_type == entity_type,
            HiddenPreference.entity_value == entity_value,
        )
    )
    await db.commit()
    return {"removed": True}


# ---------- 阅读历史 ----------

@router.post("/personal/reading")
async def record_reading(
    body: PaperIdRequest,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """记录/刷新某篇论文的阅读时间（幂等 upsert：已读则刷新 read_at）。"""
    uid = _user_id(x_user_id)
    pid = (body.paper_id or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="paper_id is required")
    exists = await db.execute(
        sa_select(ReadingHistory).where(ReadingHistory.user_id == uid, ReadingHistory.paper_id == pid)
    )
    rec = exists.scalar_one_or_none()
    if rec:
        from datetime import datetime, timezone
        rec.read_at = datetime.now(timezone.utc)
    else:
        db.add(ReadingHistory(user_id=uid, paper_id=pid))
    await db.commit()
    return {"recorded": True}


@router.get("/personal/reading-history")
async def get_reading_history(
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """阅读历史论文列表（时间倒序）。"""
    uid = _user_id(x_user_id)
    result = await db.execute(
        sa_select(ReadingHistory.paper_id, ReadingHistory.read_at)
        .where(ReadingHistory.user_id == uid)
        .order_by(ReadingHistory.read_at.desc())
        .limit(100)
    )
    rows = result.all()
    if not rows:
        return {"papers": [], "total": 0}
    ids = [r[0] for r in rows]
    read_map = {r[0]: r[1] for r in rows}
    presult = await db.execute(
        sa_select(Paper).options(
            selectinload(Paper.features),
            selectinload(Paper.scores),
        ).where(Paper.id.in_(ids))
    )
    papers = presult.scalars().all()
    cards = [_paper_to_card(p) for p in papers]
    cards.sort(key=lambda c: read_map.get(c["id"], 0), reverse=True)
    return {"papers": cards, "total": len(cards)}


@router.get("/personal/read-ids")
async def get_read_ids(
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """已读论文 id 列表（时间倒序，至多 500），供列表页做已读标记。"""
    uid = _user_id(x_user_id)
    ids = await _paper_ids_by_status(db, uid, ReadingHistory, limit=500)
    return {"paper_ids": ids}


# ---------- 关注子领域 ----------

@router.get("/personal/subfields")
async def get_subfields(
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    uid = _user_id(x_user_id)
    result = await db.execute(
        sa_select(FollowedSubfield.subfield).where(FollowedSubfield.user_id == uid)
    )
    return {"subfields": [r[0] for r in result.all()]}


@router.put("/personal/subfields")
async def set_subfields(
    body: FollowedSubfieldsRequest,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """整体替换关注的子领域列表（前端已选集合一次提交）。"""
    uid = _user_id(x_user_id)
    await db.execute(sa_delete(FollowedSubfield).where(FollowedSubfield.user_id == uid))
    for subfield in body.subfields:
        s = (subfield or "").strip()
        if s:
            db.add(FollowedSubfield(user_id=uid, subfield=s))
    await db.commit()
    return {"subfields": [s for s in body.subfields if (s or "").strip()]}