from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional, Union, List, Dict, Any
from pathlib import Path
import json

BASE_DIR = Path(__file__).parent.parent

class Settings(BaseSettings):
    app_name: str = "PaperPulse"
    app_version: str = "2.16.0"

    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR}/data/paperpulse.db"

    openai_api_key: Optional[str] = None
    zhipu_api_key: Optional[str] = None
    siliconflow_api_key: Optional[str] = None
    custom_providers: Optional[str] = None  # JSON string: [{"name":"...", "base_url":"...", "api_key":"...", "models":["..."]}]

    # 内置 provider 的 OpenAI 兼容端点覆盖（留空用默认地址）
    zhipu_base_url: Optional[str] = None
    siliconflow_base_url: Optional[str] = None
    openai_base_url: Optional[str] = None

    # 各内置 provider 的模型优先级（JSON 数组字符串，由设置页排序后持久化）
    zhipu_models: Optional[str] = None
    siliconflow_models: Optional[str] = None
    openai_models: Optional[str] = None

    # 全局默认模型（格式 'provider/model'，如 'zhipu/glm-4'）。未显式指定模型时优先使用它。
    default_model: Optional[str] = None

    # 选题验证器用的 embedding 模型（格式 'provider/model'，如 'zhipu/embedding-3'）。
    # 留空时按 provider 可用性自动选择默认 embedding 模型。
    embedding_model: Optional[str] = None

    arxiv_categories: list[str] = ["cs.AI", "cs.CL", "cs.LG", "cs.CV"]

    scheduler_enabled: bool = True
    fetch_interval_hours: int = 24

    api_token: str = Field(default="", description="API token for protected endpoints")

    # CNKI 爬虫是否无头模式运行（False 会弹出浏览器窗口，便于人工处理验证码）
    cnki_headless: bool = False

    # CNKI 论文详情跳转链接的域名头（如高校 VPN 镜像 'http://www-cnki-net-s.vpn.dufe.edu.cn:8118'）。
    # 留空使用官网默认 https://kns.cnki.net；仅改写详情接口返回的展示链接，不改动库中存储与爬虫逻辑。
    cnki_url_prefix: str = ""

    backend_port: int = 8000
    frontend_port: int = 3000

    cors_origins: Union[list[str], str] = ["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "http://localhost:3003"]

    class Config:
        env_file = ".env"
        case_sensitive = False

    def get_custom_providers(self) -> List[Dict[str, Any]]:
        if not self.custom_providers:
            return []
        try:
            return json.loads(self.custom_providers)
        except:
            return []

    @staticmethod
    def get_json_list(value: Optional[str]) -> List[str]:
        """解析 JSON 数组字符串为列表；空值或格式错误返回空列表。"""
        if not value:
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if str(v).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    def set_custom_providers(self, providers: List[Dict[str, Any]]):
        self.custom_providers = json.dumps(providers, ensure_ascii=False)

    def get_cors_origins(self) -> list[str]:
        if isinstance(self.cors_origins, str):
            try:
                return json.loads(self.cors_origins)
            except:
                return [origin.strip() for origin in self.cors_origins.split(",")]
        return self.cors_origins

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
