"""Team report sheets: a Lark Sheet tab synced on demand, its last read kept as a snapshot for the web page and MCP."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AppError, not_found
from app.models import SheetSource
from app.models.base import utcnow
from app.services import settings_store
from app.services.lark_sheets import LarkClient, LarkError

MAX_SEARCH_ROWS = 500


def client(db: Session) -> LarkClient:
    rt = settings_store.runtime(db)
    try:
        return LarkClient(rt.lark_app_id, rt.lark_app_secret, settings.lark_base_url)
    except LarkError as exc:
        raise AppError(503, "LARK_NOT_CONFIGURED", str(exc)) from exc


def summary(s: SheetSource) -> dict[str, Any]:
    return {"id": s.id, "name": s.name, "url": s.url, "tab_id": s.tab_id, "tab_title": s.tab_title, "header_row": s.header_row,
            "header": s.header or [], "row_count": s.row_count, "last_error": s.last_error,
            "last_synced_at": s.last_synced_at.isoformat() if s.last_synced_at else None}


def get(db: Session, source_id: int) -> SheetSource:
    row = db.get(SheetSource, source_id)
    if row is None:
        raise not_found("sheet")
    return row


def find(db: Session, ref: str | int) -> SheetSource:
    """By id or by name (case-insensitive), for MCP agents."""
    raw = str(ref).strip()
    if raw.isdigit():
        return get(db, int(raw))
    row = db.scalar(select(SheetSource).where(SheetSource.name.ilike(raw)))
    if row is None:
        raise not_found(f"sheet '{raw[:60]}'")
    return row


def list_all(db: Session) -> list[SheetSource]:
    return list(db.scalars(select(SheetSource).order_by(SheetSource.name)))


def tabs(db: Session, url: str) -> dict[str, Any]:
    try:
        found, linked = client(db).tabs(url)
    except LarkError as exc:
        raise AppError(422, "LARK_ERROR", str(exc)) from exc
    return {"tabs": found, "linked_tab_id": linked}


def sync(db: Session, source: SheetSource) -> SheetSource:
    """Read the tab again; on a Lark error keep the previous snapshot and record the error."""
    try:
        tab, header, rows = client(db).read_tab(source.url, source.tab_id, source.header_row, settings.sheet_max_rows)
    except LarkError as exc:
        source.last_error = str(exc)[:500]
        db.commit()
        raise AppError(422, "LARK_ERROR", str(exc)) from exc
    source.tab_id, source.tab_title = tab["sheet_id"], tab["title"]
    source.header, source.rows, source.row_count = header, rows, len(rows)
    source.last_synced_at, source.last_error = utcnow(), None
    db.commit()
    return source


def rows(source: SheetSource, q: str = "", page: int = 1, per_page: int = 50) -> tuple[list[dict[str, Any]], int]:
    """Snapshot rows filtered by a free-text search over every cell, paged."""
    data = source.rows or []
    needle = q.strip().lower()
    if needle:
        data = [r for r in data if any(needle in str(v).lower() for k, v in r.items() if k != "_row")]
    start = (page - 1) * per_page
    return data[start:start + per_page], len(data)
