"""测试环境：独立临时 SQLite + 独立 config.test.yaml（不读取环境变量）。"""

import tempfile
from pathlib import Path

import yaml

TEST_DIR = Path(tempfile.mkdtemp(prefix="reportc-test-"))

TEST_CONFIG = {
    "app": {
        "name": "报告收集系统",
        "env": "test",
        "debug": False,
        "timezone": "Asia/Shanghai",
        "secret_key": "test-secret-key-0123456789abcdef0123456789abcdef",
        "access_token_expire_minutes": 60,
        "cookie_name": "rc_admin_token",
        "cors_origins": ["http://localhost:5173"],
        "public_base_url": "http://test",
        "client_path": "/m",
        "admin_path": "/admin",
    },
    "database": {"url": f"sqlite+aiosqlite:///{(TEST_DIR / 'test.db').as_posix()}"},
    "wechat": {"require_browser": True},
    "feishu": {
        "base_url": "https://open.feishu.cn/open-apis",
        "app_id": "",
        "app_secret": "",
        "chat_id": "",
    },
    "mail": {
        "host": "smtp.exmail.qq.com",
        "port": 465,
        "use_ssl": True,
        "user": "",
        "password": "",
        "from_name": "测试",
    },
    "admin": {"initial_username": "admin", "initial_password": "TestPassw0rd!23"},
}

TEST_CONFIG_FILE = TEST_DIR / "config.test.yaml"
TEST_CONFIG_FILE.write_text(yaml.safe_dump(TEST_CONFIG, allow_unicode=True), encoding="utf-8")

import app.core.config as config_module  # noqa: E402

# 在导入 app.main 之前替换配置，确保 engine / security 等模块拿到测试配置
config_module.settings = config_module.load_settings(TEST_CONFIG_FILE)

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import login_guard, rate_limit, token_store  # noqa: E402
from app.services.bootstrap import ensure_initial_admin  # noqa: E402


@pytest.fixture(autouse=True)
async def prepare_db():
    rate_limit.reset_memory()
    login_guard.reset_memory()
    token_store.reset_memory()
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
