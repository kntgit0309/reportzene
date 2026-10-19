from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.models import AppSetting, SheetSource
from app.services import trackingis
from app.services.families import BLANKET
from app.services.family_plan import parse, plan_for
from app.services.settings_store import KEY
from tests.test_report import _save_token

B = "/api/v1/report/etsy/blanket"
ORDERS = {"Blanket": 3, "Woven Blanket": 2, "Quilted Blanket": 1}  # orders per day (date view) / per store (store view) of each
DAYS = ("2026-10-01", "2026-10-02")
STORES = [("PunGanterdesign", 1), ("ToochaStore", 2), ("NewShop", 9)]

CATS = ["Velveteen", "Woven", "Quilted"]
HEADER = [f"Column {i}" for i in range(1, 23)]
HEADER[9], HEADER[14], HEADER[19] = "10-2026", "11-2026", "12-2026"  # the month sits over its block, as in "KH Blanket"
LABELS = dict(zip(HEADER, ["Shop Name", "Team", "Ngày 1st sale", "Ngày gỡ hold 100%", "Ngày reserve", "Ngày gỡ reserve", "% Reserve", "",
                           "Total", *CATS, "", "Total", *CATS, "", "Total", *CATS], strict=True))


def _row(first: list[str], *months: tuple[int, int, int]) -> dict[str, str]:
    """First 8 columns, then per month: Total, Velveteen, Woven, Quilted, a blank column between months (layout of "KH Blanket")."""
    cells = first + [""] * (8 - len(first))
    for i, cats in enumerate(months):
        cells += ([""] if i else []) + [str(sum(cats)), *(str(c) if c else "" for c in cats)]
    return dict(zip(HEADER, cells + [""] * (22 - len(cells)), strict=True))


ROWS = [
    LABELS,
    _row([], (1020, 700, 30)),  # all-shops total row: not a shop
    _row(["PunGanterdesign", "Etsy 1", "", "", "", "", "", "x"], (250, 100, 0), (400, 200, 0)),
    _row(["ToochaStore", "Etsy 1", "7/24/2026"], (0, 0, 30), (0, 0, 70)),
    _row(["Daisyfloralsshop", "Etsy 2"], (100, 100, 0), (200, 150, 50)),
    _row(["", "Etsy 1", "4270", "1050"], (520, 500, 30)),  # per-team summary: not a shop
]


@pytest.fixture()
def upstream(monkeypatch):
    """Fake trackingis: date view sells ORDERS[s] orders a day of every sub type in the filter; store view k orders of each."""
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        q = parse_qs(urlparse(str(req.url)).query)
        n = sum(ORDERS.get(s, 0) for s in q.get("sub_product_types[]", []))
        if q["view"] == ["store"]:
            rows = [{"shop_name": name, "shop_id": i + 1, "total_order": k * n, "total_quantity": k * n, "total": 11.0 * k * n,
                     "sale_tax": 1.0 * k * n, "total_revenue": 10.0 * k * n} for i, (name, k) in enumerate(STORES)]
        else:
            rows = [{"date_at": d, "total_order": n, "total_quantity": n, "total": 11.0 * n, "sale_tax": 1.0 * n, "total_revenue": 10.0 * n}
                    for d in DAYS]
        return httpx.Response(200, json={"success": True, "data": {"data": rows, "paging": {"current_page": 1, "per_page": 200,
                                                                                              "total": len(rows), "last_page": 1}}})

    monkeypatch.setattr(trackingis, "TEST_TRANSPORT", httpx.MockTransport(handler))
    return calls


@pytest.fixture()
def plan_sheet(client, db_factory, admin):
    _save_token(client, admin, teams=["12", "13", "23"])
    with db_factory() as s:
        sheet = SheetSource(name="KH Blanket", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="Blanket",
                            header=HEADER, rows=ROWS, row_count=len(ROWS))
        s.add(sheet)
        s.commit()
    client.put("/api/v1/settings", json={"family_plan_sheets": {"blanket": sheet.id}}, headers=admin)
    return sheet


def test_blanket_plan_categories_are_its_product_types():
    plan = parse(HEADER, ROWS, BLANKET)
    assert [s["shop"] for s in plan["shops"]] == ["PunGanterdesign", "ToochaStore", "Daisyfloralsshop"]
    assert plan["shops"][0]["plan"]["10-2026"] == {"Velveteen": 250, "Woven": 100, "Quilted": 0}
    october = plan_for(plan, "2026-10-01", "2026-10-31")["groups"]
    assert october == {"Velveteen": {"plan": 350, "plan_month": 350}, "Woven": {"plan": 200, "plan_month": 200},
                       "Quilted": {"plan": 30, "plan_month": 30}}


def test_blanket_report_compares_each_product_type_with_its_plan(client, member, upstream, plan_sheet):
    data = client.get(f"{B}?date_from=2026-10-01&date_to=2026-10-31", headers=member).json()["data"]

    assert [(g["name"], [c["name"] for c in g["children"]]) for g in data["groups"]] == [
        ("Velveteen", ["Blanket"]), ("Woven", ["Woven Blanket"]), ("Quilted", ["Quilted Blanket"])]
    velveteen, woven, quilted = data["groups"]
    assert velveteen["total_quantity"] == 2 * ORDERS["Blanket"] and velveteen["plan"] == 350 and velveteen["plan_month"] == 350
    assert woven["plan"] == 200 and quilted["plan"] == 30 and quilted["achieved"] == round(quilted["total_quantity"] / 30, 4)
    assert data["total"]["plan"] == 350 + 200 + 30 and data["plan"]["sheet"]["name"] == "KH Blanket"
    assert "daily" not in velveteen["children"][0]  # several product types: the chart stacks them, not their sub types
    assert len(upstream) == 1 + 3 + 3


def test_blanket_accounts_open_onto_product_types_with_their_plan(client, member, upstream, plan_sheet):
    data = client.get(f"{B}/accounts?date_from=2026-10-01&date_to=2026-10-31", headers=member).json()["data"]

    assert [a["shop"] for a in data["accounts"]] == ["PunGanterdesign", "ToochaStore", "Daisyfloralsshop", "NewShop"]
    pun = data["accounts"][0]
    assert pun["plan"] == 350 and pun["total_quantity"] == sum(ORDERS.values())
    assert {c["name"]: c["plan"] for c in pun["children"]} == {"Velveteen": 250, "Woven": 100, "Quilted": 0}
    assert data["total"]["plan"] == 350 + 200 + 30


def test_plan_sheets_saved_per_field_before_still_count(client, db_factory, admin):
    with db_factory() as s:
        s.add(AppSetting(key=KEY, value={"ornament_plan_sheet_id": 4, "shirt_plan_sheet_id": 5}))
        s.commit()
    assert client.get("/api/v1/settings", headers=admin).json()["data"]["family_plan_sheets"] == {"ornament": 4, "shirt": 5}

    saved = client.put("/api/v1/settings", json={"family_plan_sheets": {"blanket": 6}}, headers=admin).json()["data"]
    assert saved["family_plan_sheets"] == {"ornament": 4, "shirt": 5, "blanket": 6}
    with db_factory() as s:
        assert "ornament_plan_sheet_id" not in s.get(AppSetting, KEY).value
    saved = client.put("/api/v1/settings", json={"family_plan_sheets": {"ornament": 0}}, headers=admin).json()["data"]
    assert saved["family_plan_sheets"] == {"shirt": 5, "blanket": 6}
    assert client.put("/api/v1/settings", json={"family_plan_sheets": {"no-such-family": 7}}, headers=admin).status_code == 422
