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


def _groups(labels: list[str]) -> list[dict[int, int]]:
    """The label row's blocks of "PL2 T10 | PL2 T11 | PL2 T12": month number → column, a new block at a gap or a repeat."""
    groups: list[dict[int, int]] = []
    previous = None
    for j, cell in enumerate(labels):
        m = LABEL.match(cell.strip())
        if not m or not 1 <= int(m.group(1)) <= 12:
            continue
        month = int(m.group(1))
        if not groups or month in groups[-1] or previous != j - 1:
            groups.append({})
        groups[-1][month] = j
        previous = j
    return groups


def _is_share(rows: list[list[str]], group: dict[int, int]) -> bool:
    """A block of shares ("14%", 0.14) rather than dollars."""
    cells = [r[j] for r in rows for j in group.values() if j < len(r) and _num(r[j]) is not None]
    return bool(cells) and 2 * sum(c.endswith("%") or abs(_num(c) or 0) <= 1.5 for c in cells) > len(cells)


def _table(after: list[list[str]], columns: dict[int, int], shares: dict[int, int], left_bound: int) -> dict[str, Any] | None:
    """One table: its names (the nearest mostly-text column left of its dollars, right of `left_bound`), down to its first
    empty row; None when it has no named row with figures."""
    first, last = min(columns.values()), max([*columns.values(), *shares.values()])
    valued = [r for r in after if any(j < len(r) and _num(r[j]) is not None for j in columns.values())]
    name_col = None
    for j in range(first - 1, left_bound, -1):
        filled = [r[j] for r in valued if j < len(r) and r[j]]
        if filled and 2 * sum(_num(c) is None for c in filled) > len(filled):
            name_col = j
            break
    if name_col is None:
        return None
    body: list[list[str]] = []
    for row in after:  # the table ends at its first empty row: a table further down (per team…) is something else
        if not any(row[name_col:last + 1]):
            if body:
                break
            continue
        body.append(row)
    sellers: dict[str, dict[str, Any]] = {}
    for row in body:
        name = row[name_col] if name_col < len(row) else ""
        values = {m: _num(row[j]) if j < len(row) else None for m, j in columns.items()}
        if name and any(v is not None for v in values.values()):
            share = {m: _share(row[j]) for m, j in shares.items() if j < len(row) and _share(row[j]) is not None}
            sellers.setdefault(name_key(name), {"name": name, "pl2": {m: v or 0.0 for m, v in values.items()}, "share": share})
    if not sellers:
        return None
    return {"months": sorted(columns), "sellers": sellers, "total": {m: sum(r["pl2"][m] for r in sellers.values()) for m in columns}}


def parse(header: list[str], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The tab's tables under a "PL2 T10 | T11 | T12" label row: [{months: [10, 11, 12], sellers: {name key: {name, pl2:
    {month: $}, share: {month: 0.14}}}, total: {month: $}}]. The same row may hold several tables side by side (per account,
    per seller): each block of dollars is a table, named by the text column left of it; a block of shares right after a
    table belongs to it. Which table holds the sellers is decided by their names (best)."""
    grid = [list(header), *([str(r.get(h) or "").strip() for h in header] for r in rows)]
    at = next((i for i, row in enumerate(grid) if any(LABEL.match(c.strip()) for c in row)), None)
    if at is None:
        raise AppError(422, "SELLER_PLAN_LAYOUT", 'The seller plan sheet has no "PL2 T10"-style label row (PL2 per month per seller)')
    after = grid[at + 1:]
    tables: list[dict[str, Any]] = []
    bound = -1  # tables do not reach left of the previous block
    groups = _groups(grid[at])
    for i, group in enumerate(groups):
        if _is_share(after, group):
            bound = max(group.values())
            continue
        following = groups[i + 1] if i + 1 < len(groups) else None
        shares = following if following is not None and _is_share(after, following) else {}
        table = _table(after, group, shares, bound)
        if table is not None:
            tables.append(table)
        bound = max([*group.values(), *shares.values()])
    if not tables:
        raise AppError(422, "SELLER_PLAN_LAYOUT", "The seller plan sheet has no seller rows under its PL2 labels")
    return tables


def best(tables: list[dict[str, Any]], names: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """(table, its rows of `names`, the names without a row): the table where most of the trackingis sellers have a row."""
    def rows_of(table: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name in names:
            row = match(table["sellers"], name)
            if row is not None and all(row is not r for r in out):  # two trackingis sellers can share a row
                out.append(row)
        return out

    table = max(tables, key=lambda t: len(rows_of(t)))
    return table, rows_of(table), [n for n in names if match(table["sellers"], n) is None]


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
        tables = parse(source.header or [], source.rows)
    except AppError as exc:
        return {"error": exc.message}
    names = {str(o["id"]): str(o["name"]) for o in report.filter_options(db, "sellers", user)}
    picked = [names.get(s, s) for s in q.lists["sellers"]]
    parsed, rows, missing = best(tables, picked)
    if not rows:
        listed = "; ".join(", ".join(r["name"] for r in t["sellers"].values()) for t in tables)
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
