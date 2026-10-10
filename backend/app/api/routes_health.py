"""健康检查。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from app.core.config import settings
from app.core.redis import ping as redis_ping

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app.name,
        "env": settings.app.env,
        "time": datetime.now(ZoneInfo(settings.app.timezone)).isoformat(),
        "redis": await redis_ping() if settings.redis.enabled else False,
    }
