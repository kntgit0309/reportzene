"""Etsy › Report, sales by product vs plan: each product of the business plan (Etsy › Plan, KHKD "KH theo Product") with
its ZenE sales from trackingis, next to the plan's sales (pieces) and PL2.

A plan product is matched by name: a product family (Ornament, Shirt…: every sub product type of its page), a product type
of a family (Sticker, Scrub cap… of Others), or one of families.PLAN_PRODUCTS (Quilted: no page of its own yet). "Other
products" takes every trackingis sub product type none of them covers. Each row is one trackingis query on its sub product
types (the report's other filters kept), and the total is one query on all of them: an order holding several products counts
in each row, so the rows can add up to a little more. Quantity trackingis misses and a family adds by hand (Felt Ornament)
counts here too, in the team-wide view, as on its page. The plan is for ZenE as a whole, so it compares with the team-wide
view only. Estimated PL2 ("PL2 theo KT") = quantity sold × the plan's PL2 per item, for any filters; KHKD has no line for
Other products, so theirs is set in Settings › Plan ($7 per item unless changed).
"""
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import User
from app.services import family_plan, family_report, plan, report, settings_store
from app.services.families import FAMILIES, OTHERS, PLAN_PRODUCTS
from app.services.trackingis import ReportQuery, TrackingisClient, TrackingisError

REST = "Other products"
METRICS = ("total_order", "total_quantity", "total", "sale_tax", "total_revenue", "avg_order_value")


def _catalog() -> dict[str, tuple[str | None, tuple[str, ...]]]:
    """Product name (lower case) → (page key, sub product types): families first, then PLAN_PRODUCTS (no page; the plan's
    "Quilted" is the quilted goods, not Blanket's Quilted), then the product types of the families."""
    out: dict[str, tuple[str | None, tuple[str, ...]]] = {f.name.lower(): (f.key, f.sub_types) for f in FAMILIES.values()}
    for name, subs in PLAN_PRODUCTS.items():
        out.setdefault(name.lower(), (None, subs))
    for f in FAMILIES.values():
        for group, subs in f.groups if len(f.groups) > 1 else ():
            out.setdefault(group.lower(), (f.key, subs))
    return out


def _default_names() -> list[str]:
    """Every product with a page (Others as its product types) and PLAN_PRODUCTS: the rows when there is no plan, and the
    rows added after the plan's products for any of them the plan does not list."""
    names = [f.name for f in FAMILIES.values() if f is not OTHERS]
    return [*names, *PLAN_PRODUCTS, *(group for group, _ in OTHERS.groups)]


def products(names: list[str], all_sub_types: list[str]) -> list[dict[str, Any]]:
    """[{name, page, sub_types}]: the given products in order, then Other products (trackingis order) when any is left."""
    catalog = _catalog()
    out = [{"name": n, "page": catalog.get(n.lower(), (None, ()))[0], "sub_types": list(catalog.get(n.lower(), (None, ()))[1])}
           for n in names]
    listed = {s.lower() for f in FAMILIES.values() for s in f.sub_types} | {s.lower() for subs in PLAN_PRODUCTS.values() for s in subs}
    rest = [s for s in all_sub_types if s.lower() not in listed]
    if rest:
        out.append({"name": REST, "page": OTHERS.key, "sub_types": rest})
    return out


def _with_rest(db: Session, rates: dict[str, Any]) -> dict[str, Any]:
    """The plan's PL2 per item (product lower case → $), plus Other products' from Settings › Plan when the plan has none."""
    rate = settings_store.runtime(db).other_pl2_per_item
    return rates if rate is None or rates.get(REST.lower()) is not None else {**rates, REST.lower(): rate}


def priced_products(db: Session, user: User | None) -> list[dict[str, Any]]:
    """[{name, page, sub_types, rate}]: the plan's products with a PL2 per item and sub product types, the basis of PL2 theo KT;
    [] without a readable plan."""
    try:
        sheet_plan = plan.by_product(db)
    except AppError:
        return []
    rates = _with_rest(db, {p["product"].lower(): p["pl2_per_item"] for p in sheet_plan["products"]})
    lines = products([p["product"] for p in sheet_plan["products"]], [str(o["name"]) for o in report.filter_options(db, "sub_product_types", user)])
    return [{**line, "rate": rates[line["name"].lower()]} for line in lines if rates.get(line["name"].lower()) is not None and line["sub_types"]]


def _fetch(client: TrackingisClient, lines: list[dict[str, Any]], q: ReportQuery) -> dict[str, Any]:
    every = tuple(dict.fromkeys(s for line in lines for s in line["sub_types"]))
    with ThreadPoolExecutor(max_workers=family_report.WORKERS) as pool:
        total = pool.submit(client.totals, family_report._only(q, every))
        # a product without sub product types (a plan line nothing matches) sells nothing: no query, it would filter nothing
        rows = [pool.submit(client.totals, family_report._only(q, tuple(line["sub_types"]))) if line["sub_types"] else None
                for line in lines]
        try:
            return {"total": total.result(), "rows": [f.result() if f else None for f in rows]}
        except TrackingisError:
            pool.shutdown(cancel_futures=True)  # a refused token fails every query: don't send the ones still queued
            raise


