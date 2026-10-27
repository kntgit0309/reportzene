"""Etsy › Ornament, Shirt…: ZenE sales of a product family per product type, the team's own grouping of trackingis sub
product types (app.services.families).

Each product type and each sub product type is one trackingis query filtered on its sub product types (same date / store /
seller / team filters as the report), run in parallel. An order holding several types of the family counts in each of them,
so the overall total is its own query rather than the sum of the rows. The rest group of Others (every sub product type no
family lists, dozens of them) opens onto trackingis product types instead: one product type view query.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.services import families, family_plan, family_pl2, report, settings_store
from app.services.families import Family
from app.services.trackingis import MAX_PER_PAGE, ReportQuery, TrackingisClient, TrackingisError, summarize

WORKERS = 8
DAY_FIELDS = ("date_at", "total_order", "total_quantity", "total_revenue")


def _only(q: ReportQuery, subs: tuple[str, ...]) -> ReportQuery:
    """The same filters, restricted to these sub product types (the page's own product type filters are ignored)."""
    return replace(q, view="date", page=1, lists={**q.lists, "product_types": [], "sub_product_types": list(subs)})


def resolve(db: Session, family: Family, user: User | None) -> Family:
    """The family as reported: its rest group (Others) filled with trackingis' current sub product types."""
    if not family.rest_group:
        return family
    return families.with_rest(family, [str(o["name"]) for o in report.filter_options(db, "sub_product_types", user)])


def _product_types(client: TrackingisClient, q: ReportQuery) -> list[dict[str, Any]]:
    """Totals per trackingis product type, in one query: the rows of the rest group."""
    got = client.report(replace(q, view="product_type", page=1, per_page=MAX_PER_PAGE, sort_by="total_revenue", sort_order="desc"))
    return got["rows"]


def _fetch(client: TrackingisClient, family: Family, q: ReportQuery) -> dict[str, Any]:
    rest = dict(family.groups).get(family.rest_group) if family.rest_group else None
    own_rows = [s for name, subs in family.groups if name != family.rest_group for s in subs]  # sub types with a row each
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        total = pool.submit(client.totals, _only(q, family.sub_types))
        groups = [pool.submit(client.daily, _only(q, subs)) for _, subs in family.groups]
        subs = {s: pool.submit(client.daily, _only(q, (s,))) for s in own_rows}
        by_type = pool.submit(_product_types, client, _only(q, rest)) if rest else None
        try:
            return {"total": total.result(), "groups": [g.result() for g in groups], "subs": {s: f.result() for s, f in subs.items()},
                    "rest": by_type.result() if by_type else []}
        except TrackingisError:
            pool.shutdown(cancel_futures=True)  # a refused token fails every query: don't send the ones still queued
            raise


def _share(part: float, whole: float) -> float | None:
    return round(part / whole, 4) if whole else None


def _fixes_apply(db: Session, q: ReportQuery) -> bool:
    narrowed = any(q.lists.get(f) for f in ("shops", "sellers", "designers")) or q.texts.get("keyword")
    teams = q.lists.get("teams") or []
    return not narrowed and (not teams or teams == settings_store.runtime(db).default_teams)


def _with_fixes(days: list[dict[str, Any]], fixes: dict[str, int]) -> list[dict[str, Any]]:
    """Day rows with the hand-added quantity (new dicts: the cached answer stays as trackingis sent it)."""
    out = {d["date_at"]: {**d, "total_quantity": (d.get("total_quantity") or 0) + fixes.get(d["date_at"], 0)} for d in days}
    for day, pcs in fixes.items():
        out.setdefault(day, {"date_at": day, "total_order": 0, "total_quantity": pcs, "total": 0, "sale_tax": 0, "total_revenue": 0})
    return sorted(out.values(), key=lambda d: d["date_at"])


def _plus_quantity(totals: dict[str, Any], pcs: int) -> dict[str, Any]:
    return {**totals, "total_quantity": totals["total_quantity"] + pcs, "fix_quantity": pcs} if pcs else totals


def _line(name: str, days: list[dict[str, Any]], fixes: dict[str, int], revenue: float) -> dict[str, Any]:
    """Totals of these day rows plus the hand-added quantity, and the day rows themselves."""
    days = _with_fixes(days, fixes) if fixes else days
    totals = summarize(days)
    if fixes:
        totals["fix_quantity"] = sum(fixes.values())
    return {"name": name, **totals, "share": _share(totals["total_revenue"], revenue), "daily": [{f: d.get(f) for f in DAY_FIELDS} for d in days]}


def _type_line(row: dict[str, Any], revenue: float) -> dict[str, Any]:
    """A row of the product type view as a breakdown line."""
    orders, rev = int(row.get("total_order") or 0), float(row.get("total_revenue") or 0)
    return {"name": str(row.get("product_type") or "—"), "total_order": orders, "total_quantity": int(row.get("total_quantity") or 0),
            "total": float(row.get("total") or 0), "sale_tax": float(row.get("sale_tax") or 0), "total_revenue": round(rev, 2),
            "avg_order_value": round(rev / orders, 2) if orders else 0.0, "share": _share(rev, revenue)}


def family_report(db: Session, family: Family, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    """{family: {key, name, sub_types}, total, groups: [{name, ...totals, share, daily, children: [{name, ...totals, share}]}],
    fix_note, plan, query}.

    Rows carrying hand-added quantity (family.quantity_fixes) have `fix_quantity` = the pieces added. With the family's
    plan sheet (Settings › Plan), product types and the total also carry plan / plan_month / achieved; with the business
    plan's PL2 per item (Etsy › Plan), product types, their children and the total carry pl2_est (PL2 theo KT = quantity ×
    PL2/item). A family of a single product type also gives its sub product types their `daily` rows (the page's chart then stacks them); the rest group's
    children are trackingis product types."""
    family = resolve(db, family, user)
    q = report.build_query(db, {**params, "view": "date"}, user)
    data = report._call(db, user, report._key(family.key, q), report.CACHE_TTL_S, lambda c: _fetch(c, family, q))
    fixes = {s: {d: n for d, n in by_day.items() if q.date_from <= d <= q.date_to} for s, by_day in family.quantity_fixes.items()}
    fixes = {s: by_day for s, by_day in fixes.items() if by_day} if _fixes_apply(db, q) else {}

    revenue = data["total"]["total_revenue"]
    sub_days = len(family.groups) == 1
    groups = []
    for (name, subs), days in zip(family.groups, data["groups"], strict=True):
        group_fix: dict[str, int] = {}
        for s in subs:
            for d, n in fixes.get(s, {}).items():
                group_fix[d] = group_fix.get(d, 0) + n
        if name == family.rest_group:
            children = [_type_line(r, revenue) for r in data["rest"]]
        else:
            children = [_line(s, data["subs"][s], fixes.get(s, {}), revenue) for s in subs]
        if not sub_days:
            children = [{k: v for k, v in c.items() if k != "daily"} for c in children]
        groups.append({**_line(name, days, group_fix, revenue), "children": children})
    total = {**_plus_quantity(data["total"], sum(n for by_day in fixes.values() for n in by_day.values()))}
    plan = _attach_plan(db, family, q, user, groups, total)
    _attach_pl2(family, family_pl2.rates(db, family), groups, total)
    return {"family": {"key": family.key, "name": family.name, "sub_types": list(family.sub_types)}, "total": total, "groups": groups,
            "fix_note": family.fix_note if fixes else None, "plan": plan,
            "query": {"date_from": q.date_from, "date_to": q.date_to, "teams": q.lists["teams"]}}


def _attach_plan(db: Session, family: Family, q: ReportQuery, user: User | None, groups: list[dict[str, Any]],
                 total: dict[str, Any]) -> dict[str, Any]:
    """Add plan (pieces, pro rata over the range), plan_month and achieved (quantity / plan) to the product types and the
    total; return the plan's source and scope, or {"error"} when there is none to compare with."""
    plan = family_plan.for_report(db, family, q, user)
    if "error" in plan:
        return plan
    by_group = plan.pop("groups")
    for row in groups:
        p = by_group.get(row["name"], {"plan": 0.0, "plan_month": 0})
        row |= {"plan": p["plan"], "plan_month": p["plan_month"], "achieved": _ratio(row["total_quantity"], p["plan"])}
    total["plan"] = round(sum(p["plan"] for p in by_group.values()), 1)
    total["plan_month"] = sum(p["plan_month"] for p in by_group.values())
    total["achieved"] = _ratio(total["total_quantity"], total["plan"])
    return plan


def _attach_pl2(family: Family, by_type: dict[str, float | None], groups: list[dict[str, Any]], total: dict[str, Any]) -> None:
    """Add pl2_per_item and pl2_est (PL2 theo KT) to the product types, pl2_est to their children and to the total; nothing
    without a rate. A family is one product of the plan, one rate for all; Others adds up its product types' own."""
    if not by_type:
        return
    for row in groups:
        rate = by_type.get(row["name"])
        row |= {"pl2_per_item": rate, "pl2_est": family_pl2.est(row["total_quantity"], rate)}
        for child in row["children"]:
            child["pl2_est"] = family_pl2.est(child["total_quantity"], rate)
    if family.rate_by_group:  # the rows can add up to a little more than the total: as in the Report's overview
        total["pl2_est"] = round(sum(g["pl2_est"] or 0 for g in groups), 2)
    else:
        rate = family_pl2.rate_of(by_type, family, family.groups[0][0])
        total |= {"pl2_per_item": rate, "pl2_est": family_pl2.est(total["total_quantity"], rate)}


def _ratio(actual: float, plan: float) -> float | None:
    return round(actual / plan, 4) if plan else None
