"""paper_keywords 平表回填脚本（幂等，可重复执行）

背景：papers.keywords_cn 是 JSON 列，SQLite 无法对 json_each 展开建索引；
「今日值得读」的关键词召回此前每请求全表扫描。本脚本把关键词展开回填到
paper_keywords 平表（一论文一关键词一行，keyword 建索引），召回走索引查找。

应用启动时空表会自动后台回填（main.py lifespan -> crud.backfill_paper_keywords）；
本脚本用于手动全量重建（只补缺，不删多）。查询侧在表为空时自动回退 json_each。

用法：
    cd backend && venv/bin/python scripts/backfill_paper_keywords.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.crud import backfill_paper_keywords  # noqa: E402
from app.database import init_db  # noqa: E402


async def main():
    await init_db()  # 建 paper_keywords / read_laters 等新表（幂等）
    added = await backfill_paper_keywords()
    print(f"paper_keywords backfill done: +{added} rows")


if __name__ == "__main__":
    asyncio.run(main())
