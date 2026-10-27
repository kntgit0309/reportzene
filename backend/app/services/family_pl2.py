"""PL2 theo KT of a product page: quantity sold × the PL2 per item of the business plan (Etsy › Plan, KHKD "KH theo Product"),
for any filters, as in the Report's "Sales by product vs plan".

A family is one product of that plan, so all its product types and stores count at the family's rate; Others plans each of its
product types as a product of its own (Sticker, Scrub cap…), and its rest group (Other products) counts at the rate set in
Settings › Plan ($7 unless changed). Without a readable plan, or a rate for any of the types, a page has no PL2 KT.
"""
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.services import plan, settings_store
from app.services.families import Family

REST = "Other products"


def with_rest(db: Session, rates: dict[str, Any]) -> dict[str, Any]:
    """The plan's PL2 per item (product lower case → $), plus Other products' from Settings › Plan when the plan has none."""
    rate = settings_store.runtime(db).other_pl2_per_item
    return rates if rate is None or rates.get(REST.lower()) is not None else {**rates, REST.lower(): rate}


def rates(db: Session, family: Family) -> dict[str, float | None]:
    """{product type: PL2 per item} of the family, or {} when there is no plan to read or none of its types has a rate."""
    try:
        sheet_plan = plan.by_product(db)
    except AppError:
        return {}
    found = with_rest(db, {p["product"].lower(): p["pl2_per_item"] for p in sheet_plan["products"]})
    if family.rate_by_group:
        out = {name: found.get(name.lower()) for name, _ in family.groups}
    else:
        out = dict.fromkeys((name for name, _ in family.groups), found.get(family.name.lower()))
    return out if any(r is not None for r in out.values()) else {}


def rate_of(by_type: dict[str, float | None], family: Family, part: str) -> float | None:
    """The rate of a product type, or of a sub product type of a family that is a single product type."""
    if part in by_type:
        return by_type[part]
    return next(iter(by_type.values()), None) if len(family.groups) == 1 else None


def est(quantity: float, rate: float | None) -> float | None:
    return round(quantity * rate, 2) if rate is not None else None
