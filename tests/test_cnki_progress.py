"""锁死后端进度解析契约：progress.emit* 输出的每一行都必须被后端正则命中且字段值正确。

后端 `backend/app/routers/crawler.py`（_parse_cnki_progress :185-224 与参考文献任务 :577-590）
用正则逐行解析脚本 stdout 驱动前端任务面板。任何措辞改动都会让面板断链。
"""
import io
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cnki_crawler import progress  # noqa: E402


def capture(fn):
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn()
    return buf.getvalue().rstrip("\n")


def test_page_collected():
    line = capture(lambda: progress.emit_page_collected("[k]", 3, 25, 88))
    m = re.search(r"第 (\d+) 页获取 \d+ 条，累计 (\d+) 条", line)
    assert m and int(m.group(1)) == 3 and int(m.group(2)) == 88


def test_refs_page_progress():
    line = capture(lambda: progress.emit_refs_page_progress("[r]", 2, 20, 5, 45))
    assert re.search(r"参考文献\s*第\s*2\s*页", line)
    m = re.search(r"累计\s*(\d+)\s*条", line)
    assert m and int(m.group(1)) == 45


def test_collected_total():
    line = capture(lambda: progress.emit_collected_total("[k]", 120))
    m = re.search(r"共收集 (\d+) 篇待处理论文", line)
    assert m and int(m.group(1)) == 120


def test_detail_concurrency():
    line = capture(lambda: progress.emit_detail_concurrency("[k]", 3, 40, 5))
    m = re.search(r"详情并发数: \d+，待抓 (\d+) 篇（已在库跳过 (\d+)）", line)
    assert m and int(m.group(1)) == 40 and int(m.group(2)) == 5


def test_detail_summary():
    line = capture(lambda: progress.emit_detail_summary("[k]", 32, 40, 5, 1, 1, 1))
    m = re.search(
        r"完成：成功 (\d+)/(\d+) 篇 \| 已在库 (\d+) \| 被过滤 (\d+) \| 验证码未过 (\d+) \| 失败 (\d+)",
        line,
    )
    assert m and tuple(map(int, m.groups())) == (32, 40, 5, 1, 1, 1)


def test_refs_saved():
    line = capture(lambda: progress.emit_refs_saved("    [线程0]", 12, extra=" -> 某论文"))
    m = re.search(r"参考文献已(?:写入论文|入库)\s*(\d+)\s*条", line)
    assert m and int(m.group(1)) == 12
    assert "某论文" in line


def test_refs_failed_substring():
    line = capture(lambda: progress.emit_refs_failed("    [线程0]", "boom"))
    assert "参考文献写入失败" in line
    assert "boom" in line


def test_refs_detail_summary():
    line = capture(lambda: progress.emit_refs_detail_summary("[k]", 3, 1))
    m = re.search(r"参考文献（--detail-refs）：成功\s*(\d+)\s*篇.*?失败\s*(\d+)\s*篇", line)
    assert m and (int(m.group(1)), int(m.group(2))) == (3, 1)


def test_refs_all_done():
    line = capture(lambda: progress.emit_refs_all_done("[r]", 1, 1, 30))
    m = re.search(r"共入库参考文献\s*(\d+)\s*条", line)
    assert m and int(m.group(1)) == 30


def test_ref_detail_logs_do_not_hit_progress_regexes():
    """参考文献「详情入库」的日志行不得被后端进度正则误解析。

    后端把 `[N/M]` 当详情页进度、`参考文献已写入论文 N 条` 当列表入库计数；
    详情入库日志刻意用 `(i/total)` 与不同措辞规避。
    """
    lines = [
        "[参考文献#0] 参考文献详情 (1/9) 本地已有，跳过打开：1. 张三. 中国经济增长研究[J]. 经济研究, 2020(3): 12-25.",
        "[参考文献#0] 参考文献详情 (2/9) 条目解析不出年份，跳过：李四. 无年份文献[J]. 经济研究",
        "[参考文献#0] 参考文献详情 (3/9) 详情页加载失败：王五. 打不开的文献[J]. 经济研究, 2019(1)",
        "[参考文献#0] 参考文献详情 (4/9) 非论文条目，跳过：编辑部. 征稿启事[J]. 经济研究, 2018(1)",
        "[参考文献#0] 参考文献详情 (5/9) ✓ 已入库：中国经济增长研究（2020）",
        "[参考文献#0] 参考文献详情 (6/9) 未入库（已存在 / 缺作者或关键词 / 入库异常）：赵六. 缺作者文献[J]. 经济研究, 2017(2)",
        "[参考文献#0] ⚠ 遇到安全验证页，中止本轮参考文献详情抓取（已处理 6 条）",
        "[参考文献#0] 参考文献详情小结：入库 3 条，本地已有跳过 2 条，本轮重复 0 条，年份缺失 1 条，"
        "著录不全 1 条，非论文条目 1 条，失败 1 条，遇验证页中止剩余 1 条",
    ]
    backend_re = [
        r"\[(\d+)/(\d+)\]",
        r"第 (\d+) 页获取 \d+ 条，累计 (\d+) 条",
        r"共收集 (\d+) 篇待处理论文",
        r"详情并发数: \d+，待抓 (\d+) 篇（已在库跳过 (\d+)）",
        r"完成：成功 (\d+)/(\d+) 篇 \| 已在库 (\d+) \| 被过滤 (\d+) \| 验证码未过 (\d+) \| 失败 (\d+)",
        r"参考文献已(?:写入论文|入库)\s*(\d+)\s*条",
        r"参考文献（--detail-refs）：成功\s*(\d+)\s*篇.*?失败\s*(\d+)\s*篇",
        r"参考文献\s*第\s*(\d+)\s*页",
        r"累计\s*(\d+)\s*条",
        r"共入库参考文献\s*(\d+)\s*条",
    ]
    for line in lines:
        for pat in backend_re:
            assert re.search(pat, line) is None, f"日志误撞后端正则 {pat}: {line}"
        assert "参考文献写入失败" not in line and "参考文献入库失败" not in line
