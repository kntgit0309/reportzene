"""Etsy › Report, PL2 per seller: for each seller, PL2 theo KT (their quantity of each plan product × that product's PL2 per
item; Other products at theirs from Settings › Plan) next to their PL2 plan to date and finance's PL2 theo CF ("Profit tính KPI").

Plan: the seller plan sheet (Settings › Plan, "KH quý 4.2026 theo seller": PL2 T10 | T11 | T12 in dollars per seller), each
month pro rata of the report's days, as everywhere else. CF: the "1.2 P&L Seller (Sau IP)_Monthly" tabs (Settings › Plan ›
Seller CF sheets), booked per month, so a range counts the whole months it touches. Both sheets name sellers by first name
("Linh"), trackingis by account ("Linh PT.ETS"): they are matched as in seller_plan (`match`), and two trackingis sellers
that fall on one sheet row are one row here. The sellers of the plan sheet come first, in sheet order; sellers outside it
are listed after them when they have a PL2 (KT or CF not 0), and their whole PL2 counts as gap against a plan of $0.
While the seller plan sheet cannot be read (not picked, or no "PL2 T10" label row in its snapshot) the built-in copy of the Q4
plan (seller_plan.BUILT_IN) stands in for it, and the response says why; the sheet is used again as soon as it can be read.

Plan and CF are per seller across all stores and teams: a store, team, designer or keyword filter narrows the KT only, so they
are left out then. A seller filter keeps those sellers' rows (a member limited to their own sales gets only theirs). Pieces
added by hand (Felt) are not tied to a seller, so they are not in KT here.

Each row also carries `plan_total` (the plan's months added up: "KH quý") and `months`, the seller's PL2 per month for the
seller cards of Etsy › Report: a month's whole plan, its plan to date, KT and CF; a month the report's range does not touch has
only its plan. The seller view is asked once per month the range touches (the range clipped to that month), so a month's KT is
what trackingis says for those days, and the months add up to the range. `products` is the same per product of the plan (Other
products last): the seller's pieces and PL2 KT in all and per month, for the dialog of a seller card.

`pl2_seller_types` opens a product of that dialog: for the sellers asked (a card's `seller_ids`), its product types (the team's
grouping on the product's page: Ornament → Acrylic + Wood, Shell, Shaker…) and sub product types, with the same pieces and PL2 KT
per month. It is asked when a seller card is opened: one trackingis query per month the range touches.
"""
import calendar
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import User
from app.services import family_accounts, family_plan, family_report, overview, report, seller_cf, seller_plan, settings_store
from app.services.families import FAMILIES
from app.services.pl2_accounts import _sheet
from app.services.trackingis import ReportQuery, TrackingisClient, TrackingisError

NO_SELLER = "(no seller)"
FILTERED = "PL2 plan and CF are per seller across all stores: clear the store, team, designer and keyword filters to compare with them"


def _spans(q: ReportQuery) -> list[tuple[str, str, str]]:
    """(MM-YYYY, from, to) of each month the range touches, the range clipped to that month."""
    start, end = date.fromisoformat(q.date_from), date.fromisoformat(q.date_to)
    out = []
    for month in family_plan.month_days(q.date_from, q.date_to):
        first = date(int(month[3:]), int(month[:2]), 1)
        last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
        out.append((month, max(start, first).isoformat(), min(end, last).isoformat()))
    return out


def _fetch(client: TrackingisClient, lines: list[dict[str, Any]], q: ReportQuery) -> dict[str, list[list[dict[str, Any]]]]:
    """Month → the seller view of each priced product (its sub product types only) for the range's days of that month, in parallel."""
    with ThreadPoolExecutor(max_workers=family_report.WORKERS) as pool:
        futures = {(month, i): pool.submit(family_accounts._stores, client, family_report._only(replace(q, date_from=a, date_to=b),
                                                                                              tuple(line["sub_types"])), "seller")
                   for month, a, b in _spans(q) for i, line in enumerate(lines)}
        try:
            return {month: [futures[(month, i)].result() for i in range(len(lines))] for month, _, _ in _spans(q)}
        except TrackingisError:
            pool.shutdown(cancel_futures=True)  # a refused token fails every query: don't send the ones still queued
            raise


