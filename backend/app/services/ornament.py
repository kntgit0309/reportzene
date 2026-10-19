"""Etsy › Ornament: ZenE ornament sales per product type, the team's own grouping of trackingis sub product types.

Each product type and each sub product type is one trackingis query filtered on its sub product types (same date / store /
seller / team filters as the report), run in parallel. An order holding ornaments of several types counts in each of them,
so the overall total is its own query rather than the sum of the rows.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.services import ornament_plan, report, settings_store
from app.services.trackingis import ReportQuery, TrackingisClient, TrackingisError, summarize

# Product type → trackingis sub product types (names exactly as trackingis lists them). Wooden Garland is counted in Others.
GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Acrylic + Wood", ("Cutout Ornament", "Ornament", "Ornament 2-layers", "Name ornament")),
    ("Shell", ("Shell ornament",)),
    ("Shaker", ("Shaker Ornament",)),
    ("Ceramic", ("Shaped Ornament",)),
    ("Glass", ("Glass Ornament",)),
    ("Felt", ("Felt Ornament", "Needle Felted Ornament")),
    # Others also takes every other ornament sub product type trackingis lists (checked 19/10/2026)
    ("Others", ("Linen ornament", "Flat Patchwork Ornament", "Quilted Patchwork Ornament", "Patchwork Ornament", "Crochet Ornament",
                "Wooden Garland", "2-layer Wood Orn", "ball ornament", "embroidered ornament", "Embroidery Hoop Ornament")),
)
ALL_SUB_TYPES = tuple(s for _, subs in GROUPS for s in subs)
WORKERS = 8


def _spread(total: int, first: date, days: int) -> dict[str, int]:
    """`total` split evenly over `days` days from `first` in whole units, the remainder on the first days."""
    base, extra = divmod(total, days)
    return {(first + timedelta(days=i)).isoformat(): base + (1 if i < extra else 0) for i in range(days)}


# Quantity trackingis misses, added by hand: sub product type → {day: pieces}. Only for the team-wide view (no store,
# seller, designer or keyword filter; default or every team), since the missing pieces are not tied to a store.
QUANTITY_FIXES: dict[str, dict[str, int]] = {
    # trackingis counts a multi-piece Felt Ornament as 1: 170 pcs missing over 01–18/10/2026
    "Felt Ornament": _spread(170, date(2026, 10, 1), 18),
}
FIX_NOTE = "includes pieces trackingis misses, added by hand (Felt Ornament: +170 pcs over 01–18/10/2026)"
DAY_FIELDS = ("date_at", "total_order", "total_quantity", "total_revenue")


def _only(q: ReportQuery, subs: tuple[str, ...]) -> ReportQuery:
    """The same filters, restricted to these sub product types (the page's own product type filters are ignored)."""
    return replace(q, view="date", page=1, lists={**q.lists, "product_types": [], "sub_product_types": list(subs)})


def _fetch(client: TrackingisClient, q: ReportQuery) -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        total = pool.submit(client.totals, _only(q, ALL_SUB_TYPES))
        groups = [pool.submit(client.daily, _only(q, subs)) for _, subs in GROUPS]
        subs = {s: pool.submit(client.totals, _only(q, (s,))) for s in ALL_SUB_TYPES}
        try:
            return {"total": total.result(), "groups": [g.result() for g in groups], "subs": {s: f.result() for s, f in subs.items()}}
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


def ornament_report(db: Session, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    """{total, groups: [{name, ...totals, share, daily, children: [{name, ...totals, share}]}], fix_note, plan, query}.

    Rows carrying hand-added quantity (QUANTITY_FIXES) have `fix_quantity` = the pieces added. With an ornament plan
    sheet (Settings › Plan), product types and the total also carry plan / plan_month / achieved."""
    q = report.build_query(db, {**params, "view": "date"})
    data = report._call(db, user, report._key("ornament", q), report.CACHE_TTL_S, lambda c: _fetch(c, q))
    fixes = {s: {d: n for d, n in by_day.items() if q.date_from <= d <= q.date_to} for s, by_day in QUANTITY_FIXES.items()}
    fixes = {s: by_day for s, by_day in fixes.items() if by_day} if _fixes_apply(db, q) else {}

    revenue = data["total"]["total_revenue"]
    groups = []
    for (name, subs), days in zip(GROUPS, data["groups"], strict=True):
        group_fix: dict[str, int] = {}
        for s in subs:
            for d, n in fixes.get(s, {}).items():
                group_fix[d] = group_fix.get(d, 0) + n
        days = _with_fixes(days, group_fix) if group_fix else days
        totals = summarize(days)
        if group_fix:
            totals["fix_quantity"] = sum(group_fix.values())
        children = [{"name": s, **_plus_quantity(data["subs"][s], sum(fixes.get(s, {}).values())),
                     "share": _share(data["subs"][s]["total_revenue"], revenue)} for s in subs]
        groups.append({"name": name, **totals, "share": _share(totals["total_revenue"], revenue), "children": children,
                       "daily": [{f: d.get(f) for f in DAY_FIELDS} for d in days]})
    total = {**_plus_quantity(data["total"], sum(n for by_day in fixes.values() for n in by_day.values()))}
    plan = _attach_plan(db, q, user, groups, total)
    return {"total": total, "groups": groups, "fix_note": FIX_NOTE if fixes else None, "plan": plan,
            "query": {"date_from": q.date_from, "date_to": q.date_to, "teams": q.lists["teams"]}}


def _attach_plan(db: Session, q: ReportQuery, user: User | None, groups: list[dict[str, Any]], total: dict[str, Any]) -> dict[str, Any]:
    """Add plan (pieces, pro rata over the range), plan_month and achieved (quantity / plan) to the product types and the
    total; return the plan's source and scope, or {"error"} when there is none to compare with."""
    plan = ornament_plan.for_report(db, q, user)
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


def _ratio(actual: float, plan: float) -> float | None:
    return round(actual / plan, 4) if plan else None
