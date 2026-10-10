"""腾讯企业邮箱 SMTP 发送。"""

import logging
from email.message import EmailMessage
from email.utils import formataddr

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# TODO（发布前必须处理）：测试期硬编码收件箱。
# 删除 TEST_INBOX 并把 resolve_recipients 改回按业务收件人发送。
# ============================================================
TEST_INBOX = "krisshin@yeah.net"


class MailError(RuntimeError):
    pass


def resolve_recipients(recipients: list[str]) -> list[str]:
    """测试期：所有邮件统一只发测试收件箱。"""

    return [TEST_INBOX] if TEST_INBOX else list(recipients)


async def send_mail(
    recipients: list[str],
    subject: str,
    html_body: str,
    *,
    attachment_name: str | None = None,
    attachment_bytes: bytes | None = None,
) -> None:
    # 测试期统一转测试收件箱（见文件顶部 TODO）
    recipients = resolve_recipients(recipients)
    if not recipients:
        raise MailError("收件人不能为空")
    if not settings.mail.user or not settings.mail.password:
        raise MailError("SMTP 账号或授权码未配置")

    message = EmailMessage()
    message["From"] = formataddr((settings.mail.from_name, settings.mail.user))
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
            hostname=settings.mail.host,
            port=settings.mail.port,
            username=settings.mail.user,
            password=settings.mail.password,
            use_tls=settings.mail.use_ssl,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("邮件发送失败")
        raise MailError(str(exc)) from exc

    logger.info("邮件发送成功 recipients=%s subject=%s", len(recipients), subject)
