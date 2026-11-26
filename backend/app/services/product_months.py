"""Etsy › Report, PL2 per product and month: for each product of the business plan (Etsy › Plan, KHKD "KH theo Product"), its PL2
theo KT (quantity sold × the plan's PL2 per item; Other products at theirs from Settings › Plan) next to its PL2 plan, month by
month, for the product cards of Etsy › Report.

Plan: the sheet's PL2 of each month (a seller filter of an admin, or a seller's own report, scales it by the seller's share of the
month: seller_plan), each month pro rata of the report's days (the plan to date, "KH lũy kế"); the plan of the quarter ("KH quý")
adds up the months of the sheet. The plan is for ZenE as a whole, so it compares with the team-wide view only: with a team, store,
designer or keyword filter there are no products here (the reason is in `plan.error`). Pieces the families add by hand (Felt
Ornament) count, as in "Sales by product vs plan". The trackingis query is made once per month the range touches (the range
clipped to that month), so a month's KT is what trackingis says for those days and the months add up to the range. Each month of
a product: {month, plan, plan_to_date, quantity, kt}; a month the range does not touch has only its plan.

`product_types` opens a product: its product types (the team's grouping on its page: Ornament → Acrylic + Wood, Shell…) and sub
product types with pieces and PL2 KT per month, asked when a card is opened.

`product_accounts` opens it the other way, per account: the stores that sold the product (a suspended store counts as its
replacement, Settings › Plan) with pieces and PL2 KT per month, biggest first; the pieces added by hand belong to no account and
are a line of their own, so the lines add up to the product's card.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import User
from app.services import family_accounts, family_plan, family_report, overview, plan, report, seller_plan, settings_store
from app.services.pl2_accounts import _key
from app.services.pl2_sellers import _children, _fetch_types, _node, _spans
from app.services.trackingis import ReportQuery, TrackingisClient, TrackingisError


def _fetch(client: TrackingisClient, lines: list[dict[str, Any]], q: ReportQuery) -> dict[str, list[dict[str, Any]]]:
    """Month → the totals of each priced product (its sub product types only) for the range's days of that month, in parallel."""
    spans = _spans(q)
    with ThreadPoolExecutor(max_workers=family_report.WORKERS) as pool:
        futures = {(month, i): pool.submit(client.totals, family_report._only(replace(q, date_from=a, date_to=b), tuple(line["sub_types"])))
                   for month, a, b in spans for i, line in enumerate(lines)}
        try:
            return {month: [futures[(month, i)].result() for i in range(len(lines))] for month, _, _ in spans}
        except TrackingisError:
            pool.shutdown(cancel_futures=True)  # a refused token fails every query: don't send the ones still queued
            raise


def _r2(v: float | None) -> float | None:
    return None if v is None else round(v, 2)


