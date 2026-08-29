"""日志模块：统一前缀 + 行缓冲。

根因修复：后端以 `stdout=PIPE` spawn 本脚本，Python 对非 TTY 的 stdout 用 8KB 块缓冲，
导致进度面板不实时（攒够一批才刷一次）。`setup()` 在 cli 启动时调用一次，
把 stdout 改为行缓冲，进度行即刻可达后端解析。

进度文案不走本模块（它们经 progress.py 直接 print，由后端正则锁定）。
本模块服务于排查用的普通日志。
"""
import logging
import sys

_LOG_FORMAT = "%(asctime)s｜%(levelname)-5s｜%(stage)-8s｜%(threadName)s｜%(message)s"
_DATEFMT = "%H:%M:%S"


def setup(level: int = logging.INFO) -> logging.Logger:
    """初始化日志：行缓冲 + 统一格式。cli 启动时调用一次，幂等。"""
    try:
        # Python 3.7+：把管道 stdout 改为行缓冲，进度行实时到达后端解析器
        sys.stdout.reconfigure(line_buffering=True, encoding='utf-8', errors='replace')
    except Exception:
        pass
    logger = logging.getLogger('cnki_crawler')
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATEFMT))
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def get_logger(stage: str = '') -> logging.LoggerAdapter:
    """返回带阶段前缀的 LoggerAdapter（stage 取 journal / search / refs / login）。"""
    logger = logging.getLogger('cnki_crawler')
    return logging.LoggerAdapter(logger, {'stage': stage})
