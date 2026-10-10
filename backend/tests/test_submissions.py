VALID_PAYLOAD = {
    "organization": "清华大学能源互联网创新研究院",
    "position": "研究员",
    "name": "张三",
    "phone": "13800138000",
    "email": "zhangsan@example.com",
}


async def test_wechat_authorize_url_not_configured(client):
    response = await client.get("/api/client/wechat/authorize-url")
    assert response.status_code == 503


async def test_create_submission_and_list(client, admin_client):
    created = await client.post("/api/client/submissions", json=VALID_PAYLOAD)
    assert created.status_code == 201
    assert created.json()["status"] == "pending"

    listed = await client.get("/api/admin/submissions")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "张三"


async def test_submission_validation(client):
    bad_phone = await client.post(
        "/api/client/submissions", json={**VALID_PAYLOAD, "phone": "12345"}
    )
    assert bad_phone.status_code == 422

    long_name = await client.post(
        "/api/client/submissions", json={**VALID_PAYLOAD, "name": "张" * 33}
    )
    assert long_name.status_code == 422

    bad_email = await client.post(
        "/api/client/submissions", json={**VALID_PAYLOAD, "email": "not-an-email"}
    )
    assert bad_email.status_code == 422


async def test_duplicate_submission_blocked(client):
    first = await client.post("/api/client/submissions", json=VALID_PAYLOAD)
    assert first.status_code == 201
    second = await client.post("/api/client/submissions", json=VALID_PAYLOAD)
    assert second.status_code == 409


async def test_filter_and_sort(client, admin_client):
    await client.post("/api/client/submissions", json=VALID_PAYLOAD)
    await client.post(
        "/api/client/submissions",
        json={**VALID_PAYLOAD, "name": "李四", "phone": "13900139000", "email": "lisi@example.com"},
    )

    filtered = await client.get("/api/admin/submissions", params={"name": "李"})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["name"] == "李四"

    sorted_desc = await client.get(
        "/api/admin/submissions", params={"sort_by": "name", "sort_order": "desc"}
    )
    names = [item["name"] for item in sorted_desc.json()["items"]]
    assert names == sorted(names, reverse=True)


async def test_copy_emails(client, admin_client):
    await client.post("/api/client/submissions", json=VALID_PAYLOAD)
    listed = await client.get("/api/admin/submissions")
    ids = [item["id"] for item in listed.json()["items"]]

    response = await client.post("/api/admin/submissions/copy-emails", json={"ids": ids})
    assert response.status_code == 200
    assert response.json()["emails"] == "zhangsan@example.com"
