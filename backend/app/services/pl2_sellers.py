"""Etsy › Report, PL2 per seller: for each seller, PL2 theo KT (their quantity of each plan product × that product's PL2 per
item; Other products at theirs from Settings › Plan) next to their PL2 plan to date and finance's PL2 theo CF ("Profit tính KPI").

Plan: the seller plan sheet (Settings › Plan, "KH quý 4.2026 theo seller": PL2 T10 | T11 | T12 in dollars per seller), each
month pro rata of the report's days, as everywhere else. CF: the "1.2 P&L Seller (Sau IP)_Monthly" tabs (Settings › Plan ›
Seller CF sheets), booked per month, so a range counts the whole months it touches. Both sheets name sellers by first name
("Linh"), trackingis by account ("Linh PT.ETS"): they are matched as in seller_plan (`match`), and two trackingis sellers
that fall on one sheet row are one row here. The sellers of the plan sheet come first, in sheet order; sellers outside it
are listed after them when they have a PL2 (KT or CF not 0), and their whole PL2 counts as gap against a plan of $0.

Plan and CF are per seller across all stores and teams: a store, team, designer or keyword filter narrows the KT only, so they
are left out then. A seller filter keeps those sellers' rows (a member limited to their own sales gets only theirs). Pieces
added by hand (Felt) are not tied to a seller, so they are not in KT here.
"""
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import User
from app.services import family_accounts, family_plan, family_report, overview, report, seller_cf, seller_plan, settings_store
from app.services.pl2_accounts import _sheet
from app.services.trackingis import ReportQuery, TrackingisClient, TrackingisError

NO_SELLER = "(no seller)"
FILTERED = "PL2 plan and CF are per seller across all stores: clear the store, team, designer and keyword filters to compare with them"


def _fetch(client: TrackingisClient, lines: list[dict[str, Any]], q: ReportQuery) -> list[list[dict[str, Any]]]:
    """The seller view of each priced product (its sub product types only), in parallel."""
    with ThreadPoolExecutor(max_workers=family_report.WORKERS) as pool:
        futures = [pool.submit(family_accounts._stores, client, family_report._only(q, tuple(line["sub_types"])), "seller") for line in lines]
        try:
            return [f.result() for f in futures]
        except TrackingisError:
            pool.shutdown(cancel_futures=True)  # a refused token fails every query: don't send the ones still queued
            raise


def _plan_table(db: Session, names: list[str]) -> dict[str, Any]:
    """{table, sheet} of the seller plan sheet (the table where most of `names` have a row), or {"error"}."""
    got = _sheet(db, settings_store.runtime(db).seller_plan_sheet_id, "seller plan sheet")
    if isinstance(got, str):
        return {"error": got}
    try:
        tables = seller_plan.parse(got.header or [], got.rows)
    except AppError as exc:
        return {"error": exc.message}
    return {"table": seller_plan.best(tables, names)[0], "sheet": family_plan.sheet_info(got)}


def _plan_to_date(pl2: dict[int, float], months: dict[str, tuple[int, int]], planned: list[int]) -> float | None:
    """A seller's PL2 plan for the report's days (each month pro rata); None when the sheet plans none of the months."""
    got = [pl2.get(int(m[:2]), 0.0) * days / month_days for m, (days, month_days) in months.items() if int(m[:2]) in planned]
    return sum(got) if got else None


def _line(name: str, sellers: list[str], in_plan: bool, quantity: int, plan: float | None, kt: float | None, cf: float | None,
          against: float | None) -> dict[str, Any]:
    """One row. `against` is the plan the gaps are measured from (the plan, or $0 for a seller outside it; None = no plan at
    all): kt_gap = KT − against, cf_gap = CF − against; kt_pct / cf_pct = KT / CF as a share of the plan."""
    def diff(v: float | None) -> float | None:
        return None if v is None or against is None else round(v - against, 2)

    def ratio(v: float | None) -> float | None:
        return round(v / plan, 4) if v is not None and plan else None

    return {"seller": name, "sellers": sellers, "in_plan": in_plan, "quantity": quantity, "plan": None if plan is None else round(plan, 2),
            "kt": None if kt is None else round(kt, 2), "cf": None if cf is None else round(cf, 2),
            "kt_gap": diff(kt), "kt_pct": ratio(kt), "cf_gap": diff(cf), "cf_pct": ratio(cf),
            "cf_minus_kt": round(cf - kt, 2) if kt is not None and cf is not None else None}


