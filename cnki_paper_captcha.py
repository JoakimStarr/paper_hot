#!/usr/bin/env python
"""知网爬虫薄入口。

逻辑已迁至 `cnki_crawler/` 包（见其 README/模块注释），本文件只做路径引导与启动。
**保持「脚本名与位置不变」硬契约**：后端 `backend/app/routers/crawler.py` 直接以
`sys.executable cnki_paper_captcha.py` 在仓库根 spawn 本文件，cwd 必须仍是仓库根。

用法:
    python cnki_paper_captcha.py --show-browser
    python cnki_paper_captcha.py --threads 3
    python cnki_paper_captcha.py --search "新质生产力" --show-browser
    python cnki_paper_captcha.py --ref-paper-url "https://kns.cnki.net/kcms2/article/abstract?..."
    python cnki_paper_captcha.py --ref-urls-file .cache/urls.txt --ref-max-items 200
    python cnki_paper_captcha.py --ref-title "论文标题"
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cnki_crawler.cli import main  # noqa: E402

if __name__ == '__main__':
    asyncio.run(main())
