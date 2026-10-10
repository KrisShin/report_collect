"""管理端关键操作审计。"""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_user import AdminUser
from app.models.audit_log import AuditLog


async def write_audit(
    db: AsyncSession,
    admin: AdminUser,
    action: str,
    target: str | None = None,
    detail: str | None = None,
    request: Request | None = None,
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
