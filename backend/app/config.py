from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional, Union, List, Dict, Any
from pathlib import Path
import json

BASE_DIR = Path(__file__).parent.parent

class Settings(BaseSettings):
    app_name: str = "PaperPulse"
    app_version: str = "2.18.1"

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

    # 重排模型（格式 'provider/model'，默认硅基流动 bge-reranker-v2-m3）。
    # 选题验证器两阶段检索：本地 embedding 召回候选后，调用重排模型精排取 Top-N。
    # 未配置 rerank_api_key 时自动跳过重排，降级为 embedding 相似度顺序。
    rerank_model: Optional[str] = "siliconflow/BAAI/bge-reranker-v2-m3"
    # 重排 API key / 端点（默认硅基流动）。独立于 LLM provider 配置，
    # 避免把硅基流动 key 放进硅基流动 provider 后改变全局对话模型选择。
    rerank_api_key: Optional[str] = None
    rerank_base_url: Optional[str] = None

    arxiv_categories: list[str] = []  # 已关闭：arxiv 抓取的是 CS/AI 论文，非经济学

    scheduler_enabled: bool = True

    api_token: str = Field(default="", description="API token for protected endpoints")

    # CNKI 爬虫是否无头模式运行（False 会弹出浏览器窗口，便于人工处理验证码）
    cnki_headless: bool = False

    # CNKI 论文详情跳转链接的域名头（高校 VPN/镜像地址，需与知网原子域名对应，
    # 如 kns.cnki.net 在 VPN 下通常映射为 kns-cnki-net-s.<vpn域>）。
    # 留空使用官网默认 https://kns.cnki.net；仅改写详情接口返回的展示链接，不改动库中存储与爬虫逻辑。
    cnki_url_prefix: str = ""

    backend_port: int = 8000
    frontend_port: int = 3000

    # ── 日志系统 ──
    # 日志级别（DEBUG/INFO/WARNING/ERROR）；文件日志默认关闭，仅控制台输出
    log_level: str = "INFO"
    log_file_enabled: bool = False
    log_file_path: str = f"{BASE_DIR}/data/logs/app.log"
    # 启动时清理超过该天数的动作/错误日志（0 表示不清理）
    log_retention_days: int = 30

    # 追问 Agent（工具检索）开关：开启后 AI 追问可调用工具检索论文库；
    # 关闭则退化为普通对话（不调用任何工具、不检索）。
    # 默认开启（悬浮助手/追问默认查库）；系统设置页与悬浮助手内均可关闭。
    agent_enabled: bool = True

    # AI 模型单价（每百万 tokens，元），JSON 字符串：{"模型名": 单价}；用于用量成本估算
    ai_model_prices: str = "{}"

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


settings = Settings()

# 启动早期应用 DB 覆盖（必须在 FastAPI app 构建前，否则 CORS/标题/端口用基线值）
from app.settings_store import apply_boot_overrides as _apply_boot_overrides
try:
    _apply_boot_overrides(settings)
except Exception:
    pass
