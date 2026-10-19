from app.models import SheetSource
from app.services.families import BADGE_REEL, WOODEN_BLOCK
from app.services.family_plan import parse, plan_for
from tests.test_flag import HEADER as FLAG_HEADER
from tests.test_flag import LABELS as FLAG_LABELS
from tests.test_flag import _row as flag_row
from tests.test_flag import upstream  # noqa: F401  (fixture: sells every sub product type it does not know as 0)
from tests.test_report import _save_token

# "KH Wooden Block": the header row is the label row and each month is the label of its only column
WB_HEADER = ["Shop Name", "Team", "Ngày 1st sale", "Ngày gỡ hold 100%", "Ngày reserve", "Ngày gỡ reserve", "% Reserve", "Column 8",
             "10-2026", "Column 10", "11-2026", "Column 12", "12-2026"]


def _wb_row(shop: str, team: str, *months: int) -> dict[str, str]:
    cells = [shop, team, "", "", "", "", "", ""]
    for i, pcs in enumerate(months):
        cells += ([""] if i else []) + [str(pcs)]
    return dict(zip(WB_HEADER, cells + [""] * (13 - len(cells)), strict=True))


WB_ROWS = [
    _wb_row("", "", 660, 1240, 1300),  # all-shops total row: not a shop
    _wb_row("PunGanterdesign", "Etsy 1", 100, 200, 250),
    _wb_row("ReboundSevicesShop", "Etsy 1", 50, 100, 120),
    _wb_row("", "Total", 0, 0, 0),  # summary under the shops: not a shop
]


def test_wooden_block_plan_reads_months_labelled_in_the_header_row():
    plan = parse(WB_HEADER, WB_ROWS, WOODEN_BLOCK)
    assert plan["months"] == ["10-2026", "11-2026", "12-2026"]
    assert [s["shop"] for s in plan["shops"]] == ["PunGanterdesign", "ReboundSevicesShop"]
    assert plan["shops"][0]["plan"]["11-2026"] == {"Wooden Block": 200}
    assert plan_for(plan, "2026-10-01", "2026-10-31")["groups"] == {"Wooden Block": {"plan": 150, "plan_month": 150}}


def test_badge_reel_plan_has_a_total_per_month_like_flag():
    rows = [FLAG_LABELS, flag_row([], 600, 1200, 1500), flag_row([], 1020, 1280, 1300),  # two all-shops rows: not shops
            flag_row(["PunGanterdesign", "Etsy 1"], 150, 200, 200), flag_row(["ToochaStore", "Etsy 1", "7/24/2026"])]
    plan = parse(FLAG_HEADER, rows, BADGE_REEL)
    assert [s["shop"] for s in plan["shops"]] == ["PunGanterdesign", "ToochaStore"]
    assert plan_for(plan, "2026-12-01", "2026-12-31")["groups"] == {"Badge Reel": {"plan": 200, "plan_month": 200}}


def test_wooden_block_and_badge_reel_pages(client, db_factory, admin, member, upstream):  # noqa: F811
    _save_token(client, admin, teams=["12", "13", "23"])
    with db_factory() as s:
        sheet = SheetSource(name="KH Wooden Block", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="Wooden Block",
                            header=WB_HEADER, rows=WB_ROWS, row_count=len(WB_ROWS))
        s.add(sheet)
        s.commit()
    client.put("/api/v1/settings", json={"family_plan_sheets": {"wooden_block": sheet.id}}, headers=admin)

    wb = client.get("/api/v1/report/etsy/wooden_block?date_from=2026-10-01&date_to=2026-10-31", headers=member).json()["data"]
    assert [(g["name"], [c["name"] for c in g["children"]]) for g in wb["groups"]] == [("Wooden Block", ["3D Wooden Block", "Wooden Block"])]
    assert wb["total"]["plan"] == 150 and wb["plan"]["sheet"]["name"] == "KH Wooden Block"

    badge = client.get("/api/v1/report/etsy/badge_reel?date_from=2026-10-01&date_to=2026-10-31", headers=member).json()["data"]
    assert [c["name"] for c in badge["groups"][0]["children"]] == list(BADGE_REEL.sub_types)
    assert "ID Badge Holder" in BADGE_REEL.sub_types and "No badge reel plan sheet" in badge["plan"]["error"]
