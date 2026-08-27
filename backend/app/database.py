from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

if settings.database_url.startswith("sqlite"):
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True  # PERF_PLAN 1.2：坏连接先探测，减少脏会话复用
    )

    # SQLite 默认不启用外键约束，模型里的 ondelete=CASCADE 需要每次连接时打开 PRAGMA 才生效
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_fk_on(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL：写操作不再阻塞读；busy_timeout：写锁冲突时排队等待而非立即抛
        # database is locked（此前启动维护任务批量提交会卡死并发请求写入）
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()
else:
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )

# 慢查询监听：单条 SQL 执行超过阈值记 WARNING，便于定位性能问题（日志系统辅助项）
from sqlalchemy import event as sa_event
import logging as _logging
import time as _time

_SLOW_QUERY_THRESHOLD = 1.5


@sa_event.listens_for(engine.sync_engine, "before_cursor_execute")
def _slow_query_start(conn, cursor, statement, parameters, context, executemany):
    conn._query_start_time = _time.perf_counter()


@sa_event.listens_for(engine.sync_engine, "after_cursor_execute")
def _slow_query_report(conn, cursor, statement, parameters, context, executemany):
    start = getattr(conn, "_query_start_time", None)
    if start is None:
        return
    elapsed = _time.perf_counter() - start
    if elapsed > _SLOW_QUERY_THRESHOLD:
        _logging.getLogger("app.database").warning(
            "SLOW QUERY %.1fs: %s", elapsed, str(statement)[:300]
        )

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    from app.models import (Paper, PaperFeatures, PaperScore, TopicTrend, CrawlLog, AIAnalysisReport,
                            TrendChat, ActionLog, ErrorLog, AssistantSession, AssistantMessage)
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all 不会给已存在的表补建新索引，手动确保关键索引存在
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_papers_created_at ON papers (created_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crawl_logs_crawl_start_time ON crawl_logs (crawl_start_time)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_analysis_reports_status_created ON ai_analysis_reports (status, created_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_action_logs_created_at ON action_logs (created_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_error_logs_created_at ON error_logs (created_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_assistant_messages_session ON assistant_messages (session_id, id)"))
        # create_all 也不会给已存在的表补新列；CrawlLog 增量列用 ALTER 补齐
        rows = (await conn.execute(text("PRAGMA table_info(crawl_logs)"))).fetchall()
        existing = {r[1] for r in rows}
        if "task_type" not in existing:
            await conn.execute(text("ALTER TABLE crawl_logs ADD COLUMN task_type VARCHAR(20) DEFAULT 'journal'"))
        if "log_detail" not in existing:
            await conn.execute(text("ALTER TABLE crawl_logs ADD COLUMN log_detail TEXT"))
        if "rerun_params" not in existing:
            await conn.execute(text("ALTER TABLE crawl_logs ADD COLUMN rerun_params TEXT"))
