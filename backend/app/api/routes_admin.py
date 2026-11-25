"""管理端接口：提交列表、审核、导出、复制邮箱、发送邮件。"""

import json
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

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
from app.core.time import to_db_utc
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.models.mail_log import MailLog
from app.models.person import Person
from app.models.report import Report
from app.models.submission import Submission
from app.schemas.common import PageResult
from app.schemas.submission import ReviewRequest, SubmissionRead
from app.services.audit import write_audit
from app.services.email_template import default_subject
from app.services.exporter import (
    build_submissions_xlsx,
    default_attachment_name,
    default_attachment_name_ascii,
)
from app.services.jobs import enqueue

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
    "send_mode": Submission.send_mode,
    "needs_manual": Submission.needs_manual,
    "submitted_at": Submission.submitted_at,
    "mail_sent_at": Submission.mail_sent_at,
}


def _apply_filters(
    stmt,
    *,
    report_id: str | None = None,
    processed: bool | None = None,
    ai_flag: str | None = None,
    exclude_ai_flag: str | None = None,
    organization: str | None = None,
    position: str | None = None,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    status_value: str | None = None,
    send_mode: str | None = None,
    needs_manual: bool | None = None,
    unsent: bool | None = None,
    submitted_from: datetime | None = None,
    keyword: str | None = None,
):
    if report_id:
        stmt = stmt.where(Submission.report_id == report_id)
    if processed is not None:
        stmt = stmt.where(Submission.is_processed.is_(processed))
    if ai_flag:
        stmt = stmt.where(Submission.ai_flag == ai_flag)
    if exclude_ai_flag:
        # NULL（尚未判定）也要保留，不能用 != 直接排除
        stmt = stmt.where(
            or_(Submission.ai_flag.is_(None), Submission.ai_flag != exclude_ai_flag)
        )
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
    if send_mode:
        stmt = stmt.where(Submission.send_mode == send_mode)
    if needs_manual is not None:
        stmt = stmt.where(Submission.needs_manual.is_(needs_manual))
    if unsent:
        stmt = stmt.where(Submission.mail_sent_at.is_(None))
        stmt = stmt.where(Submission.status != "sent")
    if submitted_from is not None:
        stmt = stmt.where(Submission.submitted_at >= to_db_utc(submitted_from))
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
    exclude_ai_flag: str | None = Query(None, description="排除指定 AI 标记（NULL 保留）"),
    organization: str | None = None,
    position: str | None = None,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    status_value: str | None = Query(None, alias="status"),
    send_mode: str | None = Query(None, description="发送方式：auto/manual"),
    needs_manual: bool | None = Query(None, description="是否仍需人工处理"),
    unsent: bool | None = Query(None, description="仅未发送：mail_sent_at 为空且状态非 sent"),
    recent_hours: int | None = Query(
        None, ge=1, le=72, description="仅最近 N 小时内填报"
    ),
    keyword: str | None = None,
    sort_by: str = "submitted_at",
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> PageResult[SubmissionRead]:
    submitted_from = (
        datetime.now(UTC) - timedelta(hours=recent_hours) if recent_hours else None
    )
    filters = {
        "report_id": report_id,
        "processed": processed,
        "ai_flag": ai_flag,
        "exclude_ai_flag": exclude_ai_flag,
        "organization": organization,
        "position": position,
        "name": name,
        "phone": phone,
        "email": email,
        "status_value": status_value,
        "send_mode": send_mode,
        "needs_manual": needs_manual,
        "unsent": unsent,
        "submitted_from": submitted_from,
        "keyword": keyword,
    }
    total = await db.scalar(_apply_filters(select(func.count()).select_from(Submission), **filters))

    sort_column = SORTABLE_FIELDS.get(sort_by, Submission.submitted_at)
    order = sort_column.asc() if sort_order == "asc" else sort_column.desc()

    rows_stmt = _apply_filters(select(Submission), **filters).order_by(order)
    rows_stmt = rows_stmt.offset((page - 1) * page_size).limit(page_size)
    rows = list((await db.scalars(rows_stmt)).all())
    titles = await _report_titles(db)
    person_sent = await _person_sent_map(
        db, {row.person_id for row in rows if row.person_id}
    )

    return PageResult[SubmissionRead](
        items=[_to_read(row, titles, person_sent) for row in rows],
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
    person_sent = await _person_sent_map(
        db, {submission.person_id} if submission.person_id else set()
    )
    return _to_read(submission, titles, person_sent)


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
    ids: list[int] | None = Body(None, embed=True),
    report_id: str | None = Body(None, embed=True),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> Response:
    """导出选中记录；传 report_id 时导出该报告下的全部填报。"""
    if report_id:
        rows = await _report_submission_rows(db, report_id)
    else:
        rows = await _load_rows(db, ids or [])
    titles = await _report_titles(db)
    for row in rows:
        row.report_title = titles.get(row.report_id)

    content = build_submissions_xlsx(rows)
    now = datetime.now(UTC)
    filename = default_attachment_name(now)
    # HTTP 头只能 latin-1：中文名按 RFC 5987 编码，另给 ASCII 回退名供旧客户端使用
    disposition = (
        f'attachment; filename="{default_attachment_name_ascii(now)}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": disposition},
    )


@router.post("/send-mail")
async def send_submissions_mail(
    request: Request,
    background: BackgroundTasks,
    ids: list[int] = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> dict:
    """提交邮件发送任务后立即返回，实际发送在后台进行，不阻塞请求。

    按报告分组：每个报告一条 MailLog，主题取报告的 email_subject（为空回退默认）。
    """

    rows = await _load_rows(db, ids)
    return await _queue_report_mails(
        db=db,
        background=background,
        rows=rows,
        admin=admin,
        request=request,
    )


async def _queue_report_mails(
    *,
    db: AsyncSession,
    background: BackgroundTasks,
    rows: list[Submission],
    admin: AdminUser,
    request: Request,
) -> dict:
    """按报告分组建 MailLog 并入队发送。"""

    titles = await _report_titles(db)
    for row in rows:
        row.report_title = titles.get(row.report_id)

    reports = await _reports_by_id(db, {row.report_id for row in rows if row.report_id})
    groups: dict[str | None, list[Submission]] = {}
    for row in rows:
        groups.setdefault(row.report_id, []).append(row)

    created: list[tuple[MailLog, str | None, list[Submission]]] = []
    for report_id, group_rows in groups.items():
        report = reports.get(report_id) if report_id else None
        subject = (
            report.email_subject
            if report and report.email_subject
            else default_subject(report.title if report else "")
        )
        log = MailLog(
            submission_ids=json.dumps([row.id for row in group_rows]),
            recipient=";".join(sorted({row.email for row in group_rows})),
            subject=subject,
            status="pending",
            operator_id=admin.id,
        )
        db.add(log)
        created.append((log, report_id, group_rows))

    await db.commit()
    for log, _report_id, _group_rows in created:
        await db.refresh(log)

    group_payload: list[dict] = []
    for log, report_id, group_rows in created:
        report = reports.get(report_id) if report_id else None
        group_payload.append(
            {
                "log_id": log.id,
                "report_id": report_id,
                "report_title": report.title if report else titles.get(report_id),
                "subject": log.subject,
                "count": len(group_rows),
            }
        )
        await enqueue(
            background,
            "report_mail",
            log_id=log.id,
            submission_ids=[row.id for row in group_rows],
        )

    submission_ids = [row.id for row in rows]
    await write_audit(
        db,
        admin,
        "send_mail",
        ",".join(str(item) for item in submission_ids),
        f"queued:groups={len(created)}",
        request,
    )
    logger.info(
        "邮件任务已入队 log_ids=%s count=%s",
        [log.id for log, _report_id, _rows in created],
        len(submission_ids),
    )
    return {
        "ok": True,
        "queued": True,
        "log_id": created[0][0].id if created else None,
        "log_ids": [log.id for log, _report_id, _rows in created],
        "count": len(submission_ids),
        "ids": submission_ids,
        "recipients": sorted({row.email for row in rows}),
        "groups": group_payload,
    }


async def _report_titles(db: AsyncSession) -> dict[str, str]:
    rows = (await db.execute(select(Report.id, Report.title))).all()
    return {report_id: title for report_id, title in rows}


async def _reports_by_id(db: AsyncSession, report_ids: set[str]) -> dict[str, Report]:
    if not report_ids:
        return {}
    rows = (await db.scalars(select(Report).where(Report.id.in_(report_ids)))).all()
    return {report.id: report for report in rows}


async def _person_sent_map(
    db: AsyncSession, person_ids: set[int]
) -> dict[int, bool]:
    if not person_ids:
        return {}
    rows = (
        await db.execute(
            select(Person.id, Person.has_sent).where(Person.id.in_(person_ids))
        )
    ).all()
    return {person_id: bool(has_sent) for person_id, has_sent in rows}


def _to_read(
    row: Submission,
    titles: dict[str, str],
    person_sent: dict[int, bool] | None = None,
) -> SubmissionRead:
    data = SubmissionRead.model_validate(row)
    data.report_title = titles.get(row.report_id) if row.report_id else None
    data.person_has_sent = bool(
        person_sent and row.person_id and person_sent.get(row.person_id, False)
    )
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


async def _report_submission_rows(db: AsyncSession, report_id: str) -> list[Submission]:
    """按报告取全部填报，按提交时间升序，保证导出顺序稳定。"""
    if not await db.get(Report, report_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    rows = list(
        (
            await db.scalars(
                select(Submission)
                .where(Submission.report_id == report_id)
                .order_by(Submission.submitted_at.asc(), Submission.id.asc())
            )
        ).all()
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该报告暂无填报记录")
    return rows