def _fetch_types(client: TrackingisClient, q: ReportQuery, every: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
    """Month → the product type view (a row per sub product type) of the `every` sub types, for the range's days of that month."""
    spans = _spans(q)
    with ThreadPoolExecutor(max_workers=family_report.WORKERS) as pool:
        futures = {month: pool.submit(family_report._product_types, client, family_report._only(replace(q, date_from=a, date_to=b), every))
                   for month, a, b in spans}
        try:
            return {month: futures[month].result() for month, _, _ in spans}
        except TrackingisError:
            pool.shutdown(cancel_futures=True)
            raise


def _node(name: str, subs: list[str], sold: dict[str, dict[str, int]], rate: float, children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """One line of the tree: pieces and PL2 KT of these sub types (`sold`: sub type lower case → month → pieces) at `rate`."""
    months: dict[str, dict[str, Any]] = {}
    for sub in subs:
        for month, pcs in sold.get(sub.lower(), {}).items():
            m = months.setdefault(month, {"quantity": 0, "kt": 0.0})
            m["quantity"] += pcs
            m["kt"] += pcs * rate
    out: dict[str, Any] = {"name": name, "quantity": sum(m["quantity"] for m in months.values()),
                           "kt": round(sum(m["kt"] for m in months.values()), 2),
                           "months": {k: {"quantity": m["quantity"], "kt": round(m["kt"], 2)} for k, m in months.items()}}
    if children:
        out["children"] = children
    return out


def _children(line: dict[str, Any], sold: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    """What a product opens onto: its product types when its page groups them (Ornament, Blanket, Quilted), each onto its sub
    product types; else its sub product types. Sub product types without sales are left out, product types are not."""
    rate = line["rate"]

    def leaves(subs: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
        return [n for n in (_node(s, [s], sold, rate) for s in subs) if n["quantity"]]

    family = FAMILIES.get(line.get("page") or "")
    if family is not None and family.name.lower() == line["name"].lower() and len(family.groups) > 1:
        out = []
        for group, subs in family.groups:
            own = [] if len(subs) == 1 and subs[0].lower() == group.lower() else leaves(subs)  # a type that is one sub type of its name
            out.append(_node(group, list(subs), sold, rate, own))
        return out
    if len(line["sub_types"]) == 1 and line["sub_types"][0].lower() == line["name"].lower():
        return []
    return leaves(line["sub_types"])


def pl2_seller_types(db: Session, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    """{products: [{name, children: [{name, quantity, kt, months: {MM-YYYY: {quantity, kt}}, children?}]}], months, query}: the
    pieces and PL2 KT of the sellers the report is filtered by (`sellers`, ids; a limited seller gets their own), per product
    of the plan, then per product type and sub product type, for the range's months."""
    q = report.build_query(db, {**params, "view": "date"}, user)
    lines = overview.priced_products(db, user)
    months = list(family_plan.month_days(q.date_from, q.date_to))
    query = {"date_from": q.date_from, "date_to": q.date_to, "sellers": q.lists.get("sellers", [])}
    if not lines:
        return {"products": [], "months": months, "query": query}
    every = tuple(dict.fromkeys(s for line in lines for s in line["sub_types"]))
    data = report._call(db, user, report._key("pl2_seller_types", q), report.CACHE_TTL_S, lambda c: _fetch_types(c, q, every))
    sold: dict[str, dict[str, int]] = {}
    for month, rows in data.items():
        for r in rows:
            name = str(r.get("product_type") or "").strip().lower()
            sold.setdefault(name, {})[month] = sold.get(name, {}).get(month, 0) + int(r.get("total_quantity") or 0)
    return {"products": [{"name": line["name"], "children": _children(line, sold)} for line in lines], "months": months, "query": query}


def _plan_table(db: Session, names: list[str]) -> dict[str, Any]:
    """{table, sheet} of the seller plan sheet (the table where most of `names` have a row); while the sheet cannot be read,
    {table, built_in: True, reason} with the built-in Q4 plan and why the sheet is not used."""
    got = _sheet(db, settings_store.runtime(db).seller_plan_sheet_id, "seller plan sheet")
    reason = got if isinstance(got, str) else ""
    if not reason:
        try:
            tables = seller_plan.parse(got.header or [], got.rows)
        except AppError as exc:
            reason = exc.message
    if reason:
        return {"table": seller_plan.built_in(), "built_in": True, "reason": reason}
    return {"table": seller_plan.best(tables, names)[0], "sheet": family_plan.sheet_info(got)}


def _plan_to_date(pl2: dict[int, float], months: dict[str, tuple[int, int]], planned: list[int]) -> float | None:
    """A seller's PL2 plan for the report's days (each month pro rata); None when the sheet plans none of the months."""
    got = [pl2.get(int(m[:2]), 0.0) * days / month_days for m, (days, month_days) in months.items() if int(m[:2]) in planned]
    return sum(got) if got else None


def _line(name: str, sellers: list[str], in_plan: bool, quantity: int, plan: float | None, kt: float | None, cf: float | None,
          against: float | None, plan_total: float | None = None, months: list[dict[str, Any]] | None = None,
          products: list[dict[str, Any]] | None = None, seller_ids: list[str] | None = None) -> dict[str, Any]:
    """One row. `against` is the plan the gaps are measured from (the plan, or $0 for a seller outside it; None = no plan at
    all): kt_gap = KT − against, cf_gap = CF − against; kt_pct / cf_pct = KT / CF as a share of the plan. plan_total = the
    plan's months added up (KH quý), months = the seller's PL2 per month, products = their pieces and KT per product (see the
    module's docstring)."""
    def diff(v: float | None) -> float | None:
        return None if v is None or against is None else round(v - against, 2)

    def ratio(v: float | None) -> float | None:
        return round(v / plan, 4) if v is not None and plan else None

    return {"seller": name, "sellers": sellers, "in_plan": in_plan, "quantity": quantity, "plan": None if plan is None else round(plan, 2),
            "plan_total": None if plan_total is None else round(plan_total, 2), "months": months or [], "products": products or [],
            "seller_ids": seller_ids or [],
            "kt": None if kt is None else round(kt, 2), "cf": None if cf is None else round(cf, 2),
            "kt_gap": diff(kt), "kt_pct": ratio(kt), "cf_gap": diff(cf), "cf_pct": ratio(cf),
            "cf_minus_kt": round(cf - kt, 2) if kt is not None and cf is not None else None}


def pl2_sellers(db: Session, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    """{sellers: [{seller, sellers, in_plan, quantity, plan, plan_total, months, kt, cf, kt_gap, kt_pct, cf_gap, cf_pct,
    cf_minus_kt, products, seller_ids}], total, kt,
    plan, cf, query}; plan = PL2 plan to date ($), kt_gap = kt − plan, cf_gap = cf − plan; kt / plan / cf = {"error"} when
    not available (a field of a row is then None); plan = {built_in: True, reason, months, missing} while the built-in copy of
    the Q4 plan stands in for the sheet, else {sheet, months, missing}."""
    q = report.build_query(db, {**params, "view": "date"}, user)
    rt = settings_store.runtime(db)
    options = {str(o["id"]): str(o["name"]) for o in report.filter_options(db, "sellers", user)}
    ids = {name.lower(): ident for ident, name in options.items()}  # trackingis seller name → id, to open a card's product types
    months = family_plan.month_days(q.date_from, q.date_to)

    lines = overview.priced_products(db, user)
    has_kt = bool(lines)
    kt_info: dict[str, Any] = {} if has_kt else {"error": "No plan with PL2/item to estimate from: an admin picks the plan sheet in Settings → Plan"}
    sold: dict[str, dict[str, Any]] = {}  # trackingis sellers of the report's filters: quantity and KT, in all and per month
    if has_kt:
        data = report._call(db, user, report._key("pl2_sellers", q), report.CACHE_TTL_S, lambda c: _fetch(c, lines, q))
        for month, per_line in data.items():
            for line, found in zip(lines, per_line, strict=True):
                for r in found:
                    name = str(r.get("seller_name") or "").strip() or NO_SELLER
                    s = sold.setdefault(name.lower(), {"name": name, "quantity": 0, "kt": 0.0, "months": {}, "products": {}})
                    pcs = int(r.get("total_quantity") or 0)
                    s["quantity"] += pcs
                    s["kt"] += pcs * line["rate"]
                    for into in (s["months"].setdefault(month, {"quantity": 0, "kt": 0.0}),
                                 s["products"].setdefault(line["name"], {}).setdefault(month, {"quantity": 0, "kt": 0.0})):
                        into["quantity"] += pcs
                        into["kt"] += pcs * line["rate"]

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

    def blank(name: str, in_plan: bool, plan_to_date: float | None = None, pl2: dict[int, float] | None = None) -> dict[str, Any]:
        return {"name": name, "sellers": [], "in_plan": in_plan, "quantity": 0, "kt": 0.0 if has_kt else None, "plan": plan_to_date, "cf": None,
                "pl2": pl2 or {}, "months": {}, "cf_months": {}, "products": {}}

    rows: dict[str, dict[str, Any]] = {key: blank(row["name"], True, _plan_to_date(row["pl2"], months, planned), row["pl2"])
                                       for key, row in plan_rows.items()}
    for s in sold.values():
        r = rows.setdefault(key_of(s["name"]), blank(s["name"], False))
        r["sellers"].append(s["name"])
        r["quantity"] += s["quantity"]
        if has_kt:
            r["kt"] += s["kt"]
            for month, m in s["months"].items():
                d = r["months"].setdefault(month, {"quantity": 0, "kt": 0.0})
                d["quantity"] += m["quantity"]
                d["kt"] += m["kt"]
            for name, by_month in s["products"].items():
                for month, m in by_month.items():
                    d = r["products"].setdefault(name, {}).setdefault(month, {"quantity": 0, "kt": 0.0})
                    d["quantity"] += m["quantity"]
                    d["kt"] += m["kt"]
    for key, row in cf_rows.items():
        # finance's rows: the months the range touches count whole
        r = rows.setdefault(key, blank(row["name"], False))
        r["cf_months"] = {m: v for m, v in row["actual"].items() if m in months}
        r["cf"] = sum(r["cf_months"].values())

    year_of = {int(k[:2]): k[3:] for k in months}  # the plan's months (T10…) are of the year the range has them in, else of its end

    def month_rows(r: dict[str, Any]) -> list[dict[str, Any]]:
        """The seller's PL2 per month, over the plan's months and those the range touches: the month's plan, its plan to date,
        KT, quantity and CF. A month the range does not touch has only its plan (the rest is None)."""
        out = []
        for key in sorted({f"{m:02d}-{year_of.get(m, q.date_to[:4])}" for m in planned} | set(months), key=lambda k: (k[3:], k[:2])):
            n, touched = int(key[:2]), key in months
            month_plan = r["pl2"].get(n, 0.0) if r["in_plan"] and n in planned else None
            days, length = months.get(key, (0, 1))
            sold_in = r["months"].get(key, {"quantity": 0, "kt": 0.0})
            out.append({"month": key, "plan": None if month_plan is None else round(month_plan, 2),
                        "plan_to_date": round(month_plan * days / length, 2) if touched and month_plan is not None else None,
                        "quantity": sold_in["quantity"] if touched and has_kt else None,
                        "kt": round(sold_in["kt"], 2) if touched and has_kt else None,
                        "cf": round(r["cf_months"].get(key, 0.0), 2) if touched and r["cf"] is not None else None})
        return out

    def product_rows(r: dict[str, Any]) -> list[dict[str, Any]]:
        """The seller's pieces and PL2 KT per product of the plan, in all and per month (a month without sales has no entry)."""
        out = []
        for line in lines:
            by_month = r["products"].get(line["name"], {})
            out.append({"name": line["name"], "quantity": sum(m["quantity"] for m in by_month.values()),
                        "kt": round(sum(m["kt"] for m in by_month.values()), 2),
                        "months": {k: {"quantity": m["quantity"], "kt": round(m["kt"], 2)} for k, m in by_month.items()}})
        return out

    picked = {key_of(options.get(s, s)) for s in q.lists.get("sellers", [])}  # empty = every seller
    shown = [(k, r) for k, r in rows.items() if not picked or k in picked]
    first = [r for _, r in shown if r["in_plan"]]  # the plan's sellers in sheet order, then the others by the size of their PL2
    rest = sorted((r for _, r in shown if not r["in_plan"] and (round(r["kt"] or 0, 2) or round(r["cf"] or 0, 2))),
                  key=lambda r: -abs(r["cf"] or r["kt"] or 0))
    has_plan = any(r["plan"] is not None for r in first)
    out = [_line(r["name"], r["sellers"], r["in_plan"], r["quantity"], r["plan"], r["kt"], r["cf"],
                 (r["plan"] if r["in_plan"] else 0.0) if has_plan else None,
                 sum(r["pl2"].get(m, 0.0) for m in planned) if r["in_plan"] and planned else None, month_rows(r),
                 product_rows(r) if has_kt else None, [ids[n.lower()] for n in r["sellers"] if n.lower() in ids]) for r in [*first, *rest]]

    def add(field: str) -> float | None:
        values = [r[field] for r in out if r[field] is not None]
        return round(sum(values), 2) if values else None

    total_plan = add("plan")
    total = _line("All sellers", [], False, sum(r["quantity"] for r in out), total_plan, add("kt"), add("cf"), total_plan if has_plan else None,
                  add("plan_total"))
    plan_info = plan if "error" in plan else {
        **({"built_in": True, "reason": plan["reason"]} if plan.get("built_in") else {"sheet": plan["sheet"]}),
        "months": [f"T{m}" for m in planned], "missing": [m for m in months if int(m[:2]) not in planned]}
    cf_info = cf if "error" in cf else {
        "sheets": [family_plan.sheet_info(s) for s in cf["sources"]],
        "months": sorted({m for row in cf_rows.values() for m in row["actual"]}, key=lambda m: (m[3:], m[:2])),
        "missing": [m for m in months if not any(m in row["actual"] for row in cf_rows.values())]}
    return {"sellers": out, "total": total, "kt": kt_info, "plan": plan_info, "cf": cf_info,
            "query": {"date_from": q.date_from, "date_to": q.date_to, "teams": q.lists["teams"]}}
