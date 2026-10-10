"""应用配置：全部通过环境变量 / backend/.env 注入。"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 基础
    app_name: str = "报告收集系统"
    app_env: str = "development"
    debug: bool = False
    timezone: str = "Asia/Shanghai"

    # 安全
    secret_key: str = "change-me-in-env"
    access_token_expire_minutes: int = 12 * 60
    cookie_name: str = "rc_admin_token"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 数据库
    database_url: str = (
        f"sqlite+aiosqlite:///{(BACKEND_DIR / 'data' / 'app.db').as_posix()}"
    )

    # 站点地址
    public_base_url: str = "http://localhost:5173"
    client_path: str = "/m"
    admin_path: str = "/admin"

    # 微信服务号
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    wechat_oauth_redirect_uri: str = ""

    # 飞书
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_chat_id: str = ""
    feishu_base_url: str = "https://open.feishu.cn/open-apis"

    # 邮件（腾讯企业邮箱）
    smtp_host: str = "smtp.exmail.qq.com"
    smtp_port: int = 465
    smtp_use_ssl: bool = True
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from_name: str = "清华EIRI 报告收集"

    # 管理员初始账号（仅首次启动时写入）
    admin_initial_username: str = "admin"
    admin_initial_password: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def client_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}{self.client_path}"

    @property
    def admin_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}{self.admin_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
