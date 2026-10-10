"""管理端接口：报告的创建、编辑、启用/停用。"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.models.report import Report
from app.models.submission import Submission
from app.schemas.report import ReportAdminRead, ReportCreate, ReportRead, ReportUpdate
from app.services.audit import write_audit
from app.services.report_window import to_db_utc

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
