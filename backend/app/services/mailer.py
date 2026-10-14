"""腾讯企业邮箱 SMTP 发送。

== 测试门控说明 ==
全项目只有一处门控，在 `send_mails()` 里那一行：
    需要真实发送时，把那一行注释掉即可。
除此以外没有任何地方会改写收件人（配置文件里也不再有任何收件人开关）。
"""

import asyncio
import logging
import mimetypes
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)

# 测试收件箱（仅被下面那一行门控使用）
TEST_INBOX = "krisshin@yeah.net"


class MailError(RuntimeError):
    pass


# 进度回调：(已完成, 总数, 成功, 失败)
ProgressHook = Callable[[int, int, int, int], Awaitable[None]]


@dataclass(slots=True)
class OutgoingMail:
    recipients: list[str]
    subject: str
    html_body: str
    # 纯文本兜底正文；为空时退回一句提示
    text_body: str | None = None
    attachment_name: str | None = None
    attachment_bytes: bytes | None = None
    # 静态附件目录里的文件：[(文件名, 内容)]
    extra_attachments: list[tuple[str, bytes]] = field(default_factory=list)


def _build_message(mail: OutgoingMail) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr((settings.mail.from_name, settings.mail.user))
    message["To"] = ", ".join(mail.recipients)
    message["Subject"] = mail.subject
    message.set_content(mail.text_body or "请使用支持 HTML 的邮件客户端查看本邮件。")
    message.add_alternative(mail.html_body, subtype="html")

    if mail.attachment_bytes and mail.attachment_name:
        message.add_attachment(
            mail.attachment_bytes,
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=mail.attachment_name,
        )

    for name, content in mail.extra_attachments:
        guessed, _encoding = mimetypes.guess_type(name)
        if guessed and "/" in guessed:
            maintype, subtype = guessed.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=name)

    return message


async def send_mails(
    mails: list[OutgoingMail],
    *,
    on_progress: ProgressHook | None = None,
) -> list[str | None]:
    """统一发信出口。

    - 全项目唯一的测试门控就在本函数内（见下面标注的那一行）
    - 多封邮件复用同一条 SMTP 连接，按 mail.send_interval_seconds 节流
    - 返回与入参等长的错误列表：None=成功，字符串=失败原因（单封失败不影响其他邮件）
    """

    if not mails:
        return []
    if not settings.mail.user or not settings.mail.password:
        raise MailError("SMTP 账号或授权码未配置")

    # >>>>> 唯一门控：需要测试拦截时取消下一行注释（改发 TEST_INBOX）<<<<<
    # mails = [replace(mail, recipients=[TEST_INBOX]) for mail in mails]

    errors: list[str | None] = []
    try:
        smtp = aiosmtplib.SMTP(
            hostname=settings.mail.host,
            port=settings.mail.port,
            use_tls=settings.mail.use_ssl,
            timeout=30,
        )
        async with smtp:
            await smtp.login(settings.mail.user, settings.mail.password)
            for index, mail in enumerate(mails):
                try:
                    await smtp.send_message(_build_message(mail))
                    logger.info("邮件发送成功 to=%s subject=%s", mail.recipients, mail.subject)
                    errors.append(None)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("邮件发送失败 to=%s error=%s", mail.recipients, exc)
                    errors.append(str(exc))

                if on_progress is not None:
                    done = index + 1
                    failed_count = sum(1 for item in errors if item)
                    try:
                        await on_progress(done, len(mails), done - failed_count, failed_count)
                    except Exception:  # noqa: BLE001
                        logger.warning("进度回调执行失败", exc_info=True)

                if index < len(mails) - 1:
                    await asyncio.sleep(max(settings.mail.send_interval_seconds, 0))
    except Exception as exc:  # noqa: BLE001
        logger.exception("SMTP 连接失败")
        raise MailError(f"SMTP 连接失败：{exc}") from exc

    return errors


async def send_mail(
    recipients: list[str],
    subject: str,
    html_body: str,
    text_body: str | None = None,
    *,
    attachment_name: str | None = None,
    attachment_bytes: bytes | None = None,
) -> None:
    """单封发送（内部复用统一出口，门控同样只有那一处）。"""

    if not recipients:
        raise MailError("收件人不能为空")

    errors = await send_mails(
        [
            OutgoingMail(
                recipients=list(recipients),
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                attachment_name=attachment_name,
                attachment_bytes=attachment_bytes,
            )
        ]
    )
    if errors and errors[0]:
        raise MailError(errors[0])
