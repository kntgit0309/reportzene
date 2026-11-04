"""PL2 plan of each account: the "KH theo Acc" tab of the KHKD file (Settings › Plan › Account PL2 plan sheet).

Layout read from the last sync of the tab: a row of block labels, a row of months (MM-YYYY) under them and a row "Shop Name" |
"Team" | …, then one row per account of the plans:

    PL2 theo KT  (label)   |  Total  | 10-2026 | 11-2026 | 12-2026      <- PL2 plan on the KT basis (quantity × PL2/item)
    PL2/item theo CF       |  …                                         <- not read
    PL2 theo CF  (label)   |  Total  | 10-2026 | 11-2026 | 12-2026      <- PL2 plan on the CF basis (quantity × PL2/item theo CF)

A block runs from its label to the next label of the row (labels over merged cells sit on their first column); the months of
a block are the first row below its label that has some. When a label occurs more than once (a title above the table), the
one nearest to its months is the block. "Total" columns are sums, not read. A month counts pro rata of the report's days,
as every plan does. Accounts are matched to the report's stores by name; a suspended store's plan goes to its replacement
(Settings › Plan), as the KH sheets' plans do.
"""
import re
from typing import Any

from app.core.errors import AppError
from app.services import family_plan
from app.services.plan import _num

LABELS = {"pl2 theo kt": "kt", "pl2 theo cf": "cf"}
KINDS = ("kt", "cf")
SCAN = 6  # the labels, months and "Shop Name" rows are among the first rows of the tab
_COPY = re.compile(r"\s*\(\d+\)$")  # " (2)": what lark_sheets.unique_header adds to a repeated header cell
_BLANK = re.compile(r"^Column \d+$")  # what it names a blank one


def _error(message: str) -> AppError:
    return AppError(422, "ACCOUNT_PLAN_LAYOUT", message)


def _grid(header: list[str], rows: list[dict[str, Any]]) -> list[list[str]]:
    head = ["" if _BLANK.match(h.strip()) else _COPY.sub("", h.strip()) for h in header]
    return [head, *([str(r.get(h) or "").strip() for h in header] for r in rows)]


def _blocks(grid: list[list[str]]) -> dict[str, tuple[dict[int, str], int]]:
    """kind → ({column: MM-YYYY}, row of the months) of the block of each label found, the nearest months of a label first."""
    best: dict[str, tuple[int, dict[int, str], int]] = {}
    for i, row in enumerate(grid[:SCAN]):
        for j, cell in enumerate(row):
            kind = LABELS.get(" ".join(cell.lower().split()))
            if kind is None:
                continue
            end = next((k for k in range(j + 1, len(row)) if row[k]), len(row))  # the block ends where the next label starts
            for r in range(i, min(i + 4, len(grid))):
                months: dict[int, str] = {}
                for k in range(j, end):
                    month = family_plan._month_key(grid[r][k])
                    if month and month not in months.values():
                        months[k] = month
                if months:
                    if kind not in best or min(months) - j < best[kind][0]:
                        best[kind] = (min(months) - j, months, r)
                    break
    return {kind: (months, r) for kind, (_, months, r) in best.items()}


def parse(header: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """{months: {"kt": [MM-YYYY…], "cf": […]}, accounts: [{shop, team, kt: {month: $}, cf: {month: $}}]} of the tab's snapshot."""
    grid = _grid(header, rows)
    found = _blocks(grid)
    if not found:
        raise _error('The account PL2 plan sheet has no "PL2 theo KT" or "PL2 theo CF" block with months (MM-YYYY) under its label '
                     '(the tab "KH theo Acc", read from its row 1)')
    at = next((i for i, row in enumerate(grid[:SCAN]) if any(c.lower() == "shop name" for c in row)), None)
    if at is None:
        raise _error('The account PL2 plan sheet has no "Shop Name" label in its first rows')
    name_col = next(j for j, c in enumerate(grid[at]) if c.lower() == "shop name")
    team_col = next((j for j, c in enumerate(grid[at]) if c.lower() == "team"), name_col + 1)
    start = max(at, *(r for _, r in found.values())) + 1
    accounts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in grid[start:]:
        shop, team = row[name_col], row[team_col] if team_col < len(row) else ""
        if not (shop and team) or shop.lower() in seen:  # the per-team and total rows have no shop and team
            continue
        plans = {kind: {m: v for j, m in found[kind][0].items() if (v := _num(row[j])) is not None} if kind in found else {}
                 for kind in KINDS}
        if not any(plans.values()):  # an account the plan has no figures for
            continue
        seen.add(shop.lower())
        accounts.append({"shop": shop, "team": team, **plans})
    if not accounts:
        raise _error("The account PL2 plan sheet has no account rows (Shop Name and Team) with a PL2 plan under its blocks")
    return {"months": {kind: list(found[kind][0].values()) if kind in found else [] for kind in KINDS}, "accounts": accounts}


def replace(accounts: list[dict[str, Any]], replacements: tuple[tuple[str, str], ...]) -> dict[str, dict[str, Any]]:
    """Lower-case name → account line; the plan of a suspended store goes to its replacement (Settings › Plan), and lines that
    end up on one store are added up."""
    to = {old.strip().lower(): new.strip() for old, new in replacements}
    merged: dict[str, dict[str, Any]] = {}
    for a in accounts:
        name = to.get(a["shop"].lower(), a["shop"])
        line = merged.setdefault(name.lower(), {"shop": name, "team": a["team"], "kt": {}, "cf": {}})
        for kind in KINDS:
            for month, value in a[kind].items():
                line[kind][month] = line[kind].get(month, 0.0) + value
    return merged


def to_date(plan: dict[str, float], covered: list[str], days: dict[str, tuple[int, int]],
            factors: dict[str, float] | None = None) -> float | None:
    """An account's PL2 plan for the report's days: each month of the range the sheet plans (`covered`) pro rata of its days
    (× `factors`, a seller's share of the month, when given; a month without one has no plan). None when no month is planned;
    a month the sheet plans but the account has no figure for counts $0."""
    got = [plan.get(month, 0.0) * (factors[month] if factors is not None else 1.0) * count / length
           for month, (count, length) in days.items() if month in covered and (factors is None or month in factors)]
    return sum(got) if got else None