def pl2_sellers(db: Session, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    """{sellers: [{seller, sellers, in_plan, quantity, plan, kt, cf, kt_gap, kt_pct, cf_gap, cf_pct, cf_minus_kt}], total, kt,
    plan, cf, query}; plan = PL2 plan to date ($), kt_gap = kt − plan, cf_gap = cf − plan; kt / plan / cf = {"error"} when
    not available (a field of a row is then None)."""
    q = report.build_query(db, {**params, "view": "date"}, user)
    rt = settings_store.runtime(db)
    options = {str(o["id"]): str(o["name"]) for o in report.filter_options(db, "sellers", user)}
    months = family_plan.month_days(q.date_from, q.date_to)

    lines = overview.priced_products(db, user)
    has_kt = bool(lines)
    kt_info: dict[str, Any] = {} if has_kt else {"error": "No plan with PL2/item to estimate from: an admin picks the plan sheet in Settings → Plan"}
    sold: dict[str, dict[str, Any]] = {}  # trackingis sellers of the report's filters: quantity and KT
    if has_kt:
        data = report._call(db, user, report._key("pl2_sellers", q), report.CACHE_TTL_S, lambda c: _fetch(c, lines, q))
        for line, found in zip(lines, data, strict=True):
            for r in found:
                name = str(r.get("seller_name") or "").strip() or NO_SELLER
                s = sold.setdefault(name.lower(), {"name": name, "quantity": 0, "kt": 0.0})
                pcs = int(r.get("total_quantity") or 0)
                s["quantity"] += pcs
                s["kt"] += pcs * line["rate"]

    # plan and CF are per seller across all stores and teams: filters that cut across them leave both out
    teams = q.lists.get("teams") or []
    narrowed = (any(q.lists.get(f) for f in ("shops", "designers")) or bool(q.texts.get("keyword"))
                or (bool(teams) and set(teams) != set(rt.default_teams)))
    plan = {"error": FILTERED} if narrowed else _plan_table(db, list(options.values()))
    cf = {"error": FILTERED} if narrowed else seller_cf.table(db)
    plan_rows: dict[str, dict[str, Any]] = plan["table"]["sellers"] if "table" in plan else {}
    cf_rows: dict[str, dict[str, Any]] = cf.get("sellers", {})
    planned: list[int] = plan["table"]["months"] if "table" in plan else []

    def key_of(name: str) -> str:
        """The key a trackingis seller shares with the sheet rows of their first name (plan first, then CF)."""
        for sheet_rows in (plan_rows, cf_rows):
            row = seller_plan.match(sheet_rows, name) if sheet_rows else None
            if row is not None:
                return seller_plan.name_key(row["name"])
        return seller_plan.name_key(name) or name.lower()

    def blank(name: str, in_plan: bool, plan_to_date: float | None = None) -> dict[str, Any]:
        return {"name": name, "sellers": [], "in_plan": in_plan, "quantity": 0, "kt": 0.0 if has_kt else None, "plan": plan_to_date, "cf": None}

    rows: dict[str, dict[str, Any]] = {key: blank(row["name"], True, _plan_to_date(row["pl2"], months, planned)) for key, row in plan_rows.items()}
    for s in sold.values():
        r = rows.setdefault(key_of(s["name"]), blank(s["name"], False))
        r["sellers"].append(s["name"])
        r["quantity"] += s["quantity"]
        if has_kt:
            r["kt"] += s["kt"]
    for key, row in cf_rows.items():
        # finance's rows: the months the range touches count whole
        rows.setdefault(key, blank(row["name"], False))["cf"] = sum(v for m, v in row["actual"].items() if m in months)

    picked = {key_of(options.get(s, s)) for s in q.lists.get("sellers", [])}  # empty = every seller
    shown = [(k, r) for k, r in rows.items() if not picked or k in picked]
    first = [r for _, r in shown if r["in_plan"]]  # the plan's sellers in sheet order, then the others by the size of their PL2
    rest = sorted((r for _, r in shown if not r["in_plan"] and (round(r["kt"] or 0, 2) or round(r["cf"] or 0, 2))),
                  key=lambda r: -abs(r["cf"] or r["kt"] or 0))
    has_plan = any(r["plan"] is not None for r in first)
    out = [_line(r["name"], r["sellers"], r["in_plan"], r["quantity"], r["plan"], r["kt"], r["cf"],
                 (r["plan"] if r["in_plan"] else 0.0) if has_plan else None) for r in [*first, *rest]]

    def add(field: str) -> float | None:
        values = [r[field] for r in out if r[field] is not None]
        return round(sum(values), 2) if values else None

    total_plan = add("plan")
    total = _line("All sellers", [], False, sum(r["quantity"] for r in out), total_plan, add("kt"), add("cf"), total_plan if has_plan else None)
    plan_info = plan if "error" in plan else {
        "sheet": plan["sheet"], "months": [f"T{m}" for m in planned], "missing": [m for m in months if int(m[:2]) not in planned]}
    cf_info = cf if "error" in cf else {
        "sheets": [family_plan.sheet_info(s) for s in cf["sources"]],
        "months": sorted({m for row in cf_rows.values() for m in row["actual"]}, key=lambda m: (m[3:], m[:2])),
        "missing": [m for m in months if not any(m in row["actual"] for row in cf_rows.values())]}
    return {"sellers": out, "total": total, "kt": kt_info, "plan": plan_info, "cf": cf_info,
            "query": {"date_from": q.date_from, "date_to": q.date_to, "teams": q.lists["teams"]}}
