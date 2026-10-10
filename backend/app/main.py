"""FastAPI 应用入口。"""

import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import app.models  # noqa: F401  确保模型注册到 Base.metadata
from app.api import (
    routes_admin,
    routes_admin_reports,
    routes_auth,
    routes_client,
    routes_health,
)
from app.core.config import BACKEND_DIR, settings
from app.core.diagnostics import log_client_event
from app.core.logging import setup_logging
from app.core.redis import close as close_redis
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.services.bootstrap import ensure_initial_admin


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging(settings.app.debug)
    (BACKEND_DIR / "data").mkdir(parents=True, exist_ok=True)

    # 开发/测试环境自动建表；生产环境请使用 alembic upgrade head
    if settings.app.env != "production":
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await ensure_initial_admin(session)

    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.app.name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """安全响应头 + 管理端状态变更请求的来源校验（CSRF 纵深防御）。"""

    if (
        settings.security.enforce_origin_check
        and request.method not in SAFE_METHODS
        and request.url.path.startswith("/api/admin")
    ):
        origin = request.headers.get("origin") or request.headers.get("referer") or ""
        if origin:
            origin_host = urlparse(origin).netloc
            request_host = request.headers.get("host", "")
            same_origin = bool(origin_host) and origin_host == request_host
            listed = any(
                origin.startswith(allowed.rstrip("/"))
                for allowed in settings.app.cors_origins
            )
            if not same_origin and not listed:
                return JSONResponse(status_code=403, content={"detail": "请求来源校验失败"})

    response = await call_next(request)

    if settings.security.enable_security_headers:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        if settings.app.env == "production":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
    return response


@app.middleware("http")
async def client_request_logger(request: Request, call_next):
    """记录所有 /api/client 请求：真实 UA、来源、返回码。"""

    if not request.url.path.startswith("/api/client"):
        return await call_next(request)

    started = time.perf_counter()
    response = await call_next(request)
    log_client_event(
        "http",
        {
            "method": request.method,
            "path": request.url.path,
            "query": request.url.query,
            "status": response.status_code,
            "ua": request.headers.get("user-agent"),
            "referer": request.headers.get("referer"),
            "ip": request.client.host if request.client else None,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        },
    )
    return response


@app.exception_handler(RequestValidationError)
async def client_validation_handler(request: Request, exc: RequestValidationError):
    """客户端请求体校验失败时，把原始请求体和错误一并写日志（便于排查 422）。"""

    if request.url.path.startswith("/api/client"):
        raw_body = (await request.body()).decode("utf-8", "replace")
        log_client_event(
            "validation_error",
            {
                "path": request.url.path,
                "ua": request.headers.get("user-agent"),
                "content_type": request.headers.get("content-type"),
                "body": raw_body[:2000],
                "errors": exc.errors(),
            },
        )
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


app.include_router(routes_health.router)
app.include_router(routes_auth.router)
app.include_router(routes_client.router)
app.include_router(routes_admin.router)
app.include_router(routes_admin_reports.router)
