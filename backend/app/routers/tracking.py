"""用户行为埋点（analytics）：事件上报 + 分析查询。"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy import select as sa_select, func as sa_func, desc as sa_desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import UserEvent
from app.routers.deps import verify_token

logger = logging.getLogger(__name__)
router = APIRouter()


def _user_id(x_user_id: Optional[str]) -> str:
    return (x_user_id or "").strip() or "local"


# ---------- 事件上报 ----------

class TrackEventRequest(BaseModel):
    event_type: str   # impression | click | favorite | unfavorite
    surface: str      # dashboard_today_read | paper_list | search | ...
    ref_id: Optional[str] = None
    meta: Optional[dict] = None


class TrackBatchRequest(BaseModel):
    events: List[TrackEventRequest]


@router.post("/tracking/event")
async def track_event(
    body: TrackEventRequest,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """上报单条用户行为事件。"""
    uid = _user_id(x_user_id)
    db.add(UserEvent(
        user_id=uid,
        event_type=body.event_type,
        surface=body.surface,
        ref_id=body.ref_id,
        meta=body.meta,
    ))
    await db.commit()
    return {"ok": True}


@router.post("/tracking/events")
async def track_events(
    body: TrackBatchRequest,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """批量上报用户行为事件（减少请求数）。"""
    uid = _user_id(x_user_id)
    for ev in body.events:
        db.add(UserEvent(
            user_id=uid,
            event_type=ev.event_type,
            surface=ev.surface,
            ref_id=ev.ref_id,
            meta=ev.meta,
        ))
    await db.commit()
    return {"ok": True, "count": len(body.events)}


# ---------- 分析查询 ----------

@router.get("/tracking/analytics")
async def get_analytics(
    days: int = Query(7, ge=1, le=90),
    surface: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
    x_user_id: str = Header(default=None),
):
    """查询用户行为分析数据：事件统计 + 转化漏斗。"""
    from datetime import datetime, timedelta, timezone

    uid = _user_id(x_user_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    conds = [UserEvent.user_id == uid, UserEvent.created_at >= cutoff]
    if surface:
        conds.append(UserEvent.surface == surface)

    # 事件类型计数
    result = await db.execute(
        sa_select(UserEvent.event_type, sa_func.count(UserEvent.id))
        .where(*conds)
        .group_by(UserEvent.event_type)
    )
    type_counts = {row[0]: row[1] for row in result.all()}

    # 按天统计
    result = await db.execute(
        sa_select(
            sa_func.date(UserEvent.created_at).label("day"),
            UserEvent.event_type,
            sa_func.count(UserEvent.id),
        )
        .where(*conds)
        .group_by("day", UserEvent.event_type)
        .order_by(sa_desc("day"))
    )
    daily = {}
    for day, etype, cnt in result.all():
        day_str = str(day)
        if day_str not in daily:
            daily[day_str] = {}
        daily[day_str][etype] = cnt

    # 热门点击论文
    result = await db.execute(
        sa_select(UserEvent.ref_id, sa_func.count(UserEvent.id).label("cnt"))
        .where(*conds, UserEvent.event_type == "click")
        .group_by(UserEvent.ref_id)
        .order_by(sa_desc("cnt"))
        .limit(10)
    )
    top_clicked = [{"paper_id": r[0], "clicks": r[1]} for r in result.all() if r[0]]

    # 转化漏斗：曝光 → 点击 → 收藏
    impressions = type_counts.get("impression", 0)
    clicks = type_counts.get("click", 0)
    favorites = type_counts.get("favorite", 0)
    funnel = {
        "impressions": impressions,
        "clicks": clicks,
        "favorites": favorites,
        "ctr": round(clicks / impressions, 4) if impressions > 0 else 0,
        "fav_rate": round(favorites / clicks, 4) if clicks > 0 else 0,
    }

    return {
        "period_days": days,
        "event_counts": type_counts,
        "funnel": funnel,
        "daily": daily,
        "top_clicked": top_clicked,
    }
