"""统一时间处理：数据库存 naive UTC，API 输出 aware UTC，展示使用配置时区。"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_db_utc(value: datetime | None) -> datetime | None:
    aware = as_utc(value)
    return aware.replace(tzinfo=None) if aware else None


def to_api_utc(value: datetime | None) -> datetime | None:
    return as_utc(value)


def to_local(value: datetime | None) -> datetime | None:
    aware = as_utc(value)
    if aware is None:
        return None
    return aware.astimezone(ZoneInfo(settings.app.timezone))


def format_local(value: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    local = to_local(value)
    return local.strftime(fmt) if local else ""
