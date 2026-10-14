"""后台任务实现。

同一份实现既可以被 FastAPI BackgroundTasks 调用（本地/Redis 不可用时），
也可以被 Redis worker（python -m app.worker）消费，保证任务不丢。
"""

import asyncio
import json
import logging
import time
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.mail_log import MailLog
from app.models.report import Report
from app.models.submission import Submission
from app.services.ai import check_submission
from app.services.attachments import collect_attachments
from app.services.email_template import render_report_email, render_report_email_text
from app.services.feishu import feishu_client
from app.services.mailer import MailError, OutgoingMail, send_mails

PROGRESS_INTERVAL_SECONDS = 30

logger = logging.getLogger(__name__)


async def _report_titles(db) -> dict[str, str]:  # noqa: ANN001
    rows = (await db.execute(select(Report.id, Report.title))).all()
    return {report_id: title for report_id, title in rows}


async def process_submission(submission_id: int) -> None:
    """AI 质量判定 + 飞书提醒（使用独立数据库会话）。"""

    async with AsyncSessionLocal() as db:
        submission = await db.get(Submission, submission_id)
        if not submission:
            logger.warning("后台任务：提交不存在 id=%s", submission_id)
            return

        result = await check_submission(
            organization=submission.organization,
            position=submission.position,
            name=submission.name,
            phone=submission.phone,
            email=submission.email,
        )
        submission.ai_flag = result["flag"]
        submission.ai_score = result["score"]
        submission.ai_reason = result["reason"]
        await db.commit()

        report = await db.get(Report, submission.report_id) if submission.report_id else None
        await _notify_feishu(db, submission, report.title if report else "未知报告")


async def _notify_feishu(db, submission: Submission, report_title: str) -> None:  # noqa: ANN001
    from app.core.config import settings

    text = "\n".join(
        [
            f"【新的报告提交】{report_title}",
            f"姓名：{submission.name}",
            f"单位：{submission.organization}",
            f"职务：{submission.position}",
            f"电话：{submission.phone}",
            f"邮箱：{submission.email}",
            f"提交时间：{submission.submitted_at:%Y-%m-%d %H:%M}",
            f"管理端：{settings.admin_url}",
        ]
    )
    try:
        await feishu_client.send_text(text)
        submission.feishu_status = "sent"
    except Exception as exc:  # noqa: BLE001
        logger.warning("飞书提醒发送失败 submission_id=%s error=%s", submission.id, exc)
        submission.feishu_status = "failed"
        submission.feishu_error = json.dumps({"error": str(exc)}, ensure_ascii=False)
    await db.commit()


async def _notify_feishu_safe(text: str) -> None:
    """飞书通知：失败只记日志，绝不影响发信流程。"""

    try:
        await feishu_client.send_text(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("飞书通知发送失败：%s", exc)


async def _notify_feishu_card_safe(card: dict) -> None:
    """飞书卡片通知：失败只记日志，不影响发信流程。"""

    try:
        await feishu_client.send_card(card)
    except Exception as exc:  # noqa: BLE001
        logger.warning("飞书卡片发送失败：%s", exc)


def build_mail_result_card(log_id: int, total: int, success: int, failed: int) -> dict:
    """发送完成（有失败）的交互卡片。

    按钮使用飞书卡片回调（value 原样回传），由 /api/feishu/card/callback 处理，
    回调请求会校验 verification_token、签名与来源群 chat_id。
    """

    return {
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "报告收集 · 邮件发送完成（有失败）"},
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**成功** {success} / **总数** {total}\n**失败** {failed}",
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": f"一键重试失败的 {failed} 封",
                        },
                        "type": "primary",
                        "value": {"action_type": "retry_mail", "log_id": log_id},
                    }
                ],
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "点击后由飞书回调触发，先冷却 5 分钟再重试失败邮箱",
                    }
                ],
            },
        ],
    }


class _MailProgressReporter:
    """发送期间每 PROGRESS_INTERVAL_SECONDS 秒向飞书汇报一次进度。"""

    def __init__(self, interval: float = PROGRESS_INTERVAL_SECONDS) -> None:
        self.interval = interval
        self.last = time.monotonic()

    async def __call__(self, done: int, total: int, success: int, failed: int) -> None:
        now = time.monotonic()
        if now - self.last < self.interval:
            return
        self.last = now
        await _notify_feishu_safe(
            f"【报告收集】邮件发送中：{done}/{total}，成功 {success}，失败 {failed}"
        )


