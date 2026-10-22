"""Plan of a seller: when an admin filters a report by seller, the ZenE plans (per product, product type and account) are
scaled by that seller's share of ZenE's PL2 plan for each month.

The shares come from the seller plan sheet (Settings › Plan, "KH quý 4.2026 theo seller"): a label row with "PL2 T10",
"PL2 T11", "PL2 T12" (the first such columns hold dollars, a second block of the same labels the sheet's share, "14%"),
then one row per seller, named in the nearest text column left of the dollars ("Linh"), down to the table's first empty
row. A seller's share of a month is the sheet's own share; without the % columns, their PL2 / the sellers' total that
month. The sheet names sellers by first name; a trackingis seller matches the row of their first name, accents left
out: "Linh PT.ETS" and "LinhPT" both match "Linh". A seller limited to their own sales gets their plan the same way (their sellers are the report's filter).
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

LABEL = re.compile(r"^pl2\s*t(\d{1,2})(\s*\(\d+\))?$", re.IGNORECASE)  # "PL2 T10", or "PL2 T10 (2)" as a repeated header


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
    columns: dict[int, int] = {}  # month number → its column in the first block (dollars)
    shares: dict[int, int] = {}  # … and in the second block of the same labels (the sheet's own share, "14%")
    for j, cell in enumerate(grid[at]):
        m = LABEL.match(cell.strip())
        if m and 1 <= int(m.group(1)) <= 12:
            (shares if int(m.group(1)) in columns else columns).setdefault(int(m.group(1)), j)
    first, last = min(columns.values()), max([*columns.values(), *shares.values()])
    after = grid[at + 1:]
    # the names: going left from the PL2 columns, the first column that holds mostly text where there are dollars ("Quý IV",
    # a total, is numbers; a table further left is not looked at)
    valued = [r for r in after if any(j < len(r) and _num(r[j]) is not None for j in columns.values())]
    name_col = None
    for j in range(first - 1, -1, -1):
        filled = [r[j] for r in valued if j < len(r) and r[j]]
        if filled and 2 * sum(_num(c) is None for c in filled) > len(filled):
            name_col = j
            break
    # the sellers' table ends at its first empty row (names to percentages): a table further down (per team…) is not sellers
    body: list[list[str]] = []
    left = name_col if name_col is not None else first
    for row in after:
        if not any(row[left:last + 1]):
            if body:
                break
            continue
        body.append(row)
    sellers: dict[str, dict[str, Any]] = {}
    for row in body:
        name = row[name_col] if name_col is not None and name_col < len(row) else ""
        values = {m: _num(row[j]) if j < len(row) else None for m, j in columns.items()}
        if name and any(v is not None for v in values.values()):
            share = {m: _share(row[j]) for m, j in shares.items() if j < len(row) and _share(row[j]) is not None}
            sellers.setdefault(name_key(name), {"name": name, "pl2": {m: v or 0.0 for m, v in values.items()}, "share": share})
    if not sellers:
        raise AppError(422, "SELLER_PLAN_LAYOUT", "The seller plan sheet has no seller rows under its PL2 labels")
    total = {m: sum(s["pl2"][m] for s in sellers.values()) for m in columns}
    return {"months": sorted(columns), "sellers": sellers, "total": total}


def _share(cell: str) -> float | None:
    """The sheet's share of a month: "14%" or 0.14 → 0.14."""
    v = _num(cell)
    return None if v is None else v / 100 if v > 1 else v


def applies(q: ReportQuery, user: User | None) -> bool:
    """A report filtered by seller only (teams aside): an admin's seller filter, or a seller's own report."""
    return bool(q.lists.get("sellers")) and not (q.lists.get("shops") or q.lists.get("designers") or q.texts.get("keyword"))


def _plain(name: Any) -> str:
    text = str(name or "").replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def match(sellers: dict[str, dict[str, Any]], name: str) -> dict[str, Any] | None:
    """The sheet row of a trackingis seller: their first word ("Linh PT.ETS" → "linh"), else a row name followed by
    capitals ("LinhPT" → "Linh", not "AnhTT" → "An"), the longest one when several fit."""
    if name_key(name) in sellers:
        return sellers[name_key(name)]
    compact = re.sub(r"[\s.]+", "", _plain(name))
    fits = [k for k in sellers if compact.lower().startswith(k) and (len(compact) == len(k) or not compact[len(k)].islower())]
    return sellers[max(fits, key=len)] if fits else None


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
    found = {n: match(parsed["sellers"], n) for n in picked}
    rows = list({id(r): r for r in found.values() if r is not None}.values())  # two trackingis sellers can share a row
    missing = [n for n, r in found.items() if r is None]
    if not rows:
        listed = ", ".join(s["name"] for s in parsed["sellers"].values())
        return {"error": f'The seller plan sheet has no row for {", ".join(picked)} (its rows: {listed})'}
    factors: dict[str, float] = {}
    for month in family_plan.month_days(q.date_from, q.date_to):
        m = int(month[:2])
        if all(m in r["share"] for r in rows):  # the sheet's own share (its % columns), as the team reads it
            factors[month] = sum(r["share"][m] for r in rows)
        elif parsed["total"].get(m):  # no % columns: the seller's dollars / the sellers' total
            factors[month] = sum(r["pl2"][m] for r in rows) / parsed["total"][m]
    if not factors:
        return {"error": "The seller plan sheet has no PL2 for the months of this range"}
    share_text = ", ".join(f"{month} {factors[month] * 100:.1f}%" for month in factors)
    label = f'{", ".join(r["name"] for r in rows)}: share of ZenE\'s PL2 plan {share_text}'
    if missing:
        label += f' (no row for {", ".join(missing)})'
    return {"factors": factors, "label": label, "sheet": family_plan.sheet_info(source)}
