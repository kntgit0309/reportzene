"""Etsy › Quilted: the product types of KH Quilted (Tote Bag, Laundry Basket, Weekend Bag, Table Runner), after Blanket."""
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.models import SheetSource
from app.services import trackingis
from app.services.families import FAMILIES, QUILTED
from app.services.family_plan import parse, plan_for
from tests.test_report import _save_token

Q = "/api/v1/report/etsy/quilted"
SUBS = {"Quilted Tote Bag": 4, "Quilted Laundry Basket": 3, "Quilted Weekend Bag": 2, "Quilted Table Runner": 1}  # orders a day of each
DAYS = ("2026-10-01", "2026-10-02")
STORES = [("PunGanterdesign", 1), ("ToochaStore", 2), ("NewShop", 9)]

# the labels as the team types them in KH Quilted ("Laudry", "Weeken"): both spellings are the same product type
CATS = ["Quilted Tote Bag", "Quilted Laudry Basket", "Quilted Weeken Bag", "Quilted Table Runner"]
HEADER = [f"Column {i}" for i in range(1, 26)]
HEADER[9], HEADER[15], HEADER[21] = "10-2026", "11-2026", "12-2026"
LABELS = dict(zip(HEADER, ["Shop Name", "Team", "Ngày 1st sale", "Ngày gỡ hold 100%", "Ngày reserve", "Ngày gỡ reserve", "% Reserve", "",
                           "Total", *CATS, "", "Total", *CATS, "", "Total", *CATS], strict=True))


def _row(first: list[str], *months: tuple[int, int, int, int]) -> dict[str, str]:
    """First 8 columns, then per month: Total and the 4 categories, a blank column between months (layout of "KH Blanket")."""
    cells = first + [""] * (8 - len(first))
    for i, cats in enumerate(months):
        cells += ([""] if i else []) + [str(sum(cats)), *(str(c) if c else "" for c in cats)]
    return dict(zip(HEADER, cells + [""] * (25 - len(cells)), strict=True))


ROWS = [
    LABELS,
    _row([], (400, 300, 200, 100)),  # all-shops total row: not a shop
    _row(["PunGanterdesign", "Etsy 1"], (60, 20, 10, 10), (80, 40, 20, 10)),
    _row(["ToochaStore", "Etsy 1", "7/24/2026"], (30, 0, 0, 0), (50, 0, 0, 0)),
    _row(["", "Etsy 1", "4270", "1050"], (90, 20, 10, 10)),  # per-team summary: not a shop
]


@pytest.fixture()
def upstream(monkeypatch):
    """Fake trackingis: date view sells SUBS[s] orders a day of every sub type in the filter; store view k times that."""
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        q = parse_qs(urlparse(str(req.url)).query)
        n = sum(SUBS.get(s, 0) for s in q.get("sub_product_types[]", []))
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
        sheet = SheetSource(name="KH Quilted", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="Quilted",
                            header=HEADER, rows=ROWS, row_count=len(ROWS))
        s.add(sheet)
        s.commit()
    client.put("/api/v1/settings", json={"family_plan_sheets": {"quilted": sheet.id}}, headers=admin)
    return sheet


def test_quilted_sits_after_blanket_with_its_four_product_types():
    assert list(FAMILIES)[:4] == ["ornament", "shirt", "blanket", "quilted"]
    assert [g for g, _ in QUILTED.groups] == ["Quilted Tote Bag", "Quilted Laundry Basket", "Quilted Weekend Bag", "Quilted Table Runner"]
    assert list(QUILTED.sub_types) == [g for g, _ in QUILTED.groups]  # each is one trackingis sub product type of the same name


def test_quilted_plan_reads_the_teams_spellings_as_the_same_product_types():
    plan = parse(HEADER, ROWS, QUILTED)
    assert [s["shop"] for s in plan["shops"]] == ["PunGanterdesign", "ToochaStore"]
    assert plan["shops"][0]["plan"]["10-2026"] == {"Quilted Tote Bag": 60, "Quilted Laundry Basket": 20, "Quilted Weekend Bag": 10,
                                                   "Quilted Table Runner": 10}
    for spelling in ("Quilted Laundry Basket", "quilted laudry basket", "Laundry Basket", "Quilted Weekend Bag", "Weeken Bag"):
        assert QUILTED.plan_group(spelling) in {g for g, _ in QUILTED.groups}, spelling
    october = plan_for(plan, "2026-10-01", "2026-10-31")["groups"]
    assert october["Quilted Tote Bag"] == {"plan": 90, "plan_month": 90} and october["Quilted Laundry Basket"]["plan"] == 20
    assert QUILTED.plan_group("Quilted khác") == "Others"  # a category it does not know: in the total only


def test_quilted_report_compares_each_product_type_with_its_plan(client, member, upstream, plan_sheet):
    data = client.get(f"{Q}?date_from=2026-10-01&date_to=2026-10-31", headers=member).json()["data"]

    assert [g["name"] for g in data["groups"]] == [g for g, _ in QUILTED.groups]
    tote, laundry = data["groups"][0], data["groups"][1]
    assert tote["total_quantity"] == 2 * SUBS["Quilted Tote Bag"] and tote["plan"] == 90 and tote["plan_month"] == 90
    assert laundry["plan"] == 20 and laundry["achieved"] == round(laundry["total_quantity"] / 20, 4)
    assert data["total"]["total_quantity"] == 2 * sum(SUBS.values()) and data["total"]["plan"] == 90 + 20 + 10 + 10
    assert data["plan"]["sheet"]["name"] == "KH Quilted"
    assert len(upstream) == 1 + 4 + 4  # the total, each product type and each sub product type


def test_quilted_accounts_open_onto_product_types_with_their_plan(client, member, upstream, plan_sheet):
    data = client.get(f"{Q}/accounts?date_from=2026-10-01&date_to=2026-10-31", headers=member).json()["data"]

    assert [a["shop"] for a in data["accounts"]] == ["PunGanterdesign", "ToochaStore", "NewShop"]
    pun = data["accounts"][0]
    assert pun["plan"] == 100 and pun["total_quantity"] == sum(SUBS.values())
    assert {c["name"]: c["plan"] for c in pun["children"]} == {"Quilted Tote Bag": 60, "Quilted Laundry Basket": 20,
                                                                "Quilted Weekend Bag": 10, "Quilted Table Runner": 10}


def test_without_a_plan_sheet_the_page_still_shows_sales(client, admin, member, upstream):
    _save_token(client, admin, teams=["12", "13", "23"])
    data = client.get(f"{Q}?date_from=2026-10-01&date_to=2026-10-31", headers=member).json()["data"]
    assert "No quilted plan sheet" in data["plan"]["error"] and data["total"]["total_quantity"] == 2 * sum(SUBS.values())
