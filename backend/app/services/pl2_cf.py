"""Etsy › Report, PL2 KT vs CF: finance's monthly PL2 ("PL2 theo CF": plan and actual per month for B.U ZenE and each team)
next to the PL2 estimated from sales ("PL2 theo KT": the product overview's quantity × the plan's PL2 per item) for the same
days of each month.

Layout of the sheet picked in Settings › Plan (tab "Tổng kết PL Monthly"), read from its last sync: a header row
"B.U | TỔNG | MM-YYYY…", then the rows "KẾ HOẠCH B.U ZenE" and "- Kế hoạch PL2_<team>", "THỰC ĐẠT B.U ZenE" and
"- Thực đạt Profit PL2 _<team>". The actual is per month as finance books it (the month so far for the running month); the
plan counts pro rata of the report's days (plan to date), and gap = actual − plan to date, % of plan = actual / plan to
date, as on the other plans. So the sheet's own CHÊNH LỆCH rows (actual − the whole month's plan) and the other rows
(completion rate, share, TikTok) are not read.
"""
import calendar
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import SheetSource, User
from app.services import family_plan, overview, report, settings_store
from app.services.plan import _num
from app.services.trackingis import ReportQuery

SECTIONS = (("kế hoạch", "plan"), ("thực đạt", "actual"))
ZENE = "zene"


def _team(label: str) -> str:
    """"- Kế hoạch PL2_Etsy 1" → "etsy 1"; the support account is "Kế hoạch PL2_Support Account" or "… PL2 _Support"."""
    name = label.rsplit("_", 1)[-1].strip().lower()
    return "support" if name.startswith("support") else name


