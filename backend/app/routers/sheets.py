"""Team report sheets (Lark): everyone reads the snapshots; admins add, edit, delete; anyone signed in can sync."""
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.deps import admin, current_user
from app.core.responses import ok, paged
from app.db import get_db
from app.models import SheetSource, User
from app.schemas import SheetIn, SheetTabsIn
from app.services import sheets

router = APIRouter(prefix="/sheets", tags=["sheets"])


@router.get("")
def list_sheets(request: Request, db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict[str, Any]:
    return ok([sheets.summary(s) for s in sheets.list_all(db)], request)


@router.post("/tabs")
def list_tabs(body: SheetTabsIn, request: Request, db: Session = Depends(get_db), _: User = Depends(admin)) -> dict[str, Any]:
    """Tabs of a sheet link, to pick one before saving (also proves the Lark app can open it)."""
    return ok(sheets.tabs(db, body.url), request)


@router.post("")
def create_sheet(body: SheetIn, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)) -> dict[str, Any]:
    source = SheetSource(name=body.name, url=body.url, tab_id=body.tab_id, header_row=body.header_row, created_by=user.id)
    db.add(source)
    db.commit()
    sheets.sync(db, source)
    return ok(sheets.summary(source), request, f"Synced {source.row_count} rows")


@router.put("/{source_id}")
def update_sheet(source_id: int, body: SheetIn, request: Request, db: Session = Depends(get_db), _: User = Depends(admin)) -> dict[str, Any]:
    source = sheets.get(db, source_id)
    source.name, source.url, source.tab_id, source.header_row = body.name, body.url, body.tab_id, body.header_row
    db.commit()
    sheets.sync(db, source)
    return ok(sheets.summary(source), request, f"Synced {source.row_count} rows")


@router.delete("/{source_id}")
def delete_sheet(source_id: int, request: Request, db: Session = Depends(get_db), _: User = Depends(admin)) -> dict[str, Any]:
    db.delete(sheets.get(db, source_id))
    db.commit()
    return ok(None, request, "Sheet removed")


@router.post("/{source_id}/sync")
def sync_sheet(source_id: int, request: Request, db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict[str, Any]:
    source = sheets.sync(db, sheets.get(db, source_id))
    return ok(sheets.summary(source), request, f"Synced {source.row_count} rows")


@router.get("/{source_id}/rows")
def sheet_rows(source_id: int, request: Request, q: str = Query("", max_length=200), page: int = Query(1, ge=1),
               per_page: int = Query(50, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict[str, Any]:
    items, total = sheets.rows(sheets.get(db, source_id), q, page, per_page)
    return paged(items, total, page, per_page, request)
