"""测试环境：独立临时 SQLite + 测试配置。"""

import os
import tempfile
from pathlib import Path

TEST_DIR = tempfile.mkdtemp(prefix="reportc-test-")
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{Path(TEST_DIR, 'test.db').as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key-0123456789abcdef0123456789abcdef"
os.environ["ADMIN_INITIAL_USERNAME"] = "admin"
os.environ["ADMIN_INITIAL_PASSWORD"] = "TestPassw0rd!23"
os.environ["FEISHU_APP_ID"] = ""
os.environ["FEISHU_APP_SECRET"] = ""
os.environ["FEISHU_CHAT_ID"] = ""
os.environ["SMTP_USER"] = ""
os.environ["SMTP_PASSWORD"] = ""
os.environ["WECHAT_APP_ID"] = ""
os.environ["WECHAT_APP_SECRET"] = ""

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.bootstrap import ensure_initial_admin  # noqa: E402


@pytest.fixture(autouse=True)
async def prepare_db():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await ensure_initial_admin(session)
    yield


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
async def admin_client(client: AsyncClient):
    response = await client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": "TestPassw0rd!23"},
    )
    assert response.status_code == 200
    return client

