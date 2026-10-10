async def test_report_crud_and_public_visibility(client, admin_client):
    created = await admin_client.post(
        "/api/admin/reports",
        json={"title": "2026 年度报告", "description": "填写说明"},
    )
    assert created.status_code == 201
    report_id = created.json()["id"]
    assert created.json()["is_active"] is True
    assert len(report_id) == 32 and all(c in "0123456789abcdef" for c in report_id)

    admin_list = await admin_client.get("/api/admin/reports")
    assert admin_list.status_code == 200
    row = next(item for item in admin_list.json() if item["id"] == report_id)
    assert row["submission_count"] == 0

    detail = await client.get(f"/api/client/reports/{report_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "2026 年度报告"

    updated = await admin_client.patch(
        f"/api/admin/reports/{report_id}", json={"title": "变更后的标题"}
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "变更后的标题"

    closed = await admin_client.patch(
        f"/api/admin/reports/{report_id}", json={"is_active": False}
    )
    assert closed.status_code == 200
    assert closed.json()["is_active"] is False

    assert (await client.get(f"/api/client/reports/{report_id}")).status_code == 404


async def test_report_list_is_not_exposed_to_client(client):
    # 客户端不允许枚举/选择报告，只能凭链接进入
    response = await client.get("/api/client/reports")
    assert response.status_code == 404


async def test_report_title_cannot_be_blank(admin_client):
    response = await admin_client.post("/api/admin/reports", json={"title": "   "})
    assert response.status_code == 422


async def test_report_requires_admin(client):
    assert (await client.get("/api/admin/reports")).status_code == 401
    assert (await client.post("/api/admin/reports", json={"title": "x"})).status_code == 401

async def test_report_time_window(client, admin_client):
    not_started = await admin_client.post(
        "/api/admin/reports",
        json={
            "title": "未来报告",
            "start_at": "2099-01-01T00:00:00+08:00",
            "end_at": "2099-01-02T00:00:00+08:00",
        },
    )
    assert not_started.status_code == 201
    rid = not_started.json()["id"]

    detail = await client.get(f"/api/client/reports/{rid}")
    assert detail.status_code == 200
    assert detail.json()["state"] == "not_started"

    submit = await client.post(
        "/api/client/submissions",
        json={
            "report_id": rid,
            "organization": "测试单位",
            "position": "研究员",
            "name": "张三",
            "phone": "13800138000",
            "email": "a@example.com",
        },
    )
    assert submit.status_code == 403

    ended = await admin_client.post(
        "/api/admin/reports",
        json={
            "title": "已结束报告",
            "start_at": "2020-01-01T00:00:00+08:00",
            "end_at": "2020-01-02T00:00:00+08:00",
        },
    )
    ended_id = ended.json()["id"]
    ended_detail = await client.get(f"/api/client/reports/{ended_id}")
    assert ended_detail.status_code == 200
    assert ended_detail.json()["state"] == "ended"

    opened = await admin_client.post(
        "/api/admin/reports",
        json={
            "title": "进行中报告",
            "start_at": "2020-01-01T00:00:00+08:00",
            "end_at": "2099-01-01T00:00:00+08:00",
        },
    )
    opened_id = opened.json()["id"]
    opened_detail = await client.get(f"/api/client/reports/{opened_id}")
    assert opened_detail.status_code == 200
    assert opened_detail.json()["state"] == "open"


async def test_report_window_must_be_ordered(admin_client):
    response = await admin_client.post(
        "/api/admin/reports",
        json={
            "title": "时间错误",
            "start_at": "2099-01-02T00:00:00+08:00",
            "end_at": "2099-01-01T00:00:00+08:00",
        },
    )
    assert response.status_code == 422
