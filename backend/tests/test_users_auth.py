U = "/api/v1/users"


def test_wrong_password_then_rate_limited(client, member):
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"email": "khoa@zene.test", "password": "nope"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "khoa@zene.test", "password": "nope"}).status_code == 429


def test_me_and_logout(client, member):
    assert client.get("/api/v1/auth/me", headers=member).json()["data"]["code"] == "KHOA"
    client.post("/api/v1/auth/logout", headers=member)
    assert client.get("/api/v1/auth/me", headers=member).status_code == 401


def test_admin_manages_users(client, admin, member):
    body = {"email": "Mai@zene.test", "name": "Mai", "code": "mai-01", "role": "member", "password": "12345678"}
    res = client.post(U, json=body, headers=admin).json()["data"]
    assert res["email"] == "mai@zene.test" and res["code"] == "MAI01"
    assert client.post(U, json=body, headers=admin).status_code == 409
    assert client.post(U, json={**body, "email": "x@zene.test", "code": "X1"}, headers=member).status_code == 403
    assert client.patch(f"{U}/{res['id']}", json={"is_active": False}, headers=admin).json()["data"]["is_active"] is False
    assert client.post("/api/v1/auth/login", json={"email": "mai@zene.test", "password": "12345678"}).status_code == 401


def test_admin_cannot_demote_self(client, admin):
    me = client.get("/api/v1/auth/me", headers=admin).json()["data"]
    assert client.patch(f"{U}/{me['id']}", json={"role": "member"}, headers=admin).status_code == 422
