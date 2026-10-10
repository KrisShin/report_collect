"""日志配置：统一格式，敏感字段由调用方脱敏。"""

from logging.config import dictConfig


def setup_logging(debug: bool = False) -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                }
            },
            "root": {
                "handlers": ["console"],
                "level": "DEBUG" if debug else "INFO",
            },
            "loggers": {
                "uvicorn.access": {"level": "INFO", "propagate": True},
                "sqlalchemy.engine": {"level": "DEBUG" if debug else "WARNING"},
            },
        }
    )


def mask_phone(phone: str | None) -> str:
    if not phone or len(phone) < 7:
        return phone or ""
    return f"{phone[:3]}****{phone[-4:]}"


def mask_email(email: str | None) -> str:
    if not email or "@" not in email:
        return email or ""
    name, domain = email.split("@", 1)
    if len(name) <= 2:
        return f"{name[0]}***@{domain}"
    return f"{name[:2]}***@{domain}"

