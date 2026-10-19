"""Product families with their own Etsy page (Etsy › Ornament, Etsy › Shirt): the team's grouping of trackingis sub product
types into product types, and how the family's plan sheet (KH Ornament, KH Shirt) maps onto it."""
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True)
class Family:
    key: str  # URL and cache key: /report/etsy/<key>
    name: str
    # Product type → trackingis sub product types (names exactly as trackingis lists them)
    groups: tuple[tuple[str, tuple[str, ...]], ...]
    plan_setting: str  # Settings › Plan field holding the family's plan sheet id
    plan_groups: dict[str, str]  # plan category (lower case) → product type; any other category goes to `plan_other`
    plan_other: str
    # Quantity trackingis misses, added by hand: sub product type → {day: pieces}; only in the team-wide view
    quantity_fixes: dict[str, dict[str, int]] = field(default_factory=dict)
    fix_note: str | None = None

    @property
    def sub_types(self) -> tuple[str, ...]:
        return tuple(s for _, subs in self.groups for s in subs)

    def plan_group(self, category: str) -> str:
        return self.plan_groups.get(category.strip().lower(), self.plan_other)


def _spread(total: int, first: date, days: int) -> dict[str, int]:
    """`total` split evenly over `days` days from `first` in whole units, the remainder on the first days."""
    base, extra = divmod(total, days)
    return {(first + timedelta(days=i)).isoformat(): base + (1 if i < extra else 0) for i in range(days)}


ORNAMENT = Family(
    key="ornament",
    name="Ornament",
    groups=(
        ("Acrylic + Wood", ("Cutout Ornament", "Ornament", "Ornament 2-layers", "Name ornament")),
        ("Shell", ("Shell ornament",)),
        ("Shaker", ("Shaker Ornament",)),
        ("Ceramic", ("Shaped Ornament",)),
        ("Glass", ("Glass Ornament",)),
        ("Felt", ("Felt Ornament", "Needle Felted Ornament")),
        # Others also takes every other ornament sub product type trackingis lists (checked 19/10/2026)
        ("Others", ("Linen ornament", "Flat Patchwork Ornament", "Quilted Patchwork Ornament", "Patchwork Ornament", "Crochet Ornament",
                    "Wooden Garland", "2-layer Wood Orn", "ball ornament", "embroidered ornament", "Embroidery Hoop Ornament")),
    ),
    plan_setting="ornament_plan_sheet_id",
    # trackingis cannot tell acrylic from wood ornaments apart
    plan_groups={"acrylic": "Acrylic + Wood", "wood": "Acrylic + Wood", "shaker": "Shaker", "ceramic": "Ceramic", "glass": "Glass",
                 "shell": "Shell", "felt": "Felt", "ornament khác": "Others"},
    plan_other="Others",
    # trackingis counts a multi-piece Felt Ornament as 1: 170 pcs missing over 01–18/10/2026
    quantity_fixes={"Felt Ornament": _spread(170, date(2026, 10, 1), 18)},
    fix_note="includes pieces trackingis misses, added by hand (Felt Ornament: +170 pcs over 01–18/10/2026)",
)

# One product type: the plan's T-shirt and Sweatshirt columns are compared together, the sub product types are actuals only
SHIRT = Family(
    key="shirt",
    name="Shirt",
    groups=(("Shirt", ("Shirt", "Sweatshirt", "No Brand Shirt", "Patchwork Shirt", "Comfort Color", "Baby Tee")),),
    plan_setting="shirt_plan_sheet_id",
    plan_groups={},
    plan_other="Shirt",
)

FAMILIES: dict[str, Family] = {f.key: f for f in (ORNAMENT, SHIRT)}
