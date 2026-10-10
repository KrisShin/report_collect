"""后台任务实现。

同一份实现既可以被 FastAPI BackgroundTasks 调用（本地/Redis 不可用时），
也可以被 Redis worker（python -m app.worker）消费，保证任务不丢。
"""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.mail_log import MailLog
from app.models.report import Report
from app.models.submission import Submission
from app.services.ai import check_submission
from app.services.email_template import render_report_email
from app.services.exporter import build_submissions_xlsx, default_attachment_name
from app.services.feishu import feishu_client
from app.services.mailer import MailError, send_mail

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


async def deliver_report_mail(log_id: int, submission_ids: list[int]) -> None:
    """生成附件并发送邮件，然后回写发送结果与处理状态。"""

    async with AsyncSessionLocal() as db:
        log = await db.get(MailLog, log_id)
        if not log:
            logger.warning("后台任务：邮件记录不存在 id=%s", log_id)
            return

        rows = list(
            (await db.scalars(select(Submission).where(Submission.id.in_(submission_ids)))).all()
        )
        titles = await _report_titles(db)
        for row in rows:
            row.report_title = titles.get(row.report_id)

        recipients = [item for item in (log.recipient or "").split(";") if item]
        attachment_name = default_attachment_name()

        try:
            attachment = build_submissions_xlsx(rows)
            html_body = render_report_email(records=rows)
            await send_mail(
                recipients,
                subject=log.subject,
                html_body=html_body,
                attachment_name=attachment_name,
                attachment_bytes=attachment,
            )
        except MailError as exc:
            log.status = "failed"
            log.error = str(exc)
            for row in rows:
                row.status = "failed"
                row.mail_error = str(exc)
            await db.commit()
            logger.warning("邮件发送失败 log_id=%s error=%s", log_id, exc)
            return

        now = datetime.now(UTC)
        log.status = "sent"
        log.sent_at = now
        log.attachment_name = attachment_name
        for row in rows:
            row.status = "sent"
            row.mail_sent_at = now
            row.mail_error = None
            row.is_processed = True
            row.processed_at = now
            row.processed_action = "mail_sent"
        await db.commit()
        logger.info("邮件发送完成 log_id=%s count=%s", log_id, len(rows))


HANDLERS = {
    "submission_process": process_submission,
    "report_mail": deliver_report_mail,
}
