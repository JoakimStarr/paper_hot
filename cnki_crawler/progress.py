"""进度文案 emit：后端契约类文案的唯一出口。

后端 `backend/app/routers/crawler.py` 用正则逐行解析这些文案更新任务进度，
前端消费固定字段（见 `_parse_cnki_progress` 与 `_run_references_background`）。
任何一处措辞变动都可能让进度面板断链——所以集中在这里，并由
`tests/test_cnki_progress.py` 锁死与后端正则的匹配。

调用约定：所有 emit 保持与迁移前完全一致的原文案（仅把 `{tag} ` 前缀保留在行首）。
"""
from __future__ import annotations


def _emit(tag: str, body: str) -> None:
    print(f"{tag} {body}" if tag else body)


def emit_page_collected(tag: str, page: int, count: int, cumulative: int) -> None:
    """检索翻页收集：`第 N 页获取 M 条，累计 K 条`（后端 -> page/collected，phase=collecting）。"""
    _emit(tag, f"第 {page} 页获取 {count} 条，累计 {cumulative} 条")


def emit_refs_page_progress(tag: str, page: int, count: int, new: int, cumulative: int) -> None:
    """参考文献列表翻页：`参考文献 第 N 页获取 M 条（新增 Z），累计 K 条`
    （后端 -> page、跨篇累计 collected）。"""
    _emit(tag, f"参考文献 第 {page} 页获取 {count} 条（新增 {new}），累计 {cumulative} 条")


def emit_collected_total(tag: str, total: int) -> None:
    """收集完成：`共收集 N 篇待处理论文`（后端 -> collected）。"""
    _emit(tag, f"共收集 {total} 篇待处理论文")


def emit_detail_concurrency(tag: str, workers: int, total: int, skipped: int) -> None:
    """详情并发开始：`详情并发数: N，待抓 M 篇（已在库跳过 K）`（后端 -> total/already_exists）。"""
    _emit(tag, f"详情并发数: {workers}，待抓 {total} 篇（已在库跳过 {skipped}）")


def emit_detail_summary(tag: str, ok: int, total: int, already_exists: int,
                        filtered: int, verify_failed: int, failed: int) -> None:
    """详情阶段汇总：`完成：成功 a/b 篇 | 已在库 c | 被过滤 d | 验证码未过 e | 失败 f`
    （后端 -> ok/done/already_exists/filtered/verify_failed/failed，phase=done）。"""
    _emit(tag, f"完成：成功 {ok}/{total} 篇 | 已在库 {already_exists} | "
               f"被过滤 {filtered} | 验证码未过 {verify_failed} | 失败 {failed}")


def emit_refs_saved(tag: str, count: int, extra: str = "") -> None:
    """参考文献列表入库：`✓ 参考文献已写入论文 N 条`（后端 -> refs_ok 累加）。
    extra 保留原有「-> 论文标题」后缀。"""
    _emit(tag, f"✓ 参考文献已写入论文 {count} 条{extra}")


def emit_refs_failed(tag: str, error: object) -> None:
    """参考文献写入失败（后端按「参考文献写入失败」子串计数 refs_failed++）。"""
    _emit(tag, f"✗ 参考文献写入失败: {error}")


def emit_refs_detail_summary(tag: str, ok: int, failed: int) -> None:
    """--detail-refs 顺带抓取汇总：`参考文献（--detail-refs）：成功 X 篇 | 失败 Y 篇`。"""
    _emit(tag, f"参考文献（--detail-refs）：成功 {ok} 篇 | 失败 {failed} 篇")


def emit_refs_all_done(tag: str, ok_papers: int, total_papers: int, total_refs: int) -> None:
    """参考文献模式收尾：`全部完成：a/b 篇论文，共入库参考文献 N 条`（后端 -> collected）。"""
    _emit(tag, f"全部完成：{ok_papers}/{total_papers} 篇论文，共入库参考文献 {total_refs} 条")
