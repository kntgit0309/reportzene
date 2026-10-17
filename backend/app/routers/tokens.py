"""Personal agent tokens (REST API). Shown once at creation, stored hashed, revocable."""
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import current_user
from app.core.errors import not_found, validation
from app.core.responses import ok
from app.core.security import new_token, token_hash
from app.db import get_db
from app.models import ApiToken, User

router = APIRouter(prefix="/auth/tokens", tags=["tokens"])
PREFIX = "rzn_"
MAX_TOKENS = 10


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


def _out(t: ApiToken) -> dict[str, Any]:
    return {"id": t.id, "name": t.name, "hint": t.hint, "created_at": t.created_at.isoformat(),
            "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None}


@router.get("")
def list_tokens(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, Any]:
    rows = db.scalars(select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.id.desc()))
    return ok([_out(t) for t in rows], request)


@router.post("")
def create_token(body: TokenIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, Any]:
    count = len(list(db.scalars(select(ApiToken.id).where(ApiToken.user_id == user.id))))
    if count >= MAX_TOKENS:
        raise validation(f"At most {MAX_TOKENS} tokens, delete an old one first")
    token = PREFIX + new_token()
    row = ApiToken(token_hash=token_hash(token), user_id=user.id, name=body.name.strip(), hint=token[:10])
    db.add(row)
    db.commit()
    return ok({**_out(row), "token": token}, request, "The token is shown once, copy it now")


@router.delete("/{token_id}")
def revoke_token(token_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, Any]:
    row = db.get(ApiToken, token_id)
    if row is None or row.user_id != user.id:
        raise not_found("token")
    db.delete(row)
    db.commit()
    return ok(None, request, "Token deleted")
