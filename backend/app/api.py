"""API 总路由：按功能拆分为多个子 router。"""
from fastapi import APIRouter

from app.routers import system, papers, ai, network, crawler, topic, personal, dashboard, producer

router = APIRouter()
router.include_router(system.router)
router.include_router(papers.router)
router.include_router(ai.router)
router.include_router(network.router)
router.include_router(crawler.router)
router.include_router(topic.router)
router.include_router(personal.router)
router.include_router(dashboard.router)
router.include_router(producer.router)
