"""参考文献详情入库主循环的冒烟测试（桩掉浏览器与数据库，不联网）。

验证 `_crawl_reference_details` 的去重/跳过/中止/计数等控制流。
"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cnki_crawler.crawlers import JournalCrawler  # noqa: E402
from cnki_crawler.parsing import _norm_title  # noqa: E402

U = "https://kns.cnki.net/kcms2/article/abstract?v="


def ref(i, title, year=2020, journal="经济研究", url=True):
    text = f"[{i}] {title}[J]. 张三.{journal},{year}(01): 1-10."
    return {"index": i, "text": text, "url": (U + str(i)) if url else None}


async def run(monkeypatch, refs, *, existing_titles=(), parse_ok=True,
              verify_at=None, save_ok=True, ref_detail_max=None):
    crawler = JournalCrawler()
    crawler.ref_detail_max = ref_detail_max
    crawler._db_existing_urls = lambda: asyncio.sleep(0, result={U + '0'})
    crawler._db_existing_titles = lambda: asyncio.sleep(0, result=set(existing_titles))
    loaded = []

    async def fake_load(url, page=None):
        loaded.append(url)
        if verify_at is not None and len(loaded) == verify_at:
            return None, 'verify_page'
        if url.endswith('bad'):
            return None, 'load_failed'
        return '<html></html>', None

    def fake_parse(html, url, fallback_journal=''):
        if not parse_ok:
            return {'error': 'no_title'}
        return {'title': '解析出的标题 ' + url[-1], 'authors': ['张三'], 'abstract': 'x',
                'keywords': ['k'], 'url': url, 'journal': fallback_journal}

    async def fake_save(data, journal_name=None, year=None, issue=None):
        assert data.get('year') == 2020, data
        assert journal_name == '经济研究', journal_name
        return save_ok

    crawler._load_detail_html = fake_load
    crawler._parse_detail_html = fake_parse
    crawler.save_to_database = fake_save
    monkeypatch.setattr("cnki_crawler.crawlers.random.uniform", lambda a, b: 0)
    stats = await crawler._crawl_reference_details(refs, "[test]")
    return stats, loaded


def test_crawl_all(monkeypatch):
    stats, loaded = asyncio.run(run(monkeypatch, [ref(1, '甲'), ref(2, '乙'), ref(3, '丙')]))
    assert stats['saved'] == 3 and len(loaded) == 3
    assert stats['dup_local'] == 0 and stats['failed'] == 0


def test_local_dedup_skips_open(monkeypatch):
    # ref0 按 URL 命中、ref2 按标题命中 → 都不打开详情页
    stats, loaded = asyncio.run(run(monkeypatch, [ref(0, '甲'), ref(1, '甲'), ref(2, '乙')],
                                   existing_titles={_norm_title('乙')}))
    assert stats['dup_local'] == 2 and stats['saved'] == 1 and len(loaded) == 1


def test_dup_in_run(monkeypatch):
    stats, loaded = asyncio.run(run(monkeypatch, [ref(1, '甲'), ref(1, '甲')]))
    assert stats['dup_in_run'] == 1 and stats['saved'] == 1 and len(loaded) == 1


def test_no_url_non_cnki_no_year(monkeypatch):
    stats, loaded = asyncio.run(run(monkeypatch, [
        ref(1, '甲', url=False),
        {"index": 2, "text": "[2] 乙文献[J]. 李四.经济研究,2020(1)", "url": "https://example.com/x"},
        {"index": 3, "text": "[3] 丙文献[J]. 王五.经济研究", "url": U + "3"},
    ]))
    assert stats['no_url'] == 1 and stats['non_cnki'] == 1 and stats['no_year'] == 1
    assert len(loaded) == 0


def test_verify_page_aborts(monkeypatch):
    stats, loaded = asyncio.run(run(monkeypatch, [ref(1, '甲'), ref(2, '乙'), ref(3, '丙')],
                                   verify_at=2))
    assert stats['aborted'] == 2 and stats['saved'] == 1 and len(loaded) == 2


def test_failure_and_filtered_and_incomplete(monkeypatch):
    stats, _ = asyncio.run(run(monkeypatch, [
        {'index': 1, 'text': "[1] 甲[J]. 张三.经济研究,2020(1)", 'url': U + "bad"},
        ref(2, '乙'), ref(3, '丙'),
    ]))
    assert stats['failed'] == 1 and stats['saved'] == 2

    stats, _ = asyncio.run(run(monkeypatch, [ref(1, '甲'), ref(2, '乙')], parse_ok=False))
    assert stats['filtered'] == 2 and stats['saved'] == 0

    stats, _ = asyncio.run(run(monkeypatch, [ref(1, '甲'), ref(2, '乙')], save_ok=False))
    assert stats['incomplete'] == 2 and stats['saved'] == 0


def test_ref_detail_max_truncates(monkeypatch):
    stats, loaded = asyncio.run(run(monkeypatch, [ref(i, f'文{i}') for i in range(1, 6)],
                                   ref_detail_max=2))
    assert stats['saved'] == 2 and len(loaded) == 2
