"""请求上下文与日志过滤：把 request_id / user_id 注入到每一条日志记录。

中间件在每个请求开始时 set_request_context() 写入 contextvars，
Logging 的 RequestIdFilter 负责把它们填入 LogRecord 的 request_id/user_id 字段，
供格式化器输出（日志格式里带 req=... uid=...）。这样同一请求的所有日志（含
AI 服务、调度器、爬虫等子模块）都能串起来排查。
"""
import logging
import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
user_id_var: ContextVar[str] = ContextVar("user_id", default="-")


def set_request_context(request_id: str, user_id: str):
    request_id_var.set(request_id)
    user_id_var.set(user_id)


def get_request_id() -> str:
    return request_id_var.get()


def get_user_id() -> str:
    return user_id_var.get()


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


class RequestIdFilter(logging.Filter):
    """给 LogRecord 注入 request_id / user_id（缺省 "-"），供格式器使用。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get()
        return True
