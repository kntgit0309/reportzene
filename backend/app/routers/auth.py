"""Login: "Sign in with POD" (SSO, primary) + email/password (break-glass for admins). Session in an httpOnly cookie."""
import hmac
import logging
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import current_user, session_token
from app.core.errors import AppError
from app.core.responses import ok
from app.core.security import new_token, token_hash, verify_password
from app.db import get_db
from app.models import OAuthState, User, UserSession
from app.models.base import utcnow
from app.schemas import LoginIn
from app.services import pod_sso
from app.services.sso_users import upsert_from_pod

log = logging.getLogger("rzn.auth")
router = APIRouter(prefix="/auth", tags=["auth"])
callback_router = APIRouter(tags=["auth"])  # mounted at root: /auth/pod/callback

MAX_FAILS = 5
FAIL_WINDOW_S = 600
STATE_COOKIE = "pod_sso_state"
STATE_TTL = timedelta(minutes=10)
DEFAULT_NEXT = "/etsy/report"
_fails: dict[str, deque[float]] = defaultdict(deque)


def user_out(u: User) -> dict[str, Any]:
    return {"id": u.id, "email": u.email, "name": u.name, "code": u.code, "role": u.role, "is_active": u.is_active,
            "avatar_url": u.avatar_url, "is_pod": u.pod_user_id is not None, "pod_connected": bool(u.pod_token),
            "pod_token_at": u.pod_token_at.isoformat() if u.pod_token_at else None,
            "scope_sellers": [str(s) for s in u.scope_sellers or []]}  # data scope (Settings › Users); [] = the whole of ZenE


def _start_session(db: Session, user: User, response: Response) -> None:
    token = new_token()
    db.add(UserSession(token_hash=token_hash(token), user_id=user.id, expires_at=utcnow() + timedelta(days=settings.session_days)))
    response.set_cookie(settings.cookie_name, token, max_age=settings.session_days * 86400, httponly=True,
                        secure=settings.cookie_secure, samesite="lax", path="/")


def _safe_next(path: str | None) -> str:
    """Only same-site relative paths: blocks open redirects like //evil.com."""
    if not path or not path.startswith("/") or path.startswith("//") or "\\" in path:
        return DEFAULT_NEXT
    return path[:300]


def _throttle_key(request: Request, email: str) -> str:
    return f"{request.client.host if request.client else '-'}|{email.lower()}"


def _too_many(key: str) -> bool:
    q = _fails[key]
    while q and time.monotonic() - q[0] > FAIL_WINDOW_S:
        q.popleft()
    return len(q) >= MAX_FAILS


@router.get("/config")
def auth_config(request: Request) -> dict[str, Any]:
    return ok({"pod_enabled": settings.pod_enabled, "password_enabled": settings.allow_password_login}, request)


@router.get("/pod/login")
def pod_login(next: str | None = Query(None, max_length=300), db: Session = Depends(get_db)) -> RedirectResponse:
    if not settings.pod_enabled:
        raise AppError(503, "SSO_DISABLED", "Isuccess System sign-in is not configured")
    state = secrets.token_urlsafe(32)
    db.add(OAuthState(state_hash=token_hash(state), next_path=_safe_next(next), expires_at=utcnow() + STATE_TTL))
    db.commit()
    res = RedirectResponse(pod_sso.authorize_url(state), status_code=302)
    res.set_cookie(STATE_COOKIE, state, max_age=int(STATE_TTL.total_seconds()), httponly=True, samesite="lax",
                   secure=settings.cookie_secure, path="/auth/pod")
    return res


def _fail(message: str) -> RedirectResponse:
    res = RedirectResponse(f"/login?error={quote(message)}", status_code=302)
    res.delete_cookie(STATE_COOKIE, path="/auth/pod")
    return res


@callback_router.get("/auth/pod/callback", include_in_schema=False)
def pod_callback(request: Request, state: str = Query(""), code: str = Query(""), error: str = Query(""), db: Session = Depends(get_db)) -> RedirectResponse:
    cookie_state = request.cookies.get(STATE_COOKIE, "")
    if not state or not cookie_state or not hmac.compare_digest(state, cookie_state):
        return _fail("Sign-in session does not match, reopen the sign-in page")
    row = db.get(OAuthState, token_hash(state))
    if row is None:
        return _fail("This sign-in link was already used, try again")
    db.delete(row)  # one-time use
    db.commit()
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=utcnow().tzinfo)
    if expires < utcnow():
        return _fail("Sign-in timed out, try again")
    if error == "access_denied":
        return _fail("You cancelled the Isuccess System sign-in")
    if not code:
        return _fail("Isuccess System did not return a sign-in code")
    try:
        profile = pod_sso.exchange(code)
    except pod_sso.PodAuthError as exc:
        log.warning("POD exchange rejected: %s", exc)
        return _fail(f"Isuccess System refused the sign-in: {exc}")
    except pod_sso.PodUnavailable:
        return _fail("Cannot reach Isuccess System, try again later")

    user = upsert_from_pod(db, profile)
    if not user.is_active:
        db.commit()
        return _fail("Your account has been locked in ReportZenE, ask an admin to unlock it")
    res = RedirectResponse(row.next_path or DEFAULT_NEXT, status_code=302)
    _start_session(db, user, res)
    res.delete_cookie(STATE_COOKIE, path="/auth/pod")
    db.commit()
    log.info("POD login %s (pod %s)", user.email, profile.user_id)
    return res


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not settings.allow_password_login:
        raise AppError(403, "PASSWORD_LOGIN_DISABLED", "Password sign-in is disabled, use Isuccess System")
    key = _throttle_key(request, body.email)
    if _too_many(key):
        raise AppError(429, "RATE_LIMITED", "Too many wrong passwords, try again in 10 minutes")
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        _fails[key].append(time.monotonic())
        raise AppError(401, "UNAUTHENTICATED", "Wrong email or password")
    _fails.pop(key, None)
    _start_session(db, user, response)
    db.commit()
    return ok({"user": user_out(user)}, request)


@router.post("/logout")
def logout(request: Request, response: Response, token: str | None = Depends(session_token), db: Session = Depends(get_db)) -> dict[str, Any]:
    if token:
        sess = db.get(UserSession, token_hash(token))
        if sess:
            db.delete(sess)
            db.commit()
    response.delete_cookie(settings.cookie_name, path="/")
    return ok(None, request)


@router.get("/me")
def me(request: Request, user: User = Depends(current_user)) -> dict[str, Any]:
    return ok(user_out(user), request)
