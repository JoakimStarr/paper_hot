"""进程内 TTL 缓存（PERF_PLAN §2.2）：聚合类接口短缓存，避免每次请求重复聚合。"""
import time
from typing import Any, Awaitable, Callable

_store: dict[str, tuple[float, Any]] = {}


async def ttl_cache(key: str, ttl_seconds: int, compute: Callable[[], Awaitable[Any]]) -> Any:
    """按 key 缓存协程结果；TTL 内直接命中。进程重启即失效（可接受）。"""
    now = time.time()
    hit = _store.get(key)
    if hit and now - hit[0] < ttl_seconds:
        return hit[1]
    val = await compute()
    _store[key] = (now, val)
    return val


def invalidate(prefix: str = "") -> None:
    """前缀失效（预留：爬虫入库后可调用）。"""
    for k in [k for k in _store if k.startswith(prefix)]:
        _store.pop(k, None)
