"""Product families with their own Etsy page (Etsy › Ornament, Shirt, Blanket, Quilted, Flag, Wooden Block, Badge Reel, Others): the
team's grouping of trackingis sub product types into product types, and how the family's plan sheet (KH Ornament, KH Shirt…)
maps onto it.
Adding a family: an entry here and in web/src/lib/families.ts; its plan sheet is picked in Settings › Plan."""
from dataclasses import dataclass, field, replace
from datetime import date, timedelta


@dataclass(frozen=True)
class Family:
    key: str  # URL, cache key, Settings › Plan key and MCP tool name: /report/etsy/<key>, etsy_<key>
    name: str
    # Product type → trackingis sub product types (names exactly as trackingis lists them)
    groups: tuple[tuple[str, tuple[str, ...]], ...]
    plan_groups: dict[str, str]  # plan category (lower case) → product type; any other category goes to `plan_other`
    plan_other: str
    plan_note: str  # how the plan's categories map onto the product types, for agents (MCP)
    # Quantity trackingis misses, added by hand: sub product type → {day: pieces}; only in the team-wide view
    quantity_fixes: dict[str, dict[str, int]] = field(default_factory=dict)
    fix_note: str | None = None
    # Product type taking every trackingis sub product type no family lists (Others); its rows are trackingis product types
    rest_group: str | None = None

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
    # trackingis cannot tell acrylic from wood ornaments apart
    plan_groups={"acrylic": "Acrylic + Wood", "wood": "Acrylic + Wood", "shaker": "Shaker", "ceramic": "Ceramic", "glass": "Glass",
                 "shell": "Shell", "felt": "Felt", "ornament khác": "Others"},
    plan_other="Others",
    plan_note='the plan\'s Acrylic and Wood count together as "Acrylic + Wood", "Ornament khác" as Others',
    # trackingis counts a multi-piece Felt Ornament as 1: 170 pcs missing over 01–18/10/2026, then 130 over 19–22/10/2026
    # (the team's count: 803 pcs to 22/10 against 673 in ReportZenE)
    quantity_fixes={"Felt Ornament": {**_spread(170, date(2026, 10, 1), 18), **_spread(130, date(2026, 10, 19), 4)}},
    fix_note="includes pieces trackingis misses, added by hand (Felt Ornament: +170 pcs over 01–18/10 and +130 over 19–22/10/2026)",
)

# One product type: the plan's T-shirt and Sweatshirt columns are compared together, the sub product types are actuals only
SHIRT = Family(
    key="shirt",
    name="Shirt",
    groups=(("Shirt", ("Shirt", "Sweatshirt", "No Brand Shirt", "Patchwork Shirt", "Comfort Color", "Baby Tee")),),
    plan_groups={},
    plan_other="Shirt",
    plan_note="the plan's T-shirt and Sweatshirt count together as Shirt",
)

# Product types named as in KH Blanket, each sold on trackingis as one sub product type
BLANKET = Family(
    key="blanket",
    name="Blanket",
    groups=(("Velveteen", ("Blanket",)), ("Woven", ("Woven Blanket",)), ("Quilted", ("Quilted Blanket",))),
    plan_groups={"velveteen": "Velveteen", "woven": "Woven", "quilted": "Quilted"},
    plan_other="Others",
    plan_note="the plan's Velveteen, Woven and Quilted are the product types of the same name",
)

