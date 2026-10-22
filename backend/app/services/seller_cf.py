"""PL2 theo CF of a seller: finance's "Profit tính KPI" per seller and month, for PL2: KT vs CF when the report is filtered by
seller (an admin's filter, or a seller's own report).

Finance's "PL Seller Etsy_Monthly" (rows "Profit tính KPI" per seller) pulls each team's figures with FILTER over IMPORTRANGE
tabs, which Lark's API returns as their first cell only. So ReportZenE reads where they come from: the tab
"1.2 P&L Seller (Sau IP)_Monthly" of each team's P&L file (Settings › Plan › Seller CF sheets, one team sheet per team): months
"MM-YYYY" in the header row, then a "Profit tính KPI" section, one row per seller (name in column B), until a row without a
name. The plan beside it is the seller's PL2 plan in the seller plan sheet (seller_plan).
"""
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import SheetSource, User
from app.services import family_plan, report, seller_plan, settings_store
from app.services.plan import _num
from app.services.trackingis import ReportQuery

SECTION = "profit tính kpi"


def parse(header: list[str], rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{name key: {name, actual: {MM-YYYY: PL2}}} from one team's "1.2 P&L Seller (Sau IP)_Monthly" tab."""
    grid = [list(header), *([str(r.get(h) or "").strip() for h in header] for r in rows)]
    months: dict[int, str] = {}
    for j, cell in enumerate(grid[0]):
        key = family_plan._month_key(cell)
        if key and key not in months.values():  # the first block of months (a later "Jan-26" block is something else)
            months[j] = key
    if not months:
        raise AppError(422, "SELLER_CF_LAYOUT", 'A seller CF sheet has no month (MM-YYYY) in its header row')
    start = next((i for i, r in enumerate(grid) if r and r[0].strip().lower().startswith(SECTION)), None)
    if start is None:
        raise AppError(422, "SELLER_CF_LAYOUT", 'A seller CF sheet has no "Profit tính KPI" section')
    out: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(grid[start:]):
        name = row[1].strip() if len(row) > 1 else ""
        if not name or (i and row[0].strip()):  # the section ends at a row without a seller, or at the next section's label
            break
        actual = {m: v for j, m in months.items() if j < len(row) and (v := _num(row[j])) is not None}
        out.setdefault(seller_plan.name_key(name), {"name": name, "actual": actual})
    return out


def _rows(table: dict[str, dict[str, Any]], names: list[str]) -> list[dict[str, Any]]:
    """The rows of the trackingis sellers `names`, each once (two trackingis sellers can share a row)."""
    out: list[dict[str, Any]] = []
    for name in names:
        row = seller_plan.match(table, name)
        if row is not None and all(row is not r for r in out):
            out.append(row)
    return out


def lines(db: Session, q: ReportQuery, user: User | None) -> dict[str, Any]:
    """{source, line: {plan: {MM-YYYY: $}, actual: {MM-YYYY: $}}, label, months} for the sellers of the report's filter, or
    {"error"}: actual = their "Profit tính KPI" (seller CF sheets), plan = their PL2 plan (seller plan sheet, when set)."""
    rt = settings_store.runtime(db)
    sources = [s for s in (db.get(SheetSource, i) for i in rt.seller_cf_sheets) if s is not None]
    if not sources:
        return {"error": 'No seller CF sheets yet ("1.2 P&L Seller (Sau IP)_Monthly" of each team): an admin picks them in Settings → Plan'}
    sellers: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not source.rows:
            return {"error": f'"{source.name}" has not been synced yet: sync it in Lark › Team sheets'}
        try:
            for key, row in parse(source.header or [], source.rows).items():
                sellers.setdefault(key, row)
        except AppError as exc:
            return {"error": f'"{source.name}": {exc.message}'}
    names = {str(o["id"]): str(o["name"]) for o in report.filter_options(db, "sellers", user)}
    picked = [names.get(s, s) for s in q.lists["sellers"]]
    found = _rows(sellers, picked)
    if not found:
        listed = ", ".join(s["name"] for s in sellers.values())
        return {"error": f'The seller CF sheets have no row for {", ".join(picked)} (their rows: {listed})'}
    months = sorted({m for r in found for m in r["actual"]}, key=lambda m: (m[3:], m[:2]))
    actual = {m: sum(r["actual"].get(m, 0.0) for r in found) for m in months}
    plan: dict[str, float] = {}
    plan_sheet = db.get(SheetSource, rt.seller_plan_sheet_id) if rt.seller_plan_sheet_id else None
    if plan_sheet is not None and plan_sheet.rows:
        try:
            parsed = seller_plan.parse(plan_sheet.header or [], plan_sheet.rows)
            rows = _rows(parsed["sellers"], picked)
            for month in family_plan.month_days(q.date_from, q.date_to):
                if rows and int(month[:2]) in parsed["months"]:
                    plan[month] = sum(r["pl2"][int(month[:2])] for r in rows)
        except AppError:
            plan = {}
    label = ", ".join(r["name"] for r in found)
    return {"source": sources[0], "line": {"plan": plan, "actual": actual}, "label": label, "months": months}
