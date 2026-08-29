"""交互式登录：打开有头浏览器让用户手动登录知网，回车保存会话态供后续所有模式复用。

只保存 cookies（storage_state），不保存账号密码；`.cache/` 与 `cnki_state.json`
已在 .gitignore 中，不会进版本库。
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from cnki_crawler.paths import CNKI_STATE_FILE, ensure_cache_dir
from cnki_crawler.browser import _launch_kwargs
from cnki_crawler.navigation import navigate, wait_cnki_host


async def interactive_login(state_path: Path, timeout: int = 600) -> int:
    """交互式登录。返回退出码（0 成功 / 1 失败）。

    流程：已有会话态先确认是否覆盖（默认保留，直接成功退出）→ 打开有头浏览器进知网
    首页 → 用户手动登录（扫码/账密）→ 回终端按回车 → 保存 storage_state。
    """
    ensure_cache_dir()
    print(f"登录后会将会话态保存到: {state_path}")
    if state_path.exists():
        ans = await asyncio.to_thread(input, "检测到已有会话态，是否覆盖？[y/N] ")
        if ans.strip().lower() not in ('y', 'yes'):
            print("保留已有会话态，退出。")
            return 0

    print("正在启动浏览器（有头模式）...")
    playwright = await async_playwright().start()
    browser = None
    try:
        browser = await playwright.chromium.launch(**_launch_kwargs(headless=False))
        context = await browser.new_context(locale='zh-CN', timezone_id='Asia/Shanghai')
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN','zh','en'] });
            window.chrome = { runtime: {} };
        """)
        page = await context.new_page()
        await navigate(page, 'https://www.cnki.net/', headless=False, solver=None)
        await wait_cnki_host(page)
        print("请在浏览器中完成知网登录（扫码或账密），完成后回到终端按回车...")
        await asyncio.to_thread(input, "")
        state_path.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(state_path))
        print(f"✓ 会话态已保存: {state_path}")
        return 0
    except Exception as e:
        print(f"✗ 登录流程失败: {e}")
        return 1
    finally:
        try:
            if browser is not None:
                await browser.close()
        except Exception:
            pass
        try:
            await playwright.stop()
        except Exception:
            pass
