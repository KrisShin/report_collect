"""应用配置：统一从 backend/config.yaml 读取，不使用环境变量。

配置文件路径固定为 backend/config.yaml；模板见 backend/config.example.yaml。
测试可通过 load_settings(path) 加载独立 YAML，并替换模块级 settings。
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_FILE = BACKEND_DIR / "config.yaml"


class AppConfig(BaseModel):
    name: str = "报告收集系统"
    env: str = "development"
    debug: bool = False
    timezone: str = "Asia/Shanghai"
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 720
    cookie_name: str = "rc_admin_token"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    public_base_url: str = "http://localhost:5173"
    client_path: str = "/m"
    admin_path: str = "/admin"


class DatabaseConfig(BaseModel):
    url: str = ""


class WeChatConfig(BaseModel):
    """方案 A：不做网页授权，仅校验 UA。"""

    require_browser: bool = True
    # 开发环境是否也强制校验 UA（默认关闭，便于本地/Postman 调试）
    enforce_in_dev: bool = False


class FeishuConfig(BaseModel):
    base_url: str = "https://open.feishu.cn/open-apis"
    app_id: str = ""
    app_secret: str = ""
    chat_id: str = ""


class MailConfig(BaseModel):
    host: str = "smtp.exmail.qq.com"
    port: int = 465
    use_ssl: bool = True
    user: str = ""
    password: str = ""
    from_name: str = "清华EIRI 报告收集"
    # 一键发送邮件的收件人；为空时回退为提交人的邮箱
    recipients: list[str] = Field(default_factory=list)
    # 测试拦截：为 True 时所有邮件强制只发给 recipients，忽略真实收件人
    intercept_all: bool = False


class AiConfig(BaseModel):
    """DeepSeek V4 Flash 垃圾/虚假信息判定。"""

    enabled: bool = False
    base_url: str = ""
    api_key: str = ""
    model: str = "deepseek-v4-flash"
    timeout_seconds: int = 60
    max_tokens: int = 1200


class DiagnosticsConfig(BaseModel):
    """客户端诊断日志（临时排查真实微信浏览器行为）。"""

    log_client_requests: bool = True
    log_dir: str = "logs"
    log_body: bool = True
    # 生产环境默认关闭（含 PII），确需排查时显式打开
    allow_in_production: bool = False


class RedisConfig(BaseModel):
    """Redis：限流、登录锁定、任务队列。未启用时自动降级为进程内实现。"""

    enabled: bool = False
    url: str = "redis://127.0.0.1:6379/0"
    key_prefix: str = "reportc"
    socket_timeout: float = 2.0
    job_queue_key: str = "jobs"


class SecurityConfig(BaseModel):
    """安全策略：登录锁定、接口限流、CSRF 与安全响应头。"""

    login_max_failures: int = 5
    login_lock_seconds: int = 900
    submit_ip_per_minute: int = 10
    submit_phone_per_hour: int = 3
    diagnostics_per_minute: int = 30
    enforce_origin_check: bool = True
    enable_security_headers: bool = True
    # 同一报告内唯一性限制（IP 限制请注意 NAT 场景）
    unique_phone_per_report: bool = True
    unique_email_per_report: bool = True
    unique_ip_per_report: bool = True


class AdminConfig(BaseModel):
    initial_username: str = "admin"
    initial_password: str = ""


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    wechat: WeChatConfig = Field(default_factory=WeChatConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    mail: MailConfig = Field(default_factory=MailConfig)
    ai: AiConfig = Field(default_factory=AiConfig)
    diagnostics: DiagnosticsConfig = Field(default_factory=DiagnosticsConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)

    @property
    def client_url(self) -> str:
        return f"{self.app.public_base_url.rstrip('/')}{self.app.client_path}"

    @property
    def admin_url(self) -> str:
        return f"{self.app.public_base_url.rstrip('/')}{self.app.admin_path}"


def load_settings(path: Path | None = None) -> Settings:
    config_path = path or DEFAULT_CONFIG_FILE
    if not config_path.exists():
        raise FileNotFoundError(
            f"配置文件不存在：{config_path}\n"
            "请从 config.example.yaml 复制一份为 config.yaml 并填写。"
        )

    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    database = data.setdefault("database", {})
    if not database.get("url"):
        database["url"] = (
            f"sqlite+aiosqlite:///{(BACKEND_DIR / 'data' / 'app.db').as_posix()}"
        )
    return Settings.model_validate(data)


settings = load_settings()
