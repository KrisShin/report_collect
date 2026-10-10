"""客户端接口：报告详情、表单提交（方案 A：仅 UA 校验）。

客户端不提供报告列表接口，只能凭管理员提供的 /m/{report_id} 链接进入指定报告。
"""

import contextlib
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_wechat_browser
from app.core import redis as redis_module
from app.core.config import settings
from app.core.diagnostics import log_client_event
from app.db.session import get_db
from app.models.report import Report
from app.models.submission import Submission
from app.schemas.report import ReportPublic
from app.schemas.submission import SubmissionCreate, SubmissionCreated
from app.services.jobs import enqueue
from app.services.rate_limit import hit
from app.services.report_window import window_message, window_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/client", tags=["client"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class ClientDiagnostic(BaseModel):
    """前端上报的诊断信息（微信内看不到返回值时使用）。"""

    event: str = "client"
    url: str | None = None
    ua: str | None = None
    status: int | None = None
    message: str | None = None
    detail: Any | None = None
    payload: Any | None = None


@router.post("/diagnostic")
async def client_diagnostic(body: ClientDiagnostic, request: Request) -> dict:
    ip = _client_ip(request)
    allowed, _ = await hit(
        f"diag:{ip}", settings.security.diagnostics_per_minute, 60
    )
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="上报过于频繁")

    log_client_event(
        "client_report",
        {
            "ip": ip,
            "referer": request.headers.get("referer"),
            **body.model_dump(),
        },
    )
    return {"ok": True}


@router.get("/reports/{report_id}", response_model=ReportPublic)
async def get_active_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_wechat_browser),
) -> ReportPublic:
    report = await db.get(Report, report_id)
    if not report or not report.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在或已关闭")

    payload = ReportPublic.model_validate(report)
    payload.state = window_state(report)
    return payload


async def _find_conflict(
    db: AsyncSession, report_id: str, phone: str, email: str, ip: str
) -> str | None:
    """同一报告内，手机号 / 邮箱 / IP 任一命中已有提交即视为重复。"""

    if settings.security.unique_phone_per_report:
        exists = await db.scalar(
            select(Submission.id)
            .where(Submission.report_id == report_id)
            .where(Submission.phone == phone)
            .limit(1)
        )
        if exists:
            return "该手机号已提交过本报告，请勿重复提交"

    if settings.security.unique_email_per_report:
        exists = await db.scalar(
            select(Submission.id)
            .where(Submission.report_id == report_id)
            .where(Submission.email == email)
            .limit(1)
        )
        if exists:
            return "该邮箱已提交过本报告，请勿重复提交"

    if settings.security.unique_ip_per_report and ip and ip != "unknown":
        exists = await db.scalar(
            select(Submission.id)
            .where(Submission.report_id == report_id)
            .where(Submission.client_ip == ip)
            .limit(1)
        )
        if exists:
            return "当前网络已提交过本报告，请勿重复提交"

    return None


@router.post("/submissions", response_model=SubmissionCreated, status_code=status.HTTP_201_CREATED)
async def create_submission(
    payload: SubmissionCreate,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_wechat_browser),
) -> SubmissionCreated:
    ip = _client_ip(request)

    allowed, _remaining = await hit(
        f"submit:ip:{ip}", settings.security.submit_ip_per_minute, 60
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="提交过于频繁，请稍后再试",
        )

    allowed, _remaining = await hit(
        f"submit:phone:{payload.report_id}:{payload.phone}",
        settings.security.submit_phone_per_hour,
        3600,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="同一手机号提交过于频繁，请稍后再试",
        )

    report = await db.get(Report, payload.report_id)
    if not report or not report.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在或已关闭")
    if window_state(report) != "open":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=window_message(report))

    # 分布式锁：同一报告 + 手机号并发提交时只放行一个（Redis 不可用时退化为数据库唯一约束）
    redis_client = redis_module.get_redis()
    lock_key = redis_module.key(f"submit:lock:{report.id}:{payload.phone}")
    locked = False
    if redis_client is not None:
        try:
            locked = bool(await redis_client.set(lock_key, "1", nx=True, ex=10))
        except Exception as exc:  # noqa: BLE001
            logger.warning("获取提交锁失败，忽略锁：%s", exc)
            locked = False
        if not locked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="请勿重复提交"
            )

    try:
        conflict = await _find_conflict(
            db, report.id, payload.phone, str(payload.email), ip
        )
        if conflict:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=conflict)

        submission = Submission(
            report_id=report.id,
            organization=payload.organization,
            position=payload.position,
            name=payload.name,
            phone=payload.phone,
            phone_source="manual",
            email=str(payload.email),
            status="pending",
            is_processed=False,
            client_ip=ip,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(submission)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该手机号或邮箱已提交过本报告，请勿重复提交",
            ) from exc
        await db.refresh(submission)
    finally:
        if locked and redis_client is not None:
            with contextlib.suppress(Exception):
                await redis_client.delete(lock_key)

    log_client_event(
        "submission_created",
        {
            "submission_id": submission.id,
            "report_id": report.id,
            "name": submission.name,
            "phone": submission.phone,
            "email": submission.email,
            "ua": request.headers.get("user-agent"),
            "referer": request.headers.get("referer"),
            "ip": ip,
        },
    )

    # AI 判定 + 飞书提醒：Redis 可用时由独立 worker 消费，否则进程内后台任务
    await enqueue(background, "submission_process", submission_id=submission.id)

    return SubmissionCreated(id=submission.id, status="pending")
