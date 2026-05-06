from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "PaperPulse"
    app_version: str = "1.0.0"
    
    database_url: str = "sqlite+aiosqlite:///./paperpulse.db"
    
    openai_api_key: Optional[str] = None
    
    arxiv_categories: list[str] = ["cs.AI", "cs.CL", "cs.LG", "cs.CV"]
    
    scheduler_enabled: bool = True
    fetch_interval_hours: int = 24
    
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "http://localhost:3003"]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