def parse(header: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """{months: [MM-YYYY…], lines: {"zene" | team: {"plan" | "actual": {month: value}}}} from snapshot rows."""
    def cells(row: dict[str, Any]) -> list[str]:
        return [str(row.get(h) or "").strip() for h in header]

    labels = [h.strip() for h in header]
    body = rows
    if not labels or labels[0].lower() != "b.u":  # the "B.U | TỔNG | months" row is not the header: find it
        at = next((i for i, r in enumerate(rows) if cells(r)[0].lower() == "b.u"), None)
        if at is None:
            raise AppError(422, "PL2_CF_LAYOUT", 'The PL2 CF sheet has no "B.U" label row with the months (MM-YYYY)')
        labels, body = cells(rows[at]), rows[at + 1:]
    months = {j: m for j, m in ((j, family_plan._month_key(t)) for j, t in enumerate(labels)) if m}
    if not months:
        raise AppError(422, "PL2_CF_LAYOUT", "The PL2 CF sheet has no month (MM-YYYY) in its B.U row")
    lines: dict[str, dict[str, dict[str, float]]] = {}
    for row in body:
        c = cells(row)
        label = c[0].lstrip("- ").lower()
        section = next((key for prefix, key in SECTIONS if label.startswith(prefix)), None)
        if section is None:
            continue
        line = lines.setdefault(ZENE if "b.u" in label else _team(c[0]), {})
        line[section] = {m: v for j, m in months.items() if (v := _num(c[j])) is not None}
    if ZENE not in lines:
        raise AppError(422, "PL2_CF_LAYOUT", 'The PL2 CF sheet has no "KẾ HOẠCH / THỰC ĐẠT B.U ZenE" rows')
    return {"months": list(months.values()), "lines": lines}


def _scope(db: Session, q: ReportQuery, user: User | None) -> dict[str, Any]:
    """{source, parsed, keys, label}: the CF lines the report's filters select (B.U ZenE, or the teams picked), or {"error"}."""
    rt = settings_store.runtime(db)
    if rt.pl2_cf_sheet_id is None:
        return {"error": "No PL2 CF sheet yet: an admin picks it in Settings → Plan"}
    source = db.get(SheetSource, rt.pl2_cf_sheet_id)
    if source is None:
        return {"error": "The PL2 CF sheet was removed from Team sheets: an admin picks another in Settings → Plan"}
    if not source.rows:
        return {"error": f'"{source.name}" has not been synced yet: sync it in Lark › Team sheets'}
    if any(q.lists.get(f) for f in ("shops", "sellers", "designers")) or q.texts.get("keyword"):
        return {"error": "PL2 CF is per team: clear the store, seller, designer and keyword filters to compare with it"}
    try:
        parsed = parse(source.header or [], source.rows)
        teams = q.lists.get("teams") or []
        keys = [ZENE] if not teams or set(teams) == set(rt.default_teams) else sorted(family_plan._names(db, user, "teams", teams))
    except AppError as exc:
        return {"error": exc.message}
    label = "B.U ZenE" if keys == [ZENE] else ", ".join(k.title() for k in keys)
    return {"source": source, "parsed": parsed, "keys": keys, "label": label}


def _figures(lines: dict[str, dict[str, dict[str, float]]], keys: list[str], month: str) -> dict[str, float | None]:
    """Plan and actual of the month, added up over the selected lines (None when none of them has the figure)."""
    out: dict[str, float | None] = {}
    for _, field in SECTIONS:
        values = [lines.get(k, {}).get(field, {}).get(month) for k in keys]
        out[field] = round(sum(v for v in values if v is not None), 2) if any(v is not None for v in values) else None
    return out


def _to_date(cf: dict[str, float | None], days: int, month_days: int) -> dict[str, float | None]:
    """The month's plan and actual with plan_to_date (pro rata of the report's days), gap and achieved against it."""
    to_date = round(cf["plan"] * days / month_days, 2) if cf["plan"] is not None else None
    return {**cf, "plan_to_date": to_date, "gap": _diff(cf["actual"], to_date), "achieved": _ratio(cf["actual"], to_date)}


def _ratio(a: float | None, b: float | None) -> float | None:
    return round(a / b, 4) if a is not None and b else None


def _diff(a: float | None, b: float | None) -> float | None:
    return round(a - b, 2) if a is not None and b is not None else None


def pl2_report(db: Session, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    """{months: [{month, days, month_days, plan, plan_to_date, actual, gap, achieved, kt, kt_minus_cf, teams}], total, cf,
    query}. kt = PL2 theo KT for the report's days of the month; plan / actual = PL2 theo CF of the month, gap = actual −
    plan_to_date and achieved = actual / plan_to_date (teams: the per-team lines when the whole of ZenE is selected)."""
    q = report.build_query(db, {**params, "view": "date"}, user)
    scope = _scope(db, q, user)
    cf_info = {"error": scope["error"]} if "error" in scope else {
        "sheet": family_plan.sheet_info(scope["source"]), "scope": scope["label"], "months": scope["parsed"]["months"]}
    months = []
    for month, (days, month_days) in family_plan.month_days(q.date_from, q.date_to).items():
        mm, yyyy = (int(x) for x in month.split("-"))
        first, last = date(yyyy, mm, 1).isoformat(), date(yyyy, mm, calendar.monthrange(yyyy, mm)[1]).isoformat()
        part = {**params, "date_from": max(q.date_from, first), "date_to": min(q.date_to, last)}
        kt = overview.overview(db, part, user)["total"].get("pl2_est")
        line: dict[str, Any] = {"month": month, "days": days, "month_days": month_days, "kt": kt}
        if "error" not in scope:
            lines, keys = scope["parsed"]["lines"], scope["keys"]
            cf = _to_date(_figures(lines, keys, month), days, month_days)
            line |= {**cf, "kt_minus_cf": _diff(kt, cf["actual"])}
            if keys == [ZENE]:
                line["teams"] = [{"team": k.title() if k != "support" else "Support Account",
                                  **_to_date(_figures(lines, [k], month), days, month_days)} for k in lines if k != ZENE]
        months.append(line)

    def add(field: str) -> float | None:
        values = [m.get(field) for m in months if m.get(field) is not None]
        return round(sum(values), 2) if values else None

    total = {f: add(f) for f in ("plan", "plan_to_date", "actual", "gap", "kt")}
    total |= {"achieved": _ratio(total["actual"], total["plan_to_date"]), "kt_minus_cf": _diff(total["kt"], total["actual"])}
    return {"months": months, "total": total, "cf": cf_info,
            "query": {"date_from": q.date_from, "date_to": q.date_to, "teams": q.lists["teams"]}}
