"""统一验证码闸 wait_clean 的单元测试（fake page，不联网）。"""
import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cnki_crawler import captcha_gate  # noqa: E402


class _Loc:
    def __init__(self, visible):
        self._visible = visible

    async def count(self):
        return 1 if self._visible else 0

    async def is_visible(self):
        return self._visible


class _First:
    def __init__(self, visible):
        self._loc = _Loc(visible)

    async def count(self):
        return await self._loc.count()

    async def is_visible(self):
        return await self._loc.is_visible()


class _PageLocator:
    def __init__(self, visible):
        self.first = _First(visible)


class FakePage:
    """最小 Page 桩：`.url` 属性 + `locator(sel).first.{count,is_visible}`。"""

    def __init__(self, url="https://kns.cnki.net/kcms2/...", popup=False):
        self.url = url
        self._popup = popup

    def locator(self, sel):
        return _PageLocator(self._popup)


class _Solver:
    """可注入的验证码解决器桩。"""

    def __init__(self, available=True, kind="slider", ok=True):
        self._available = available
        self._kind = kind
        self._ok = ok
        self.calls = []

    def is_available(self):
        return self._available

    async def detect_captcha_type(self, page):
        self.calls.append("detect")
        return self._kind

    async def solve_slider_captcha(self, page):
        self.calls.append("slider")
        return self._ok

    async def solve_click_captcha(self, page):
        self.calls.append("click")
        return self._ok


def test_is_verify_url():
    assert captcha_gate.is_verify_url("https://kns.cnki.net/verify/?code=x")
    assert not captcha_gate.is_verify_url("https://kns.cnki.net/kcms2/...")
    assert not captcha_gate.is_verify_url("")


def test_wait_clean_clean_page_ok():
    page = FakePage()
    solver = _Solver()
    ok = asyncio.run(captcha_gate.wait_clean(page, tag="[t]", timeout=1,
                                             headless=True, solver=solver))
    assert ok is True
    assert solver.calls == []


def test_wait_clean_verify_url_solved():
    # /verify 页面：自动解决成功一次后页面恢复 → 通过
    class _SwitchPage(FakePage):
        def __init__(self):
            super().__init__(url="https://kns.cnki.net/verify/?code=x")
            self.solved = False

        @property
        def url(self):
            return "https://kns.cnki.net/kcms2/..." if self.solved else "https://kns.cnki.net/verify/?code=x"

        @url.setter
        def url(self, v):
            pass

    page = _SwitchPage()
    solver = _Solver(ok=True)
    original = solver.solve_slider_captcha

    async def _auto_solve_wrapper():
        async def solving(pg):
            ok = await original(pg)
            page.solved = True
            return ok
        solver.solve_slider_captcha = solving
        return await captcha_gate.wait_clean(page, tag="[t]", timeout=3,
                                             headless=True, solver=solver)

    assert asyncio.run(_auto_solve_wrapper()) is True


def test_wait_clean_headless_timeout_reports_breaker(monkeypatch):
    # 无头 + 自动解失败 → 轮询到超时 → False 且上报熔断
    page = FakePage(url="https://kns.cnki.net/verify/?code=x")
    solver = _Solver(ok=False)
    reported = []

    monkeypatch.setattr(captcha_gate, "_report_captcha", lambda tag="": reported.append(tag))
    start = time.monotonic()
    ok = asyncio.run(captcha_gate.wait_clean(page, tag="[t]", timeout=1,
                                             headless=True, solver=solver))
    assert ok is False
    assert reported, "headless 超时应上报熔断"
    assert time.monotonic() - start >= 1.0


def test_wait_clean_popup_solver_unavailable(monkeypatch):
    # 弹窗验证码存在且 solver 不可用：headless 超时失败（上报熔断）
    page = FakePage(popup=True)
    solver = _Solver(available=False)
    reported = []
    monkeypatch.setattr(captcha_gate, "_report_captcha", lambda tag="": reported.append(tag))
    ok = asyncio.run(captcha_gate.wait_clean(page, tag="[t]", timeout=1,
                                             headless=True, solver=solver))
    assert ok is False
    assert reported
