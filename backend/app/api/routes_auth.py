"""管理端认证接口。"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.auth import AdminMe, ChangePasswordRequest, LoginRequest

router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth"])


@router.post("/login", response_model=AdminMe)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    admin = await db.scalar(select(AdminUser).where(AdminUser.username == payload.username))
    if (
        not admin
        or not admin.is_active
        or not verify_password(payload.password, admin.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")

    token = create_access_token(subject=str(admin.id))
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )

    admin.last_login_ip = request.client.host if request.client else None
    from datetime import UTC, datetime

    admin.last_login_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(admin)
    return admin


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(settings.cookie_name, path="/")
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

