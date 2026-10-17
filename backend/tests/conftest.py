import os

# Tests must not see deploy-time secrets/config passed in the shell (deploy.sh runs pytest with them set).
for _var in [k for k in os.environ if k.startswith(("POD_", "BOOTSTRAP_", "TRACKINGIS_", "DEFAULT_TEAMS", "COOKIE_", "CORS_", "SECRET_KEY", "LARK_"))]:
    os.environ.pop(_var)
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["BOOTSTRAP_EMAIL"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db import Base, get_db, make_engine
from app.main import create_app
from app.models import User
from app.routers import auth

PASSWORD = "secret-pass-1"


@pytest.fixture()
def db_factory(monkeypatch):
    engine = make_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    from app import mcp_server
    monkeypatch.setattr(mcp_server, "SessionLocal", factory)  # MCP tools read the test database
    yield factory
    engine.dispose()


@pytest.fixture()
def client(db_factory, tmp_path, monkeypatch):
    from app.services import report, settings_store
    monkeypatch.setattr(settings_store, "SECRET_FILE", tmp_path / "secret.key")
    report.clear_cache()
    app = create_app(init_db=False)

    def _db():
        s = db_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    auth._fails.clear()
    with TestClient(app) as c:
        yield c


def _user(db_factory, email: str, name: str, code: str, role: str) -> User:
    with db_factory() as s:
        u = User(email=email, name=name, code=code, role=role, password_hash=hash_password(PASSWORD))
        s.add(u)
        s.commit()
        return u


def _login(client: TestClient, email: str) -> dict:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    token = res.cookies.get("rzn_session")
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin(client, db_factory):
    _user(db_factory, "boss@zene.test", "Boss", "BOSS", "admin")
    return _login(client, "boss@zene.test")


@pytest.fixture()
def member(client, db_factory):
    _user(db_factory, "khoa@zene.test", "Khoa", "KHOA", "member")
    return _login(client, "khoa@zene.test")
