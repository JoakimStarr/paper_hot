from fastapi import FastAPI, Request, Response, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging

from app.config import settings
from app.database import init_db
from app.api import router as api_router
from app.scheduler import PaperScheduler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

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

    # P0 遗留#2/#3：无论定时器是否开启，启动即刷新趋势数据 + 补齐存量 embedding
    spawn_background_task(scheduler.run_startup_maintenance())

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
    
    logger.info("Shutting down PaperPulse...")
    if settings.scheduler_enabled:
        scheduler.stop()


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

# 添加中间件，禁用缓存
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

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
