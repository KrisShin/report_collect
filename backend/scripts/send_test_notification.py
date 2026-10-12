"""联调脚本：向飞书群发送测试消息，并向指定邮箱发送测试邮件（带 xlsx 附件）。

用法（在 backend 目录下）：
    C:\\Users\\HP\\miniconda3\\envs\\reportc\\python.exe -m scripts.send_test_notification
    ... -m scripts.send_test_notification --mail-to someone@example.com
"""

import argparse
import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from app.core.config import settings
from app.services.exporter import build_submissions_xlsx, default_attachment_name
from app.services.feishu import feishu_client
from app.services.mailer import TEST_INBOX, send_mail


async def send_feishu_test() -> None:
    text = "\n".join(
        [
            "【联调测试】报告收集系统",
            f"飞书机器人连通正常，发送时间：{datetime.now(UTC):%Y-%m-%d %H:%M:%S} UTC",
        ]
    )
    await feishu_client.send_text(text)
    print("[OK] 飞书测试消息已发送")


async def send_mail_test(recipient: str) -> None:
    sample = SimpleNamespace(
        organization="清华大学能源互联网创新研究院",
        position="联调测试",
        name="测试记录",
        phone="13800138000",
        email=recipient,
        submitted_at=datetime.now(UTC),
    )
    attachment = build_submissions_xlsx([sample], sheet_title="联调测试")
    attachment_name = default_attachment_name()

    await send_mail(
        [recipient],
        subject="【测试】报告收集系统邮件联调",
        html_body=(
            "<p>这是一封来自报告收集系统的联调测试邮件。</p>"
            "<p>如果你收到这封邮件，说明腾讯企业邮箱 SMTP 配置正常，附件为 xlsx 模板示例。</p>"
        ),
        attachment_name=attachment_name,
        attachment_bytes=attachment,
    )
    actual = TEST_INBOX or recipient
    print(
        f"[OK] 测试邮件已发送，请求收件人 {recipient}，"
        f"实际收件人 {actual}，附件 {attachment_name}"
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mail-to", default=settings.mail.user, help="测试邮件收件人")
    parser.add_argument("--skip-feishu", action="store_true")
    parser.add_argument("--skip-mail", action="store_true")
    args = parser.parse_args()

    if not args.skip_feishu:
        try:
            await send_feishu_test()
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] 飞书发送失败：{exc}")

    if not args.skip_mail:
        try:
            await send_mail_test(args.mail_to)
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] 邮件发送失败：{exc}")


if __name__ == "__main__":
    asyncio.run(main())
