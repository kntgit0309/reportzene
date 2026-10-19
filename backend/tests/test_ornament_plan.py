import pytest

from app.core.errors import AppError
from app.models import SheetSource
from app.services import report
from app.services.families import ORNAMENT
from app.services.family_plan import month_days, parse, plan_for
from tests.test_ornament import O, upstream  # noqa: F401  (fixture)
from tests.test_report import _save_token

CATS = ["Acrylic", "Wood", "Shaker", "Ceramic", "Glass", "Shell", "Felt", "Ornament khác"]
HEADER = [f"Column {i}" for i in range(1, 38)]
HEADER[9], HEADER[19], HEADER[29] = "10-2026", "11-2026", "12-2026"  # the month sits over its block, as in the sheet


def _row(first: list[str], *months: tuple[int, list[int]]) -> dict[str, str]:
    """First 8 columns, then per month: Total + 8 categories, a blank column between months (layout of "KH Ornament")."""
    cells = first + [""] * (8 - len(first))
    for i, (total, cats) in enumerate(months):
        cells += ([""] if i else []) + [str(total), *(str(c) if c else "" for c in cats)]
    return dict(zip(HEADER, cells + [""] * (37 - len(cells)), strict=True))


LABELS = dict(zip(HEADER, ["Shop Name", "Team", "Ngày 1st sale", "Ngày gỡ hold 100%", "Ngày reserve", "Ngày gỡ reserve", "% Reserve", "",
                           "Total", *CATS, "", "Total", *CATS, "", "Total", *CATS], strict=True))
ROWS = [
    LABELS,
    _row([], (5535, [1605, 560, 490, 460, 205, 165, 1200, 850])),  # all-shops total row: not a shop
    _row(["PunGanterdesign", "Etsy 1"], (525, [215, 80, 50, 50, 30, 0, 0, 100]), (1650, [600, 300, 250, 250, 100, 0, 0, 150]),
         (1580, [600, 300, 250, 250, 100, 0, 0, 80])),
    _row(["Daisyfloralsshop", "Etsy 2", "7/23/2026"], (275, [50, 20, 30, 30, 15, 0, 100, 30]), (915, [200, 140, 100, 100, 50, 0, 250, 75]),
         (720, [200, 140, 100, 100, 50, 0, 100, 30])),
    _row(["OnebyHenry", "Etsy 3"], (940, [30, 0, 0, 10, 0, 0, 800, 100]), (1700, [60, 20, 20, 20, 20, 0, 1400, 160]),
         (640, [60, 20, 20, 20, 20, 0, 450, 50])),
    _row(["", "Etsy 1", "18695", "2710"], (2710, [1095, 350, 250, 210, 125, 90, 200, 390])),  # per-team summary: not a shop
]
OCT_FELT = 0 + 100 + 800
OCT_ACRYLIC_WOOD = (215 + 80) + (50 + 20) + (30 + 0)


def test_plan_sheet_is_read_per_shop_month_and_product_type():
    plan = parse(HEADER, ROWS, ORNAMENT)
    assert plan["months"] == ["10-2026", "11-2026", "12-2026"] and [s["shop"] for s in plan["shops"]] == ["PunGanterdesign",
                                                                                                          "Daisyfloralsshop", "OnebyHenry"]
    pun = plan["shops"][0]["plan"]["10-2026"]
    assert pun["Acrylic + Wood"] == 295 and pun["Others"] == 100 and pun["Felt"] == 0

    october = plan_for(plan, "2026-10-01", "2026-10-31")
    assert october["groups"]["Felt"] == {"plan": OCT_FELT, "plan_month": OCT_FELT}
    assert october["groups"]["Acrylic + Wood"]["plan"] == OCT_ACRYLIC_WOOD and october["missing_months"] == []
    to_date = plan_for(plan, "2026-10-01", "2026-10-19")["groups"]["Felt"]
    assert to_date == {"plan": round(OCT_FELT * 19 / 31, 1), "plan_month": OCT_FELT}
    assert plan_for(plan, "2026-10-01", "2026-10-31", teams={"etsy 3"})["groups"]["Felt"]["plan"] == 800
    one_shop = plan_for(plan, "2026-10-01", "2026-10-31", shops={"punganterdesign"})
    assert one_shop["shops"] == 1 and one_shop["groups"]["Acrylic + Wood"]["plan"] == 295
    assert plan_for(plan, "2026-10-01", "2026-10-31", shops={"no such shop"})["shops"] == 0
    assert plan_for(plan, "2026-09-25", "2026-10-31")["missing_months"] == ["09-2026"]


def test_month_days_splits_a_range_over_months():
    assert month_days("2026-10-20", "2026-11-05") == {"10-2026": (12, 31), "11-2026": (5, 30)}


def test_plan_sheet_without_its_labels_is_a_layout_error():
    with pytest.raises(AppError) as err:
        parse(HEADER, ROWS[1:], ORNAMENT)
    assert err.value.code == "ORNAMENT_PLAN_LAYOUT"


def test_ornament_report_compares_quantity_with_the_plan(client, db_factory, admin, member, upstream, monkeypatch):  # noqa: F811
    _save_token(client, admin, teams=["12", "13", "23"])
    url = f"{O}?date_from=2026-10-01&date_to=2026-10-02"
    assert "Settings" in client.get(url, headers=member).json()["data"]["plan"]["error"]

    with db_factory() as s:
        sheet = SheetSource(name="KH Ornament", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="Ornament",
                            header=HEADER, rows=ROWS, row_count=len(ROWS))
        s.add(sheet)
        s.commit()
    assert client.put("/api/v1/settings", json={"ornament_plan_sheet_id": sheet.id}, headers=admin).json()["data"][
        "ornament_plan_sheet_id"] == sheet.id

    data = client.get(url, headers=member).json()["data"]
    assert data["plan"]["scope"] == "ZenE" and data["plan"]["sheet"]["name"] == "KH Ornament"
    felt = next(g for g in data["groups"] if g["name"] == "Felt")
    assert felt["plan"] == round(OCT_FELT * 2 / 31, 1) and felt["plan_month"] == OCT_FELT
    assert felt["achieved"] == round(felt["total_quantity"] / felt["plan"], 4)
    assert data["total"]["plan"] == round(sum(g["plan"] for g in data["groups"]), 1)

    # one team: only its shops' plan
    monkeypatch.setattr(report, "filter_options", lambda db, kind, user=None: [{"id": 13, "name": "Etsy 2.ZenE"}])
    one_team = client.get(f"{url}&teams=13", headers=member).json()["data"]
    assert one_team["plan"]["scope"] == "Etsy 2" and next(g for g in one_team["groups"] if g["name"] == "Felt")["plan_month"] == 100

    seller = client.get(f"{url}&sellers=7", headers=member).json()["data"]
    assert "seller" in seller["plan"]["error"] and "plan" not in seller["groups"][0]
