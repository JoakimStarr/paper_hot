"""统一导航：过全局闸 → goto → 验证码清理。收口全部 page.goto 调用点。

原脚本 11 处 goto 各自为政：有的过闸无验证码判定（warmup / fetch_journals /
回首页 / _locate_paper_by_title），有的双重风控（ReferenceCrawler.run），
有的根本不进闸。统一后每一处都是同一套「pacing_wait → goto → wait_clean」。
"""
import asyncio

from cnki_crawler.pacing import _pacing_wait
from cnki_crawler.captcha_gate import wait_clean


async def wait_cnki_host(page, rounds: int = 90, sleep: float = 2.0) -> bool:
    """等待页面落到 cnki.net 域（首页直连被风控拦截时 goto 可能落到其它域）。"""
    for _ in range(rounds):
        if 'cnki.net' in page.url:
            return True
        await asyncio.sleep(sleep)
    return False


async def navigate(page, url, *, tag: str = "", wait_until: str = 'domcontentloaded',
                   timeout: int = 60000, gate: bool = True,
                   headless: bool = True, solver=None,
                   captcha_timeout: int = 180) -> bool:
    """统一导航：全局闸 → goto → 验证码清理。

    - gate=False：跳过全局闸（验证码重试等场景）；
    - solver=None：跳过验证码清理（仅暖场/回首页等轻量页面可用，页面稳定由调用方负责）；
    - 返回 False：验证码在 captcha_timeout 内未解决（调用方自行处理）。
    """
    if gate:
        await _pacing_wait()
    await page.goto(url, wait_until=wait_until, timeout=timeout)
    if solver is not None:
        return await wait_clean(page, tag=tag, timeout=captcha_timeout,
                                headless=headless, solver=solver)
    return True
