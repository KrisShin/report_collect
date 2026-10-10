from app.services.wechat import is_wechat_browser

BASE_PAYLOAD = {
    "organization": "清华大学能源互联网创新研究院",
    "position": "研究员",
    "name": "张三",
    "phone": "13800138000",
    "email": "zhangsan@example.com",
}


async def create_report(admin_client, title: str = "测试报告") -> int:
    response = await admin_client.post("/api/admin/reports", json={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


def test_is_wechat_browser():
    wechat_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) MicroMessenger/8.0.49"
    chrome_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0 Safari/537.36"
    assert is_wechat_browser(wechat_ua) is True
    assert is_wechat_browser(chrome_ua) is False
    assert is_wechat_browser(None) is False


async def test_create_submission_and_list(client, admin_client):
    report_id = await create_report(admin_client, "年度报告收集")
    created = await client.post(
        "/api/client/submissions", json={**BASE_PAYLOAD, "report_id": report_id}
    )
    assert created.status_code == 201
    assert created.json()["status"] == "pending"

    listed = await client.get("/api/admin/submissions")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "张三"
    assert body["items"][0]["report_id"] == report_id
    assert body["items"][0]["report_title"] == "年度报告收集"


async def test_submission_requires_active_report(client, admin_client):
    # 非法 id 格式 → 422
    invalid = await client.post("/api/client/submissions", json={**BASE_PAYLOAD, "report_id": 9999})
    assert invalid.status_code == 422

    # 合法格式但不存在 → 404
    missing = await client.post(
        "/api/client/submissions", json={**BASE_PAYLOAD, "report_id": "0" * 32}
    )
    assert missing.status_code == 404

    report_id = await create_report(admin_client)
    await admin_client.patch(f"/api/admin/reports/{report_id}", json={"is_active": False})
    closed = await client.post(
        "/api/client/submissions", json={**BASE_PAYLOAD, "report_id": report_id}
    )
    assert closed.status_code == 404


async def test_submission_validation(client, admin_client):
    report_id = await create_report(admin_client)

    bad_phone = await client.post(
        "/api/client/submissions",
        json={**BASE_PAYLOAD, "report_id": report_id, "phone": "12345"},
    )
    assert bad_phone.status_code == 422

    long_name = await client.post(
        "/api/client/submissions",
        json={**BASE_PAYLOAD, "report_id": report_id, "name": "张" * 33},
    )
    assert long_name.status_code == 422

    bad_email = await client.post(
        "/api/client/submissions",
        json={**BASE_PAYLOAD, "report_id": report_id, "email": "not-an-email"},
    )
    assert bad_email.status_code == 422


async def test_duplicate_submission_blocked(client, admin_client):
    report_id = await create_report(admin_client)
    payload = {**BASE_PAYLOAD, "report_id": report_id}
    assert (await client.post("/api/client/submissions", json=payload)).status_code == 201
    assert (await client.post("/api/client/submissions", json=payload)).status_code == 409


async def test_filter_by_report(client, admin_client):
    report_a = await create_report(admin_client, "报告 A")
    report_b = await create_report(admin_client, "报告 B")

    await client.post("/api/client/submissions", json={**BASE_PAYLOAD, "report_id": report_a})
    await client.post(
        "/api/client/submissions",
        json={
            **BASE_PAYLOAD,
            "report_id": report_b,
            "name": "李四",
            "phone": "13900139000",
            "email": "lisi@example.com",
        },
    )

    only_a = await client.get("/api/admin/submissions", params={"report_id": report_a})
    assert only_a.status_code == 200
    assert only_a.json()["total"] == 1
    assert only_a.json()["items"][0]["report_title"] == "报告 A"

    all_rows = await client.get(
        "/api/admin/submissions", params={"sort_by": "name", "sort_order": "asc"}
    )
    assert [item["name"] for item in all_rows.json()["items"]] == ["张三", "李四"]


async def test_copy_emails(client, admin_client):
    report_id = await create_report(admin_client)
    await client.post("/api/client/submissions", json={**BASE_PAYLOAD, "report_id": report_id})
    listed = await client.get("/api/admin/submissions")
    ids = [item["id"] for item in listed.json()["items"]]

    response = await client.post("/api/admin/submissions/copy-emails", json={"ids": ids})
    assert response.status_code == 200
    assert response.json()["emails"] == "zhangsan@example.com"

async def test_processed_and_ai_filters(client, admin_client):
    from app.db.session import AsyncSessionLocal
    from app.models.submission import Submission

    report_id = await create_report(admin_client)
    await client.post("/api/client/submissions", json={**BASE_PAYLOAD, "report_id": report_id})

    listed = await client.get("/api/admin/submissions")
    submission_id = listed.json()["items"][0]["id"]

    assert (await client.get("/api/admin/submissions", params={"processed": "true"})).json()[
        "total"
    ] == 0
    assert (await client.get("/api/admin/submissions", params={"processed": "false"})).json()[
        "total"
    ] == 1

    async with AsyncSessionLocal() as session:
        row = await session.get(Submission, submission_id)
        row.is_processed = True
        row.ai_flag = "suspicious"
        row.ai_reason = "占位数据"
        await session.commit()

    assert (await client.get("/api/admin/submissions", params={"processed": "true"})).json()[
        "total"
    ] == 1
    suspicious = await client.get("/api/admin/submissions", params={"ai_flag": "suspicious"})
    assert suspicious.json()["total"] == 1
    assert suspicious.json()["items"][0]["ai_reason"] == "占位数据"

async def test_email_must_be_ascii(client, admin_client):
    report_id = await create_report(admin_client)

    chinese_domain = await client.post(
        "/api/client/submissions",
        json={**BASE_PAYLOAD, "report_id": report_id, "email": "12321@234.爱出色的"},
    )
    assert chinese_domain.status_code == 422

    no_tld = await client.post(
        "/api/client/submissions",
        json={**BASE_PAYLOAD, "report_id": report_id, "email": "user@localhost"},
    )
    assert no_tld.status_code == 422

    normal = await client.post(
        "/api/client/submissions",
        json={**BASE_PAYLOAD, "report_id": report_id, "phone": "13712340001"},
    )
    assert normal.status_code == 201

async def test_send_mail_is_queued(client, admin_client):
    report_id = await create_report(admin_client)
    await client.post("/api/client/submissions", json={**BASE_PAYLOAD, "report_id": report_id})
    listed = await client.get("/api/admin/submissions")
    ids = [item["id"] for item in listed.json()["items"]]

    response = await client.post("/api/admin/submissions/send-mail", json={"ids": ids})
    assert response.status_code == 200
    body = response.json()
    assert body["queued"] is True
    assert body["count"] == 1
    assert body["log_id"] > 0

async def test_unique_email_and_ip_per_report(client, admin_client, monkeypatch):
    from app.core.config import settings

    report_id = await create_report(admin_client)
    first = await client.post(
        "/api/client/submissions", json={**BASE_PAYLOAD, "report_id": report_id}
    )
    assert first.status_code == 201

    # 同邮箱、不同手机号 → 拒绝
    same_email = await client.post(
        "/api/client/submissions",
        json={
            **BASE_PAYLOAD,
            "report_id": report_id,
            "phone": "13700137000",
        },
    )
    assert same_email.status_code == 409
    assert "邮箱" in same_email.json()["detail"]

    # 不同手机号、不同邮箱，但同一 IP → 拒绝
    same_ip = await client.post(
        "/api/client/submissions",
        json={
            **BASE_PAYLOAD,
            "report_id": report_id,
            "phone": "13700137001",
            "email": "another@example.com",
        },
    )
    assert same_ip.status_code == 409
    assert "网络" in same_ip.json()["detail"]

    # 关闭 IP 限制后可以提交
    monkeypatch.setattr(settings.security, "unique_ip_per_report", False)
    allowed = await client.post(
        "/api/client/submissions",
        json={
            **BASE_PAYLOAD,
            "report_id": report_id,
            "phone": "13700137002",
            "email": "third@example.com",
        },
    )
    assert allowed.status_code == 201
