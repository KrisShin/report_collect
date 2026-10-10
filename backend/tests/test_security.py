import fakeredis.aioredis

from app.core import redis as redis_module
from app.core.config import settings
from app.services import rate_limit

VALID_PAYLOAD = {
    "organization": "清华大学能源互联网创新研究院",
    "position": "研究员",
    "name": "张三",
    "phone": "13800138000",
    "email": "zhangsan@example.com",
}


async def create_report(admin_client, title: str = "安全测试报告") -> str:
    response = await admin_client.post("/api/admin/reports", json={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


async def test_security_headers(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "referrer-policy" in response.headers


async def test_origin_check_blocks_cross_site_write(client):
    response = await client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": "x"},
        headers={"Origin": "http://evil.example.com"},
    )
    assert response.status_code == 403
    assert "来源" in response.json()["detail"]


async def test_origin_check_allows_configured_origin(client):
    response = await client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": "wrong-password"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 401


async def test_login_lockout_after_failures(client, monkeypatch):
    monkeypatch.setattr(settings.security, "login_max_failures", 2)
    monkeypatch.setattr(settings.security, "login_lock_seconds", 300)

    first = await client.post(
        "/api/admin/auth/login", json={"username": "admin", "password": "bad-1"}
    )
    assert first.status_code == 401

    second = await client.post(
        "/api/admin/auth/login", json={"username": "admin", "password": "bad-2"}
    )
    assert second.status_code == 429

    # 锁定后即使密码正确也不放行
    locked = await client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": "TestPassw0rd!23"},
    )
    assert locked.status_code == 429


async def test_login_success_resets_failure_counter(client, monkeypatch):
    monkeypatch.setattr(settings.security, "login_max_failures", 3)

    assert (
        await client.post(
            "/api/admin/auth/login", json={"username": "admin", "password": "bad"}
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/admin/auth/login",
            json={"username": "admin", "password": "TestPassw0rd!23"},
        )
    ).status_code == 200
    # 失败计数已清零，仍然可以继续尝试
    assert (
        await client.post(
            "/api/admin/auth/login", json={"username": "admin", "password": "bad"}
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/admin/auth/login", json={"username": "admin", "password": "bad"}
        )
    ).status_code == 401


async def test_logout_revokes_token(client):
    await client.post(
        "/api/admin/auth/login", json={"username": "admin", "password": "TestPassw0rd!23"}
    )
    assert (await client.get("/api/admin/auth/me")).status_code == 200

    assert (await client.post("/api/admin/auth/logout")).status_code == 200
    # client fixture 仍持有旧 token（httpx 不会自动清除 cookie），但已被注销
    assert (await client.get("/api/admin/auth/me")).status_code == 401


async def test_submit_rate_limit_by_ip(client, admin_client, monkeypatch):
    monkeypatch.setattr(settings.security, "submit_ip_per_minute", 1)
    report_id = await create_report(admin_client)

    first = await client.post(
        "/api/client/submissions", json={**VALID_PAYLOAD, "report_id": report_id}
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/client/submissions",
        json={
            **VALID_PAYLOAD,
            "report_id": report_id,
            "phone": "13900139001",
            "email": "second@example.com",
        },
    )
    assert second.status_code == 429


async def test_rate_limit_uses_redis_when_enabled(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "_client", fake)
    monkeypatch.setattr(settings.redis, "enabled", True)

    allowed, remaining = await rate_limit.hit("test:key", limit=2, window_seconds=60)
    assert allowed is True
    assert remaining == 1

    allowed, remaining = await rate_limit.hit("test:key", limit=2, window_seconds=60)
    assert allowed is True
    assert remaining == 0

    allowed, remaining = await rate_limit.hit("test:key", limit=2, window_seconds=60)
    assert allowed is False

    stored = await fake.get(redis_module.key("rl:test:key"))
    assert stored == "3"
