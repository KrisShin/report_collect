"""客户端诊断日志：记录真实微信浏览器的 UA、请求体与返回码。

- 日志文件：backend/logs/client-requests.log
- 生产环境默认关闭（含个人信息）；确需排查时设置 diagnostics.allow_in_production: true
- 日志中的手机号与邮箱自动脱敏
"""

import json
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import BACKEND_DIR, settings

logger = logging.getLogger("app.diagnostics")
_configured = False

_PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _mask_email(value: str) -> str:
    name, _, domain = value.partition("@")
    if len(name) <= 2:
        return f"{name[:1]}***@{domain}"
    return f"{name[:2]}***@{domain}"


def _mask(text: str) -> str:
    text = _PHONE_RE.sub(lambda m: f"{m.group()[:3]}****{m.group()[-4:]}", text)
    return _EMAIL_RE.sub(lambda m: _mask_email(m.group()), text)


def _configure() -> None:
    global _configured
    if _configured:
        return

    log_dir = BACKEND_DIR / settings.diagnostics.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(log_dir / "client-requests.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger.setLevel(logging.INFO)
    logger.propagate = True
    logger.addHandler(handler)
    _configured = True


def log_client_event(event: str, payload: dict) -> None:
    if not settings.diagnostics.log_client_requests:
        return
    if settings.app.env == "production" and not settings.diagnostics.allow_in_production:
        return

    _configure()
    moment = datetime.now(ZoneInfo(settings.app.timezone)).strftime("%Y-%m-%d %H:%M:%S")
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if not settings.diagnostics.log_body:
        text = text[:500]
    logger.info("%s | %s | %s", moment, event, _mask(text)[:4000])
