"""Etsy sale report for ZenE: validated query → trackingis, shared by the REST API and the MCP tools."""
import logging
import re
import threading
import time
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.deps import local_today
from app.core.errors import AppError, validation
from app.models import User
from app.services import settings_store
from app.services.trackingis import LIST_FILTERS, SORT_FIELDS, TEXT_FILTERS, VIEWS, ReportQuery, TrackingisClient, TrackingisError

log = logging.getLogger("rzn.report")
MAX_RANGE_DAYS = 366
CACHE_TTL_S = 60  # same filters within a minute reuse the answer (MCP agents and page reloads)
OPTIONS_TTL_S = 30 * 60
SYMBOLS = (">", ">=", "=", "<=", "<")
_ID_RE = re.compile(r"^[\w .&'\-]{1,120}$", re.UNICODE)
_cache: dict[tuple[Any, ...], tuple[float, Any]] = {}
_lock = threading.Lock()


def _cached(key: tuple[Any, ...], ttl: float, fn: Any) -> Any:
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = fn()
    with _lock:
        if len(_cache) > 500:
            _cache.clear()
        _cache[key] = (now, value)
    return value


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _date(value: str | None, field: str, default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise validation("Dates are YYYY-MM-DD", {field: [f"Not a date: {value}"]}) from exc


def _list(value: str | list[str] | None, field: str) -> list[str]:
    items = value if isinstance(value, list) else (value or "").split(",")
    out = [str(i).strip() for i in items if str(i).strip()]
    bad = [i for i in out if not _ID_RE.match(i)]
    if bad:
        raise validation("Invalid filter value", {field: [f"Not allowed: {bad[0][:40]}"]})
    return out[:200]


def build_query(db: Session, params: dict[str, Any]) -> ReportQuery:
    """Validate raw filters (REST query string or MCP arguments). Missing dates = this month so far; missing teams = Settings."""
    today = local_today()
    date_from = _date(params.get("date_from"), "date_from", today.replace(day=1))
    date_to = _date(params.get("date_to"), "date_to", today)
    if date_to < date_from:
        raise validation("date_to is before date_from", {"date_to": ["Must be on or after date_from"]})
    if (date_to - date_from) > timedelta(days=MAX_RANGE_DAYS):
        raise validation(f"At most {MAX_RANGE_DAYS} days per report", {"date_from": ["Range too long"]})
    view = (params.get("view") or "date").strip()
    if view not in VIEWS:
        raise validation("Unknown view", {"view": [f"One of {', '.join(VIEWS)}"]})
    sort_by = (params.get("sort_by") or "date_at").strip()
    if sort_by not in SORT_FIELDS:
        raise validation("Unknown sort field", {"sort_by": [f"One of {', '.join(SORT_FIELDS)}"]})
    sort_order = (params.get("sort_order") or "desc").strip().lower()
    if sort_order not in ("asc", "desc"):
        raise validation("sort_order is asc or desc", {"sort_order": ["asc or desc"]})
    lists = {f: _list(params.get(f), f) for f in LIST_FILTERS}
    if params.get("teams") is None:
        lists["teams"] = settings_store.runtime(db).default_teams
    texts = {f: str(params.get(f) or "").strip()[:200] for f in TEXT_FILTERS}
    if texts["symbol"] and texts["symbol"] not in SYMBOLS:
        raise validation("Unknown comparison", {"symbol": [f"One of {' '.join(SYMBOLS)}"]})
    if texts["total_order"] and not texts["total_order"].isdigit():
        raise validation("total_order is a whole number", {"total_order": ["Whole number"]})
    page = max(1, int(params.get("page") or 1))
    per_page = max(1, min(int(params.get("per_page") or 20), 200))
    return ReportQuery(date_from.isoformat(), date_to.isoformat(), view, page, per_page, sort_by, sort_order, lists, texts)


def tokens_for(db: Session, user: User | None) -> list[tuple[str, str]]:
    """[(source, token)] to try in order: the user's own SSO token (their trackingis rights), then the shared one."""
    out = []
    own = settings_store.decrypt(user.pod_token) if user is not None and user.pod_token else ""
    if own:
        out.append(("user", own))
    shared = settings_store.runtime(db).trackingis_token
    if shared and shared != own:
        out.append(("shared", shared))
    if not out:
        raise AppError(503, "TRACKINGIS_NOT_CONFIGURED",
                       "No trackingis access yet: sign in with Isuccess System again, or an admin pastes a shared token in Settings")
    return out


def _call(db: Session, user: User | None, kind: tuple[Any, ...], ttl: float, fn: Any) -> Any:
    """Run fn(client) with the first token trackingis accepts; answers are cached per token (rights differ per account)."""
    last: TrackingisError | None = None
    for source, token in tokens_for(db, user):
        client = TrackingisClient(token)
        try:
            return _cached((token[-12:], *kind), ttl, lambda c=client: fn(c))
        except TrackingisError as exc:
            last = exc
            if not exc.auth_failed:
                break
            log.info("trackingis refused the %s token of user %s, trying the next one", source, user.id if user else "-")
    assert last is not None
    raise AppError(last.status, "TRACKINGIS_ERROR", str(last)) from last


def _key(kind: str, q: ReportQuery) -> tuple[Any, ...]:
    return (kind, q.date_from, q.date_to, q.view, q.page, q.per_page, q.sort_by, q.sort_order,
            tuple((k, tuple(v)) for k, v in sorted(q.lists.items())), tuple(sorted(q.texts.items())))


def etsy_report(db: Session, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    q = build_query(db, params)
    data = _call(db, user, _key("report", q), CACHE_TTL_S, lambda c: c.report(q))
    return {**data, "query": {"date_from": q.date_from, "date_to": q.date_to, "view": q.view, "teams": q.lists["teams"]}}


def etsy_totals(db: Session, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    q = build_query(db, {**params, "view": "date"})
    data = _call(db, user, _key("totals", q), CACHE_TTL_S, lambda c: c.totals(q))
    return {**data, "date_from": q.date_from, "date_to": q.date_to}


def filter_options(db: Session, kind: str, user: User | None = None) -> list[dict[str, Any]]:
    rows = _call(db, user, ("options", kind), OPTIONS_TTL_S, lambda c: c.options(kind))
    if kind == "teams":  # ZenE teams first: BU ZenE and its children
        zene = {r["id"] for r in rows if str(r.get("name", "")).lower() == "zene"}
        rows = sorted(rows, key=lambda r: (r.get("id") not in zene and r.get("parent_id") not in zene, str(r.get("name", ""))))
    out = []
    for r in rows:
        if not isinstance(r, dict):  # some filter routes answer plain strings
            out.append({"id": str(r), "name": str(r)})
            continue
        ident = r.get("id", r.get("value"))
        item = {"id": ident, "name": r.get("name") or r.get("shop_name") or r.get("label") or r.get("text") or str(ident)}
        if kind == "teams":
            item |= {"parent_id": r.get("parent_id"), "type": r.get("type")}
        out.append(item)
    return out
