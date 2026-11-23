"""管理端接口：报告的创建、编辑、启用/停用，以及邮件模板/附件上传。"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.config import settings
from app.core.security import verify_password
from app.core.time import to_api_utc, to_db_utc
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.models.report import Report
from app.models.submission import Submission
from app.schemas.report import (
    ReportAdminRead,
    ReportCreate,
    ReportDeleteRequest,
    ReportRead,
    ReportUpdate,
)
from app.services.attachments import collect_legacy_attachments
from app.services.audit import write_audit
from app.services.email_template import HTML_TEMPLATE_NAME, load_global_template_html
from app.services.report_uploads import (
    UploadError,
    UploadTooLargeError,
    delete_uploaded_attachment,
    has_uploaded_attachments,
    list_uploaded_attachments,
    remove_report_upload_dir,
    sanitize_filename,
    save_attachment_payloads,
    save_uploaded_attachments,
)

router = APIRouter(prefix="/api/admin/reports", tags=["admin-reports"])


@router.get("", response_model=list[ReportAdminRead])
async def list_reports(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> list[ReportAdminRead]:
    stmt = (
        select(Report, func.count(Submission.id))
        .outerjoin(Submission, Submission.report_id == Report.id)
        .group_by(Report.id)
        .order_by(Report.sort_order, Report.id)
    )
    rows = (await db.execute(stmt)).all()
    return [
        ReportAdminRead(
            **ReportRead.model_validate(report).model_dump(),
            submission_count=count,
            attachment_count=len(list_uploaded_attachments(report.id)),
        )
        for report, count in rows
    ]


@router.post("", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> Report:
    data = payload.model_dump()
    data["start_at"] = to_db_utc(data.get("start_at"))
    data["end_at"] = to_db_utc(data.get("end_at"))

    report = Report(**data)
    db.add(report)
    await db.commit()
    await db.refresh(report)

    await write_audit(db, admin, "report_create", str(report.id), report.title, request)
    return report


@router.patch("/{report_id}", response_model=ReportRead)
async def update_report(
    report_id: str,
    payload: ReportUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> Report:
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")

    data = payload.model_dump(exclude_unset=True)
    start_at = data.get("start_at", report.start_at)
    end_at = data.get("end_at", report.end_at)
    if start_at and end_at and start_at >= end_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="开始时间必须早于结束时间",
        )

    if "start_at" in data:
        data["start_at"] = to_db_utc(data["start_at"])
    if "end_at" in data:
        data["end_at"] = to_db_utc(data["end_at"])

    for key, value in data.items():
        setattr(report, key, value)
    await db.commit()
    await db.refresh(report)

    await write_audit(db, admin, "report_update", str(report.id), report.title, request)
    return report


@router.get("/{report_id}", response_model=ReportRead)
async def get_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> Report:
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    return report


async def _get_report_or_404(db: AsyncSession, report_id: str) -> Report:
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    return report


@router.get("/{report_id}/email-template")
async def get_email_template(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> dict:
    report = await _get_report_or_404(db, report_id)
    if not report.email_template_html:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="尚未上传自定义邮件模板"
        )
    return {
        "html": report.email_template_html,
        "name": report.email_template_name,
        "updated_at": to_api_utc(report.email_template_updated_at),
    }


@router.post("/{report_id}/email-template")
async def upload_email_template(
    report_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> dict:
    report = await _get_report_or_404(db, report_id)

    raw_name = file.filename or ""
    if Path(raw_name).suffix.lower() not in {".html", ".htm"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="邮件模板必须是 .html 或 .htm 文件",
        )
    try:
        name = sanitize_filename(raw_name)
    except UploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    limit = settings.mail.max_template_kb * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"邮件模板不能超过 {settings.mail.max_template_kb} KB",
        )
    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邮件模板不能为空"
        )
    try:
        html = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="邮件模板必须是 UTF-8 编码的 HTML 文件",
        ) from exc
    if "\x00" in html:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邮件模板包含非法字符"
        )

    now = datetime.now(UTC)
    report.email_template_html = html
    report.email_template_name = name
    report.email_template_updated_at = now
    await db.commit()
    await db.refresh(report)
    await write_audit(
        db,
        admin,
        "report_template_upload",
        report.id,
        f"{name} ({len(content)} bytes)",
        request,
    )
    return {
        "ok": True,
        "has_email_template": True,
        "name": name,
        "size": len(content),
        "updated_at": now,
    }


@router.delete("/{report_id}/email-template")
async def delete_email_template(
    report_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> dict:
    report = await _get_report_or_404(db, report_id)
    report.email_template_html = None
    report.email_template_name = None
    report.email_template_updated_at = None
    await db.commit()
    await write_audit(db, admin, "report_template_delete", report.id, None, request)
    return {"ok": True, "has_email_template": False}


@router.post("/{report_id}/email-template/import-global")
async def import_global_email_template(
    report_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> dict:
    report = await _get_report_or_404(db, report_id)
    if report.email_template_html:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该报告已有自定义模板，请先删除后再导入",
        )

    try:
        html = load_global_template_html()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="全局模板读取失败",
        ) from exc

    now = datetime.now(UTC)
    report.email_template_html = html
    report.email_template_name = HTML_TEMPLATE_NAME
    report.email_template_updated_at = now
    await db.commit()
    await db.refresh(report)
    size = len(html.encode("utf-8"))
    await write_audit(
        db,
        admin,
        "report_template_import_global",
        report.id,
        f"{HTML_TEMPLATE_NAME} ({size} bytes)",
        request,
    )
    return {
        "ok": True,
        "has_email_template": True,
        "name": HTML_TEMPLATE_NAME,
        "size": size,
        "updated_at": now,
    }


@router.get("/{report_id}/attachments")
async def list_report_attachments(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> dict:
    await _get_report_or_404(db, report_id)
    items = list_uploaded_attachments(report_id)
    return {"items": items, "total": len(items), "uses_legacy": len(items) == 0}


@router.post("/{report_id}/attachments")
async def upload_report_attachments(
    report_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> dict:
    report = await _get_report_or_404(db, report_id)
    try:
        saved = await save_uploaded_attachments(report_id, files)
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)
        ) from exc
    except UploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    items = list_uploaded_attachments(report_id)
    await write_audit(
        db,
        admin,
        "report_attachment_upload",
        report.id,
        ";".join(saved),
        request,
    )
    return {"ok": True, "uploaded": saved, "items": items, "total": len(items)}


@router.delete("/{report_id}/attachments/{filename}")
async def delete_report_attachment(
    report_id: str,
    filename: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> dict:
    report = await _get_report_or_404(db, report_id)
    try:
        deleted = delete_uploaded_attachment(report_id, filename)
    except UploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在"
        )
    items = list_uploaded_attachments(report_id)
    await write_audit(
        db, admin, "report_attachment_delete", report.id, filename, request
    )
    return {"ok": True, "remaining": len(items)}


@router.post("/{report_id}/attachments/import-global")
async def import_global_report_attachments(
    report_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> dict:
    report = await _get_report_or_404(db, report_id)
    if has_uploaded_attachments(report_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该报告已有上传附件，请先删除后再导入",
        )

    files = collect_legacy_attachments(report_id)
    if not files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有可导入的全局附件",
        )

    try:
        imported = save_attachment_payloads(report_id, files)
    except UploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if not imported:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有可导入的全局附件",
        )

    items = list_uploaded_attachments(report_id)
    await write_audit(
        db,
        admin,
        "report_attachment_import_global",
        report.id,
        ";".join(imported),
        request,
    )
    return {"ok": True, "imported": imported, "items": items, "total": len(items)}


@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    payload: ReportDeleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> dict:
    """删除报告；有提交记录时禁止删除，密码作为二次确认。"""

    report = await _get_report_or_404(db, report_id)
    if not verify_password(payload.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="管理员密码错误"
        )

    count = await db.scalar(
        select(func.count())
        .select_from(Submission)
        .where(Submission.report_id == report_id)
    )
    if count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"该报告已有 {count} 条提交记录，无法删除；请先停用或清理提交记录",
        )

    title = report.title
    await db.delete(report)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该报告已有提交记录，无法删除",
        ) from exc

    deleted_attachments = remove_report_upload_dir(report_id)
    await write_audit(
        db,
        admin,
        "report_delete",
        report_id,
        f"{title}; attachments={deleted_attachments}",
        request,
    )
    return {"ok": True, "deleted_attachments": deleted_attachments}