def product_months(db: Session, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    """{products: [{name, page, in_plan, quantity, kt, plan, plan_total, kt_pct, months: [{month, plan, plan_to_date, quantity,
    kt}]}], total, plan, query}; plan = PL2 plan to date ($), plan_total = the sheet's months added up (KH quý), kt_pct = kt / plan.
    `plan` is {sheet, months, missing, scope} or {error}, and then there are no products."""
    q = report.build_query(db, {**params, "view": "date"}, user)
    query = {"date_from": q.date_from, "date_to": q.date_to, "teams": q.lists["teams"]}
    info = overview._plan(db, q, user)
    if "error" in info:
        return {"products": [], "total": None, "plan": {"error": info["error"]}, "query": query}
    lines = overview.priced_products(db, user)
    if not lines:
        return {"products": [], "total": None, "plan": {"error": "No plan with PL2/item to estimate from: an admin picks the plan sheet in Settings → Plan"},
                "query": query}

    sheet_plan = plan.by_product(db)
    sheet_months: list[str] = list(sheet_plan["months"])
    pl2 = {p["product"].lower(): p["pl2"] for p in sheet_plan["products"]}  # the plan's PL2 of each product, per month of the sheet
    seller = seller_plan.shares(db, q, user) if seller_plan.applies(q, user) else None
    factors = seller["factors"] if seller and "factors" in seller else None  # a seller: their share of each month
    touched = family_plan.month_days(q.date_from, q.date_to)
    keys = sorted({*sheet_months, *touched}, key=lambda m: (m[3:], m[:2]))

    data = report._call(db, user, report._key("product_months", q), report.CACHE_TTL_S, lambda c: _fetch(c, lines, q))
    fixes = {month: overview._fixes(db, replace(q, date_from=a, date_to=b)) for month, a, b in _spans(q)}  # pieces added by hand

    def month_plan(name: str, month: str) -> float | None:
        values = pl2.get(name.lower())
        factor = 1.0 if factors is None else factors.get(month)
        if values is None or month not in sheet_months or factor is None:
            return None
        return (values[sheet_months.index(month)] or 0.0) * factor

    products = []
    for i, line in enumerate(lines):
        in_plan = line["name"].lower() in pl2
        months = []
        for key in keys:
            planned = month_plan(line["name"], key) if in_plan else None
            days, length = touched.get(key, (0, 1))
            pcs = None
            if key in touched:
                pcs = int(data[key][i].get("total_quantity") or 0) + sum(fixes[key].get(s, 0) for s in line["sub_types"])
            months.append({"month": key, "plan": planned, "plan_to_date": planned * days / length if key in touched and planned is not None else None,
                           "quantity": pcs, "kt": None if pcs is None else pcs * line["rate"]})
        products.append({"name": line["name"], "page": line.get("page"), "in_plan": in_plan, "months": months})

    def totals(rows: list[dict[str, Any]], field: str) -> float | None:
        values = [m[field] for r in rows for m in r["months"] if m[field] is not None]
        return sum(values) if values else None

    def finish(name: str, page: str | None, in_plan: bool, rows: list[dict[str, Any]], months: list[dict[str, Any]]) -> dict[str, Any]:
        quantity, kt = totals(rows, "quantity") or 0, totals(rows, "kt") or 0.0
        plan_total, plan_to_date = totals(rows, "plan"), totals(rows, "plan_to_date")
        return {"name": name, "page": page, "in_plan": in_plan, "quantity": int(quantity), "kt": round(kt, 2), "plan": _r2(plan_to_date),
                "plan_total": _r2(plan_total), "kt_pct": round(kt / plan_to_date, 4) if plan_to_date else None,
                "months": [{**m, **{f: _r2(m[f]) for f in ("plan", "plan_to_date", "kt")}} for m in months]}

    def month_sum(key: str, field: str) -> float | None:
        values = [m[field] for p in products for m in p["months"] if m["month"] == key and m[field] is not None]
        return sum(values) if values else None

    rows = [finish(p["name"], p["page"], p["in_plan"], [p], p["months"]) for p in products]
    summed = [{"month": k, **{f: month_sum(k, f) for f in ("plan", "plan_to_date", "quantity", "kt")}} for k in keys]
    total = finish("All products", None, False, [{"months": summed}], summed)
    scope = {"scope": seller["label"]} if seller and "label" in seller else {"scope": info.get("scope", "ZenE")}
    return {"products": rows, "total": total, "plan": {"sheet": info["sheet"], "months": sheet_months, "missing": info["missing_months"], **scope},
            "query": query}


def product_types(db: Session, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    """{name, children: [{name, quantity, kt, months: {MM-YYYY: {quantity, kt}}, children?}], months}: the product `product` of the
    plan opened onto its product types and sub product types, for the report's filters; the pieces added by hand count."""
    q = report.build_query(db, {**params, "view": "date"}, user)
    name = str(params.get("product") or "").strip()
    line = next((p for p in overview.priced_products(db, user) if p["name"].lower() == name.lower()), None)
    if line is None:
        raise AppError(404, "PRODUCT_NOT_FOUND", f'No product "{name}" in the plan')
    data = report._call(db, user, report._key(f"product_types:{line['name']}", q), report.CACHE_TTL_S,
                        lambda c: _fetch_types(c, q, tuple(line["sub_types"])))
    sold: dict[str, dict[str, int]] = {}
    for month, rows in data.items():
        for r in rows:
            sub = str(r.get("product_type") or "").strip().lower()
            sold.setdefault(sub, {})[month] = sold.get(sub, {}).get(month, 0) + int(r.get("total_quantity") or 0)
    wanted = {s.lower() for s in line["sub_types"]}
    for month, a, b in _spans(q):  # pieces the families add by hand (Felt Ornament): in a product's pieces, so in its tree too
        for sub, pcs in overview._fixes(db, replace(q, date_from=a, date_to=b)).items():
            if sub.lower() in wanted:
                sold.setdefault(sub.lower(), {})[month] = sold.get(sub.lower(), {}).get(month, 0) + pcs
    return {"name": line["name"], "children": _children(line, sold), "months": list(family_plan.month_days(q.date_from, q.date_to))}


HAND = "Added by hand (no account)"


def _fetch_stores(client: TrackingisClient, q: ReportQuery, subs: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
    """Month → the store view of the `subs` sub product types for the range's days of that month, in parallel."""
    spans = _spans(q)
    with ThreadPoolExecutor(max_workers=family_report.WORKERS) as pool:
        futures = {month: pool.submit(family_accounts._stores, client, family_report._only(replace(q, date_from=a, date_to=b), subs))
                   for month, a, b in spans}
        try:
            return {month: futures[month].result() for month, _, _ in spans}
        except TrackingisError:
            pool.shutdown(cancel_futures=True)
            raise


def product_accounts(db: Session, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    """{name, children: [{name, quantity, kt, months: {MM-YYYY: {quantity, kt}}}], count, months}: the product `product` of the plan per
    account (the report's filters apply: a seller's own report lists their accounts), biggest PL2 KT first, then the pieces added
    by hand (Felt Ornament) that no account has."""
    q = report.build_query(db, {**params, "view": "date"}, user)
    name = str(params.get("product") or "").strip()
    line = next((p for p in overview.priced_products(db, user) if p["name"].lower() == name.lower()), None)
    if line is None:
        raise AppError(404, "PRODUCT_NOT_FOUND", f'No product "{name}" in the plan')
    to = {_key(old): new.strip() for old, new in settings_store.runtime(db).account_replacements}
    subs = tuple(line["sub_types"])
    data = report._call(db, user, report._key(f"product_accounts:{line['name']}", q), report.CACHE_TTL_S, lambda c: _fetch_stores(c, q, subs))

    sold: dict[str, dict[str, Any]] = {}  # account → {name, months: {month: pieces}}
    for month, rows in data.items():
        for r in rows:
            pcs = int(r.get("total_quantity") or 0)
            if not pcs:
                continue
            shop = to.get(_key(r.get("shop_name"))) or str(r.get("shop_name") or "").strip() or "(no store name)"  # a suspended store: its replacement
            account = sold.setdefault(_key(shop), {"name": shop, "months": {}})
            account["months"][month] = account["months"].get(month, 0) + pcs
    nodes = [_node(a["name"], ["_"], {"_": a["months"]}, line["rate"]) for a in sold.values()]
    nodes.sort(key=lambda n: (-n["kt"], n["name"].lower()))

    wanted = {s.lower() for s in subs}
    by_hand: dict[str, int] = {}
    for month, a, b in _spans(q):
        pcs = sum(v for sub, v in overview._fixes(db, replace(q, date_from=a, date_to=b)).items() if sub.lower() in wanted)
        if pcs:
            by_hand[month] = pcs
    if by_hand:
        nodes.append(_node(HAND, ["_"], {"_": by_hand}, line["rate"]))
    return {"name": line["name"], "children": nodes, "count": len(sold), "months": list(family_plan.month_days(q.date_from, q.date_to))}