# Product types named as in KH Quilted, each sold on trackingis as one sub product type. The sheet's labels are matched in both
# spellings (the team writes "Laudry" and "Weeken"); a category it does not know goes to "Others" and counts in the total only.
QUILTED = Family(
    key="quilted",
    name="Quilted",
    groups=(("Quilted Tote Bag", ("Quilted Tote Bag",)), ("Quilted Laundry Basket", ("Quilted Laundry Basket",)),
            ("Quilted Weekend Bag", ("Quilted Weekend Bag",)), ("Quilted Table Runner", ("Quilted Table Runner",))),
    plan_groups={"quilted tote bag": "Quilted Tote Bag", "tote bag": "Quilted Tote Bag",
                 "quilted laundry basket": "Quilted Laundry Basket", "quilted laudry basket": "Quilted Laundry Basket",
                 "laundry basket": "Quilted Laundry Basket", "laudry basket": "Quilted Laundry Basket",
                 "quilted weekend bag": "Quilted Weekend Bag", "quilted weeken bag": "Quilted Weekend Bag",
                 "weekend bag": "Quilted Weekend Bag", "weeken bag": "Quilted Weekend Bag",
                 "quilted table runner": "Quilted Table Runner", "table runner": "Quilted Table Runner"},
    plan_other="Others",
    plan_note="the plan's Quilted Tote Bag, Laundry Basket, Weekend Bag and Table Runner are the product types of the same name",
)

# One product type, like Shirt; KH Flag has a Total per month and no categories
FLAG = Family(
    key="flag",
    name="Flag",
    groups=(("Flag", ("Garden Flag", "House Flag", "Flag", "Patchwork Garden Flag", "fan flag", "Banner")),),
    plan_groups={},
    plan_other="Flag",
    plan_note="the plan has one Total per month, for Flag as a whole",
)

# One product type each, like Flag; their KH sheets have one value per month and no categories
WOODEN_BLOCK = Family(
    key="wooden_block",
    name="Wooden Block",
    groups=(("Wooden Block", ("3D Wooden Block", "Wooden Block")),),
    plan_groups={},
    plan_other="Wooden Block",
    plan_note="the plan has one value per month, for Wooden Block as a whole",
)
BADGE_REEL = Family(
    key="badge_reel",
    name="Badge Reel",
    groups=(("Badge Reel", ("badge reel", "shaker badge reel", "Badge Reel 2-layers", "Badge Buddy", "Combo Badge Reel + Buddy",
                            "ID Badge Holder")),),
    plan_groups={},
    plan_other="Badge Reel",
    plan_note="the plan has one Total per month, for Badge Reel as a whole",
)

# The products of KH SP khác (planned per product for ZenE as a whole, not per shop), and every sub product type no other
# family lists. "Car Sticker" and "UV DTF Car Sticker" are not in trackingis' sub product type list yet (19/10/2026).
OTHERS = Family(
    key="others",
    name="Others",
    groups=(("Sticker", ("Bumper Sticker", "Peeker Sticker", "UV DTF Sticker", "Car Sticker", "UV DTF Car Sticker", "Sticker")),
            ("Scrub cap", ("Scrub cap",)), ("Fabric Welcome Sign", ("Fabric Welcome Sign",)), ("Baseball Jersey", ("Baseball Jersey",))),
    plan_groups={"sticker": "Sticker", "scrub cap": "Scrub cap", "fabric welcome sign": "Fabric Welcome Sign",
                 "baseball jersey": "Baseball Jersey"},
    plan_other="Other products",
    plan_note="KH SP khác plans per product (Sticker, Scrub cap, Fabric Welcome Sign, Baseball Jersey) for ZenE as a whole",
    rest_group="Other products",
)

FAMILIES: dict[str, Family] = {f.key: f for f in (ORNAMENT, SHIRT, BLANKET, QUILTED, FLAG, WOODEN_BLOCK, BADGE_REEL, OTHERS)}


def with_rest(family: Family, all_sub_types: list[str]) -> Family:
    """The family with its rest group: every trackingis sub product type (in trackingis order) that no family lists.
    A family without a rest group, or with nothing left over, is returned as it is."""
    if not family.rest_group:
        return family
    listed = {s.lower() for f in FAMILIES.values() for s in f.sub_types}
    rest = tuple(s for s in all_sub_types if s.lower() not in listed)
    return replace(family, groups=(*family.groups, (family.rest_group, rest))) if rest else family
