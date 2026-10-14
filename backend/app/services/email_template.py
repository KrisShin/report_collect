"""邮件 HTML 模板渲染。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import BACKEND_DIR, settings

TEMPLATE_DIR = BACKEND_DIR / "app" / "templates"
HTML_TEMPLATE_NAME = "email_report.html"
TEXT_TEMPLATE_NAME = "email_report.txt"

env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_report_email_text() -> str:
    """纯文本正文。

    与 ``email_report.html`` 的正文保持一致（无变量），供不支持 HTML 的
    客户端兜底显示；段落之间保留空行，客户端里换行依旧可读。
    """
    return (TEMPLATE_DIR / TEXT_TEMPLATE_NAME).read_text(encoding="utf-8").strip()


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

    template = env.get_template(HTML_TEMPLATE_NAME)
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
