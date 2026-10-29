"""Auth dependencies: current user from cookie or Bearer token, admin guard."""
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AppError, forbidden, not_found, validation
from app.core.security import token_hash
from app.db import get_db
from app.models import ApiToken, User, UserSession
from app.models.base import utcnow


def session_token(request: Request, authorization: str | None = Header(default=None)) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.cookies.get(settings.cookie_name)


def user_from_token(db: Session, token: str | None) -> User:
    """Browser session or personal agent token → active user, else 401."""
    if not token:
        raise AppError(401, "UNAUTHENTICATED", "Not signed in")
    hashed = token_hash(token)
    sess = db.get(UserSession, hashed)
    if sess is not None:
        expires = sess.expires_at if sess.expires_at.tzinfo else sess.expires_at.replace(tzinfo=UTC)
        if expires < utcnow():
            raise AppError(401, "UNAUTHENTICATED", "Session expired")
        user_id = sess.user_id
    else:
        api = db.scalar(select(ApiToken).where(ApiToken.token_hash == hashed))
        if api is None:
            raise AppError(401, "UNAUTHENTICATED", "Invalid session or token")
        api.last_used_at = utcnow()
        db.commit()
        user_id = api.user_id
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(401, "UNAUTHENTICATED", "This account is locked")
    return user


VIEW_AS_HEADER = "x-view-as"


def real_user(token: str | None = Depends(session_token), db: Session = Depends(get_db)) -> User:
    """Who is signed in, whatever account they are viewing as."""
    return user_from_token(db, token)


def view_as_target(db: Session, token: str | None, user: User, method: str, raw: str) -> User:
    """The seller account `user` is viewing as ("View as" on the header X-View-As = its user id), or an error.

    Only a signed-in browser session may (not an agent token), only a user an admin allowed (admins always), only to a
    seller account (an active member limited to some sellers), and read-only: every report, filter and sheet is then
    exactly what that seller gets, and nothing can be changed in their name."""
    if not user.may_view_as:
        raise forbidden("Your account cannot view as another account")
    if token is None or db.get(UserSession, token_hash(token)) is None:
        raise forbidden("View as needs a browser session, not an agent token")
    if not raw.isdigit():
        raise validation("X-View-As is the id of a seller account")
    if int(raw) == user.id:
        return user
    target = db.get(User, int(raw))
    if target is None or not target.is_active:
        raise not_found("seller account")
    if target.is_admin or target.seller_scope is None:
        raise forbidden("You can only view as a seller account (a member limited to some sellers)")
    if method not in ("GET", "HEAD"):
        raise forbidden(f"Read-only while viewing as {target.name}: exit View as to change anything")
    return target


def current_user(request: Request, token: str | None = Depends(session_token), db: Session = Depends(get_db)) -> User:
    """The user every request acts as: the signed-in one, or the seller account they view as."""
    user = user_from_token(db, token)
    raw = request.headers.get(VIEW_AS_HEADER)
    return view_as_target(db, token, user, request.method, raw.strip()) if raw and raw.strip() else user


def full_access(user: User = Depends(current_user)) -> User:
    """Pages that hold the whole of ZenE's data (Etsy › Plan, Lark › Team sheets): not for a member limited to their own sales."""
    if user.seller_scope is not None:
        raise forbidden("Your account sees only your own sales: this page holds the whole of ZenE's data")
    return user


def admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise forbidden("Only admins can do this")
    return user


def local_today() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()