async def deliver_report_mail(log_id: int, submission_ids: list[int]) -> None:
    """方案 A：勾选 N 条 → 发 N 封，每封只发给该条本人，附件只含本人这一条。

    复用一条 SMTP 连接顺序发送，按 mail.send_interval_seconds 节流；
    单封失败不影响其他邮件，逐条回写状态。
    """

    async with AsyncSessionLocal() as db:
        log = await db.get(MailLog, log_id)
        if not log:
            logger.warning("后台任务：邮件记录不存在 id=%s", log_id)
            return

        rows = list(
            (await db.scalars(select(Submission).where(Submission.id.in_(submission_ids)))).all()
        )
        titles = await _report_titles(db)

        mails: list[OutgoingMail] = []
        attached_names: list[str] = []
        text_body = render_report_email_text()
        for row in rows:
            row.report_title = titles.get(row.report_id)
            # 附件只使用附件目录里的静态文件（不再自动生成 xlsx）
            static_files = collect_attachments(row.report_id)
            if static_files:
                attached_names = [name for name, _ in static_files]
            mails.append(
                OutgoingMail(
                    recipients=[row.email],
                    subject=log.subject,
                    html_body=render_report_email(
                        records=[row],
                        extra_attachments=[name for name, _ in static_files],
                    ),
                    text_body=text_body,
                    extra_attachments=static_files,
                )
            )

        reporter = _MailProgressReporter()
        try:
            results = await send_mails(mails, on_progress=reporter)
        except MailError as exc:
            log.status = "failed"
            log.error = str(exc)
            for row in rows:
                row.mail_error = str(exc)
            await db.commit()
            logger.warning("邮件发送失败（连接异常）log_id=%s error=%s", log_id, exc)
            await _notify_feishu_safe(
                f"【报告收集】邮件发送失败：SMTP 连接异常，成功 0/{len(rows)}"
            )
            return

        now = datetime.now(UTC)
        success = 0
        failed_ids: list[int] = []
        for row, error in zip(rows, results, strict=False):
            if error is None:
                success += 1
                row.status = "sent"
                row.mail_sent_at = now
                row.mail_error = None
                row.is_processed = True
                row.processed_at = now
                row.processed_action = "mail_sent"
            else:
                # 发送失败：不改变原状态（仍可再次勾选重发），只记录失败原因
                row.mail_error = error
                failed_ids.append(row.id)

        failed = len(rows) - success
        log.status = "sent" if failed == 0 else ("failed" if success == 0 else "partial")
        log.attachment_name = ";".join(attached_names) or None
        log.failed_submission_ids = json.dumps(failed_ids)
        log.sent_at = now if success else None
        log.error = None if failed == 0 else f"{failed} 封发送失败"
        await db.commit()
        logger.info("邮件发送完成 log_id=%s 成功=%s 失败=%s", log_id, success, failed)

        if failed:
            # 有失败：交互卡片，带"一键重试失败"按钮
            await _notify_feishu_card_safe(
                build_mail_result_card(log.id, total=len(rows), success=success, failed=failed)
            )
        else:
            # 全部成功：纯文本汇报，不带按钮
            await _notify_feishu_safe(f"【报告收集】邮件发送完成：成功 {success}/{len(rows)}")


async def schedule_report_mail_retry(log_id: int, submission_ids: list[int]) -> None:
    """失败重试：先冷却 retry_delay_seconds，再重发这批失败的邮箱。

    用 asyncio.create_task 延迟执行，不阻塞 worker 任务队列。
    """

    delay = max(settings.mail.retry_delay_seconds, 0)
    logger.info("失败重试已排定 log_id=%s 冷却=%ss 数量=%s", log_id, delay, len(submission_ids))
    asyncio.create_task(_delayed_report_mail(log_id, submission_ids, delay))


async def _delayed_report_mail(log_id: int, submission_ids: list[int], delay: int) -> None:
    await asyncio.sleep(delay)
    await deliver_report_mail(log_id, submission_ids)


HANDLERS = {
    "submission_process": process_submission,
    "report_mail": deliver_report_mail,
    "report_mail_retry": schedule_report_mail_retry,
}
