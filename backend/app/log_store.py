"""异步日志落库：动作/错误记录先入内存队列，由消费者任务批量写库。

设计约束：
- 绝不阻塞请求：submit_* 用 put_nowait，队列满时丢弃并告警（日志系统的可靠性
  不应以业务请求的可用性为代价）。
- 批量写：攒 BATCH_SIZE 条或间隔 BATCH_INTERVAL 秒一次性 INSERT（单事务），
  减少 SQLite 写入压力。
- 生命周期：start() 在 lifespan 启动后调用；stop() 排空剩余再退出。
"""
import asyncio
import logging
from datetime import datetime, timezone

from app.database import AsyncSessionLocal
from app.models import ActionLog, ErrorLog

logger = logging.getLogger(__name__)

_MAX_QUEUE = 2000
_BATCH_SIZE = 20
_BATCH_INTERVAL = 1.0

_queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE)
_consumer_task: "asyncio.Task | None" = None


def submit_action(*, request_id: str, user_id: str, method: str, path: str,
                  status_code: int, duration_ms: int, query: str | None = None):
    _enqueue({
        "kind": "action",
        "request_id": request_id,
        "user_id": user_id,
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "query": query,
        "created_at": datetime.now(timezone.utc),
    })


def submit_error(*, source: str = "backend", request_id: str = "-", user_id: str = "-",
                 method: str | None = None, path: str | None = None, status_code: int | None = None,
                 error_type: str = "Exception", error_message: str = "", traceback: str | None = None,
                 request_info: dict | None = None):
    _enqueue({
        "kind": "error",
        "source": source,
        "request_id": request_id,
        "user_id": user_id,
        "method": method,
        "path": path,
        "status_code": status_code,
        "error_type": error_type,
        "error_message": error_message,
        "traceback": traceback,
        "request_info": request_info,
        "created_at": datetime.now(timezone.utc),
    })


def _enqueue(record: dict):
    try:
        _queue.put_nowait(record)
    except asyncio.QueueFull:
        logger.warning("log queue full, dropping log record: %s", record.get("kind"))


def start():
    """启动消费者任务（幂等）。"""
    global _consumer_task
    if _consumer_task is not None and not _consumer_task.done():
        return
    _consumer_task = asyncio.create_task(_consume_loop())


async def stop(timeout: float = 5.0):
    """排空队列后停止消费者；超时则取消任务。"""
    global _consumer_task
    task = _consumer_task
    if task is None:
        return
    try:
        await _queue.put(None)  # 结束哨兵
        await asyncio.wait_for(task, timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        task.cancel()
    _consumer_task = None


async def _consume_loop():
    batch: list[dict] = []
    while True:
        try:
            record = await asyncio.wait_for(_queue.get(), timeout=_BATCH_INTERVAL)
        except asyncio.TimeoutError:
            # 空闲一段时间仍有未落库的积压 → 强制刷一批
            if batch:
                await _flush(batch)
                batch = []
            continue
        if record is None:
            if batch:
                await _flush(batch)
            return
        batch.append(record)
        if len(batch) >= _BATCH_SIZE:
            await _flush(batch)
            batch = []


async def _flush(records: list):
    try:
        async with AsyncSessionLocal() as db:
            for rec in records:
                if rec["kind"] == "action":
                    db.add(ActionLog(
                        request_id=rec["request_id"], user_id=rec["user_id"],
                        method=rec["method"], path=rec["path"],
                        status_code=rec["status_code"], duration_ms=rec["duration_ms"],
                        query=rec["query"], created_at=rec["created_at"],
                    ))
                else:
                    db.add(ErrorLog(
                        source=rec["source"], request_id=rec["request_id"], user_id=rec["user_id"],
                        method=rec["method"], path=rec["path"], status_code=rec["status_code"],
                        error_type=rec["error_type"], error_message=rec["error_message"],
                        traceback=rec["traceback"], request_info=rec["request_info"],
                        created_at=rec["created_at"],
                    ))
            await db.commit()
    except Exception as e:
        # 写库失败只告警不抛：日志系统不能影响业务
        logger.warning(f"failed to persist {len(records)} log records: {e}")
