from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up PaperPulse...")
    
    await init_db()
    logger.info("Database initialized")
    
    if settings.scheduler_enabled:
        scheduler.start()
        await scheduler.run_initial_fetch()
    
    yield
    
    logger.info("Shutting down PaperPulse...")
    if settings.scheduler_enabled:
        scheduler.stop()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
