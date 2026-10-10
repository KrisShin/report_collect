"""客户端接口：微信授权、表单提交。"""

import json
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_wechat_browser
from app.core.config import settings
from app.db.session import get_db
from app.models.submission import Submission
from app.schemas.submission import SubmissionCreate, SubmissionCreated
from app.services.feishu import feishu_client
from app.services.wechat import WeChatError, build_authorize_url, exchange_code_for_openid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/client", tags=["client"])
WECHAT_OPENID_COOKIE = "rc_wx_openid"
DUPLICATE_WINDOW_SECONDS = 5


@router.get("/wechat/authorize-url")
async def wechat_authorize_url() -> dict:
    try:
        return {"url": build_authorize_url(state="submit")}
    except WeChatError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


@router.get("/wechat/callback")
async def wechat_callback(code: str, response: Response, state: str = "submit") -> RedirectResponse:
    try:
        data = await exchange_code_for_openid(code)
    except WeChatError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    redirect = RedirectResponse(
        url=f"{settings.public_base_url.rstrip('/')}{settings.client_path}?wx=1"
    )
    redirect.set_cookie(
        key=WECHAT_OPENID_COOKIE,
        value=data["openid"],
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
        max_age=7 * 24 * 3600,
        path="/",
    )
    return redirect


@router.post("/submissions", response_model=SubmissionCreated, status_code=status.HTTP_201_CREATED)
async def create_submission(
    payload: SubmissionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_wechat_browser),
) -> SubmissionCreated:
    openid = request.cookies.get(WECHAT_OPENID_COOKIE)

    # 5 秒内同一 openid / 同一手机号重复提交视为重复请求
    window_start = datetime.now(UTC) - timedelta(seconds=DUPLICATE_WINDOW_SECONDS)
    duplicate_stmt = select(Submission.id).where(Submission.submitted_at >= window_start)
    if openid:
        duplicate_stmt = duplicate_stmt.where(
            or_(Submission.wx_openid == openid, Submission.phone == payload.phone)
        )
    else:
        duplicate_stmt = duplicate_stmt.where(Submission.phone == payload.phone)
    if await db.scalar(duplicate_stmt.limit(1)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请勿重复提交")

    submission = Submission(
        organization=payload.organization,
        position=payload.position,
        name=payload.name,
        phone=payload.phone,
        phone_source="manual",
        email=str(payload.email),
        wx_openid=openid,
        status="pending",
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    await _notify_feishu(db, submission)

    return SubmissionCreated(id=submission.id, status="pending")


async def _notify_feishu(db: AsyncSession, submission: Submission) -> None:
    text = "\n".join(
        [
            "【新的报告提交】需要审核",
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


