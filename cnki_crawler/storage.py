"""历史记录（HistoryManager）、检索断点（checkpoint）—— 磁盘状态层。

依赖 paths.py 定位文件；不依赖 playwright / ddddocr，可独立测试。
"""
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

from cnki_crawler.paths import (
    CACHE_DIR,
    DATA_DIR,
    JOURNALS_HISTORY_FILE,
    PAPERS_HISTORY_FILE,
    SEARCH_CHECKPOINT_FILE,
)

JOURNAL_CACHE_DAYS = 7
PAPER_CACHE_DAYS = 30


# —— 关键词检索断点：停止/中断后可从上次进度续跑（collect=翻页收集中 / detail=详情入库中）——
# 注意：详情阶段本身逐篇入库即持久化，恢复时靠 URL 去重跳过已入库论文
def _load_search_checkpoint():
    try:
        return json.loads(SEARCH_CHECKPOINT_FILE.read_text(encoding='utf-8'))
    except Exception:
        return None


def _save_search_checkpoint(data: dict):
    try:
        data = dict(data)
        data['saved_at'] = datetime.now().isoformat(timespec='seconds')
        SEARCH_CHECKPOINT_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    except Exception as e:
        print(f"  [checkpoint] 写入断点失败: {e}")


def _clear_search_checkpoint():
    try:
        SEARCH_CHECKPOINT_FILE.unlink(missing_ok=True)
    except Exception:
        pass


class HistoryManager:
    """历史记录管理器（期刊导航 / 论文链接的本地缓存）"""
    _lock = threading.Lock()

    @staticmethod
    def load_journals_history() -> dict:
        """加载期刊历史记录"""
        if JOURNALS_HISTORY_FILE.exists():
            with open(JOURNALS_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'last_updated': None, 'journals': {}}

    @staticmethod
    def _atomic_write(path: Path, data: dict):
        """原子写 JSON：先写临时文件再 rename，避免崩溃/中断时损坏缓存文件。"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)

    @staticmethod
    def save_journals_history(journals: dict):
        """保存期刊历史记录"""
        data = {
            'last_updated': datetime.now().isoformat(),
            'journals': journals
        }
        HistoryManager._atomic_write(JOURNALS_HISTORY_FILE, data)

    @staticmethod
    def load_papers_history() -> dict:
        """加载论文链接历史记录"""
        if PAPERS_HISTORY_FILE.exists():
            with open(PAPERS_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'last_updated': None, 'papers': {}}

    @staticmethod
    def save_papers_history(papers: dict):
        """保存论文链接历史记录"""
        data = {
            'last_updated': datetime.now().isoformat(),
            'papers': papers
        }
        HistoryManager._atomic_write(PAPERS_HISTORY_FILE, data)

    @staticmethod
    def is_journals_cache_valid() -> bool:
        """检查期刊缓存是否有效"""
        history = HistoryManager.load_journals_history()
        if not history['last_updated']:
            return False
        last_updated = datetime.fromisoformat(history['last_updated'])
        return datetime.now() - last_updated < timedelta(days=JOURNAL_CACHE_DAYS)

    @staticmethod
    def is_journal_year_crawled(journal_name: str, year: str) -> bool:
        """检查期刊某年份是否已爬取"""
        history = HistoryManager.load_papers_history()
        papers = history.get('papers', {})
        if journal_name not in papers:
            return False
        if year not in papers[journal_name]:
            return False
        year_data = papers[journal_name][year]
        return len(year_data) > 0

    @staticmethod
    def get_papers_for_journal_year(journal_name: str, year: str) -> list:
        """获取期刊某年份的所有论文链接（过滤非论文条目）"""
        history = HistoryManager.load_papers_history()
        papers = history.get('papers', {})
        if journal_name not in papers:
            return []
        if year not in papers[journal_name]:
            return []

        skip_keywords = [
            '征稿启事', '征稿', '征文', '征订', '稿约', '投稿须知', '投稿指南',
            '总目录', '目录', '索引', '内容提要',
            '编辑部公告', '编辑部关于', '编辑部声明', '公告', '声明', '启事', '通知', '更正', '勘误', '补遗',
            '书评', '评介', '学院简介', '中心简介', '新书介绍', '新书评介',
            '会议纪要', '会议综述', '会议报道', '会议简报',
            '新闻', '消息', '简讯', '报道',
            '广告', '致谢名单', '致谢专家', '鸣谢',
            '卷首语', '编者按', '导读', '操作指南', '使用指南', '手册',
            '人才招聘', '全球人才招聘', '招生', '培训', '课程', '讲座',
            '版权声明', '著作权', '授权声明',
            '欢迎订阅', '订阅杂志', '订购', '欢迎购买',
        ]

        all_papers = []
        for issue_num, issue_data in papers[journal_name][year].items():
            if 'papers' in issue_data:
                for paper in issue_data['papers']:
                    title = paper.get('title', '')
                    if any(keyword in title for keyword in skip_keywords):
                        continue
                    all_papers.append(paper)
        return all_papers

    @staticmethod
    def add_papers_for_journal_issue(journal_name: str, year: str, issue: str, papers: list):
        """添加期刊某期次的论文链接"""
        with HistoryManager._lock:
            history = HistoryManager.load_papers_history()
            if 'papers' not in history:
                history['papers'] = {}
            if journal_name not in history['papers']:
                history['papers'][journal_name] = {}
            if year not in history['papers'][journal_name]:
                history['papers'][journal_name][year] = {}

            history['papers'][journal_name][year][issue] = {
                'last_crawled': datetime.now().isoformat(),
                'papers': papers
            }
            HistoryManager.save_papers_history(history['papers'])
