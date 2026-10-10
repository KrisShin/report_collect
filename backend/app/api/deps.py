"""API 依赖：认证与微信浏览器校验。"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.admin_user import AdminUser


async def get_current_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    token = request.cookies.get(settings.cookie_name)
    if not token:
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录已失效，请重新登录",
    )
    if not token:
        raise credentials_error

    try:
        payload = decode_access_token(token)
        admin_id = int(payload["sub"])
    except Exception as exc:  # noqa: BLE001
        raise credentials_error from exc

    admin = await db.get(AdminUser, admin_id)
    if not admin or not admin.is_active:
        raise credentials_error
    return admin


async def require_wechat_browser(request: Request) -> None:
    """仅允许微信内置浏览器访问（开发环境放行，便于本地调试）。"""

    if settings.app_env != "production":
        return
    user_agent = request.headers.get("user-agent", "")
    if "MicroMessenger" not in user_agent:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请在微信中打开本页面",
        )
