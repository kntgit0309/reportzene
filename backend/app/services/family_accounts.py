"""Etsy › Ornament / Shirt by account: each store's sales of the family (trackingis) next to its line of the family's plan.

Actual: the trackingis store view filtered on every sub product type of the family, and once per product type for the
breakdown — per sub product type when the family is a single product type (run in parallel, cached like the report).
Plan: the shop rows of the plan sheet, matched by store name. A suspended store listed in Settings › Plan hands its plan
line and its sales to its replacement. Pieces added by hand (Family.quantity_fixes) are not tied to a store, so they are
not in these rows.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.services import family_plan, family_report, report, settings_store
from app.services.families import Family
from app.services.trackingis import MAX_PER_PAGE, ReportQuery, TrackingisClient, TrackingisError

MAX_PAGES = 5  # 200 stores per page
METRICS = ("total_order", "total_quantity", "total", "sale_tax", "total_revenue")


def _stores(client: TrackingisClient, q: ReportQuery) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        got = client.report(replace(q, view="store", page=page, per_page=MAX_PER_PAGE, sort_by="total_revenue", sort_order="desc"))
        rows += got["rows"]
        if page >= int(got["paging"].get("last_page") or 1):
            break
    return rows


def _parts(family: Family) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """What a store opens onto: its product types, or its sub product types when the family is a single product type."""
    return family.groups if len(family.groups) > 1 else tuple((s, (s,)) for s in family.sub_types)


def _fetch(client: TrackingisClient, family: Family, q: ReportQuery) -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=family_report.WORKERS) as pool:
        every = pool.submit(_stores, client, family_report._only(q, family.sub_types))
        groups = {name: pool.submit(_stores, client, family_report._only(q, subs)) for name, subs in _parts(family)}
        try:
            return {"all": every.result(), "groups": {name: f.result() for name, f in groups.items()}}
        except TrackingisError:
            pool.shutdown(cancel_futures=True)  # a refused token fails every query: don't send the ones still queued
            raise


def _key(name: Any) -> str:
    return str(name or "").strip().lower()


def _by_store(rows: list[dict[str, Any]], to: dict[str, str]) -> dict[str, dict[str, Any]]:
    """trackingis store rows keyed by store name; a suspended store's sales are added to its replacement (Settings › Plan)."""
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        name = to.get(_key(r.get("shop_name"))) or str(r.get("shop_name") or "")
        merged = out.setdefault(_key(name), {"shop_name": name, **dict.fromkeys(METRICS, 0.0)})
        for f in METRICS:
            merged[f] += float(r.get(f) or 0)
    return out


def _metrics(row: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {f: float((row or {}).get(f) or 0) for f in METRICS}
    out["total_order"], out["total_quantity"] = int(out["total_order"]), int(out["total_quantity"])
    out["total_revenue"] = round(out["total_revenue"], 2)
    out["avg_order_value"] = round(out["total_revenue"] / out["total_order"], 2) if out["total_order"] else 0.0
    return out


def _with_plan(line: dict[str, Any], plan: dict[str, float] | None) -> dict[str, Any]:
    if plan is None:
        return {**line, "plan": None, "plan_month": None, "achieved": None}
    p = round(plan["plan"], 1)
    return {**line, "plan": p, "plan_month": round(plan["plan_month"]), "achieved": round(line["total_quantity"] / p, 4) if p else None}


def _sum_plan(shop_plans: list[dict[str, Any]]) -> dict[str, float]:
    groups = [g for p in shop_plans for g in p["groups"].values()]
    return {"plan": sum(g["plan"] for g in groups), "plan_month": sum(g["plan_month"] for g in groups)}


def accounts_report(db: Session, family: Family, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    """{accounts: [{shop, team, in_plan, …metrics, plan, plan_month, achieved, children: [product type lines]}], total, plan,
    query}. Stores of the plan come first in sheet order, then stores with sales of the family but no plan line. Children
    are sub product types, without a plan, when the family is a single product type."""
    family = family_report.resolve(db, family, user)
    q = report.build_query(db, {**params, "view": "date"})
    data = report._call(db, user, report._key(f"{family.key}_accounts", q), report.CACHE_TTL_S, lambda c: _fetch(c, family, q))
    replacements = settings_store.runtime(db).account_replacements
    to = {_key(old): new.strip() for old, new in replacements}
    actual = _by_store(data["all"], to)
    by_part = {name: _by_store(rows, to) for name, rows in data["groups"].items()}

    s = family_plan.scope(db, family, q, user)
    plans: list[dict[str, Any]] = []
    plan_info: dict[str, Any] = {"error": s["error"]} if "error" in s else {}
    if not plan_info and not s["parsed"]["per_store"]:
        plan_info = {"error": f'"{s["source"].name}" plans per product for ZenE as a whole, not per store: '
                              f'the product type table above compares with it'}
    if not plan_info:
        per_shop = family_plan.shop_plans(s["parsed"], q.date_from, q.date_to, s["teams"], s["shops"])
        plans = per_shop["shops"]
        plan_info = {"sheet": family_plan.sheet_info(s["source"]), "scope": s["label"], "months": per_shop["months"],
                     "missing_months": per_shop["missing_months"]}
    has_plan = "error" not in plan_info
    by_group = len(family.groups) > 1  # children are the plan's product types, so they carry their part of the plan

    planned = {_key(p["shop"]): p for p in plans}
    others = sorted((k for k in actual if k not in planned), key=lambda k: -float(actual[k].get("total_revenue") or 0))
    accounts = []
    for key in [*planned, *others]:
        p = planned.get(key)
        name = p["shop"] if p else str(actual[key].get("shop_name") or key)
        children = []
        for part, _subs in _parts(family):
            row = by_part[part].get(key)
            gp = p["groups"].get(part) if p and has_plan and by_group else None
            if row is None and not (gp and gp["plan_month"]):
                continue
            line = {"name": part, **_metrics(row)}
            children.append(_with_plan(line, gp or ({"plan": 0.0, "plan_month": 0.0} if p else None)) if has_plan and by_group else line)
        line = {"shop": name, "team": p["team"] if p else None, "in_plan": p is not None, **_metrics(actual.get(key)),
                "replaces": [old for old, new in replacements if _key(new) == key], "children": children}
        accounts.append(_with_plan(line, _sum_plan([p]) if p else None) if has_plan else line)

    total = _metrics({f: sum(a[f] for a in accounts) for f in METRICS})
    if has_plan:  # from the unrounded shop plans, so it is the same as the product type table's total
        total = _with_plan(total, _sum_plan(plans))
    return {"accounts": accounts, "total": total, "plan": plan_info,
            "query": {"date_from": q.date_from, "date_to": q.date_to, "teams": q.lists["teams"]}}
