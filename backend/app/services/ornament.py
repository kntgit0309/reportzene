"""Etsy › Ornament: ZenE ornament sales per product type, the team's own grouping of trackingis sub product types.

Each product type and each sub product type is one trackingis query filtered on its sub product types (same date / store /
seller / team filters as the report), run in parallel. An order holding ornaments of several types counts in each of them,
so the overall total is its own query rather than the sum of the rows.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.services import report
from app.services.trackingis import ReportQuery, TrackingisClient, TrackingisError, summarize

# Product type → trackingis sub product types (names exactly as trackingis lists them). Wooden Garland is counted in Others.
GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Acrylic + Wood", ("Cutout Ornament", "Ornament", "Ornament 2-layers")),
    ("Shell", ("Shell ornament",)),
    ("Shaker", ("Shaker Ornament",)),
    ("Ceramic", ("Shaped Ornament",)),
    ("Glass", ("Glass Ornament",)),
    ("Felt", ("Felt Ornament", "Needle Felted Ornament")),
    ("Others", ("Linen ornament", "Flat Patchwork Ornament", "Quilted Patchwork Ornament", "Patchwork Ornament", "Crochet Ornament",
                "Wooden Garland")),
)
ALL_SUB_TYPES = tuple(s for _, subs in GROUPS for s in subs)
WORKERS = 8
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


def ornament_report(db: Session, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    """{total, groups: [{name, ...totals, share, daily, children: [{name, ...totals, share}]}], query}."""
    q = report.build_query(db, {**params, "view": "date"})
    data = report._call(db, user, report._key("ornament", q), report.CACHE_TTL_S, lambda c: _fetch(c, q))
    revenue = data["total"]["total_revenue"]
    groups = []
    for (name, subs), days in zip(GROUPS, data["groups"], strict=True):
        totals = summarize(days)
        children = [{"name": s, **data["subs"][s], "share": _share(data["subs"][s]["total_revenue"], revenue)} for s in subs]
        groups.append({"name": name, **totals, "share": _share(totals["total_revenue"], revenue), "children": children,
                       "daily": [{f: d.get(f) for f in DAY_FIELDS} for d in days]})
    return {"total": data["total"], "groups": groups,
            "query": {"date_from": q.date_from, "date_to": q.date_to, "teams": q.lists["teams"]}}
