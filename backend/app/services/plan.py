"""Etsy plan by product: one block of a team sheet (its last synced snapshot), read from a start column.

Layout of the block (tab "KH theo Product" of the quarterly KHKD sheet, column Q onwards):

    Product | PL2/item | Total Sales | Total PL2 | Tỷ trọng | Sales/mo × months | Sales/day × months | PL2 × months

A label row has "Product" in the start column and the month names after the fixed columns; the block ends at the
first empty label. Under it, a row without a product is the plan total, then one row per product.
"""
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import SheetSource
from app.services import settings_store
from app.services.sheets import summary

FIXED = ("product", "pl2_per_item", "total_sales", "total_pl2", "share")
MONTHLY = ("sales", "sales_per_day", "pl2")  # one group of month columns each, in this order
LABEL = "product"


def column_letter(n: int) -> str:
    """1 → A, 17 → Q, 27 → AA."""
    out = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def _num(text: str) -> float | None:
    """A sheet cell as a number: "1,234", "$445" and "48%" count; "", "x" and words do not."""
    raw = text.strip().replace(",", "").replace("$", "")
    scale = 100 if raw.endswith("%") else 1
    try:
        return float(raw.rstrip("%")) / scale
    except ValueError:
        return None


def _layout_error(message: str) -> AppError:
    return AppError(422, "PLAN_LAYOUT", message)


def parse(header: list[str], rows: list[dict[str, Any]], start_column: int, max_products: int) -> dict[str, Any]:
    """{months, products, total} from snapshot rows (dicts keyed by `header`, in sheet order)."""
    where = f"column {column_letter(start_column)} ({start_column})"
    keys = header[start_column - 1:]
    if not keys:
        raise _layout_error(f"The sheet has no {where}: check the start column in Settings → Plan")

    def cells(row: dict[str, Any]) -> list[str]:
        return [str(row.get(k) or "").strip() for k in keys]

    label_at = next((i for i, r in enumerate(rows) if cells(r)[0].lower() == LABEL), None)
    if label_at is None:
        raise _layout_error(f'No "Product" label in {where}: check the start column in Settings → Plan')
    labels = cells(rows[label_at])[len(FIXED):]
    width = next((i for i, text in enumerate(labels) if not text), len(labels))
    months = labels[:width // len(MONTHLY)]
    if not months or width % len(MONTHLY):
        raise _layout_error(f"Expected {len(MONTHLY)} groups of month columns (Sales/mo, Sales/day, PL2) after Tỷ trọng in {where}")

    def line(name: str, row: list[str]) -> dict[str, Any]:
        nums = [_num(t) for t in row[1:len(FIXED) + width]]
        nums += [None] * (len(FIXED) - 1 + width - len(nums))
        out: dict[str, Any] = {"product": name, **dict(zip(FIXED[1:], nums[:len(FIXED) - 1], strict=True))}
        monthly = nums[len(FIXED) - 1:]
        for g, field in enumerate(MONTHLY):
            out[field] = monthly[g * len(months):(g + 1) * len(months)]
        return out

    total: dict[str, Any] | None = None
    products: list[dict[str, Any]] = []
    for row in rows[label_at + 1:]:
        c = cells(row)
        if c[0]:
            products.append(line(c[0], c))
            if len(products) >= max_products:
                break
        elif products:
            break  # first empty product cell after the list ends the block
        elif total is None and any(c[1:len(FIXED) + width]):
            total = line("Total", c)
    if not products:
        raise _layout_error(f'No product rows under "Product" in {where}')
    return {"months": months, "products": products, "total": total or _sum(products, len(months))}


def _sum(products: list[dict[str, Any]], months: int) -> dict[str, Any]:
    """Plan total when the sheet has no total row."""
    def add(values: list[float | None]) -> float:
        return sum(v or 0 for v in values)

    out: dict[str, Any] = {"product": "Total", "pl2_per_item": None, "share": None}
    for f in ("total_sales", "total_pl2"):
        out[f] = add([p[f] for p in products])
    for f in MONTHLY:
        out[f] = [add([p[f][m] for p in products]) for m in range(months)]
    return out


def by_product(db: Session) -> dict[str, Any]:
    """The plan of the sheet picked in Settings, read from its last sync."""
    rt = settings_store.runtime(db)
    if rt.plan_sheet_id is None:
        raise AppError(503, "PLAN_NOT_CONFIGURED", "No plan sheet yet: an admin picks it in Settings → Plan")
    source = db.get(SheetSource, rt.plan_sheet_id)
    if source is None:
        raise AppError(503, "PLAN_NOT_CONFIGURED", "The plan sheet was removed from Team sheets: an admin picks another in Settings → Plan")
    if not source.rows:
        raise AppError(409, "PLAN_NOT_SYNCED", f'"{source.name}" has not been synced yet: press Sync')
    plan = parse(source.header or [], source.rows, rt.plan_start_column, rt.plan_products)
    return {"sheet": summary(source), "start_column": rt.plan_start_column, "column_letter": column_letter(rt.plan_start_column),
            "max_products": rt.plan_products, **plan}
