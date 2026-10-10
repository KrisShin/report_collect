"""管理端认证接口。"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.auth import AdminMe, ChangePasswordRequest, LoginRequest
from app.services import login_guard
from app.services.token_store import revoke

router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth"])


@router.post("/login", response_model=AdminMe)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    ip = request.client.host if request.client else "unknown"
    identity = f"{ip}:{payload.username}"

    locked_seconds = await login_guard.is_locked(identity)
    if locked_seconds:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录失败次数过多，请 {max(locked_seconds // 60, 1)} 分钟后再试",
        )

    admin = await db.scalar(select(AdminUser).where(AdminUser.username == payload.username))
    if (
        not admin
        or not admin.is_active
        or not verify_password(payload.password, admin.password_hash)
    ):
        remaining_lock = await login_guard.record_failure(identity)
        if remaining_lock:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"登录失败次数过多，请 {max(remaining_lock // 60, 1)} 分钟后再试",
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")

    await login_guard.clear(identity)

    token = create_access_token(subject=str(admin.id))
    response.set_cookie(
        key=settings.app.cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.app.env == "production",
        max_age=settings.app.access_token_expire_minutes * 60,
        path="/",
    )

    admin.last_login_ip = request.client.host if request.client else None
    from datetime import UTC, datetime

    admin.last_login_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(admin)
    return admin


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(settings.app.cookie_name)
    if token:
        try:
            payload = decode_access_token(token)
            exp = int(payload.get("exp") or 0)
            ttl = max(exp - int(datetime.now(UTC).timestamp()), 1)
            await revoke(str(payload.get("jti") or ""), ttl)
        except Exception:  # noqa: BLE001
            pass
    response.delete_cookie(settings.app.cookie_name, path="/")
    return {"ok": True}


@router.get("/me", response_model=AdminMe)
async def me(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    return admin


@router.post("/change-password", response_model=AdminMe)
async def change_password(
    payload: ChangePasswordRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    if not verify_password(payload.old_password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")
    if payload.old_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与原密码相同"
        )

    admin.password_hash = hash_password(payload.new_password)
    admin.must_change_password = False
    await db.commit()
    await db.refresh(admin)
    return admin

