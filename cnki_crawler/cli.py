"""命令行入口：argparse + main（薄入口脚本 cnki_paper_captcha.py 委托到这里）。

保持与后端 backend/app/routers/crawler.py 的 spawn 契约完全一致：
参数名/语义、退出码、stdout 进度文案。
"""
import argparse
import asyncio
import re
import sys
from pathlib import Path

from cnki_crawler.paths import CACHE_DIR, CNKI_STATE_FILE, ensure_cache_dir
from cnki_crawler.parsing import CNKI_SEARCH_FIELDS
from cnki_crawler.logging_setup import setup as _setup_logging
from cnki_crawler.captcha_solver import probe as _probe_ocr
from cnki_crawler.crawlers import (
    KeywordSearchCrawler,
    MultiThreadedCrawler,
    ReferenceCrawler,
)



async def main():
    # 行缓冲（进度面板实时）+ 统一日志前缀；原单文件脚本在模块顶层做，这里收口成显式调用
    _setup_logging()
    # 可选 OCR 依赖探测 + .cache 目录准备
    _probe_ocr()
    ensure_cache_dir()
    # allow_abbrev=False：杜绝 --ref-paper 这类前缀缩写被静默当作 --ref-paper-url
    # （历史上会把「标题」当 URL 传给 page.goto，报 Cannot navigate to invalid URL）
    parser = argparse.ArgumentParser(
        description='知网爬虫 - 验证码自动解决版本（按期刊 / 按关键词检索 / 参考文献抓取）',
        allow_abbrev=False)
    parser.add_argument('--show-browser', action='store_true', help='显示浏览器窗口（默认不显示）')
    parser.add_argument('--threads', type=int, default=3, help='期刊收集阶段的并发浏览器数（默认3）')
    parser.add_argument('--search', type=str, default=None,
                        help='按关键词/主题检索知网并入库（启用检索模式，替代按期刊爬取）')
    parser.add_argument('--search-field', type=str, default='主题',
                        help=f'检索字段（可选：{" / ".join(CNKI_SEARCH_FIELDS)}，默认主题）')
    parser.add_argument('--max-pages', type=int, default=None,
                        help='检索模式最大翻页数（不设则翻到最后一页）')
    parser.add_argument('--years', type=str, default=None,
                        help='年份区间，如 2024-2026（仅检索模式，按结果行年份过滤，可选）')
    parser.add_argument('--no-login-state', action='store_true',
                        help='禁用登录态复用（默认自动复用 .cache/cnki_state.json）')
    parser.add_argument('--login', action='store_true',
                        help='交互式登录：打开有头浏览器让用户手动登录知网，回车后保存会话态到 .cache/cnki_state.json 供后续复用')
    parser.add_argument('--state-file', type=str, default=None,
                        help='自定义会话态文件路径（多进程并发爬取时各自隔离，避免并发写损坏；默认 .cache/cnki_state.json）')
    parser.add_argument('--urls-only', action='store_true',
                        help='只收集论文 URL 写入文件，不抓详情入库（仅检索模式）')
    parser.add_argument('--urls-file', type=str, default=None,
                        help='URL 输出文件路径（默认 .cache/urls.txt，配合 --urls-only）')
    parser.add_argument('--search-url', type=str, default=None,
                        help='直接复用已保存的检索结果页 URL（传完整URL，或传含URL的文本文件路径）')
    parser.add_argument('--save-url-file', type=str, default=None,
                        help='检索结果页 URL 保存路径（默认 .cache/search_url.txt）')
    parser.add_argument('--detail-workers', type=int, default=3,
                        help='详情页并发抓取 tab 数（默认3；期刊模式与检索模式均有效，翻页/收集仍按各自并发模型）')
    parser.add_argument('--resume', action='store_true',
                        help='断点续跑：存在同关键词断点（.cache/search_checkpoint.json）时从上次进度继续')
    parser.add_argument('--ref-paper-url', type=str, action='append', default=None,
                        help='参考文献模式：论文详情页链接，可重复传多个；批量可配合 --ref-urls-file')
    parser.add_argument('--ref-title', type=str, default=None,
                        help='参考文献模式：论文标题（检索后取第一条结果进详情页抓参考文献）')
    parser.add_argument('--ref-urls-file', type=str, default=None,
                        help='参考文献模式：论文详情页链接清单文件（每行一个 URL，# 开头为注释）')
    parser.add_argument('--ref-max-items', type=int, default=None,
                        help='单篇参考文献条数上限（默认不限）')
    parser.add_argument('--ref-interval', type=float, default=6.0,
                        help='参考文献模式两篇论文之间的基础间隔秒数（实际随机上浮至约1.8倍；默认6，易触发验证码时调大）')
    parser.add_argument('--detail-refs', action='store_true',
                        help='抓论文详情时在同一详情页顺带抓取参考文献入库（省二次导航，总体更不易触发风控；期刊/检索模式均生效）')
    parser.add_argument('--ref-no-details', action='store_true',
                        help='参考文献模式：只抓引用列表，不抓每条参考文献自身的详情（默认会抓详情并入库）')
    parser.add_argument('--ref-detail-max', type=int, default=None,
                        help='参考文献模式：每篇最多抓多少条参考文献的详情（默认不限；先小批量试跑可设 2）')
    parser.add_argument('--ref-detail-workers', type=int, default=8,
                        help='参考文献模式：详情抓取并发 worker tab 数（默认8）')
    args = parser.parse_args()

    # —— 交互式登录：--login 与 --no-login-state 语义冲突（一个要写会话态、一个禁用会话态）——
    if args.login:
        if args.no_login_state:
            print("[ERROR] --login 与 --no-login-state 语义冲突，不能同时使用")
            sys.exit(2)
        from cnki_crawler.login import interactive_login
        state_path = Path(args.state_file) if args.state_file else CNKI_STATE_FILE
        sys.exit(await interactive_login(state_path))

    if args.detail_refs and args.detail_workers > 2:
        print("[提示] --detail-refs 开启时建议 --detail-workers ≤ 2：每个 tab 都可能翻参考文献页，请求经全局导航闸排队，并发多会更慢且更易触发风控")

    # 参考文献模式：--ref-paper-url（可多个）/ --ref-urls-file / --ref-title 任一提供即启用
    refs_mode_intended = bool(args.ref_paper_url) or bool(args.ref_urls_file) \
        or bool((args.ref_title or '').strip())
    ref_urls = list(args.ref_paper_url or [])
    if args.ref_urls_file:
        try:
            for line in Path(args.ref_urls_file).read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    ref_urls.append(line)
        except Exception as e:
            print(f"[ERROR] 读取 URL 清单文件失败: {e}")
            sys.exit(1)
    if refs_mode_intended:
        # 启动浏览器前先校验，避免把非法 URL / 空标题喂给 page.goto 才报错
        bad_urls = [u for u in ref_urls if not re.match(r'^https?://', u)]
        if bad_urls:
            print(f"[ERROR] 以下 --ref-paper-url 不是合法 http(s) 链接（共 {len(bad_urls)} 个）：")
            for u in bad_urls[:5]:
                print(f"        {u[:120]}")
            print("        —— 若想按论文标题检索，请改用 --ref-title \"论文标题\"")
            sys.exit(1)
        if not ref_urls and not (args.ref_title or '').strip():
            print("[ERROR] 参考文献模式需要至少一个详情页链接（--ref-paper-url）或论文标题（--ref-title）")
            sys.exit(1)
        state_file = None if args.no_login_state else (
            args.state_file or str(CACHE_DIR / 'cnki_state.json')
        )
        ref_crawler = ReferenceCrawler(
            headless=not args.show_browser,
            state_file=state_file,
            paper_urls=ref_urls,
            paper_title=args.ref_title,
            max_items=args.ref_max_items,
            interval=args.ref_interval,
            crawl_ref_details=not args.ref_no_details,
            ref_detail_max=args.ref_detail_max,
            ref_detail_workers=args.ref_detail_workers,
        )
        await ref_crawler.run()
        return

    if args.search:
        # 校验检索字段，未知值回退到默认「主题」
        if args.search_field not in CNKI_SEARCH_FIELDS:
            print(f"[WARN] 未知检索字段: {args.search_field}，可选: {' / '.join(CNKI_SEARCH_FIELDS)}，回退为默认「主题」")
            args.search_field = '主题'
        min_year = max_year = None
        if args.years:
            parts = args.years.replace('，', ',').split('-')
            try:
                min_year = int(parts[0].strip())
                max_year = int(parts[1].strip()) if len(parts) > 1 else min_year
            except Exception:
                print("年份格式错误，忽略 --years，应为如 2024-2026")
                min_year = max_year = None
        state_file = None if args.no_login_state else (
            args.state_file or str(CACHE_DIR / 'cnki_state.json')
        )
        # --search-url 支持直接传 URL，或传一个含 URL 的本地文件路径（自动读取）
        search_url = args.search_url
        if search_url and Path(search_url).is_file():
            search_url = Path(search_url).read_text(encoding='utf-8').strip()
        crawler = KeywordSearchCrawler(
            headless=not args.show_browser,
            keyword=args.search,
            search_field=args.search_field,
            max_pages=args.max_pages,
            min_year=min_year,
            max_year=max_year,
            state_file=state_file,
            urls_only=args.urls_only,
            urls_file=args.urls_file,
            search_url=search_url,
            search_url_file=args.save_url_file,
            detail_workers=args.detail_workers,
            resume=args.resume,
            refs_with_details=args.detail_refs,
            ref_max_items=args.ref_max_items,
        )
        await crawler.run_search()
        return

    crawler = MultiThreadedCrawler(
        headless=not args.show_browser,
        max_workers=args.threads,
        detail_workers=args.detail_workers,
        refs_with_details=args.detail_refs,
        ref_max_items=args.ref_max_items,
    )
    await crawler.run()
