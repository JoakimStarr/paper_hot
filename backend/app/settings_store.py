"""用户自定义配置持久化（system_settings 表）。

优先级：system_settings(DB) > 环境变量 > backend/.env 基线。
- 启动时：apply_boot_overrides()（同步，sqlite 直读）→ 应用构建前生效；
  init_db 后可再用 load_overrides + apply_overrides 校准一次。
- 设置页保存：save_override() 写 DB 并即时 setattr 到运行时 settings。
- 端口类键（MIRROR_ENV_KEYS）额外镜像写 backend/.env：start.sh 在应用启动前读端口，
  仅存 DB 时启动器无法感知。
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import select as sa_select

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent   # backend/

# 允许通过设置页持久化的 Settings 键白名单
ALLOWED_KEYS = {
    "zhipu_api_key",
    "openai_api_key",
    "siliconflow_api_key",
    "custom_providers",
    "default_model",
    "embedding_model",
    "app_name",
    "cnki_url_prefix",
    "zhipu_models",
    "siliconflow_models",
    "openai_models",
    "backend_port",
    "frontend_port",
    "log_level",
    "log_file_enabled",
    "log_file_path",
    "log_retention_days",
    "agent_enabled",
}

# 这些键同时镜像写 .env —— start.sh 需要在 Python 进程启动前知道端口
MIRROR_ENV_KEYS = {"backend_port", "frontend_port"}


def _coerce(current_value, raw: Optional[str]):
    """按运行时属性当前类型把字符串值转换回 bool/int/str。"""
    if raw is None:
        return None
    if isinstance(current_value, bool):
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if isinstance(current_value, int) and not isinstance(current_value, bool):
        try:
            return int(str(raw).strip())
        except ValueError:
            return current_value
    return str(raw)


def apply_overrides(runtime_settings, overrides: Dict[str, str]) -> int:
    """把 {key: raw_str} 覆盖应用到 settings 对象，返回成功应用的条数。"""
    applied = 0
    for key, raw in overrides.items():
        if key not in ALLOWED_KEYS or not hasattr(runtime_settings, key):
            continue
        try:
            setattr(runtime_settings, key, _coerce(getattr(runtime_settings, key), raw))
            applied += 1
        except Exception as e:
            logger.warning(f"Ignoring invalid DB setting override '{key}': {e}")
    return applied


async def load_overrides(db=None) -> Dict[str, str]:
    """读取全部用户配置覆盖。db 为空时自开会话。"""
    from app.models import SystemSetting

    if db is not None:
        result = await db.execute(sa_select(SystemSetting.key, SystemSetting.value))
        return {row[0]: row[1] for row in result.fetchall()}

    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        result = await session.execute(sa_select(SystemSetting.key, SystemSetting.value))
        return {row[0]: row[1] for row in result.fetchall()}


def apply_boot_overrides(runtime_settings) -> int:
    """进程启动早期（FastAPI app 构建前）同步加载覆盖。

    SQLite 直读规避 async 引擎在导入期不可用的问题；首启表尚不存在时静默跳过。
    """
    from app.config import settings as s
    if not s.database_url.startswith("sqlite"):
        return 0
    db_path = s.database_url.split("///", 1)[-1]
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute("SELECT key, value FROM system_settings").fetchall()
        finally:
            conn.close()
        return apply_overrides(runtime_settings, dict(rows))
    except Exception:
        # 表不存在/文件锁等 → 无覆盖可用，保持基线配置
        return 0


async def save_override(db, key: str, value: Optional[str]):
    """保存单条覆盖：写 DB + 同步内存对象。调用方通常在请求事务内（get_db 会 commit）。"""
    from app.models import SystemSetting

    if key not in ALLOWED_KEYS:
        raise ValueError(f"setting '{key}' is not configurable")

    result = await db.execute(
        sa_select(SystemSetting).where(SystemSetting.key == key)
    )
    row = result.scalars().first()
    if row is None:
        db.add(SystemSetting(key=key, value=value))
    else:
        row.value = value

    from app.config import settings
    if hasattr(settings, key):
        setattr(settings, key, _coerce(getattr(settings, key), value))

    if key in MIRROR_ENV_KEYS and value is not None:
        await upsert_env_line(key, str(value))


async def upsert_env_line(key: str, value: str):
    """镜像写一行 KEY=value 到 backend/.env（保留其余内容）。阻塞 IO 极小，放线程池执行。"""
    import asyncio

    def _write():
        env_path = BASE_DIR / ".env"
        lines = []
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        found = False
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k == key:
                    new_lines.append(f"{key}={value}\n")
                    found = True
                    continue
            new_lines.append(line)
        if not found:
            new_lines.append(f"{key}={value}\n")
        tmp = env_path.with_suffix(".env.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        tmp.replace(env_path)

    try:
        await asyncio.to_thread(_write)
    except Exception as e:
        logger.warning(f"Mirror write of '{key}' to .env failed: {e}")


def dumps_json(value) -> str:
    return json.dumps(value, ensure_ascii=False)
