"""View as a seller account: an admin, or a member an admin allowed, sees ReportZenE as that seller does, read-only."""
from tests.conftest import _login, _user
from tests.test_mcp import _token
from tests.test_report import _save_token
from tests.test_user_scope import LINH, MAI, R, _limit, upstream  # noqa: F401  (fixture: trackingis with Linh PT and Mai VTT)

AS = "X-View-As"
RANGE = "date_from=2026-10-01&date_to=2026-10-02"


def _as(headers: dict, user_id: int) -> dict:
    return {**headers, AS: str(user_id)}


def test_an_admin_sees_the_app_as_a_seller_does(client, admin, member, upstream):  # noqa: F811
    _save_token(client, admin)
    seller = _limit(client, admin, member, [LINH])
    as_seller = _as(admin, seller)

    me = client.get("/api/v1/auth/me", headers=as_seller).json()["data"]
    assert me["id"] == seller and me["role"] == "member" and me["scope_sellers"] == [LINH]
    assert me["viewed_by"]["name"] == "Boss" and me["may_view_as"] is True  # the right is the signed-in user's own
    plain = client.get("/api/v1/auth/me", headers=admin).json()["data"]
    assert plain["role"] == "admin" and "viewed_by" not in plain

    client.get(f"{R}?view=store&{RANGE}&sellers={MAI}", headers=as_seller)
    assert upstream[-1]["sellers[]"] == [LINH]  # their sales only, whatever the filter asks
    assert [s["name"] for s in client.get(f"{R}/options/sellers", headers=as_seller).json()["data"]] == ["Linh PT"]
    for path in ("/api/v1/sheets", "/api/v1/plan/products"):  # the whole of ZenE: closed to them, so to the viewer
        assert client.get(path, headers=as_seller).status_code == 403
    assert client.get("/api/v1/settings", headers=as_seller).status_code == 403  # admin-only
    assert client.get("/api/v1/users", headers=as_seller).status_code == 403


def test_a_sign_in_tells_whether_the_user_may_view_as(client, db_factory):
    _user(db_factory, "boss2@zene.test", "Boss2", "BOSS2", "admin")
    _user(db_factory, "plain@zene.test", "Plain", "PLAIN", "member")
    for email, may in (("boss2@zene.test", True), ("plain@zene.test", False)):
        res = client.post("/api/v1/auth/login", json={"email": email, "password": "secret-pass-1"})
        assert res.json()["data"]["user"]["may_view_as"] is may
        client.cookies.clear()


def test_viewing_as_is_read_only(client, admin, member, upstream):  # noqa: F811
    seller = _limit(client, admin, member, [LINH])
    res = client.patch(f"/api/v1/users/{seller}", json={"is_active": False}, headers=_as(admin, seller))
    assert res.status_code == 403 and "Read-only" in res.json()["meta"]["message"]
    assert client.put("/api/v1/settings", json={"default_teams": ["12"]}, headers=_as(admin, seller)).status_code == 403
    assert client.get("/api/v1/auth/me", headers=_as(admin, seller)).json()["data"]["is_active"] is True  # nothing changed


def test_who_may_view_as_whom(client, db_factory, admin, member, upstream):  # noqa: F811
    seller = _limit(client, admin, member, [LINH])
    _user(db_factory, "maivtt@zene.test", "Mai VTT", "MAIVTT", "member")
    mai = _login(client, "maivtt@zene.test")
    mai_id = client.get("/api/v1/auth/me", headers=mai).json()["data"]["id"]

    # a member an admin has not allowed cannot
    assert client.get("/api/v1/auth/me", headers=mai).json()["data"]["may_view_as"] is False
    assert client.get("/api/v1/auth/view-as", headers=mai).status_code == 403
    assert client.get("/api/v1/auth/me", headers=_as(mai, seller)).status_code == 403

    res = client.patch(f"/api/v1/users/{mai_id}", json={"can_view_as": True}, headers=admin)
    assert res.json()["data"]["can_view_as"] is True
    assert [u["id"] for u in client.get("/api/v1/auth/view-as", headers=mai).json()["data"]] == [seller]  # seller accounts only
    me = client.get("/api/v1/auth/me", headers=_as(mai, seller)).json()["data"]
    assert me["id"] == seller and me["viewed_by"]["name"] == "Mai VTT"

    # not as an admin, as a member who sees the whole of ZenE, as a locked or unknown account, or with a bad id
    admin_id = client.get("/api/v1/auth/me", headers=admin).json()["data"]["id"]
    assert client.get("/api/v1/auth/me", headers=_as(mai, admin_id)).status_code == 403
    assert client.get("/api/v1/auth/me", headers=_as(admin, mai_id)).status_code == 403  # Mai sees all: nothing to view as
    assert client.get("/api/v1/auth/me", headers=_as(admin, 9999)).status_code == 404
    assert client.get("/api/v1/auth/me", headers={**admin, AS: "linh"}).status_code == 422
    client.patch(f"/api/v1/users/{seller}", json={"is_active": False}, headers=admin)
    assert client.get("/api/v1/auth/me", headers=_as(admin, seller)).status_code == 404
    assert client.get("/api/v1/auth/view-as", headers=admin).json()["data"] == []

    # allowing is the admin's: a viewer cannot grant it to themselves
    assert client.patch(f"/api/v1/users/{mai_id}", json={"can_view_as": False}, headers=mai).status_code == 403
    assert client.get("/api/v1/auth/me", headers=mai).json()["data"]["may_view_as"] is True


def test_an_agent_token_cannot_view_as(client, admin, member, upstream):  # noqa: F811
    seller = _limit(client, admin, member, [LINH])
    token = _token(client, admin)
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}", AS: str(seller)})
    assert res.status_code == 403 and "browser session" in res.json()["meta"]["message"]
