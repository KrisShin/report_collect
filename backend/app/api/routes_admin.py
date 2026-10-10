"""管理端接口：列表、审核、导出、复制邮箱、发送邮件。"""

import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.models.audit_log import AuditLog
from app.models.mail_log import MailLog
from app.models.submission import Submission
from app.schemas.common import PageResult
from app.schemas.submission import ReviewRequest, SubmissionRead
from app.services.exporter import build_submissions_xlsx, default_attachment_name
from app.services.mailer import MailError, send_mail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/submissions", tags=["admin-submissions"])

SORTABLE_FIELDS = {
    "id": Submission.id,
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
    organization: str | None = None,
    position: str | None = None,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    status_value: str | None = None,
    keyword: str | None = None,
):
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
    rows = (await db.scalars(rows_stmt)).all()

    return PageResult[SubmissionRead](
        items=[SubmissionRead.model_validate(row) for row in rows],
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
) -> Submission:
    submission = await db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")

    submission.status = payload.status
    submission.review_note = payload.note
    submission.reviewed_by = admin.id
    submission.reviewed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(submission)

    await _write_audit(db, admin, "review", str(submission.id), payload.status, request)
    return submission


@router.post("/copy-emails")
async def copy_emails(
    ids: list[int] = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
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
    ids: list[int] = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> dict:
    rows = await _load_rows(db, ids)
    recipients = sorted({row.email for row in rows})
    attachment = build_submissions_xlsx(rows)
    attachment_name = default_attachment_name()

    log = MailLog(
        submission_ids=json.dumps([row.id for row in rows]),
        recipient=";".join(recipients),
        subject="【报告收集】信息确认",
        attachment_name=attachment_name,
        status="pending",
        operator_id=admin.id,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    try:
        await send_mail(
            recipients,
            subject=log.subject,
            html_body=_build_mail_html(len(rows)),
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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"邮件发送失败：{exc}"
        ) from exc

    now = datetime.now(UTC)
    log.status = "sent"
    log.sent_at = now
    for row in rows:
        row.status = "sent"
        row.mail_sent_at = now
        row.mail_error = None

    await db.commit()
    await _write_audit(db, admin, "send_mail", ",".join(str(row.id) for row in rows), None, request)
    return {"ok": True, "count": len(rows), "recipients": recipients, "attachment": attachment_name}


async def _load_rows(db: AsyncSession, ids: list[int]) -> list[Submission]:
    if not ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先选择记录")
    rows = list((await db.scalars(select(Submission).where(Submission.id.in_(ids)))).all())
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    if len(rows) != len(set(ids)):
        logger.warning("部分记录不存在 requested=%s found=%s", len(ids), len(rows))
    return rows


def _build_mail_html(count: int) -> str:
    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         font-size:14px;color:#333;">
      <p>您好：</p>
      <p>您提交的报告信息已通过审核，共 {count} 条记录，详见附件。</p>
      <p>如有疑问，请直接回复本邮件联系管理员。</p>
      <p style="margin-top:24px;">清华EIRI</p>
    </div>
    """


async def _write_audit(
    db: AsyncSession,
    admin: AdminUser,
    action: str,
    target: str | None,
    detail: str | None,
    request: Request | None,
) -> None:
    db.add(
        AuditLog(
            actor_id=admin.id,
            actor_name=admin.username,
            action=action,
            target=target,
            detail=detail,
            client_ip=request.client.host if request and request.client else None,
        )
    )
    await db.commit()

