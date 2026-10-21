"""Auth dependencies: current user from cookie or Bearer token, admin guard."""
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AppError, forbidden
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


def current_user(token: str | None = Depends(session_token), db: Session = Depends(get_db)) -> User:
    return user_from_token(db, token)


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
