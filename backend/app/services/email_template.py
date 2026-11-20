"""邮件 HTML 模板渲染。"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import BACKEND_DIR, settings
from app.core.time import to_local

TEMPLATE_DIR = BACKEND_DIR / "app" / "templates"
HTML_TEMPLATE_NAME = "email_report.html"
TEXT_TEMPLATE_NAME = "email_report.txt"

# 报告未设置 email_subject 时使用的默认主题
DEFAULT_SUBJECT = "【报告分享】中国电动重卡补能基础设施进展报告"


def default_subject(report_title: str | None) -> str:
    """报告未填写邮件主题时，默认主题跟随报告标题。"""

    title = (report_title or "").strip()
    if not title:
        return DEFAULT_SUBJECT
    return (f"【报告分享】{title}")[:255]


def load_global_template_html() -> str:
    """读取全局 HTML 模板原文（用于导入到报告）。"""

    return (TEMPLATE_DIR / HTML_TEMPLATE_NAME).read_text(encoding="utf-8")

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
    template_html: str | None = None,
) -> str:
    """渲染邮件 HTML。

    上传的报告模板按静态内容原样返回（不经过 Jinja），
    未上传时继续使用全局 Jinja 模板。
    """

    if template_html:
        return template_html

    tz = ZoneInfo(settings.app.timezone)
    moment = to_local(generated_at or datetime.now(UTC)) or datetime.now(tz)

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
