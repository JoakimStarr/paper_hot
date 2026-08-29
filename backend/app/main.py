from fastapi import FastAPI, Request, Response, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from contextlib import asynccontextmanager
import asyncio
import logging
import time
import traceback

from app.config import settings
from app.database import init_db
from app.api import router as api_router
from app.scheduler import PaperScheduler
from app.logging_config import setup_logging
from app.log_context import set_request_context, new_request_id, get_request_id, get_user_id
from app import log_store

setup_logging()

logger = logging.getLogger(__name__)

scheduler = PaperScheduler()


_background_tasks = set()


def spawn_background_task(coro):
    """创建后台任务并持有引用，避免被垃圾回收中途中断（详见 asyncio.create_task 文档）。"""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up PaperPulse...")

    await init_db()
    logger.info("Database initialized")

    await _cleanup_zombie_reports()
    await _cleanup_stale_crawl_logs()
    await _cleanup_expired_logs()

    # 启动日志落库消费者（请求中间件/异常处理器经 log_store 异步写库）
    log_store.start()

    # P0 遗留#2/#3：无论定时器是否开启，启动即刷新趋势数据 + 补齐存量 embedding
    spawn_background_task(scheduler.run_startup_maintenance())

    # paper_keywords 平表：空表时后台回填（工作台关键词召回走索引查找；幂等）
    from app.crud import backfill_paper_keywords
    spawn_background_task(backfill_paper_keywords(only_if_empty=True))

    if settings.scheduler_enabled:
        scheduler.start()
        # 初始抓取放后台执行，避免阻塞服务启动（外部网络慢时接口迟迟不可用）
        spawn_background_task(scheduler.run_initial_fetch())

    yield

    logger.info("Shutting down PaperPulse...")
    if settings.scheduler_enabled:
        scheduler.stop()
    for task in list(_background_tasks):
        task.cancel()
    await log_store.stop()


async def _cleanup_zombie_reports():
    """清理超时僵尸报告：
    - ai_analysis_reports / batch_reports 超过10分钟仍 running -> 直接删除/标记失败
    （服务重启会遗留 running 记录，否则前端轮询永远转圈）
    """
    from sqlalchemy import text as sa_text
    from app.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_text("""
                    DELETE FROM ai_analysis_reports 
                    WHERE status = 'running' 
                    AND created_at < datetime('now', '-10 minutes')
                """)
            )
            if result.rowcount > 0:
                await db.commit()
                logger.info(f"Deleted {result.rowcount} zombie analysis reports")
    except Exception as e:
        logger.warning(f"Failed to cleanup zombie reports: {e}")

    # P0/#7：批量分析报告僵尸化处理（后端重启后遗留的 running 记录标记为 failed）
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_text("""
                    UPDATE batch_reports
                    SET status = 'failed',
                        error_message = '服务重启，任务中断，请重试'
                    WHERE status = 'running'
                    AND created_at < datetime('now', '-10 minutes')
                """)
            )
            if result.rowcount > 0:
                await db.commit()
                logger.info(f"Marked {result.rowcount} zombie batch report(s) as failed")
    except Exception as e:
        logger.warning(f"Failed to cleanup zombie batch reports: {e}")

    # 单篇分析 pending 僵尸：服务重启打断 LLM 调用后，paper_analyses.status='pending'
    # 无任何路径回收，该论文会永久返回"分析正在进行中"。超时即标记失败。
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_text("""
                    UPDATE paper_analyses
                    SET status = 'failed',
                        analysis = '分析因服务重启中断，请重新发起'
                    WHERE status = 'pending'
                    AND created_at < datetime('now', '-30 minutes')
                """)
            )
            if result.rowcount > 0:
                await db.commit()
                logger.info(f"Marked {result.rowcount} zombie pending analysis(es) as failed")
    except Exception as e:
        logger.warning(f"Failed to cleanup zombie paper analyses: {e}")


async def _cleanup_stale_crawl_logs():
    """把超过2小时仍是 running 的爬虫日志标记为 failed（服务重启遗留的僵尸记录，
    否则 /crawl/start 会永远拒绝启动，对应期刊也会被跳过）。"""
    from app.crud import CrawlLogCRUD
    from app.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            cleaned = await CrawlLogCRUD.mark_stale_running_failed(db)
            if cleaned > 0:
                await db.commit()
                logger.info(f"Marked {cleaned} stale crawl log(s) as failed")
    except Exception as e:
        logger.warning(f"Failed to cleanup stale crawl logs: {e}")


