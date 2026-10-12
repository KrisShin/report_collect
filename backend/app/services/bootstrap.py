"""首次启动初始化：创建固定初始管理员账号。"""

import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.admin_user import AdminUser

logger = logging.getLogger(__name__)


async def ensure_initial_admin(session: AsyncSession) -> None:
    count = await session.scalar(select(func.count()).select_from(AdminUser))
    if count:
        return

    if not settings.admin.initial_password:
        logger.warning("未配置 ADMIN_INITIAL_PASSWORD，跳过创建初始管理员")
        return

    admin = AdminUser(
        username=settings.admin.initial_username,
        password_hash=hash_password(settings.admin.initial_password),
        display_name="系统管理员",
        must_change_password=True,
    )
    session.add(admin)
    try:
        await session.commit()
    except IntegrityError:
        # 多 worker 同时启动时的并发创建，忽略即可
        await session.rollback()
        return
    logger.info("已创建初始管理员账号 username=%s", settings.admin.initial_username)
