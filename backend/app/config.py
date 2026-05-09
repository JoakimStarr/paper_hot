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
    
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "http://localhost:3003"]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
