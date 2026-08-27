"""日志系统查询接口：系统页「日志」标签页的数据源。

- GET  /system/action-logs        动作日志列表（筛选 + 分页）
- GET  /system/error-logs         错误日志列表（筛选 + 分页）
- GET  /system/error-logs/{id}    单条错误详情（含完整 traceback）
- POST /logs/client               前端错误上报（免鉴权：只写日志，无副作用）
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select as sa_select, desc as sa_desc, func as sa_func, or_ as sa_or
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ActionLog, ErrorLog
from app.routers.deps import verify_token, _isoformat_utc
from app import log_store

logger = logging.getLogger(__name__)
router = APIRouter()


def _uid(x_user_id: Optional[str]) -> str:
    return (x_user_id or "").strip() or "local"


def _parse_dt(value: Optional[str]):
    """把 'YYYY-MM-DD' / 'YYYY-MM-DD HH:MM[:SS]' 解析为 datetime；无效返回 None。"""
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _action_to_dict(a: ActionLog) -> dict:
    return {
        "id": a.id,
        "request_id": a.request_id,
        "user_id": a.user_id,
        "method": a.method,
        "path": a.path,
        "status_code": a.status_code,
        "duration_ms": a.duration_ms,
        "query": a.query,
        "created_at": _isoformat_utc(a.created_at),
    }


def _error_to_dict(e: ErrorLog, with_traceback: bool = False) -> dict:
    return {
        "id": e.id,
        "source": e.source,
        "request_id": e.request_id,
        "user_id": e.user_id,
        "method": e.method,
        "path": e.path,
        "status_code": e.status_code,
        "error_type": e.error_type,
        "error_message": e.error_message,
        "traceback": e.traceback if with_traceback else None,
        "request_info": e.request_info,
        "created_at": _isoformat_utc(e.created_at),
    }


@router.get("/system/action-logs")
async def list_action_logs(
    user_id: Optional[str] = None,
    method: Optional[str] = None,
    path: Optional[str] = None,
    status: Optional[int] = None,
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    conds = []
    if user_id:
        conds.append(ActionLog.user_id == user_id)
    if method:
        conds.append(ActionLog.method == method.upper())
    if path:
        conds.append(ActionLog.path.ilike(f"%{path}%"))
    if status is not None:
        conds.append(ActionLog.status_code == status)
    if from_:
        dt = _parse_dt(from_)
        if dt:
            conds.append(ActionLog.created_at >= dt)
    if to:
        dt = _parse_dt(to)
        if dt:
            conds.append(ActionLog.created_at <= dt)

    total = (await db.execute(
        sa_select(sa_func.count()).select_from(ActionLog).where(*conds)
    )).scalar() or 0

    rows = await db.execute(
        sa_select(ActionLog)
        .where(*conds)
        .order_by(sa_desc(ActionLog.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [_action_to_dict(a) for a in rows.scalars()],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/system/error-logs")
async def list_error_logs(
    source: Optional[str] = None,
    user_id: Optional[str] = None,
    error_type: Optional[str] = None,
    status: Optional[int] = None,
    keyword: Optional[str] = None,
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    conds = []
    if source:
        conds.append(ErrorLog.source == source)
    if user_id:
        conds.append(ErrorLog.user_id == user_id)
    if error_type:
        conds.append(ErrorLog.error_type == error_type)
    if status is not None:
        conds.append(ErrorLog.status_code == status)
    if keyword:
        conds.append(sa_or(ErrorLog.error_message.ilike(f"%{keyword}%"), ErrorLog.path.ilike(f"%{keyword}%")))
    if from_:
        dt = _parse_dt(from_)
        if dt:
            conds.append(ErrorLog.created_at >= dt)
    if to:
        dt = _parse_dt(to)
        if dt:
            conds.append(ErrorLog.created_at <= dt)

    total = (await db.execute(
        sa_select(sa_func.count()).select_from(ErrorLog).where(*conds)
    )).scalar() or 0

    rows = await db.execute(
        sa_select(ErrorLog)
        .where(*conds)
        .order_by(sa_desc(ErrorLog.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [_error_to_dict(e) for e in rows.scalars()],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/system/error-logs/{error_id}")
async def get_error_log_detail(
    error_id: int,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    row = await db.get(ErrorLog, error_id)
    if not row:
        raise HTTPException(status_code=404, detail="Error log not found")
    return _error_to_dict(row, with_traceback=True)


class ClientErrorRequest(BaseModel):
    message: str = ""
    stack: Optional[str] = None
    url: Optional[str] = None
    level: str = "error"   # error | warning
    user_agent: Optional[str] = None


@router.post("/logs/client")
async def report_client_error(
    body: ClientErrorRequest,
    x_user_id: str = Header(default=None),
):
    """前端错误上报：window error / 未捕获 Promise 拒绝 / API 5xx。免鉴权，只写日志。"""
    message = (body.message or "").strip() or "Unknown frontend error"
    log_store.submit_error(
        source="frontend",
        request_id="-",
        user_id=_uid(x_user_id),
        status_code=None,
        error_type="FrontendError",
        error_message=message[:2000],
        traceback=(body.stack or "")[-20000:] or None,
        request_info={
            "url": (body.url or "")[:500] or None,
            "level": body.level,
            "user_agent": (body.user_agent or "")[:300] or None,
        },
    )
    return {"ok": True}
