"""详情并发流水线 run_details 的单元测试（fake context，不联网）。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cnki_crawler.detail_pipeline import run_details  # noqa: E402


class _FakePage:
    pass


class _FakeContext:
    def __init__(self):
        self.pages = []

    async def new_page(self):
        page = _FakePage()
        self.pages.append(page)
        return page


async def _run(items, crawl, workers=2, on_ok=None):
    ctx = _FakeContext()
    stats = await run_details(ctx, items, workers=workers, tag="[t]", crawl=crawl, on_ok=on_ok)
    return stats, ctx


def test_all_ok_with_on_ok():
    items = [{'paper': {'title': f'论文{i}'}} for i in range(4)]
    ok_calls = []

    async def crawl(page, item):
        return {'title': item['paper']['title'], 'authors': ['x']}

    stats, ctx = asyncio.run(_run(items, crawl, workers=2, on_ok=lambda it: ok_calls.append(it['paper']['title'])))
    assert stats['ok'] == 4 and stats['total'] == 4
    assert stats['failed'] == stats['filtered'] == stats['verify_failed'] == stats['already_exists'] == 0
    assert ok_calls == ['论文0', '论文1', '论文2', '论文3'] or len(ok_calls) == 4
    assert len(ctx.pages) == 2  # 两个 worker 各开一个 tab


def test_reason_counting():
    items = [{'paper': {'title': f'p{i}'}} for i in range(4)]
    results = [{'error': 'already_exists'}, {'error': 'verify_page'},
               {'error': 'filtered_non_paper'}, {'error': 'boom'}]

    async def crawl(page, item):
        return results.pop(0)

    stats, _ = asyncio.run(_run(items, crawl, workers=1))
    assert stats['ok'] == 0 and stats['total'] == 4
    assert stats['already_exists'] == stats['verify_failed'] == stats['filtered'] == stats['failed'] == 1


def test_empty_queue():
    stats, ctx = asyncio.run(_run([], lambda page, item: None, workers=1))
    assert stats['total'] == 0 and stats['ok'] == 0
    # worker 会各自开 tab 后立即因队列空退出
    assert len(ctx.pages) == 1


def test_success_and_failure_mix():
    items = [{'paper': {'title': f'p{i}'}} for i in range(3)]

    async def crawl(page, item):
        if item['paper']['title'] == 'p1':
            return {'error': 'verify_page'}
        return {'title': item['paper']['title']}

    stats, _ = asyncio.run(_run(items, crawl, workers=2))
    assert stats['ok'] == 2 and stats['verify_failed'] == 1 and stats['total'] == 3
