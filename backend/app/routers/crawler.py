"""爬虫、调度器、相似度重算与数据维护接口。"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db, AsyncSessionLocal
from app.config import settings
from app.crud import PaperCRUD, CrawlLogCRUD, PaperSimilarityCRUD
from app.schemas import CrawlLogResponse, CrawlLogListResponse
from app.models import PaperSimilarity
from app.routers.deps import verify_token

logger = logging.getLogger(__name__)
router = APIRouter()


class CrawlStartRequest(BaseModel):
    journal_names: Optional[List[str]] = None


class CrawlStartResponse(BaseModel):
    crawl_log_id: str
    status: str
    message: str


@router.post("/crawl/start", response_model=CrawlStartResponse)
async def start_crawl(
    request: CrawlStartRequest = Body(default=CrawlStartRequest()),
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token)
):
    try:
        # 服务重启会遗留 running 状态的僵尸日志，先清理（超2小时必为残留）再判断占用
        cleaned = await CrawlLogCRUD.mark_stale_running_failed(db)
        if cleaned > 0:
            await db.commit()
            logger.warning(f"Cleaned {cleaned} stale running crawl log(s) before starting new crawl")

        active_crawl = await CrawlLogCRUD.get_active_crawl(db)
        if active_crawl:
            raise HTTPException(
                status_code=400,
                detail=f"A crawl task is already running ({active_crawl.journal_name}, "
                       f"started {active_crawl.crawl_start_time}). Please wait for it to complete."
            )

        from app.main import scheduler
        task_id = await scheduler.trigger_manual_crawl(request.journal_names)

        return CrawlStartResponse(
            crawl_log_id=task_id,
            status="started",
            message=f"Crawl task started for journals: {request.journal_names or 'all'}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error ({type(e).__name__})")


class CNKICrawlRequest(BaseModel):
    journal_names: Optional[List[str]] = None
    max_results_per_journal: int = 20
    max_journals: Optional[int] = None


@router.post("/crawl/cnki/top50/start")
async def start_cnki_top50_crawl(body: CNKICrawlRequest = Body(default=CNKICrawlRequest()), token: bool = Depends(verify_token)):
    """手动触发知网 TOP50 期刊爬取（DrissionPage 浏览器爬虫，建议在本机运行）。

    默认非无头模式会弹出浏览器窗口，遇到验证码时可人工处理。
    """
    try:
        from app.main import scheduler
        task_id = await scheduler.trigger_manual_cnki_crawl(
            journal_names=body.journal_names,
            max_results_per_journal=body.max_results_per_journal,
            max_journals=body.max_journals,
        )
        return {"status": "started", "task_id": task_id, "message": "知网TOP50爬取已启动（浏览器窗口模式下可人工处理验证码）"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start CNKI top50 crawl: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error ({type(e).__name__})")


@router.post("/crawl/cnki/navi/start")
async def start_cnki_navi_crawl(token: bool = Depends(verify_token)):
    """手动触发知网期刊导航爬取（DrissionPage 浏览器爬虫，建议在本机运行）。"""
    try:
        from app.main import scheduler
        task_id = await scheduler.trigger_manual_cnki_navi_crawl()
        return {"status": "started", "task_id": task_id, "message": "知网导航爬取已启动"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start CNKI navi crawl: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error ({type(e).__name__})")


@router.get("/crawl/status", response_model=CrawlLogListResponse)
async def get_crawl_status(
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    logs, total = await CrawlLogCRUD.get_crawl_logs(db, page_size=limit)
    return CrawlLogListResponse(
        logs=[CrawlLogResponse.model_validate(log) for log in logs],
        total=total,
        page=1,
        page_size=limit,
        has_next=total > limit
    )


@router.post("/update-trend-scores")
async def update_trend_scores(db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    """手动触发趋势分数更新"""
    try:
        await PaperCRUD.bulk_update_paper_trend_scores(db)
        await db.commit()
        return {"status": "success", "message": "Trend scores updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error ({type(e).__name__})")


_similarity_task_state = {"running": False, "last_pairs": 0, "last_error": None}


async def _recompute_similarities_background():
    """后台全量重算相似度：整个语料一次性计算（分批会导致跨批论文对永远算不到），
    CPU 密集部分放线程池避免阻塞事件循环。"""
    from sqlalchemy import select
    from app.models import Paper, PaperSimilarity
    from app.similarity import compute_all_similarities
    from app.database import AsyncSessionLocal
    from sqlalchemy import insert as sa_insert

    _similarity_task_state["running"] = True
    _similarity_task_state["last_error"] = None
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Paper.id, Paper.abstract).order_by(Paper.id))
            papers = [(r[0], r[1]) for r in result.all() if r[1]]

        if len(papers) < 2:
            _similarity_task_state["last_pairs"] = 0
            return

        all_pairs = await asyncio.to_thread(compute_all_similarities, papers)

        async with AsyncSessionLocal() as db:
            await PaperSimilarityCRUD.clear_all(db)
            await db.flush()
            rows = [
                {"paper_id_a": a, "paper_id_b": b, "similarity_score": score}
                for a, b, score in all_pairs
            ]
            # 分块批量插入，避免单条 SQL 绑定变量超限
            for i in range(0, len(rows), 500):
                await db.execute(sa_insert(PaperSimilarity), rows[i:i + 500])
            await db.commit()

        _similarity_task_state["last_pairs"] = len(all_pairs)
        logger.info(f"Similarity recompute finished: {len(all_pairs)} pairs")
    except Exception as e:
        _similarity_task_state["last_error"] = str(e)
        logger.error(f"Similarity recompute failed: {e}")
    finally:
        _similarity_task_state["running"] = False


@router.post("/recompute-all-similarities")
async def recompute_all_similarities(token: bool = Depends(verify_token)):
    if _similarity_task_state["running"]:
        return {"status": "already_running", "message": "相似度重算正在进行中"}
    from app.main import spawn_background_task
    spawn_background_task(_recompute_similarities_background())
    return {"status": "started", "message": "相似度全量重算已开始（后台执行）"}


@router.get("/recompute-all-similarities")
async def recompute_all_similarities_status(token: bool = Depends(verify_token)):
    return _similarity_task_state


@router.get("/scheduler/jobs")
async def get_scheduler_jobs(token: bool = Depends(verify_token)):
    from app.main import scheduler
    jobs = scheduler.get_jobs_info()
    running = scheduler.is_running()
    return {"running": running, "jobs": jobs}


@router.post("/scheduler/trigger/{job_id}")
async def trigger_scheduler_job(job_id: str, token: bool = Depends(verify_token)):
    from app.main import scheduler
    try:
        scheduler.trigger_job(job_id)
        return {"status": "ok", "message": f"Job {job_id} triggered"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/scheduler/toggle")
async def toggle_scheduler(token: bool = Depends(verify_token)):
    from app.main import scheduler
    if scheduler.is_running():
        scheduler.pause()
        return {"status": "paused"}
    else:
        try:
            scheduler.resume()
        except Exception:
            scheduler.start()
        return {"status": "resumed"}


@router.post("/maintenance/cleanup")
async def cleanup_database(db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    from sqlalchemy import text as sa_text

    try:
        deleted_papers = 0
        deleted_features = 0
        deleted_scores = 0
        deleted_reports = 0

        result = await db.execute(sa_text("""
            DELETE FROM papers
            WHERE title IS NULL OR title = '' OR abstract IS NULL OR abstract = ''
        """))
        deleted_papers = result.rowcount or 0
        await db.flush()

        # 同标题重复论文只保留最早一条（CNKI 动态 URL 绕过唯一约束产生的历史重复）
        result = await db.execute(sa_text("""
            DELETE FROM papers
            WHERE id NOT IN (SELECT MIN(id) FROM papers GROUP BY title)
              AND title IN (SELECT title FROM papers GROUP BY title HAVING COUNT(*) > 1)
        """))
        deleted_papers += result.rowcount or 0
        await db.flush()

        result = await db.execute(sa_text("""
            DELETE FROM paper_features
            WHERE paper_id NOT IN (SELECT id FROM papers)
        """))
        deleted_features = result.rowcount or 0
        await db.flush()

        result = await db.execute(sa_text("""
            DELETE FROM paper_scores
            WHERE paper_id NOT IN (SELECT id FROM papers)
        """))
        deleted_scores = result.rowcount or 0
        await db.flush()

        result = await db.execute(sa_text("""
            DELETE FROM ai_analysis_reports
            WHERE status = 'running'
            AND created_at < datetime('now', '-10 minutes')
        """))
        deleted_reports = result.rowcount or 0

        # 其余子表的孤儿清理（FK 约束此前未开启，历史数据可能残留孤儿行）
        result = await db.execute(sa_text(
            "DELETE FROM paper_similarities WHERE paper_id_a NOT IN (SELECT id FROM papers) "
            "OR paper_id_b NOT IN (SELECT id FROM papers)"
        ))
        deleted_similarities = result.rowcount or 0
        result = await db.execute(sa_text(
            "DELETE FROM paper_analyses WHERE paper_id NOT IN (SELECT id FROM papers)"
        ))
        deleted_analyses = result.rowcount or 0
        result = await db.execute(sa_text(
            "DELETE FROM paper_chats WHERE paper_id NOT IN (SELECT id FROM papers)"
        ))
        deleted_paper_chats = result.rowcount or 0
        result = await db.execute(sa_text(
            "DELETE FROM trend_chats WHERE report_id NOT IN (SELECT id FROM ai_analysis_reports)"
        ))
        deleted_trend_chats = result.rowcount or 0

        await db.commit()

        return {
            "deleted_papers": deleted_papers,
            "deleted_features": deleted_features,
            "deleted_scores": deleted_scores,
            "deleted_reports": deleted_reports,
            "deleted_similarities": deleted_similarities,
            "deleted_analyses": deleted_analyses,
            "deleted_paper_chats": deleted_paper_chats,
            "deleted_trend_chats": deleted_trend_chats,
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error ({type(e).__name__})")


@router.post("/maintenance/recompute-scores")
async def recompute_all_scores(db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    """全量重算论文评分（新近性/期刊分级/关键词热度），修复历史常数评分。"""
    try:
        updated = await PaperCRUD.recompute_all_scores(db)
        await db.commit()
        return {"status": "success", "updated_scores": updated}
    except Exception as e:
        await db.rollback()
        logger.error(f"Recompute scores failed: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error ({type(e).__name__})")


