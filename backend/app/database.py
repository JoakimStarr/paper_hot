from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

if settings.database_url.startswith("sqlite"):
    engine = create_async_engine(
        settings.database_url,
        echo=False
    )

    # SQLite 默认不启用外键约束，模型里的 ondelete=CASCADE 需要每次连接时打开 PRAGMA 才生效
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_fk_on(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
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
    from app.models import Paper, PaperFeatures, PaperScore, TopicTrend, CrawlLog, AIAnalysisReport, TrendChat
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all 不会给已存在的表补建新索引，手动确保关键索引存在
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_papers_created_at ON papers (created_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crawl_logs_crawl_start_time ON crawl_logs (crawl_start_time)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_analysis_reports_status_created ON ai_analysis_reports (status, created_at)"))
