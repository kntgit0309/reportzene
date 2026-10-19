"""Etsy sale report (ZenE): rows per view, summary cards, the ornament / shirt breakdowns and filter options, read from trackingis."""
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.orm import Session

from app.core.deps import current_user
from app.core.responses import ok
from app.db import get_db
from app.models import User
from app.services import family_accounts, family_report, report
from app.services.families import FAMILIES

router = APIRouter(prefix="/report/etsy", tags=["report"])
OPTION_KINDS = "^(shops|sellers|designers|product_types|sub_product_types|teams)$"
FAMILY_KEYS = f"^({'|'.join(FAMILIES)})$"


def _params(request: Request) -> dict[str, Any]:
    """Query string as filters: list filters are comma lists; `teams` absent = the ZenE teams from Settings."""
    return dict(request.query_params)


@router.get("")
def etsy_report(request: Request, view: str = Query("date", max_length=20), date_from: str | None = Query(None, max_length=10),
                date_to: str | None = Query(None, max_length=10), page: int = Query(1, ge=1, le=10_000),
                per_page: int = Query(20, ge=1, le=200), db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, Any]:
    params = {**_params(request), "view": view, "date_from": date_from, "date_to": date_to, "page": page, "per_page": per_page}
    return ok(report.etsy_report(db, params, user), request)


@router.get("/totals")
def etsy_totals(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, Any]:
    return ok(report.etsy_totals(db, _params(request), user), request)


@router.get("/options/{kind}")
def options(request: Request, kind: str = Path(pattern=OPTION_KINDS), db: Session = Depends(get_db),
            user: User = Depends(current_user)) -> dict[str, Any]:
    return ok(report.filter_options(db, kind, user), request)


@router.get("/{family}")
def family_sales(request: Request, family: str = Path(pattern=FAMILY_KEYS), db: Session = Depends(get_db),
                 user: User = Depends(current_user)) -> dict[str, Any]:
    """Sales of a product family per product type (Etsy › Ornament, Etsy › Shirt), same filters as the report."""
    return ok(family_report.family_report(db, FAMILIES[family], _params(request), user), request)


@router.get("/{family}/accounts")
def family_accounts_report(request: Request, family: str = Path(pattern=FAMILY_KEYS), db: Session = Depends(get_db),
                           user: User = Depends(current_user)) -> dict[str, Any]:
    """Sales of a product family per store next to the store's line of the family's plan (KH Ornament, KH Shirt)."""
    return ok(family_accounts.accounts_report(db, FAMILIES[family], _params(request), user), request)
