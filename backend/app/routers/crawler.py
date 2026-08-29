"""爬虫、调度器、相似度重算与数据维护接口。"""
import asyncio
import json
import logging
import os
import re
import signal
import sys
from collections import deque
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db, AsyncSessionLocal
from app.config import settings, BASE_DIR
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
        busy = scheduler._find_running_task("cnki_top50")
        if busy:
            raise HTTPException(status_code=400, detail=f"知网TOP50爬取任务已在进行中（{busy[:8]}…），请等待完成或先停止")
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
        busy = scheduler._find_running_task("cnki_navi")
        if busy:
            raise HTTPException(status_code=400, detail=f"知网导航爬取任务已在进行中（{busy[:8]}…），请等待完成")
        task_id = await scheduler.trigger_manual_cnki_navi_crawl()
        return {"status": "started", "task_id": task_id, "message": "知网导航爬取已启动"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start CNKI navi crawl: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error ({type(e).__name__})")


class CNKISearchRequest(BaseModel):
    """知网关键词检索爬取入参（对应 cnki_paper_captcha.py --search 检索模式）。"""
    keyword: str
    search_field: str = "主题"      # 主题/篇名/关键词/作者等
    years: Optional[str] = None     # 年份区间，如 2024-2026
    max_pages: Optional[int] = None  # 最大翻页数，默认翻到最后一页
    detail_workers: int = 3          # 详情页并发抓取数
    show_browser: bool = False       # 是否显示浏览器窗口（无头模式遇验证码只能自动解，显示窗口可人工处理）
    detail_refs: bool = False        # 详情入库后在同一详情页顺带抓参考文献（省二次导航）


# 与 cnki_paper_captcha.py 的 CNKI_SEARCH_FIELDS 保持一致
CNKI_SEARCH_FIELDS = [
    "主题", "篇关摘", "关键词", "篇名", "全文", "作者", "第一作者", "通讯作者",
    "作者单位", "基金", "摘要", "小标题", "参考文献", "分类号", "文献来源", "DOI",
]


# 关键词爬取任务状态（内存态；进程重启后归零。结果见 crawl_logs 与脚本 stdout 尾部）
_cnki_search_state = {
    "running": False,
    "paused": False,
    "keyword": None,
    "started_at": None,
    "finished_at": None,
    "message": None,
    "stopped_by_user": False,
    "progress": None,
    "last_log": [],
}
# 子进程句柄单独存（不进 state，避免 /status 序列化失败）
_cnki_search_proc: Optional[asyncio.subprocess.Process] = None


# 最近日志行数上限：状态里只保留尾部一小段，避免长期爬取把内存撑大
_MAX_STATUS_LOG_LINES = 30

# 关键词检索断点文件（由 cnki_paper_captcha.py 在翻页/详情阶段写入，脚本同级的 .cache/ 下）
_SEARCH_CHECKPOINT_FILE = BASE_DIR.parent / ".cache" / "search_checkpoint.json"


def _read_search_checkpoint() -> Optional[dict]:
    try:
        return json.loads(_SEARCH_CHECKPOINT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _empty_cnki_progress() -> dict:
    return {
        "phase": "starting",
        "page": 0,
        "collected": 0,
        "done": 0,
        "total": 0,
        "ok": 0,
        "already_exists": 0,
        "filtered": 0,
        "verify_failed": 0,
        "failed": 0,
        "refs_ok": 0,
        "refs_failed": 0,
    }


def _parse_cnki_progress(line: str, prog: dict) -> dict:
    """从爬虫 stdout 的进度行解析字段，合并进 prog（幂等，只覆盖更具体的值）。"""
    m = re.search(r"\[(\d+)/(\d+)\]", line)
    if m:
        prog["done"] = int(m.group(1))
        prog["total"] = int(m.group(2))
        prog["phase"] = "details"
    m = re.search(r"第 (\d+) 页获取 \d+ 条，累计 (\d+) 条", line)
    if m:
        prog["page"] = int(m.group(1))
        prog["collected"] = int(m.group(2))
        prog["phase"] = "collecting"
    m = re.search(r"共收集 (\d+) 篇待处理论文", line)
    if m:
        prog["collected"] = int(m.group(1))
        prog["phase"] = "collecting"
    m = re.search(r"详情并发数: \d+，待抓 (\d+) 篇（已在库跳过 (\d+)）", line)
    if m:
        prog["total"] = int(m.group(1))
        prog["already_exists"] = int(m.group(2))
        prog["phase"] = "details"
    m = re.search(r"完成：成功 (\d+)/(\d+) 篇 \| 已在库 (\d+) \| 被过滤 (\d+) \| 验证码未过 (\d+) \| 失败 (\d+)", line)
    if m:
        prog["ok"] = int(m.group(1))
        prog["done"] = int(m.group(2))
        prog["already_exists"] = int(m.group(3))
        prog["filtered"] = int(m.group(4))
        prog["verify_failed"] = int(m.group(5))
        prog["failed"] = int(m.group(6))
        prog["phase"] = "done"
    # --detail-refs 顺带抓取的参考文献进度：每篇「✓ 参考文献已入库 N 条」累加，
    # 汇总行「参考文献（--detail-refs）：成功 X 篇 | 失败 Y 篇」直接覆盖
    m = re.search(r"参考文献已入库\s*(\d+)\s*条", line)
    if m:
        prog["refs_ok"] = prog.get("refs_ok", 0) + int(m.group(1))
    m = re.search(r"参考文献（--detail-refs）：成功\s*(\d+)\s*篇.*?失败\s*(\d+)\s*篇", line)
    if m:
        prog["refs_ok"] = int(m.group(1))
        prog["refs_failed"] = int(m.group(2))
    return prog


async def _run_cnki_search_background(keyword: str, search_field: str, years: Optional[str],
                                      max_pages: Optional[int], detail_workers: int,
                                      show_browser: bool = False, resume: bool = False,
                                      detail_refs: bool = False):
    """以后端子进程方式复用 cnki_paper_captcha.py --search 检索模式抓取并入库。

    该脚本内置通过 app.crud 写入 paperpulse.db 并记录 CrawlLog（详见其 main / run_search），
    这里只负责用当前 venv 的 python 拉起子进程，等待其结束后记录简要结果。
    show_browser=True 时以 --show-browser 打开浏览器窗口，遇验证码可人工处理。
    resume=True 且存在同关键词断点时，脚本从上次进度续跑（跳过已收集页 / 已入库论文）。
    """
    import asyncio
    global _cnki_search_proc
    _cnki_search_state["running"] = True
    _cnki_search_state["paused"] = False
    _cnki_search_state["keyword"] = keyword
    _cnki_search_state["started_at"] = datetime.now(timezone.utc).isoformat()
    _cnki_search_state["finished_at"] = None
    _cnki_search_state["stopped_by_user"] = False
    _cnki_search_state["progress"] = _empty_cnki_progress()
    _cnki_search_state["last_log"] = []
    _cnki_search_state["message"] = "浏览器窗口模式，遇验证码请在弹出窗口中人工处理" if show_browser else "启动中…"

    script = BASE_DIR.parent / "cnki_paper_captcha.py"
    cmd = [
        sys.executable, str(script), "--search", keyword,
        "--search-field", search_field, "--detail-workers", str(max(1, detail_workers)),
    ]
    if show_browser:
        cmd += ["--show-browser"]
    if detail_refs:
        cmd += ["--detail-refs"]
    if years:
        cmd += ["--years", years]
    if max_pages:
        cmd += ["--max-pages", str(max(int(max_pages), 1))]
    if resume:
        cmd += ["--resume"]
        _cnki_search_state["message"] = "检测到上次进度，从断点续跑…"

    # 建 keyword 类型爬取任务记录：任务面板展示 + 一键重跑需要 rerun_params
    crawl_log_id: Optional[int] = None
    try:
        from app.schemas import CrawlLogCreate
        async with AsyncSessionLocal() as db:
            crawl_log = await CrawlLogCRUD.create_crawl_log(db, CrawlLogCreate(
                journal_name=keyword,
                crawl_start_time=datetime.now(),
                task_type="keyword",
                rerun_params=json.dumps({
                    "search_field": search_field,
                    "years": years,
                    "max_pages": max_pages,
                    "detail_workers": detail_workers,
                    "show_browser": show_browser,
                    "detail_refs": detail_refs,
                }, ensure_ascii=False),
            ))
            await db.commit()
            crawl_log_id = crawl_log.id
    except Exception as e:
        logger.warning(f"Failed to create keyword crawl_log: {e}")

    # 进度/日志在 try 外初始化，保证 finally 回写任务记录时始终可用
    prog = _empty_cnki_progress()
    recent: deque[str] = deque(maxlen=_MAX_STATUS_LOG_LINES)
    proc = None

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(BASE_DIR.parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,  # 独立进程组：暂停/继续用 os.killpg 连浏览器一起停
        )
        _cnki_search_proc = proc

        # 逐行消费 stdout，实时解析进度；只保留最近 N 行日志，避免全量缓冲撑内存。
        # 状态字段都是小对象，每行刷新一次的成本可忽略。
        tail = ""
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            if len(line) > 500:  # 截断超长行（异常堆栈/调试输出），状态保持轻量
                line = line[:500] + "…"
            recent.append(line)
            tail = line
            _parse_cnki_progress(line, prog)
            _cnki_search_state["progress"] = dict(prog)
            _cnki_search_state["last_log"] = list(recent)
        await proc.wait()

        if _cnki_search_state.get("stopped_by_user"):
            _cnki_search_state["message"] = "已停止"
        elif proc.returncode == 0:
            _cnki_search_state["message"] = f"已完成。{tail}" if tail else "已完成。"
        else:
            _cnki_search_state["message"] = f"脚本退出码 {proc.returncode}。尾部输出：{tail}" if tail else f"脚本退出码 {proc.returncode}。"
    except Exception as e:
        logger.error(f"CNKI keyword search subprocess failed: {e}")
        _cnki_search_state["message"] = f"启动失败：{e}"
    finally:
        _cnki_search_proc = None
        _cnki_search_state["paused"] = False
        _cnki_search_state["finished_at"] = datetime.now(timezone.utc).isoformat()
        _cnki_search_state["running"] = False
        if _cnki_search_state.get("stopped_by_user"):
            _cnki_search_state["message"] = "已停止"
            _cnki_search_state["progress"]["phase"] = "stopped"
        # 回写 keyword 任务记录：成功/失败数 + 日志尾部（供任务面板展开查看）
        if crawl_log_id:
            try:
                async with AsyncSessionLocal() as db:
                    await CrawlLogCRUD.update_crawl_log(
                        db, crawl_log_id,
                        crawl_end_time=datetime.now(),
                        papers_fetched=prog.get("ok") if prog else 0,
                        papers_failed=prog.get("failed") if prog else 0,
                        status=("stopped" if _cnki_search_state.get("stopped_by_user")
                                else ("completed" if proc and proc.returncode == 0 else "failed")),
                        log_detail="\n".join(recent) if recent else None,
                    )
                    await db.commit()
            except Exception as e:
                logger.warning(f"Failed to update keyword crawl_log: {e}")


@router.post("/crawl/cnki/search/start")
async def start_cnki_search(body: CNKISearchRequest, token: bool = Depends(verify_token)):
    """按关键词触发知网检索爬取并入库（复用 cnki_paper_captcha.py --search，浏览器窗口模式可人工处理验证码）。"""
    keyword = (body.keyword or "").strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="keyword is required")
    if _cnki_search_state["running"]:
        return {"status": "already_running", "keyword": _cnki_search_state["keyword"]}
    search_field = (body.search_field or "主题").strip() or "主题"
    if search_field not in CNKI_SEARCH_FIELDS:
        raise HTTPException(status_code=400, detail=f"不支持的检索字段: {search_field}，可选: {' / '.join(CNKI_SEARCH_FIELDS)}")
    # 断点自动检测：同关键词存在断点则续跑（跳过已收集页 / 已入库论文），否则从头执行
    ckpt = _read_search_checkpoint()
    resume = bool(ckpt and ckpt.get("keyword") == keyword)
    from app.main import spawn_background_task
    spawn_background_task(_run_cnki_search_background(
        keyword=keyword,
        search_field=search_field,
        years=body.years,
        max_pages=body.max_pages,
        detail_workers=body.detail_workers,
        show_browser=body.show_browser,
        detail_refs=body.detail_refs,
        resume=resume,
    ))
    return {"status": "started", "keyword": keyword, "resumed": resume}


@router.get("/crawl/cnki/search/status")
async def cnki_search_status(token: bool = Depends(verify_token)):
    """关键词爬取任务状态（运行中 / 暂停 / 最近结果 / 断点摘要）。"""
    state = dict(_cnki_search_state)
    ckpt = _read_search_checkpoint()
    state["checkpoint"] = ({
        "keyword": ckpt.get("keyword"),
        "phase": ckpt.get("phase"),
        "page": ckpt.get("page"),
        "papers": len(ckpt.get("papers") or []),
        "saved_at": ckpt.get("saved_at"),
    } if ckpt else None)
    return state


def _cnki_search_signal(sig: signal.Signals):
    """对关键词爬取子进程进程组发送信号（连 Playwright 浏览器一起停/续）。"""
    if not hasattr(signal, "SIGSTOP"):
        raise HTTPException(status_code=400, detail="当前平台不支持暂停/继续")
    proc = _cnki_search_proc
    if not proc or proc.returncode is not None:
        raise HTTPException(status_code=400, detail="当前没有运行中的爬取任务")
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        raise HTTPException(status_code=400, detail="爬取任务已结束")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送信号失败：{e}")


@router.post("/crawl/cnki/search/pause")
async def pause_cnki_search(token: bool = Depends(verify_token)):
    """暂停关键词爬取（SIGSTOP 整个进程组；暂停期间进度冻结，可随时继续）。"""
    _cnki_search_signal(signal.SIGSTOP)
    _cnki_search_state["paused"] = True
    _cnki_search_state["message"] = "已暂停（可随时继续）"
    return {"status": "paused"}


@router.post("/crawl/cnki/search/resume")
async def resume_cnki_search(token: bool = Depends(verify_token)):
    """继续已暂停的关键词爬取（SIGCONT）。"""
    if not _cnki_search_state.get("paused"):
        raise HTTPException(status_code=400, detail="任务未处于暂停状态")
    _cnki_search_signal(signal.SIGCONT)
    _cnki_search_state["paused"] = False
    _cnki_search_state["message"] = "已恢复"
    return {"status": "running"}


@router.post("/crawl/cnki/search/stop")
async def stop_cnki_search(token: bool = Depends(verify_token)):
    """停止关键词爬取：SIGTERM 整个进程组（暂停中先 SIGCONT 再终止），超时 SIGKILL 兜底。"""
    proc = _cnki_search_proc
    if not proc or proc.returncode is not None:
        raise HTTPException(status_code=400, detail="当前没有运行中的爬取任务")
    # 标记为用户主动停止，后台任务收尾时给出明确文案
    _cnki_search_state["stopped_by_user"] = True
    try:
        # 暂停中的进程无法处理信号：先 SIGCONT 让进程组恢复，再 SIGTERM 终止
        os.killpg(proc.pid, signal.SIGCONT)
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止失败：{e}")
    # 等待子进程退出，超时则 SIGKILL 兜底
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            pass
    _cnki_search_state["paused"] = False
    _cnki_search_state["finished_at"] = datetime.now(timezone.utc).isoformat()
    _cnki_search_state["running"] = False
    _cnki_search_state["message"] = "已停止"
    if _cnki_search_state.get("progress"):
        _cnki_search_state["progress"]["phase"] = "stopped"
    return {"status": "stopped"}


# —— 参考文献爬取（task_type=references）：给定论文链接或标题，抓详情页参考文献列表 ——
_refs_state = {
    "running": False,
    "paper_url": None,
    "paper_title": None,
    "started_at": None,
    "finished_at": None,
    "message": None,
    "stopped_by_user": False,
    "progress": None,
    "last_log": [],
}
_refs_proc: Optional[asyncio.subprocess.Process] = None


class ReferencesStartRequest(BaseModel):
    paper_url: Optional[str] = None
    urls: Optional[List[str]] = None       # 批量模式：多个详情页链接（>1 时脚本走 --ref-urls-file）
    paper_title: Optional[str] = None
    max_items: Optional[int] = None
    interval: Optional[float] = None
    show_browser: bool = False             # 显示浏览器窗口（无头模式遇验证码只能自动解，显示窗口可人工处理）


async def _run_references_background(paper_url: Optional[str], paper_title: Optional[str],
                                     max_items: Optional[int], interval: Optional[float] = None,
                                     urls: Optional[List[str]] = None, show_browser: bool = False):
    """参考文献爬取后台任务：spawn cnki_paper_captcha.py --ref-* 子进程并解析进度。"""
    global _refs_proc
    _refs_state["running"] = True
    _refs_state["stopped_by_user"] = False
    _refs_state["paper_url"] = paper_url
    _refs_state["paper_title"] = paper_title
    _refs_state["started_at"] = datetime.now(timezone.utc).isoformat()
    _refs_state["finished_at"] = None
    _refs_state["progress"] = _empty_cnki_progress()
    _refs_state["last_log"] = []
    _refs_state["message"] = "浏览器窗口模式，遇验证码请在弹出窗口中人工处理" if show_browser else "启动中…"

    script = BASE_DIR.parent / "cnki_paper_captcha.py"
    cmd = [sys.executable, str(script)]
    if urls and len(urls) > 1:
        # 批量：写临时清单文件走 --ref-urls-file（脚本逐篇抓取，单篇间隔仍由 --ref-interval 控制）
        cache_dir = BASE_DIR.parent / ".cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        urls_file = cache_dir / f"refs_urls_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
        urls_file.write_text("\n".join(urls), encoding="utf-8")
        cmd += ["--ref-urls-file", str(urls_file)]
    elif urls:
        cmd += ["--ref-paper-url", urls[0]]
    elif paper_url:
        cmd += ["--ref-paper-url", paper_url]
    else:
        cmd += ["--ref-title", paper_title or ""]
    if max_items:
        cmd += ["--ref-max-items", str(max(int(max_items), 1))]
    if interval and float(interval) >= 1:
        cmd += ["--ref-interval", str(float(interval))]
    if show_browser:
        cmd += ["--show-browser"]

    # 建任务记录：任务面板展示 + 重跑参数（paper_url/urls/paper_title/max_items/interval/show_browser）
    crawl_log_id: Optional[int] = None
    try:
        from app.schemas import CrawlLogCreate
        async with AsyncSessionLocal() as db:
            crawl_log = await CrawlLogCRUD.create_crawl_log(db, CrawlLogCreate(
                journal_name=(paper_title or (urls[0] if urls else paper_url) or "参考文献爬取")[:200],
                crawl_start_time=datetime.now(),
                task_type="references",
                rerun_params=json.dumps({
                    "paper_url": paper_url,
                    "urls": urls,
                    "paper_title": paper_title,
                    "max_items": max_items,
                    "interval": interval,
                    "show_browser": show_browser,
                }, ensure_ascii=False),
            ))
            await db.commit()
            crawl_log_id = crawl_log.id
    except Exception as e:
        logger.warning(f"Failed to create references crawl_log: {e}")

    prog = _empty_cnki_progress()
    recent: deque[str] = deque(maxlen=_MAX_STATUS_LOG_LINES)
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(BASE_DIR.parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        _refs_proc = proc
        tail = ""
        refs_done_total = 0  # 已完成篇目的入库条目总和（配合单篇「累计 N 条」跨篇累加）
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            if len(line) > 500:
                line = line[:500] + "…"
            recent.append(line)
            tail = line
            _parse_cnki_progress(line, prog)
            # 参考文献模式日志解析：`参考文献 第 X 页获取 Y 条（新增 Z），累计 N 条`。
            # 「累计 N 条」是单篇内计数：用已完成篇目的入库条目总和做跨篇累加，
            # 保证前端「累计条目」随批量任务单调递增而不回跳。
            m_page = re.search(r"参考文献\s*第\s*(\d+)\s*页", line)
            if m_page:
                prog["page"] = int(m_page.group(1))
            m_saved = re.search(r"参考文献已入库\s*(\d+)\s*条", line)
            if m_saved:
                refs_done_total += int(m_saved.group(1))
            m_total = re.search(r"累计\s*(\d+)\s*条", line)
            if m_total:
                prog["collected"] = refs_done_total + int(m_total.group(1))
            m_all = re.search(r"共入库参考文献\s*(\d+)\s*条", line)
            if m_all:
                prog["collected"] = int(m_all.group(1))
            if "参考文献入库失败" in line:
                prog["refs_failed"] = prog.get("refs_failed", 0) + 1
            _refs_state["progress"] = dict(prog)
            _refs_state["last_log"] = list(recent)
        await proc.wait()

        if _refs_state.get("stopped_by_user"):
            _refs_state["message"] = "已停止"
        elif proc.returncode == 0:
            _refs_state["message"] = f"已完成。{tail}" if tail else "已完成。"
        else:
            _refs_state["message"] = f"脚本退出码 {proc.returncode}。尾部输出：{tail}" if tail else f"脚本退出码 {proc.returncode}。"
    except Exception as e:
        logger.error(f"References crawl subprocess failed: {e}")
        _refs_state["message"] = f"启动失败：{e}"
    finally:
        _refs_proc = None
        _refs_state["finished_at"] = datetime.now(timezone.utc).isoformat()
        _refs_state["running"] = False
        if _refs_state.get("stopped_by_user"):
            _refs_state["message"] = "已停止"
            if _refs_state.get("progress"):
                _refs_state["progress"]["phase"] = "stopped"
        if crawl_log_id:
            try:
                async with AsyncSessionLocal() as db:
                    await CrawlLogCRUD.update_crawl_log(
                        db, crawl_log_id,
                        crawl_end_time=datetime.now(),
                        papers_fetched=prog.get("collected") if prog else 0,
                        papers_failed=prog.get("failed") if prog else 0,
                        status=("stopped" if _refs_state.get("stopped_by_user")
                                else ("completed" if proc and proc.returncode == 0 else "failed")),
                        log_detail="\n".join(recent) if recent else None,
                    )
                    await db.commit()
            except Exception as e:
                logger.warning(f"Failed to update references crawl_log: {e}")


@router.post("/crawl/references/start")
async def start_references_crawl(body: ReferencesStartRequest, token: bool = Depends(verify_token)):
    """触发参考文献爬取：链接（单个/批量）直接抓，或给标题检索定位（默认取第一条结果）。"""
    paper_url = (body.paper_url or "").strip() or None
    paper_title = (body.paper_title or "").strip() or None
    urls = [u.strip() for u in (body.urls or []) if u.strip()] or None
    if paper_url and not paper_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="paper_url 需以 http(s):// 开头")
    if urls and any(not u.startswith(("http://", "https://")) for u in urls):
        raise HTTPException(status_code=400, detail="批量链接需每行都以 http(s):// 开头")
    if not paper_url and not urls and not paper_title:
        raise HTTPException(status_code=400, detail="paper_url、urls 与 paper_title 至少填一个")
    if _refs_state["running"]:
        return {"status": "already_running", "paper_title": _refs_state["paper_title"]}
    from app.main import spawn_background_task
    spawn_background_task(_run_references_background(
        paper_url=paper_url,
        paper_title=paper_title,
        max_items=body.max_items,
        interval=body.interval,
        urls=urls,
        show_browser=body.show_browser,
    ))
    return {"status": "started"}


@router.get("/crawl/references/status")
async def references_crawl_status(token: bool = Depends(verify_token)):
    """参考文献爬取任务状态。"""
    return dict(_refs_state)


@router.post("/crawl/references/stop")
async def stop_references_crawl(token: bool = Depends(verify_token)):
    """停止参考文献爬取（SIGTERM 进程组，超时 SIGKILL 兜底）。"""
    proc = _refs_proc
    if not proc or proc.returncode is not None:
        raise HTTPException(status_code=400, detail="当前没有运行中的参考文献爬取任务")
    _refs_state["stopped_by_user"] = True
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止失败：{e}")
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            pass
    _refs_state["finished_at"] = datetime.now(timezone.utc).isoformat()
    _refs_state["running"] = False
    _refs_state["message"] = "已停止"
    if _refs_state.get("progress"):
        _refs_state["progress"]["phase"] = "stopped"
    return {"status": "stopped"}


class ReferencesBackfillRequest(BaseModel):
    limit: Optional[int] = 30          # 本轮补抓篇数（1-200）
    max_items: Optional[int] = None    # 每篇最多抓多少条参考文献
    interval: Optional[float] = None   # 单篇间隔秒数（防封控）


@router.post("/crawl/references/backfill")
async def backfill_references_crawl(body: ReferencesBackfillRequest, db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    """智能批量补抓：自动选出「未抓取过参考文献」的论文队列（按 置顶 > 收藏 > 已读 > 综合评分 优先），
    复用 references 后台任务逐篇抓取。解决手动单篇触发覆盖率永远起不来的问题。"""
    if _refs_state["running"]:
        return {"status": "already_running", "paper_title": _refs_state["paper_title"]}

    from sqlalchemy import select as sa_select, func as sa_func, case as sa_case
    from app.models import Paper, PaperScore, PaperReference, PinnedPaper, Favorite, ReadingHistory

    limit = max(1, min(int(body.limit or 30), 200))

    # 未抓取过的论文（paper_references 覆盖式写入，distinct paper_url 即已抓集合）
    refs_url = sa_select(PaperReference.paper_url).distinct().scalar_subquery()
    priority = sa_case(
        (sa_select(PinnedPaper.id).where(PinnedPaper.paper_id == Paper.id).limit(1).exists(), 3),
        (sa_select(Favorite.id).where(Favorite.paper_id == Paper.id).limit(1).exists(), 2),
        (sa_select(ReadingHistory.id).where(ReadingHistory.paper_id == Paper.id).limit(1).exists(), 1),
        else_=0,
    ).label("priority")
    rows = (await db.execute(
        sa_select(Paper.id, Paper.url, Paper.title, priority, PaperScore.final_score)
        .outerjoin(PaperScore, PaperScore.paper_id == Paper.id)
        .where(Paper.url.isnot(None), Paper.url != "", ~Paper.url.in_(refs_url))
        .order_by(priority.desc(), sa_func.coalesce(PaperScore.final_score, 0).desc(), Paper.published_at.desc())
        .limit(limit)
    )).fetchall()

    urls = [r[1] for r in rows if r[1]]
    if not urls:
        return {"status": "empty", "message": "没有需要补抓的论文（全库已覆盖或论文无有效链接）"}

    from app.main import spawn_background_task
    spawn_background_task(_run_references_background(
        paper_url=None, paper_title=f"智能补抓（{len(urls)} 篇）",
        max_items=body.max_items, interval=body.interval, urls=urls,
    ))
    return {"status": "started", "queued": len(urls)}


@router.get("/crawl/references/coverage")
async def references_coverage(db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    """参考文献覆盖率：已抓取论文数 / 有效链接论文总数（系统页展示用）。"""
    from sqlalchemy import select as sa_select, func as sa_func
    from app.models import Paper, PaperReference

    with_refs = (await db.execute(
        sa_select(sa_func.count(sa_func.distinct(PaperReference.paper_url)))
    )).scalar() or 0
    total = (await db.execute(
        sa_select(sa_func.count(Paper.id)).where(Paper.url.isnot(None), Paper.url != "")
    )).scalar() or 0
    return {"papers_with_refs": int(with_refs), "papers_total": int(total)}


class CrawlRerunRequest(BaseModel):
    log_id: int


@router.post("/crawl/rerun")
async def rerun_crawl(body: CrawlRerunRequest, db: AsyncSession = Depends(get_db), token: bool = Depends(verify_token)):
    """一键重跑爬取任务：按 task_type 分派（keyword→关键词检索；journal→期刊调度爬取）。"""
    log = await CrawlLogCRUD.get_crawl_log_by_id(db, body.log_id)
    if not log:
        raise HTTPException(status_code=404, detail="爬取任务不存在")
    ttype = log.task_type or "journal"
    if ttype == "keyword":
        if _cnki_search_state["running"]:
            raise HTTPException(status_code=400, detail="已有关键词爬取任务在运行")
        params: dict = {}
        try:
            params = json.loads(log.rerun_params or "{}")
        except Exception:
            params = {}
        from app.main import spawn_background_task
        # 断点自动检测：同关键词存在断点则从上次进度续跑
        ckpt = _read_search_checkpoint()
        resume = bool(ckpt and ckpt.get("keyword") == log.journal_name)
        spawn_background_task(_run_cnki_search_background(
            keyword=log.journal_name,
            search_field=params.get("search_field") or "主题",
            years=params.get("years"),
            max_pages=params.get("max_pages"),
            detail_workers=int(params.get("detail_workers") or 3),
            show_browser=bool(params.get("show_browser", False)),
            detail_refs=bool(params.get("detail_refs", False)),
            resume=resume,
        ))
        return {"status": "started", "task_type": "keyword", "name": log.journal_name, "resumed": resume}
    if ttype == "references":
        if _refs_state["running"]:
            raise HTTPException(status_code=400, detail="已有参考文献爬取任务在运行")
        params: dict = {}
        try:
            params = json.loads(log.rerun_params or "{}")
        except Exception:
            params = {}
        from app.main import spawn_background_task
        spawn_background_task(_run_references_background(
            paper_url=params.get("paper_url"),
            paper_title=params.get("paper_title") or log.journal_name,
            max_items=params.get("max_items"),
            interval=params.get("interval"),
            urls=params.get("urls"),
            show_browser=bool(params.get("show_browser", False)),
        ))
        return {"status": "started", "task_type": "references", "name": log.journal_name}
    # journal 类型：调度器按期刊重跑
    from app.main import scheduler
    try:
        task_id = await scheduler.trigger_manual_crawl([log.journal_name])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "started", "task_type": "journal", "name": log.journal_name, "task_id": task_id}


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


@router.post("/maintenance/backfill-abstracts")
async def backfill_abstracts(token: bool = Depends(verify_token)):
    """手动触发空摘要补抓任务（经济研究/中国工业经济，P0-2）。"""
    from app.main import scheduler
    busy = scheduler._find_running_task("backfill_abstracts")
    if busy:
        raise HTTPException(status_code=400, detail=f"摘要补抓任务已在进行中（{busy[:8]}…），请等待完成")
    try:
        task_id = await scheduler.trigger_manual_backfill()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "started", "task_id": task_id}


@router.get("/maintenance/backfill-abstracts")
async def backfill_abstracts_status(token: bool = Depends(verify_token)):
    """查询空摘要补抓任务状态。"""
    from app.main import scheduler
    tasks = {
        tid: info for tid, info in scheduler.active_crawl_tasks.items()
        if info.get("task_type") == "backfill_abstracts"
    }
    return {"tasks": tasks}


