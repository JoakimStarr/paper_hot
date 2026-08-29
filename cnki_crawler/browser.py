"""浏览器启动辅助：统一的启动参数 + 系统浏览器通道探测。

说明：BrowserSession 的抽取（init_browser / close_browser / storage_state / 反检测
指纹）在后续阶段从 Crawler 基类中收敛进来；目前这里只放纯函数。
"""


def _launch_kwargs(headless: bool) -> dict:
    """统一的浏览器启动参数（多处启动点共用）。

    移除了 --disable-web-security / --disable-features=IsolateOrigins 等
    非必需且可能被检测的 flag，仅保留稳定性必需的参数。
    """
    kwargs = {
        'headless': headless,
        'args': [
            '--no-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',
        ]
    }
    # 优先复用系统已安装的浏览器（Windows 用 Edge，Linux 用 Chrome），避免下载自带内核
    channel = detect_browser_channel()
    if channel:
        kwargs['channel'] = channel
    return kwargs


def detect_browser_channel():
    """检测可用的系统浏览器，返回 playwright channel 名；都没有则返回 None。

    优先复用本机已安装的浏览器，避免下载 Playwright 自带内核：
    - Windows: 使用系统 Edge（channel='msedge'）
    - Linux:   使用系统 Chrome（channel='chrome'）
    """
    import os
    import shutil
    if os.name == 'nt':
        # Windows 下 Edge 几乎必然存在
        edge_path = shutil.which('msedge')
        if not edge_path:
            candidates = [
                r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
            ]
            edge_path = next((p for p in candidates if os.path.exists(p)), None)
        if edge_path:
            return 'msedge'
    else:
        # Linux / macOS：优先 Chrome，其次 Edge
        if shutil.which('google-chrome') or shutil.which('google-chrome-stable'):
            return 'chrome'
        if shutil.which('microsoft-edge') or shutil.which('microsoft-edge-stable'):
            return 'msedge'
    return None
