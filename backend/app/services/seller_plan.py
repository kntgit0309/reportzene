"""Plan of a seller: when an admin filters a report by seller, the ZenE plans (per product, product type and account) are
scaled by that seller's share of ZenE's PL2 plan for each month.

The shares come from the seller plan sheet (Settings › Plan, "KH quý 4.2026 theo seller"): a label row with "PL2 T10",
"PL2 T11", "PL2 T12" (the first such columns hold dollars; a second block of the same labels, the percentages, is not read),
then one row per seller with their PL2 plan for each month, named in the text cell left of those columns ("Linh"). A
seller's share of a month = their PL2 / the sellers' total that month. The sheet names sellers by first name; a trackingis
seller ("Linh PT.ETS") matches the row of their first name, accents left out. A member limited to their own sales keeps the
actuals-only report (no plan).
"""
import re
import unicodedata
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import SheetSource, User
from app.services import family_plan, report, settings_store
from app.services.plan import _num
from app.services.trackingis import ReportQuery

LABEL = re.compile(r"^pl2\s*t(\d{1,2})$", re.IGNORECASE)


def name_key(name: Any) -> str:
    """"Thuỷ NT.ETS" → "thuy": the first word, lower case, without accents (the sheet writes first names only)."""
    text = str(name or "").replace("đ", "d").replace("Đ", "D")
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    words = re.split(r"[\s.]+", text.strip().lower())
    return words[0] if words else ""


def parse(header: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """{months: [10, 11, 12], sellers: {name key: {name, pl2: {month number: $}}}, total: {month number: $}}."""
    grid = [list(header), *([str(r.get(h) or "").strip() for h in header] for r in rows)]
    at = next((i for i, row in enumerate(grid) if any(LABEL.match(c.strip()) for c in row)), None)
    if at is None:
        raise AppError(422, "SELLER_PLAN_LAYOUT", 'The seller plan sheet has no "PL2 T10"-style label row (PL2 per month per seller)')
    columns: dict[int, int] = {}  # month number → its column (the first block: dollars)
    for j, cell in enumerate(grid[at]):
        m = LABEL.match(cell.strip())
        if m and 1 <= int(m.group(1)) <= 12:
            columns.setdefault(int(m.group(1)), j)
    first = min(columns.values())
    sellers: dict[str, dict[str, Any]] = {}
    for row in grid[at + 1:]:
        name = next((c for c in reversed(row[:first]) if c and _num(c) is None), "")  # the text cell left of the PL2 columns
        values = {m: _num(row[j]) if j < len(row) else None for m, j in columns.items()}
        if name and any(v is not None for v in values.values()):
            sellers.setdefault(name_key(name), {"name": name, "pl2": {m: v or 0.0 for m, v in values.items()}})
    if not sellers:
        raise AppError(422, "SELLER_PLAN_LAYOUT", "The seller plan sheet has no seller rows under its PL2 labels")
    total = {m: sum(s["pl2"][m] for s in sellers.values()) for m in columns}
    return {"months": sorted(columns), "sellers": sellers, "total": total}


def applies(q: ReportQuery, user: User | None) -> bool:
    """A report filtered by seller only (teams aside), for someone who sees the whole of ZenE."""
    if user is not None and user.seller_scope is not None:
        return False  # their own sales: the seller version shows actuals only
    return bool(q.lists.get("sellers")) and not (q.lists.get("shops") or q.lists.get("designers") or q.texts.get("keyword"))


def shares(db: Session, q: ReportQuery, user: User | None) -> dict[str, Any]:
    """{factors: {MM-YYYY: share}, label, sheet} for the sellers of the report's filter, or {"error"}."""
    sheet_id = settings_store.runtime(db).seller_plan_sheet_id
    if sheet_id is None:
        return {"error": "No seller plan sheet yet (KH theo seller): an admin picks it in Settings → Plan"}
    source = db.get(SheetSource, sheet_id)
    if source is None:
        return {"error": "The seller plan sheet was removed from Team sheets: an admin picks another in Settings → Plan"}
    if not source.rows:
        return {"error": f'"{source.name}" has not been synced yet: sync it in Lark › Team sheets'}
    try:
        parsed = parse(source.header or [], source.rows)
    except AppError as exc:
        return {"error": exc.message}
    names = {str(o["id"]): str(o["name"]) for o in report.filter_options(db, "sellers", user)}
    picked = [names.get(s, s) for s in q.lists["sellers"]]
    rows = [parsed["sellers"][name_key(n)] for n in picked if name_key(n) in parsed["sellers"]]
    missing = [n for n in picked if name_key(n) not in parsed["sellers"]]
    if not rows:
        return {"error": f'The seller plan sheet has no row for {", ".join(picked)} (it names sellers by first name)'}
    factors: dict[str, float] = {}
    for month in family_plan.month_days(q.date_from, q.date_to):
        m = int(month[:2])
        if parsed["total"].get(m):
            factors[month] = sum(r["pl2"][m] for r in rows) / parsed["total"][m]
    if not factors:
        return {"error": "The seller plan sheet has no PL2 for the months of this range"}
    share_text = ", ".join(f"{month} {factors[month] * 100:.1f}%" for month in factors)
    label = f'{", ".join(r["name"] for r in rows)}: share of ZenE\'s PL2 plan {share_text}'
    if missing:
        label += f' (no row for {", ".join(missing)})'
    return {"factors": factors, "label": label, "sheet": family_plan.sheet_info(source)}
