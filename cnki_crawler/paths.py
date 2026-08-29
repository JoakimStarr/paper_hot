"""路径与仓库定位常量（包内所有模块从这里取路径）。

⚠️ 原单文件脚本里这些路径基于 `Path(__file__).resolve().parent`（= 仓库根）；
搬进包后 `parent` 变成 `cnki_crawler/`，一律用 `parents[1]`（仓库根）。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # 仓库根

CACHE_DIR = ROOT / '.cache'
SEARCH_CHECKPOINT_FILE = CACHE_DIR / 'search_checkpoint.json'
CNKI_STATE_FILE = CACHE_DIR / 'cnki_state.json'

BACKEND_DIR = ROOT / 'backend'
DATA_DIR = BACKEND_DIR / 'data'
JOURNALS_HISTORY_FILE = DATA_DIR / 'journals_history.json'
PAPERS_HISTORY_FILE = DATA_DIR / 'papers_history.json'

# 脚本需要复用后端 app 包（PaperCRUD / AsyncSessionLocal）入库；
# 一次性把 backend/ 放入 sys.path（保持原脚本行为，模块导入即生效）
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def ensure_cache_dir() -> Path:
    """显式确保 .cache 目录存在（原脚本在模块顶层 mkdir，这里收口成显式调用）。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def _collect_state_file(index: int) -> Path:
    return CACHE_DIR / f'cnki_state_collect_{index}.json'
