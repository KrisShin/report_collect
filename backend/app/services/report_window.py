"""报告填报时间段处理。"""

from datetime import UTC, datetime

from app.core.time import format_local
from app.models.report import Report


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

    def fmt(value: datetime | None) -> str:
        return format_local(value) or "未设置"

    state = window_state(report)
    if state == "not_started":
        return f"填报尚未开始，开始时间：{fmt(report.start_at)}"
    if state == "ended":
        return f"填报已结束，结束时间：{fmt(report.end_at)}"
    return ""
