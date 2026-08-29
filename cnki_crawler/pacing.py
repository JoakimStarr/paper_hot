"""全局请求节流 + 验证码熔断（跨浏览器 / 跨 tab 共享，进程内单例）。

核心思想：无论开多少个浏览器/tab，全局「导航」速率被令牌桶锁死，
避免聚合请求率过高触发知网风控；验证码连续出现时熔断翻倍并短暂停顿。
"""
import asyncio
import time

PACING_BASE_INTERVAL = 1.5       # 全局最小导航间隔（秒）
PACING_MAX_INTERVAL = 8.0        # 熔断后间隔上限
CIRCUIT_BREAKER_WINDOW = 60      # 熔断计数窗口（秒）
CIRCUIT_BREAKER_THRESHOLD = 2    # 窗口内出现几次验证码即熔断
CIRCUIT_BREAKER_COOLDOWN = 15    # 熔断时额外停顿（秒）
PACING_DECAY_FACTOR = 0.5        # 安静期后间隔衰减系数
PACING_DECAY_AFTER = 180         # 多久无验证码后开始衰减（秒）

_pacing = {
    'interval': PACING_BASE_INTERVAL,
    'next_token': 0.0,            # time.monotonic() 时间戳
    'cooldown_until': 0.0,
    'captcha_times': [],          # 窗口内验证码时间戳（time.monotonic()）
}


async def _pacing_wait():
    """全局导航闸：单事件循环内同步 check-and-set，保证全局导航间隔。"""
    loop = asyncio.get_event_loop()
    # 静默期衰减（间隔向基础值回落）
    if _pacing['captcha_times']:
        latest = max(_pacing['captcha_times'])
        if time.monotonic() - latest > PACING_DECAY_AFTER and _pacing['interval'] > PACING_BASE_INTERVAL:
            _pacing['interval'] = max(PACING_BASE_INTERVAL, _pacing['interval'] * PACING_DECAY_FACTOR)
    while True:
        now = time.monotonic()
        # 熔断冷却：额外停顿
        if now < _pacing['cooldown_until']:
            await asyncio.sleep(_pacing['cooldown_until'] - now)
            continue
        if now >= _pacing['next_token']:
            _pacing['next_token'] = now + _pacing['interval']
            return
        await asyncio.sleep(_pacing['next_token'] - now)


def _report_captcha(tag: str = ""):
    """记录一次验证码事件；窗口内达到阈值则熔断（间隔翻倍 + 冷却）。"""
    now = time.monotonic()
    _pacing['captcha_times'] = [t for t in _pacing['captcha_times'] if now - t < CIRCUIT_BREAKER_WINDOW]
    _pacing['captcha_times'].append(now)
    if len(_pacing['captcha_times']) >= CIRCUIT_BREAKER_THRESHOLD:
        new_int = min(_pacing['interval'] * 2, PACING_MAX_INTERVAL)
        if new_int != _pacing['interval']:
            print(f"  [熔断{tag}] {CIRCUIT_BREAKER_WINDOW}s 内 {len(_pacing['captcha_times'])} 次验证码，"
                  f"全局导航间隔 {_pacing['interval']}s -> {new_int}s")
            _pacing['interval'] = new_int
        _pacing['captcha_times'] = []
        _pacing['cooldown_until'] = now + CIRCUIT_BREAKER_COOLDOWN
        print(f"  [熔断{tag}] 全部爬取暂停 {CIRCUIT_BREAKER_COOLDOWN}s 冷却")
