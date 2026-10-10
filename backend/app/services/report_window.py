"""报告填报时间段处理。"""

from datetime import UTC, datetime

from app.models.report import Report


def to_db_utc(value: datetime | None) -> datetime | None:
    """统一按 naive UTC 存库（与 submitted_at 等字段保持一致）。"""

    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(tzinfo=None)


def to_api_utc(value: datetime | None) -> datetime | None:
    """输出给前端时补上 UTC 时区，前端再按本地时区展示。"""

    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def window_state(report: Report, now: datetime | None = None) -> str:
    """返回 open / not_started / ended。"""

    moment = (now or datetime.now(UTC)).astimezone(UTC).replace(tzinfo=None)
    if report.start_at and moment < report.start_at:
        return "not_started"
    if report.end_at and moment > report.end_at:
        return "ended"
    return "open"


def window_message(report: Report) -> str:
    """不在填报时间段内时的提示文案（本地时间展示）。"""

    from zoneinfo import ZoneInfo

    from app.core.config import settings

    tz = ZoneInfo(settings.app.timezone)

    def fmt(value: datetime | None) -> str:
        if value is None:
            return "未设置"
        return value.replace(tzinfo=UTC).astimezone(tz).strftime("%Y-%m-%d %H:%M")

    state = window_state(report)
    if state == "not_started":
        return f"填报尚未开始，开始时间：{fmt(report.start_at)}"
    if state == "ended":
        return f"填报已结束，结束时间：{fmt(report.end_at)}"
    return ""
