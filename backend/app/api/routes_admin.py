"""管理端接口：提交列表、审核、导出、复制邮箱、发送邮件。"""

import json
import logging
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.models.mail_log import MailLog
from app.models.report import Report
from app.models.submission import Submission
from app.schemas.common import PageResult
from app.schemas.submission import ReviewRequest, SubmissionRead
from app.services.audit import write_audit
from app.services.exporter import build_submissions_xlsx, default_attachment_name
from app.services.jobs import enqueue
from app.services.mailer import resolve_recipients

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/submissions", tags=["admin-submissions"])

SORTABLE_FIELDS = {
    "id": Submission.id,
    "report_id": Submission.report_id,
    "organization": Submission.organization,
    "position": Submission.position,
    "name": Submission.name,
    "phone": Submission.phone,
    "email": Submission.email,
    "status": Submission.status,
    "submitted_at": Submission.submitted_at,
    "mail_sent_at": Submission.mail_sent_at,
}


def _apply_filters(
    stmt,
    *,
    report_id: str | None = None,
    processed: bool | None = None,
    ai_flag: str | None = None,
    organization: str | None = None,
    position: str | None = None,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    status_value: str | None = None,
    keyword: str | None = None,
):
    if report_id:
        stmt = stmt.where(Submission.report_id == report_id)
    if processed is not None:
        stmt = stmt.where(Submission.is_processed.is_(processed))
    if ai_flag:
        stmt = stmt.where(Submission.ai_flag == ai_flag)
    if organization:
        stmt = stmt.where(Submission.organization.contains(organization))
    if position:
        stmt = stmt.where(Submission.position.contains(position))
    if name:
        stmt = stmt.where(Submission.name.contains(name))
    if phone:
        stmt = stmt.where(Submission.phone.contains(phone))
    if email:
        stmt = stmt.where(Submission.email.contains(email))
    if status_value:
        stmt = stmt.where(Submission.status == status_value)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                Submission.organization.like(like),
                Submission.position.like(like),
                Submission.name.like(like),
                Submission.phone.like(like),
                Submission.email.like(like),
            )
        )
    return stmt


@router.get("", response_model=PageResult[SubmissionRead])
async def list_submissions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    report_id: str | None = None,
    processed: bool | None = Query(None, description="是否已处理"),
    ai_flag: str | None = Query(None, description="AI 标记：ok/suspicious/error/skipped"),
    organization: str | None = None,
    position: str | None = None,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    status_value: str | None = Query(None, alias="status"),
    keyword: str | None = None,
    sort_by: str = "submitted_at",
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> PageResult[SubmissionRead]:
    filters = {
        "report_id": report_id,
        "processed": processed,
        "ai_flag": ai_flag,
        "organization": organization,
        "position": position,
        "name": name,
        "phone": phone,
        "email": email,
        "status_value": status_value,
        "keyword": keyword,
    }
    total = await db.scalar(_apply_filters(select(func.count()).select_from(Submission), **filters))

    sort_column = SORTABLE_FIELDS.get(sort_by, Submission.submitted_at)
    order = sort_column.asc() if sort_order == "asc" else sort_column.desc()

    rows_stmt = _apply_filters(select(Submission), **filters).order_by(order)
    rows_stmt = rows_stmt.offset((page - 1) * page_size).limit(page_size)
    rows = list((await db.scalars(rows_stmt)).all())
    titles = await _report_titles(db)

    return PageResult[SubmissionRead](
        items=[_to_read(row, titles) for row in rows],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.patch("/{submission_id}/review", response_model=SubmissionRead)
async def review_submission(
    submission_id: int,
    payload: ReviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> SubmissionRead:
    submission = await db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")

    submission.status = payload.status
    submission.review_note = payload.note
    submission.reviewed_by = admin.id
    submission.reviewed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(submission)

    await write_audit(db, admin, "review", str(submission.id), payload.status, request)
    titles = await _report_titles(db)
    return _to_read(submission, titles)


@router.post("/copy-emails")
async def copy_emails(
    ids: list[int] = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> dict:
    if not ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先选择记录")
    rows = (await db.scalars(select(Submission).where(Submission.id.in_(ids)))).all()
    emails = sorted({row.email for row in rows})
    return {"emails": ";".join(emails), "count": len(emails)}


@router.post("/export")
async def export_submissions(
    ids: list[int] = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> Response:
    rows = await _load_rows(db, ids)
    titles = await _report_titles(db)
    for row in rows:
        row.report_title = titles.get(row.report_id)

    content = build_submissions_xlsx(rows)
    filename = default_attachment_name()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/send-mail")
async def send_submissions_mail(
    request: Request,
    background: BackgroundTasks,
    ids: list[int] = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> dict:
    """提交邮件发送任务后立即返回，实际发送在后台进行，不阻塞请求。"""

    rows = await _load_rows(db, ids)
    titles = await _report_titles(db)
    for row in rows:
        row.report_title = titles.get(row.report_id)

    recipients = resolve_recipients(sorted({row.email for row in rows}))
    submission_ids = [row.id for row in rows]

    log = MailLog(
        submission_ids=json.dumps(submission_ids),
        recipient=";".join(recipients),
        subject="【报告收集】信息确认",
        status="pending",
        operator_id=admin.id,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    await enqueue(background, "report_mail", log_id=log.id, submission_ids=submission_ids)
    await write_audit(
        db,
        admin,
        "send_mail",
        ",".join(str(item) for item in submission_ids),
        "queued",
        request,
    )

    logger.info("邮件任务已入队 log_id=%s count=%s", log.id, len(submission_ids))
    return {
        "ok": True,
        "queued": True,
        "log_id": log.id,
        "count": len(submission_ids),
        "recipients": recipients,
    }


async def _report_titles(db: AsyncSession) -> dict[int, str]:
    rows = (await db.execute(select(Report.id, Report.title))).all()
    return {report_id: title for report_id, title in rows}


def _to_read(row: Submission, titles: dict[int, str]) -> SubmissionRead:
    data = SubmissionRead.model_validate(row)
    data.report_title = titles.get(row.report_id) if row.report_id else None
    return data


async def _load_rows(db: AsyncSession, ids: list[int]) -> list[Submission]:
    if not ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先选择记录")
    rows = list((await db.scalars(select(Submission).where(Submission.id.in_(ids)))).all())
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    if len(rows) != len(set(ids)):
        logger.warning("部分记录不存在 requested=%s found=%s", len(ids), len(rows))
    return rows
