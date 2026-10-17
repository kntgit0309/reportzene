from urllib.parse import parse_qs, unquote, urlparse

import httpx
import pytest
from sqlalchemy import create_engine, inspect, text

from app.config import settings
from app.db_migrate import add_missing_columns
from app.models import User
from app.services import pod_sso
from app.services.pod_sso import PodProfile
from app.services.sso_users import suggest_code
from tests.conftest import PASSWORD, _user

KHOA = PodProfile(user_id=501, name="Nguyễn Hữu Khoa", email="khoa@pod.test", avatar_url="https://pod.test/a.png")


@pytest.fixture()
def pod_on(monkeypatch):
    monkeypatch.setattr(settings, "pod_app_key", "app-key")
    monkeypatch.setattr(settings, "pod_app_secret", "app-secret")
    monkeypatch.setattr(settings, "pod_redirect_url", "https://reportzene.test/auth/pod/callback")
    monkeypatch.setattr(settings, "pod_allowed_users", "khoa@pod.test, boss@pod.test")


def _start(client, next_path="/ads"):
    res = client.get(f"/api/v1/auth/pod/login?next={next_path}", follow_redirects=False)
    assert res.status_code == 302
    return parse_qs(urlparse(res.headers["location"]).query)["state"][0]


def _callback(client, monkeypatch, profile: PodProfile, state: str):
    monkeypatch.setattr(pod_sso, "exchange", lambda code: profile)
    return client.get(f"/auth/pod/callback?state={state}&code=abc", follow_redirects=False)


def test_config_reports_sso_off_by_default(client):
    assert client.get("/api/v1/auth/config").json()["data"] == {"pod_enabled": False, "password_enabled": True}
    assert client.get("/api/v1/auth/pod/login", follow_redirects=False).status_code == 503


def test_login_redirects_to_pod_with_state_cookie(client, pod_on):
    res = client.get("/api/v1/auth/pod/login?next=/ads", follow_redirects=False)
    q = parse_qs(urlparse(res.headers["location"]).query)
    assert res.headers["location"].startswith("https://production.trackingis.info/sso/authorize")
    assert q["app"] == ["app-key"] and q["redirect_url"] == ["https://reportzene.test/auth/pod/callback"]
    assert res.cookies.get("pod_sso_state") == q["state"][0]


def test_first_pod_login_creates_member_and_session(client, pod_on, monkeypatch, db_factory):
    res = _callback(client, monkeypatch, KHOA, _start(client))
    assert res.status_code == 302 and res.headers["location"] == "/ads"
    me = client.get("/api/v1/auth/me").json()["data"]
    assert me["role"] == "member" and me["code"] == "KHOA" and me["is_pod"] and me["email"] == "khoa@pod.test"
    with db_factory() as s:
        assert s.query(User).filter_by(pod_user_id=501).one().password_hash == "!"


def test_pod_login_links_existing_account_and_keeps_role(client, pod_on, monkeypatch, db_factory):
    _user(db_factory, "khoa@pod.test", "Khoa", "BOSS", "admin")
    _callback(client, monkeypatch, KHOA, _start(client))
    me = client.get("/api/v1/auth/me").json()["data"]
    assert me["role"] == "admin" and me["code"] == "BOSS" and me["is_pod"]


def test_state_is_one_time_and_must_match_cookie(client, pod_on, monkeypatch):
    _start(client)
    assert _callback(client, monkeypatch, KHOA, "forged").headers["location"].startswith("/login?error=")
    state = _start(client)
    assert _callback(client, monkeypatch, KHOA, state).headers["location"] == "/ads"
    client.cookies.set("pod_sso_state", state, path="/auth/pod")
    assert _callback(client, monkeypatch, KHOA, state).headers["location"].startswith("/login?error=")


def test_open_redirect_is_blocked(client, pod_on, monkeypatch):
    assert _callback(client, monkeypatch, KHOA, _start(client, "//evil.com")).headers["location"] == "/etsy/report"


def test_locked_user_cannot_sign_in(client, pod_on, monkeypatch, db_factory):
    _callback(client, monkeypatch, KHOA, _start(client))
    with db_factory() as s:
        s.query(User).filter_by(pod_user_id=501).update({"is_active": False})
        s.commit()
    client.cookies.clear()
    assert "locked" in unquote(_callback(client, monkeypatch, KHOA, _start(client)).headers["location"])


def test_pod_errors_go_back_to_login(client, pod_on, monkeypatch):
    def boom(code):
        raise pod_sso.PodUnavailable("down")

    state = _start(client)
    monkeypatch.setattr(pod_sso, "exchange", boom)
    assert client.get(f"/auth/pod/callback?state={state}&code=x", follow_redirects=False).headers["location"].startswith("/login?error=")


def test_pod_only_user_cannot_use_password(client, pod_on, monkeypatch):
    _callback(client, monkeypatch, KHOA, _start(client))
    assert client.post("/api/v1/auth/login", json={"email": "khoa@pod.test", "password": PASSWORD}).status_code == 401


def test_suggest_code_strips_accents_and_dedupes(db_factory):
    _user(db_factory, "a@x.test", "A", "KHOA", "member")
    with db_factory() as s:
        assert suggest_code(s, "Nguyễn Hữu Khoa", None, 1) == "KHOA2"
        assert suggest_code(s, "Trần Đức", None, 1) == "DUC"
        assert suggest_code(s, None, "lan.pham@x.test", 1) == "LANPHAM"


def test_exchange_parses_pod_response(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/v2/sso/exchange"
        return httpx.Response(200, json={"success": True, "data": {"token": "t", "user": {"id": 7, "name": "Lan", "email": "LAN@X.TEST"}}})

    monkeypatch.setattr(pod_sso, "_client", lambda: httpx.Client(base_url="https://pod.test", transport=httpx.MockTransport(handler)))
    assert pod_sso.exchange("code") == PodProfile(user_id=7, name="Lan", email="lan@x.test", avatar_url=None, token="t")


def test_exchange_rejected(monkeypatch):
    transport = httpx.MockTransport(lambda req: httpx.Response(400, json={"success": False, "message": "bad code"}))
    monkeypatch.setattr(pod_sso, "_client", lambda: httpx.Client(base_url="https://pod.test", transport=transport))
    with pytest.raises(pod_sso.PodAuthError, match="bad code"):
        pod_sso.exchange("code")


def test_migration_adds_pod_columns_to_old_users_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(200), name VARCHAR(120), code VARCHAR(16), "
                          "role VARCHAR(16), password_hash VARCHAR(255), is_active BOOLEAN, created_at DATETIME)"))
    added = add_missing_columns(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert {"users.pod_user_id", "users.avatar_url"} <= set(added) and {"pod_user_id", "avatar_url"} <= cols


def test_first_pod_login_outside_allow_list_is_locked(client, pod_on, monkeypatch, db_factory):
    stranger = PodProfile(user_id=777, name="Người Lạ", email="stranger@pod.test", avatar_url=None)
    res = _callback(client, monkeypatch, stranger, _start(client))
    assert res.status_code == 302 and res.headers["location"].startswith("/login?error=")
    assert client.get("/api/v1/auth/me").status_code == 401
    with db_factory() as s:
        assert s.query(User).filter_by(pod_user_id=777).one().is_active is False  # waits for an admin to unlock it
