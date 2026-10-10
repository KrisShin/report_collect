"""腾讯企业邮箱 SMTP 发送。"""

import logging
from email.message import EmailMessage
from email.utils import formataddr

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


class MailError(RuntimeError):
    pass


async def send_mail(
    recipients: list[str],
    subject: str,
    html_body: str,
    *,
    attachment_name: str | None = None,
    attachment_bytes: bytes | None = None,
) -> None:
    if not recipients:
        raise MailError("收件人不能为空")
    if not settings.smtp_user or not settings.smtp_password:
        raise MailError("SMTP 账号或授权码未配置")

    message = EmailMessage()
    message["From"] = formataddr((settings.mail_from_name, settings.smtp_user))
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content("请使用支持 HTML 的邮件客户端查看本邮件。")
    message.add_alternative(html_body, subtype="html")

    if attachment_bytes and attachment_name:
        message.add_attachment(
            attachment_bytes,
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=attachment_name,
        )

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_ssl,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("邮件发送失败")
        raise MailError(str(exc)) from exc

    logger.info("邮件发送成功 recipients=%s subject=%s", len(recipients), subject)
