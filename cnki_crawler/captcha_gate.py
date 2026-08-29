"""统一验证码闸：URL /verify 判定 + 弹窗判定 + 自动解决 + 手动等待 + 熔断上报。

取代原脚本里割裂的两套实现：
- `JournalCrawler.wait_for_page_stable`：只判 URL /verify，headless 撞验证页不
  `_report_captcha`（熔断几乎不触发，后续请求仍按 1.5s 基础间隔猛发）；
- `KeywordSearchCrawler._ensure_no_captcha`：判 URL + 弹窗，但只在检索流程使用。

统一后的 `wait_clean` 对「URL /verify」与「不改变 URL 的弹窗/遮罩」都判定：
循环自动解决（滑块/点选）→ 非无头时提示手动完成并轮询 → 超时上报熔断并返回 False。
"""
import asyncio

from cnki_crawler.pacing import _report_captcha
from cnki_crawler.parsing import VERIFY_URL_PREFIX

# 验证码弹窗/遮罩检测（不改变 URL 时的滑块 iframe 等，选择器需精确，避免误命中结果页普通元素）
CAPTCHA_POPUP_SELECTORS = [
    '//iframe[contains(@src,"captcha") or contains(@src,"verify") or contains(@src,"nc_") or contains(@src,"yidun")]',
    '//div[contains(@class,"verify-slide") or contains(@class,"verify-slider")]',
    '//div[contains(@class,"nc-container") or contains(@class,"yidun")]',
    '//div[@id="captcha"]',
]


def is_verify_url(url: str) -> bool:
    """是否命中知网 /verify 安全验证页（URL 判定）。"""
    return bool(url) and VERIFY_URL_PREFIX in url


async def popup_visible(page) -> bool:
    """检测不改变 URL 的验证码弹窗/遮罩。"""
    for sel in CAPTCHA_POPUP_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            continue
    return False


async def wait_clean(page, *, tag: str = "", timeout: int = 180,
                     headless: bool, solver) -> bool:
    """确保当前页面无安全验证；成功返回 True，超时/无解时上报熔断并返回 False。

    循环：URL /verify 或弹窗任一存在 → 自动解决（滑块/点选；无头下每次循环重试，
    直到成功或超时）→ 非无头时提示手动完成并轮询 → 超时 `_report_captcha` 后返回 False。
    """
    start = asyncio.get_event_loop().time()
    prompted = False
    noticed = False
    while True:
        url_verify = is_verify_url(page.url)
        popup = await popup_visible(page)
        if not url_verify and not popup:
            if prompted:
                print(f"{tag} ✓ 安全验证已通过")
            return True
        if not noticed:
            noticed = True
            print(f"{tag} ⚠ 遇到安全验证")
        if asyncio.get_event_loop().time() - start > timeout:
            print(f"{tag} 等待安全验证超时")
            _report_captcha(tag=tag)
            return False
        # 优先尝试自动解决
        if solver and solver.is_available():
            try:
                ctype = await solver.detect_captcha_type(page)
                ok = False
                if ctype == 'slider':
                    ok = await solver.solve_slider_captcha(page)
                elif ctype == 'click':
                    ok = await solver.solve_click_captcha(page)
                if ok:
                    continue
            except Exception:
                pass
        if not prompted and not headless:
            print(f"{tag} 请在浏览器中手动完成安全验证/滑块...")
            prompted = True
        await asyncio.sleep(1.5)
