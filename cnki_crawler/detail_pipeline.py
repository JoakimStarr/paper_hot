"""详情并发流水线：期刊模式与关键词模式共用的「N 个 worker tab 并发抓详情入库」。

原脚本把这段并发逻辑在 fetch_details_concurrent（期刊）与 run_search（检索）里
近乎逐行复制了两遍。这里收敛为一个 run_details：调用方负责构建任务列表与
「如何抓」的闭包（期刊要传 jn/year/issue 并更新各刊日志，检索不用），
本模块只负责 worker 池、进度打印与按原因统计。

进度文案经 progress.emit* 输出（后端契约，见 progress.py 注释）。
"""
import asyncio
import random

from cnki_crawler import progress


async def run_details(context, queue_items: list, *, workers: int, tag: str,
                      crawl, on_ok=None) -> dict:
    """并发抓详情入库。

    - context：浏览器 context（worker 用 context.new_page() 各自开 tab）
    - queue_items：任务列表，元素为 dict，须含 'paper'（供标题打印）；其余字段
      （如 jn/year/issue）由 crawl 闭包自行解读
    - crawl(page, item)：async callable，返回 crawl_paper_detail 的 result dict
    - on_ok(item)：可选，每成功一篇回调（期刊模式用来累加各刊成功数）

    返回 stats：{'ok','total','already_exists','filtered','verify_failed','failed'}
    （already_exists 为运行时遇到已存在的计数，调用方预过滤的 skipped 需自行累加）。
    """
    total = len(queue_items)
    done = ok = 0
    stats = {'already_exists': 0, 'filtered': 0, 'verify_failed': 0, 'failed': 0}
    queue = asyncio.Queue()
    for it in queue_items:
        queue.put_nowait(it)

    async def detail_worker(wid: int):
        nonlocal done, ok
        wtag = f"{tag}[W{wid}]"
        page = await context.new_page()
        try:
            while True:
                try:
                    item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                done += 1
                title = (item.get('paper') or {}).get('title', '')[:30]
                print(f"{wtag} [{done}/{total}] 处理: {title}...")
                res = await crawl(page, item)
                if res and res.get('title'):
                    ok += 1
                    if on_ok is not None:
                        on_ok(item)
                else:
                    reason = res.get('error', 'failed') if res else 'failed'
                    if reason == 'already_exists':
                        stats['already_exists'] += 1
                    elif reason == 'verify_page':
                        stats['verify_failed'] += 1
                    elif reason == 'filtered_non_paper':
                        stats['filtered'] += 1
                    else:
                        stats['failed'] += 1
                await asyncio.sleep(random.uniform(0.5, 1.5))
        finally:
            try:
                await page.close()
            except Exception:
                pass

    await asyncio.gather(*[detail_worker(i) for i in range(max(1, workers))])
    stats.update(ok=ok, done=done, total=total)
    return stats
