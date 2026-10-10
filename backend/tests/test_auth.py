async def test_login_and_me(client):
    response = await client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": "TestPassw0rd!23"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "admin"

    me = await client.get("/api/admin/auth/me")
    assert me.status_code == 200
    assert me.json()["must_change_password"] is True


async def test_login_wrong_password(client):
    response = await client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert response.status_code == 401


async def test_me_requires_login(client):
    response = await client.get("/api/admin/auth/me")
    assert response.status_code == 401


async def test_change_password(client):
    await client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": "TestPassw0rd!23"},
    )
    response = await client.post(
        "/api/admin/auth/change-password",
        json={"old_password": "TestPassw0rd!23", "new_password": "NewPassw0rd!456"},
    )
    assert response.status_code == 200
    assert response.json()["must_change_password"] is False
