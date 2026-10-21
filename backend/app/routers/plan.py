"""Etsy plan by product (Etsy › Plan): read from the plan team sheet picked in Settings."""
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import full_access
from app.core.responses import ok
from app.db import get_db
from app.models import User
from app.services import plan

router = APIRouter(prefix="/plan", tags=["plan"])


@router.get("/products")
def plan_by_product(request: Request, db: Session = Depends(get_db), _: User = Depends(full_access)) -> dict[str, Any]:
    return ok(plan.by_product(db), request)
