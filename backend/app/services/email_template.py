"""邮件 HTML 模板渲染。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import BACKEND_DIR, settings

TEMPLATE_DIR = BACKEND_DIR / "app" / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_report_email(
    *,
    records: list,
    generated_at: datetime | None = None,
    extra_attachments: list[str] | None = None,
) -> str:
    tz = ZoneInfo(settings.app.timezone)
    moment = (generated_at or datetime.now(tz)).astimezone(tz)

    report_titles: list[str] = []
    for record in records:
        title = getattr(record, "report_title", None)
        if title and title not in report_titles:
            report_titles.append(title)

    template = env.get_template("email_report.html")
    return template.render(
        generated_at=moment.strftime("%Y-%m-%d %H:%M"),
        record_count=len(records),
        report_titles=report_titles,
        extra_attachments=extra_attachments or [],
        records=[
            {
                "index": index + 1,
                "report": getattr(record, "report_title", "") or "-",
                "name": record.name,
                "organization": record.organization,
                "position": record.position,
                "phone": record.phone,
                "email": record.email,
            }
            for index, record in enumerate(records)
        ],
    )