def _plan(db: Session, q: ReportQuery) -> dict[str, Any]:
    """{sheet, months, missing_months, scope, products: {name lower: {plan, plan_month, pl2_per_item, pl2_plan}}, names,
    per_item} for the report's range, or {"error"} when there is no plan or the filters narrow the report below ZenE (then
    still with names and per_item: PL2 per item applies to any part of the sales)."""
    try:
        sheet_plan = plan.by_product(db)
    except AppError as exc:
        return {"error": exc.message}
    names = [p["product"] for p in sheet_plan["products"]]
    per_item = {p["product"].lower(): p["pl2_per_item"] for p in sheet_plan["products"]}
    teams = q.lists.get("teams") or []
    if (any(q.lists.get(f) for f in ("shops", "sellers", "designers")) or q.texts.get("keyword")
            or (teams and set(teams) != set(settings_store.runtime(db).default_teams))):
        return {"error": f'"{sheet_plan["sheet"]["name"]}" plans per product for ZenE as a whole: clear the team, store, seller, '
                         f'designer and keyword filters to compare with it', "names": names, "per_item": per_item}
    days = family_plan.month_days(q.date_from, q.date_to)
    index = {m: i for i, m in enumerate(sheet_plan["months"])}
    covered = [{"month": m, "days": d, "month_days": md} for m, (d, md) in days.items() if m in index]
    out: dict[str, dict[str, Any]] = {}
    for p in sheet_plan["products"]:
        sales, pl2 = p["sales"], p["pl2"]
        pcs = sum((sales[index[c["month"]]] or 0) * c["days"] / c["month_days"] for c in covered)
        profit = sum((pl2[index[c["month"]]] or 0) * c["days"] / c["month_days"] for c in covered)
        out[p["product"].lower()] = {"plan": pcs, "plan_month": sum(sales[index[c["month"]]] or 0 for c in covered),
                                     "pl2_per_item": p["pl2_per_item"], "pl2_plan": profit}
    return {"sheet": sheet_plan["sheet"], "months": covered, "missing_months": [m for m in days if m not in index], "scope": "ZenE",
            "products": out, "names": names, "per_item": per_item}


def _metrics(totals: dict[str, Any] | None) -> dict[str, Any]:
    return {f: (totals or {}).get(f) or 0 for f in METRICS}


def _fixes(db: Session, q: ReportQuery) -> dict[str, int]:
    """Sub product type → pieces the families add by hand in the range (Family.quantity_fixes), team-wide view only."""
    if not family_report._fixes_apply(db, q):
        return {}
    out = {s: sum(n for day, n in by_day.items() if q.date_from <= day <= q.date_to)
           for f in FAMILIES.values() for s, by_day in f.quantity_fixes.items()}
    return {s: n for s, n in out.items() if n}


def _with_fix(sold: dict[str, Any], pcs: int) -> dict[str, Any]:
    return {**sold, "total_quantity": sold["total_quantity"] + pcs, "fix_quantity": pcs} if pcs else sold


def overview(db: Session, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    """{rows: [{name, page, sub_types, …metrics, share, plan, plan_month, achieved, pl2_per_item, pl2_plan, pl2_est}], total,
    plan, query}. Rows follow the plan's products, then Other products; plan fields are absent when the plan does not compare
    (no plan, or filters below ZenE); pl2_per_item / pl2_est are absent only when there is no plan sheet to read."""
    q = report.build_query(db, {**params, "view": "date"}, user)
    plan_info = _plan(db, q)
    names = plan_info.pop("names", [])
    names += [n for n in _default_names() if n.lower() not in {x.lower() for x in names}]  # a page the plan does not list
    by_name = plan_info.pop("products", {})
    per_item = plan_info.pop("per_item", {})
    if per_item:  # with a plan, Other products count at their PL2 per item too
        per_item = _with_rest(db, per_item)
    lines = products(names, [str(o["name"]) for o in report.filter_options(db, "sub_product_types", user)])
    data = report._call(db, user, report._key("overview", q), report.CACHE_TTL_S, lambda c: _fetch(c, lines, q))

    fixes = _fixes(db, q)
    total = _with_fix(_metrics(data["total"]), sum(fixes.values()))
    rows = []
    for line, got in zip(lines, data["rows"], strict=True):
        sold = _with_fix(_metrics(got), sum(fixes.get(s, 0) for s in line["sub_types"]))
        row = {**line, **sold, "share": round(sold["total_revenue"] / total["total_revenue"], 4) if total["total_revenue"] else None}
        if per_item:
            rate = per_item.get(line["name"].lower())
            row |= {"pl2_per_item": rate, "pl2_est": round(row["total_quantity"] * rate, 2) if rate is not None else None}
        if "error" not in plan_info:
            p = by_name.get(line["name"].lower())
            row |= {"plan": round(p["plan"], 1) if p else None, "plan_month": round(p["plan_month"]) if p else None,
                    "achieved": round(row["total_quantity"] / p["plan"], 4) if p and p["plan"] else None,
                    "pl2_plan": round(p["pl2_plan"], 2) if p else None}
        rows.append(row)
    if per_item:
        total["pl2_est"] = round(sum(r["pl2_est"] or 0 for r in rows), 2)
    if "error" not in plan_info:
        planned = list(by_name.values())
        plan_pcs = sum(p["plan"] for p in planned)
        total |= {"plan": round(plan_pcs, 1), "plan_month": round(sum(p["plan_month"] for p in planned)),
                  "achieved": round(total["total_quantity"] / plan_pcs, 4) if plan_pcs else None,
                  "pl2_plan": round(sum(p["pl2_plan"] for p in planned), 2)}
    return {"rows": rows, "total": total, "plan": plan_info,
            "query": {"date_from": q.date_from, "date_to": q.date_to, "teams": q.lists["teams"]}}
