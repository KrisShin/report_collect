"""健康检查。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "time": datetime.now(ZoneInfo(settings.timezone)).isoformat(),
    }
