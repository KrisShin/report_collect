"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  确保模型注册到 Base.metadata
from app.api import routes_admin, routes_auth, routes_client, routes_health
from app.core.config import BACKEND_DIR, settings
from app.core.logging import setup_logging
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.services.bootstrap import ensure_initial_admin


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging(settings.debug)
    (BACKEND_DIR / "data").mkdir(parents=True, exist_ok=True)

    # 开发/测试环境自动建表；生产环境请使用 alembic upgrade head
    if settings.app_env != "production":
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await ensure_initial_admin(session)

    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router)
app.include_router(routes_auth.router)
app.include_router(routes_client.router)
app.include_router(routes_admin.router)