async def _cleanup_expired_logs():
    """启动时清理超过保留期的动作/错误日志（LOG_RETENTION_DAYS，<=0 不清理）。"""
    days = settings.log_retention_days
    if not days or days <= 0:
        return
    from sqlalchemy import text as sa_text
    from app.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            for table in ("action_logs", "error_logs"):
                result = await db.execute(
                    sa_text(f"DELETE FROM {table} WHERE created_at < datetime('now', '-{int(days)} days')")
                )
                if result.rowcount:
                    await db.commit()
                    logger.info(f"Cleaned {result.rowcount} expired {table}")
    except Exception as e:
        logger.warning(f"Failed to cleanup expired logs: {e}")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan
)

# CORS：配置的前端端口动态加入白名单（端口可在系统页修改）
_cors_origins = settings.get_cors_origins()
_frontend_origin = f"http://localhost:{settings.frontend_port}"
if _frontend_origin not in _cors_origins:
    _cors_origins.append(_frontend_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # 放行任意 localhost/127.0.0.1 端口（start.sh 端口被占用时前端可能随机换端口）
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 日志系统：请求/动作全量记录（纯 ASGI 中间件，外层包裹 CORS）
# 为每个请求生成 request_id 并写入 contextvars（贯穿该请求所有日志），
# 记录 method/path/status/耗时到 action_logs；响应头附 X-Request-ID 便于前端串联。
#
# 用纯 ASGI（而非 @app.middleware("http")/BaseHTTPMiddleware）实现：BaseHTTPMiddleware
# 会缓冲并重包响应体，嵌套两层时对 SSE 流式响应/304 等特殊响应会触发 uvicorn 的
# 'Response content longer than Content-Length' 崩溃。纯 ASGI 只透传消息，天然安全。
_SKIP_ACTION_LOG_PREFIXES = ("/health", "/api/health", "/docs", "/redoc", "/openapi.json", "/api/logs/client")


class RequestLoggingMiddleware:
    """纯 ASGI 中间件：动作全量记录 + request_id 注入 + 禁用缓存头。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path.startswith(_SKIP_ACTION_LOG_PREFIXES):
            await self.app(scope, receive, send)
            return

        request_id = new_request_id()
        user_id = "local"
        for name, value in scope.get("headers", []):
            if name == b"x-user-id":
                user_id = value.decode("utf-8", "ignore").strip() or "local"
                break
        set_request_context(request_id, user_id)

        method = scope.get("method", "")
        query = (scope.get("query_string") or b"").decode("utf-8", "ignore")[:500] or None
        start = time.perf_counter()
        status_code = 500

        async def wrapped_send(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                if "cache-control" not in headers:
                    headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                    headers["Pragma"] = "no-cache"
                    headers["Expires"] = "0"
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception:
            # 异常处理器负责记录 ErrorLog；这里补一条动作记录后继续向上抛
            duration_ms = int((time.perf_counter() - start) * 1000)
            log_store.submit_action(
                request_id=request_id, user_id=user_id, method=method,
                path=path, status_code=500, duration_ms=duration_ms, query=query,
            )
            raise

        duration_ms = int((time.perf_counter() - start) * 1000)
        log_store.submit_action(
            request_id=request_id, user_id=user_id, method=method,
            path=path, status_code=status_code, duration_ms=duration_ms, query=query,
        )


app.add_middleware(RequestLoggingMiddleware)


# ---------- 异常处理器：统一日志 + 错误报告入库（log_store） ----------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    message = str(exc)[:2000]
    log_store.submit_error(
        source="backend", request_id=get_request_id(), user_id=get_user_id(),
        method=request.method, path=request.url.path, status_code=422,
        error_type="RequestValidationError", error_message=message,
        request_info={"query": (request.url.query or "")[:500] or None},
    )
    logger.warning("request validation failed path=%s detail=%s", request.url.path, message)
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code >= 500:
        log_store.submit_error(
            source="backend", request_id=get_request_id(), user_id=get_user_id(),
            method=request.method, path=request.url.path, status_code=exc.status_code,
            error_type="HTTPException", error_message=str(exc.detail)[:2000],
            request_info={"query": (request.url.query or "")[:500] or None},
        )
        logger.error("http error path=%s status=%s detail=%s",
                     request.url.path, exc.status_code, exc.detail)
    else:
        logger.info("http %s %s status=%s", request.method, request.url.path, exc.status_code)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log_store.submit_error(
        source="backend", request_id=get_request_id(), user_id=get_user_id(),
        method=request.method, path=request.url.path, status_code=500,
        error_type=type(exc).__name__, error_message=str(exc)[:2000],
        traceback=tb[-20000:],
        request_info={"query": (request.url.query or "")[:500] or None},
    )
    logger.error("unhandled error path=%s", request.url.path, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
