"""Plan of a product family (sheet "KH Ornament" tab Ornament, "KH Shirt" tab Shirt…): planned sales in pieces per shop,
month and category of the family.

Layout read from the last sync of the family's sheet picked in Settings › Plan:
  - a label row starting "Shop Name" | "Team" | …, then one block per month: "Total" followed by the categories
    (Ornament: Acrylic, Wood, Shaker, Ceramic, Glass, Shell, Felt, Ornament khác; Shirt: T-shirt, Sweatshirt), each mapped
    onto a product type of the family (families.Family.plan_group); the month (MM-YYYY) is a column name over the block;
  - every row below with a shop name and a team is that shop's plan (the per-team and total rows are sums, not read).
Plan sales are pieces, compared with the report's quantity. A month partly in the date range counts pro rata of its days.
"""
import calendar
import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import SheetSource, User
from app.services import report, settings_store
from app.services.families import Family
from app.services.trackingis import ReportQuery

_MONTH_RE = re.compile(r"^(\d{1,2})-(\d{4})$")


def _layout_error(family: Family, message: str) -> AppError:
    return AppError(422, f"{family.key.upper()}_PLAN_LAYOUT", message)


def _pcs(text: str) -> float:
    try:
        return float(text.replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _month_key(text: str) -> str | None:
    m = _MONTH_RE.match(text.strip())
    return f"{int(m.group(1)):02d}-{m.group(2)}" if m else None


def parse(header: list[str], rows: list[dict[str, Any]], family: Family) -> dict[str, Any]:
    """{months: ["10-2026", …], shops: [{shop, team, plan: {month: {product type: pcs}}}]} from snapshot rows."""
    def cells(row: dict[str, Any]) -> list[str]:
        return [str(row.get(h) or "").strip() for h in header]

    label_at = next((i for i, r in enumerate(rows) if cells(r)[0].lower() == "shop name"), None)
    if label_at is None:
        raise _layout_error(family, f'The {family.name.lower()} plan sheet has no "Shop Name" label in its first column')
    labels = cells(rows[label_at])
    blocks: list[tuple[str, list[tuple[int, str]]]] = []
    for start, text in enumerate(labels):
        if text.lower() != "total":
            continue
        end = start + 1
        while end < len(labels) and labels[end]:
            end += 1
        month = next((k for k in (_month_key(h) for h in header[start:end]) if k), None)
        if month is None or end == start + 1:
            raise _layout_error(family, f'No month (MM-YYYY) over the "Total" block in column {start + 1} of the '
                                        f'{family.name.lower()} plan sheet')
        blocks.append((month, [(j, family.plan_group(labels[j])) for j in range(start + 1, end)]))
    if not blocks:
        raise _layout_error(family, f'The {family.name.lower()} plan sheet has no "Total" month block after the shop columns')

    shops = []
    for row in rows[label_at + 1:]:
        c = cells(row)
        if not (c[0] and c[1]):
            continue
        plan: dict[str, dict[str, float]] = {}
        for month, cols in blocks:
            per = plan.setdefault(month, {})
            for j, group in cols:
                per[group] = per.get(group, 0.0) + _pcs(c[j])
        shops.append({"shop": c[0], "team": c[1], "plan": plan})
    return {"months": [m for m, _ in blocks], "shops": shops}


def replace_accounts(parsed: dict[str, Any], replacements: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    """The plan line of a suspended store goes to its replacement (Settings › Plan), in the suspended store's place;
    lines that end up on one store are added up. Each shop gets `replaces`: the suspended stores it took over."""
    to = {old.strip().lower(): new.strip() for old, new in replacements}
    merged: dict[str, dict[str, Any]] = {}
    for s in parsed["shops"]:
        name = to.get(s["shop"].lower(), s["shop"])
        line = merged.setdefault(name.lower(), {"shop": name, "team": s["team"], "plan": {}, "replaces": []})
        for month, groups in s["plan"].items():
            per = line["plan"].setdefault(month, {})
            for group, pcs in groups.items():
                per[group] = per.get(group, 0.0) + pcs
        if name != s["shop"]:
            line["replaces"].append(s["shop"])
    return {**parsed, "shops": list(merged.values())}


def month_days(date_from: str, date_to: str) -> dict[str, tuple[int, int]]:
    """MM-YYYY → (days of the range in that month, days of the month)."""
    start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    out: dict[str, tuple[int, int]] = {}
    first = start.replace(day=1)
    while first <= end:
        last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
        out[f"{first.month:02d}-{first.year}"] = ((min(end, last) - max(start, first)).days + 1, last.day)
        first = last + timedelta(days=1)
    return out


def shop_plans(parsed: dict[str, Any], date_from: str, date_to: str, teams: set[str] | None = None,
               shops: set[str] | None = None) -> dict[str, Any]:
    """Per kept shop, in sheet order: {shop, team, groups: {product type: {plan (pro rata), plan_month}}}, unrounded;
    plus the months covered and those the sheet has no plan for. `teams` / `shops`: lower-case names, None = every shop."""
    rows = [s for s in parsed["shops"] if (teams is None or s["team"].lower() in teams) and (shops is None or s["shop"].lower() in shops)]
    out: list[dict[str, Any]] = [{"shop": s["shop"], "team": s["team"], "replaces": s.get("replaces", []), "groups": {}} for s in rows]
    covered, missing = [], []
    for month, (days, month_len) in month_days(date_from, date_to).items():
        if month not in parsed["months"]:
            missing.append(month)
            continue
        covered.append({"month": month, "days": days, "month_days": month_len})
        for s, line in zip(rows, out, strict=True):
            for group, pcs in s["plan"].get(month, {}).items():
                g = line["groups"].setdefault(group, {"plan": 0.0, "plan_month": 0.0})
                g["plan"] += pcs * days / month_len
                g["plan_month"] += pcs
    return {"shops": out, "months": covered, "missing_months": missing}


def plan_for(parsed: dict[str, Any], date_from: str, date_to: str, teams: set[str] | None = None,
             shops: set[str] | None = None) -> dict[str, Any]:
    """Plan per product type for the range, over the kept shops: `plan` (pro rata) and `plan_month` (the whole months)."""
    per_shop = shop_plans(parsed, date_from, date_to, teams, shops)
    groups: dict[str, dict[str, float]] = {}
    for line in per_shop["shops"]:
        for group, p in line["groups"].items():
            g = groups.setdefault(group, {"plan": 0.0, "plan_month": 0.0})
            g["plan"] += p["plan"]
            g["plan_month"] += p["plan_month"]
    return {"groups": {k: {"plan": round(v["plan"], 1), "plan_month": round(v["plan_month"])} for k, v in groups.items()},
            "months": per_shop["months"], "missing_months": per_shop["missing_months"], "shops": len(per_shop["shops"])}


def _names(db: Session, user: User | None, kind: str, ids: list[str]) -> set[str]:
    """trackingis ids → lower-case names (teams: "Etsy 1.ZenE" → "etsy 1", as the plan sheet writes them)."""
    by_id = {str(o["id"]): str(o["name"]) for o in report.filter_options(db, kind, user)}
    names = {by_id.get(i, i) for i in ids}
    return {n.split(".")[0].strip().lower() for n in names} if kind == "teams" else {n.strip().lower() for n in names}


def scope(db: Session, family: Family, q: ReportQuery, user: User | None) -> dict[str, Any]:
    """{source, parsed, teams, shops, label}: the family's plan sheet and the teams / stores the report's filters keep,
    or {"error": why there is no plan to compare with}."""
    rt = settings_store.runtime(db)
    sheet_id = rt.family_plan_sheets.get(family.key)
    if sheet_id is None:
        return {"error": f"No {family.name.lower()} plan sheet yet: an admin picks it in Settings → Plan"}
    source = db.get(SheetSource, sheet_id)
    if source is None:
        return {"error": f"The {family.name.lower()} plan sheet was removed from Team sheets: an admin picks another in Settings → Plan"}
    if not source.rows:
        return {"error": f'"{source.name}" has not been synced yet: sync it in Lark › Team sheets'}
    if any(q.lists.get(f) for f in ("sellers", "designers")) or q.texts.get("keyword"):
        return {"error": "The plan is per store and team: clear the seller, designer and keyword filters to compare with it"}
    try:
        parsed = replace_accounts(parse(source.header or [], source.rows, family), rt.account_replacements)
        selected_teams = q.lists.get("teams") or []
        teams = None if not selected_teams or set(selected_teams) == set(rt.default_teams) else _names(db, user, "teams", selected_teams)
        shops = _names(db, user, "shops", q.lists["shops"]) if q.lists.get("shops") else None
    except AppError as exc:
        return {"error": exc.message}
    label = f"{len(shops)} store(s)" if shops else (", ".join(sorted(t.title() for t in teams)) if teams else "ZenE")
    return {"source": source, "parsed": parsed, "teams": teams, "shops": shops, "label": label}


def sheet_info(source: SheetSource) -> dict[str, Any]:
    return {"id": source.id, "name": source.name, "tab_title": source.tab_title,
            "last_synced_at": source.last_synced_at.isoformat() if source.last_synced_at else None}


def for_report(db: Session, family: Family, q: ReportQuery, user: User | None) -> dict[str, Any]:
    """The family's plan matching the report's filters, or {"error": why there is none}."""
    s = scope(db, family, q, user)
    if "error" in s:
        return s
    result = plan_for(s["parsed"], q.date_from, q.date_to, s["teams"], s["shops"])
    return {"sheet": sheet_info(s["source"]), "scope": s["label"], **result}
