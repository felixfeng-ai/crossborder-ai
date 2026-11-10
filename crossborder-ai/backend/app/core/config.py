"""VeyaShip - Global Configuration.

Centralized settings using Pydantic Settings.
All environment variables are loaded and validated here.
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import model_validator
import json


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Application ---
    APP_NAME: str = "VeyaShip"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = ""                          # 必须通过 .env 设置
    APP_URL: str = "http://localhost:8000"        # 生产环境改为实际域名
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_ROOT: str = "/app"

    @property
    def DOCS_ENABLED(self) -> bool:
        """文档接口仅在 DEBUG 模式下开放。"""
        return bool(self.DEBUG) and bool(self.SECRET_KEY)

    # ── 数据库配置 ────────────────────────────────────────────
    # 连接字符串格式：协议://用户名:密码@地址:端口/数据库名
    # PostgreSQL: postgresql+asyncpg://user:pass@localhost:5432/db
    # SQLite:     sqlite+aiosqlite:///./文件名.db

    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "crossborder_ai"          # 数据库名
    POSTGRES_USER: str = "crossborder"            # 数据库用户
    POSTGRES_PASSWORD: str = ""
    DATABASE_URL: Optional[str] = None            # 手动指定的完整连接串
    USE_SQLITE: bool = False                      # True=SQLite开发 False=PostgreSQL生产

    @property
    def DB_URL(self) -> str:
        """获取最终使用的数据库连接字符串。

        规则：
        - USE_SQLITE=True → SQLite 文件数据库（开发用，无需安装）
        - 有 DATABASE_URL → 直接用（生产环境）
        - 否则 → 用各 POSTGRES_* 字段拼接
        """
        if self.USE_SQLITE:
            return "sqlite+aiosqlite:///./crossborder_ai.db"
        return str(self.DATABASE_URL or self._build_pg_url())

    def _build_pg_url(self) -> str:
        """从各字段拼接 PostgreSQL 连接字符串。"""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @model_validator(mode="before")
    @classmethod
    def assemble_db_url(cls, values: dict) -> dict:
        """如果没填 DATABASE_URL，自动拼接一个。"""
        if values.get("DATABASE_URL") is None:
            user = values.get("POSTGRES_USER", "crossborder")
            password = values.get("POSTGRES_PASSWORD", "change_this_password")
            server = values.get("POSTGRES_SERVER", "localhost")
            port = values.get("POSTGRES_PORT", 5432)
            db = values.get("POSTGRES_DB", "crossborder_ai")
            values["DATABASE_URL"] = (
                f"postgresql+asyncpg://{user}:{password}@{server}:{port}/{db}"
            )
        return values

    # --- JWT ---
    JWT_SECRET_KEY: str = ""                    # 必须通过 .env 设置
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    # --- CORS ---
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost",
        "https://localhost",
    ]

    @model_validator(mode="before")
    @classmethod
    def parse_cors_origins(cls, values: dict) -> dict:
        origins = values.get("BACKEND_CORS_ORIGINS")
        if isinstance(origins, str):
            try:
                values["BACKEND_CORS_ORIGINS"] = json.loads(origins)
            except json.JSONDecodeError:
                values["BACKEND_CORS_ORIGINS"] = [origins]
        return values

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        """生产环境（非 SQLite）必须配置 JWT 密钥，防止空密钥伪造登录令牌。

        之前 JWT_SECRET_KEY 为空时只打印 WARNING 继续启动，
        HMAC 用空串签名 → 任何 token 都可伪造，等于没有登录。
        本地开发（USE_SQLITE=true）允许留空，方便开箱即用。
        """
        if not self.USE_SQLITE and not self.JWT_SECRET_KEY:
            raise ValueError(
                "JWT_SECRET_KEY 未配置：生产环境必须设置 JWT_SECRET_KEY，"
                "否则任何人都能伪造登录令牌"
            )
        return self

    # --- Qdrant ---
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "crossborder_embeddings"

    @property
    def QDRANT_URL(self) -> str:
        return f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}"

    # --- DeepSeek ---
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"  # 2026年7月更新：deepseek-chat 已弃用，改用 v4 系列
    DEEPSEEK_TEMPERATURE: float = 0.7

    # --- Replicate ---
    REPLICATE_API_KEY: Optional[str] = None
    REPLICATE_MODEL: str = "black-forest-labs/flux-schnell"

    # --- Aliyun DashScope (通义万相) ---
    ALIYUN_DASHSCOPE_API_KEY: Optional[str] = None
    ALIYUN_IMAGE_MODEL: str = "wanx2.1-t2i-turbo"

    # --- Shopify ---
    SHOPIFY_API_KEY: Optional[str] = None
    SHOPIFY_API_SECRET: Optional[str] = None
    SHOPIFY_REDIRECT_URI: Optional[str] = None

    # --- Amazon SP-API ---
    AMAZON_APP_ID: Optional[str] = None
    AMAZON_CLIENT_ID: Optional[str] = None
    AMAZON_CLIENT_SECRET: Optional[str] = None
    AMAZON_REDIRECT_URI: Optional[str] = None

    # --- Creem.io ---
    CREEM_API_KEY: Optional[str] = None
    CREEM_WEBHOOK_SECRET: Optional[str] = None
    CREEM_PUBLISHABLE_KEY: Optional[str] = None

    # --- Scraping API (1688 etc.) ---
    # 服务商级别配置，对接 Open Claw / Onebound 等数据接口
    # 用户无需感知，由 VeyaShip 统一提供
    ONEBOUND_API_KEY: Optional[str] = None
    ONEBOUND_API_SECRET: Optional[str] = None
    # Just One API 的 1688 商品详情 Token；网页配置优先于环境变量。
    JUSTONE_API_TOKEN: Optional[str] = None

    # --- Redis ---
    REDIS_URL: Optional[str] = None

    # --- WeChat Mini Program ---
    WEIXIN_APP_ID: Optional[str] = None
    WEIXIN_APP_SECRET: Optional[str] = None

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    # --- Observability ---
    # 设置 SENTRY_DSN 后自动接入 Sentry 错误告警（未设置则跳过）
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # --- Admin ---
    # 平台管理员邮箱列表（可配置多个），有权限审批套餐升级申请等后台操作。
    # 通过 require_admin 依赖校验，生产环境用 .env 覆盖。
    ADMIN_EMAILS: List[str] = ["admin@veyaship.com"]

    class Config:
        env_file = "../.env"      # .env 在项目根目录（相对于 backend/ 目录）
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
