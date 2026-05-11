from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path

# 获取 backend 目录的绝对路径
BASE_DIR = Path(__file__).parent.parent

class Settings(BaseSettings):
    app_name: str = "PaperPulse"
    app_version: str = "1.0.0"
    
    # 使用绝对路径
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR}/data/paperpulse.db"
    
    openai_api_key: Optional[str] = None
    zhipu_api_key: Optional[str] = None
    siliconflow_api_key: Optional[str] = None
    
    arxiv_categories: list[str] = ["cs.AI", "cs.CL", "cs.LG", "cs.CV"]
    
    scheduler_enabled: bool = True
    fetch_interval_hours: int = 24
    
    api_token: str = Field(default="", description="API token for protected endpoints")
    
    backend_port: int = 8000
    frontend_port: int = 3000
    
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "http://localhost:3003"]
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    @staticmethod
    def update_setting(key: str, value: str):
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
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        if hasattr(settings, key):
            setattr(settings, key, value)


settings = Settings()
