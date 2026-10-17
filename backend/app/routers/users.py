"""Users of ReportZenE: admins list, create, unlock and change them."""
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import admin
from app.core.errors import AppError, not_found, validation
from app.core.responses import ok
from app.core.security import hash_password
from app.db import get_db
from app.models import NO_PASSWORD, User, UserSession
from app.routers.auth import user_out
from app.schemas import UserCreate, UserUpdate
from app.services.naming import clean_code

router = APIRouter(prefix="/users", tags=["users"])


def _code(raw: str) -> str:
    code = clean_code(raw, 16)
    if len(code) < 2:
        raise validation("The short code needs at least 2 characters A-Z/0-9", {"code": ["Invalid"]})
    return code


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "DUPLICATE", "Email or short code already in use") from exc


@router.get("")
def list_users(request: Request, db: Session = Depends(get_db), _: User = Depends(admin)) -> dict[str, Any]:
    return ok([user_out(u) for u in db.scalars(select(User).order_by(User.name))], request)


@router.post("")
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db), _: User = Depends(admin)) -> dict[str, Any]:
    user = User(email=body.email.strip().lower(), name=body.name.strip(), code=_code(body.code), role=body.role, password_hash=hash_password(body.password) if body.password else NO_PASSWORD)
    db.add(user)
    _commit(db)
    return ok(user_out(user), request, "User created")


@router.patch("/{user_id}")
def update_user(user_id: int, body: UserUpdate, request: Request, db: Session = Depends(get_db), me: User = Depends(admin)) -> dict[str, Any]:
    user = db.get(User, user_id)
    if user is None:
        raise not_found("user")
    if user.id == me.id and (body.role == "member" or body.is_active is False):
        raise validation("You cannot demote or lock yourself")
    for field in ("name", "role", "is_active"):
        if getattr(body, field) is not None:
            setattr(user, field, getattr(body, field))
    if body.code is not None:
        user.code = _code(body.code)
    if body.password:
        user.password_hash = hash_password(body.password)
    if body.password or body.is_active is False:
        db.query(UserSession).filter(UserSession.user_id == user.id).delete()
    _commit(db)
    return ok(user_out(user), request, "Saved")
