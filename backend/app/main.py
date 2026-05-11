from fastapi import FastAPI, Request, Response, HTTPException, Depends, Header
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


async def verify_api_token(x_api_token: str = Header(default=None)):
    if settings.api_token and settings.api_token != "":
        if x_api_token is None or x_api_token != settings.api_token:
            raise HTTPException(status_code=401, detail="Invalid or missing API token")
    return True


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
