"""统一日志配置：控制台（stderr）+ 可选滚动文件（RotatingFileHandler）。

所有模块都通过 stdlib logging.getLogger(__name__) 打日志，这里只需配置根
logger 一次即可全局生效（含 AI 服务、调度器、爬虫）。每条日志都带
request_id/user_id（来自 app.log_context），便于按请求串联排查。
"""
import logging
import logging.config
from pathlib import Path

from app.config import settings
from app.log_context import RequestIdFilter

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | req=%(request_id)s uid=%(user_id)s | %(name)s | %(message)s"


def setup_logging():
    """按 Settings 配置根 logger。幂等：重复调用会按最新配置重建 handler。"""
    level = (settings.log_level or "INFO").strip().upper()
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        level = "INFO"

    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stderr",
            # 过滤器挂在 handler 上：对经手的所有记录（含子 logger 传播上来的）
            # 统一注入 request_id/user_id，避免子 logger 没有根级 filter 导致格式化 KeyError
            "filters": ["request_context"],
        },
    }
    if settings.log_file_enabled:
        path = Path(settings.log_file_path or "data/logs/app.log")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(path),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "default",
            "filters": ["request_context"],
        }

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": _LOG_FORMAT,
            },
        },
        "filters": {
            "request_context": {
                "()": RequestIdFilter,
            },
        },
        "handlers": handlers,
        "root": {
            "level": level,
            "handlers": list(handlers.keys()),
        },
    })
