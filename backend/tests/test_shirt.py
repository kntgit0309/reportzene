from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.models import SheetSource
from app.services import trackingis
from app.services.families import SHIRT
from app.services.family_plan import parse, plan_for
from tests.test_report import _save_token

S = "/api/v1/report/etsy/shirt"
ORDERS = {s: i + 1 for i, s in enumerate(SHIRT.sub_types)}  # orders per day of each sub product type (date view)
DAYS = ("2026-10-01", "2026-10-02")
STORES = [("PunGanterdesign", 1, 3), ("CuongCafCrochet", 2, 2), ("AuthenticJJ", 3, 1), ("NewShop", 9, 4)]  # name, id, orders per sub type

HEADER = [f"Column {i}" for i in range(1, 20)]
HEADER[9], HEADER[13], HEADER[17] = "10-2026", "11-2026", "12-2026"  # the month sits over its block, as in "KH Shirt"
LABELS = dict(zip(HEADER, ["Shop Name", "Team", "Ngày 1st sale", "Ngày gỡ hold 100%", "Ngày reserve", "Ngày gỡ reserve", "% Reserve", "",
                           "Total", "T-shirt", "Sweatshirt", "", "Total", "T-shirt", "Sweatshirt", "", "Total", "T-shirt", "Sweatshirt"],
                  strict=True))


def _row(first: list[str], *months: tuple[int, int]) -> dict[str, str]:
    """First 8 columns, then per month: Total, T-shirt, Sweatshirt, a blank column between months (layout of "KH Shirt")."""
    cells = first + [""] * (8 - len(first))
    for i, (tee, sweat) in enumerate(months):
        cells += ([""] if i else []) + [str(tee + sweat), str(tee or ""), str(sweat or "")]
    return dict(zip(HEADER, cells + [""] * (19 - len(cells)), strict=True))


ROWS = [
    LABELS,
    _row([], (2750, 500), (2050, 650)),  # all-shops total row: not a shop
    _row(["PunGanterdesign", "Etsy 1", "", "", "", "", "", "x"], (1000, 100), (800, 100), (400, 100)),
    _row(["CuongCafCrochet", "Etsy 2", "", "", "8/17/2026", "11/15/2026", "0.75", "x"], (250, 0), (150, 0), (150, 0)),
    _row(["Daisyfloralsshop", "Etsy 2", "7/23/2026"], (0, 100), (0, 150), (0, 200)),
    _row(["", "Etsy 1", "5000", "2200"], (2000, 200)),  # per-team summary: not a shop
]
OCT_PLAN = 1100 + 250 + 100


@pytest.fixture()
def upstream(monkeypatch):
    """Fake trackingis: date view sells ORDERS[s] orders a day of every sub type in the filter; store view sells k orders of each."""
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        q = parse_qs(urlparse(str(req.url)).query)
        subs = q.get("sub_product_types[]", [])
        if q["view"] == ["store"]:
            n = len(subs)
            rows = [{"shop_name": name, "shop_id": i, "total_order": k * n, "total_quantity": 2 * k * n, "total": 11.0 * k * n,
                     "sale_tax": 1.0 * k * n, "total_revenue": 10.0 * k * n} for name, i, k in STORES]
        else:
            n = sum(ORDERS.get(s, 0) for s in subs)
            rows = [{"date_at": d, "total_order": n, "total_quantity": 2 * n, "total": 11.0 * n, "sale_tax": 1.0 * n,
                     "total_revenue": 10.0 * n} for d in DAYS]
        return httpx.Response(200, json={"success": True, "data": {"data": rows, "paging": {"current_page": 1, "per_page": 200,
                                                                                              "total": len(rows), "last_page": 1}}})

    monkeypatch.setattr(trackingis, "TEST_TRANSPORT", httpx.MockTransport(handler))
    return calls


@pytest.fixture()
def plan_sheet(client, db_factory, admin):
    _save_token(client, admin, teams=["12", "13", "23"])
    with db_factory() as s:
        sheet = SheetSource(name="KH Shirt", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="Shirt",
                            header=HEADER, rows=ROWS, row_count=len(ROWS))
        s.add(sheet)
        s.commit()
    saved = client.put("/api/v1/settings", json={"family_plan_sheets": {"shirt": sheet.id}}, headers=admin).json()["data"]
    assert saved["family_plan_sheets"] == {"shirt": sheet.id}
    return sheet


def test_shirt_plan_counts_t_shirt_and_sweatshirt_together():
    plan = parse(HEADER, ROWS, SHIRT)
    assert plan["months"] == ["10-2026", "11-2026", "12-2026"]
    assert [s["shop"] for s in plan["shops"]] == ["PunGanterdesign", "CuongCafCrochet", "Daisyfloralsshop"]
    assert plan["shops"][0]["plan"]["10-2026"] == {"Shirt": 1100} and plan["shops"][2]["plan"]["12-2026"] == {"Shirt": 200}
    assert plan_for(plan, "2026-10-01", "2026-10-31")["groups"] == {"Shirt": {"plan": OCT_PLAN, "plan_month": OCT_PLAN}}


def test_shirt_report_is_one_product_type_opening_onto_its_sub_types(client, member, upstream, plan_sheet):
    data = client.get(f"{S}?date_from=2026-10-01&date_to=2026-10-02", headers=member).json()["data"]

    assert data["family"] == {"key": "shirt", "name": "Shirt", "sub_types": list(SHIRT.sub_types)} and data["fix_note"] is None
    [shirt] = data["groups"]
    assert shirt["name"] == "Shirt" and [c["name"] for c in shirt["children"]] == list(SHIRT.sub_types)
    assert shirt["total_order"] == 2 * sum(ORDERS.values()) == data["total"]["total_order"]
    comfort = next(c for c in shirt["children"] if c["name"] == "Comfort Color")
    assert comfort["total_order"] == 2 * ORDERS["Comfort Color"] and [d["date_at"] for d in comfort["daily"]] == list(DAYS)

    # the plan's T-shirt and Sweatshirt together, for 2 of October's 31 days
    assert data["plan"]["sheet"]["name"] == "KH Shirt" and data["plan"]["scope"] == "ZenE"
    assert shirt["plan"] == data["total"]["plan"] == round(OCT_PLAN * 2 / 31, 1) and shirt["plan_month"] == OCT_PLAN
    assert data["total"]["achieved"] == round(data["total"]["total_quantity"] / data["total"]["plan"], 4)

    # one query for the total, one for the product type, one per sub product type, all on shirt sub product types only
    assert len(upstream) == 1 + 1 + len(SHIRT.sub_types)
    for req in upstream:
        assert set(parse_qs(urlparse(str(req.url)).query)["sub_product_types[]"]) <= set(SHIRT.sub_types)


def test_shirt_plan_sheet_is_its_own_setting(client, member, upstream, plan_sheet):
    ornament = client.get("/api/v1/report/etsy/ornament?date_from=2026-10-01&date_to=2026-10-02", headers=member).json()["data"]
    assert "No ornament plan sheet" in ornament["plan"]["error"]
    assert client.get("/api/v1/report/etsy/no-such-family", headers=member).status_code == 422


def test_shirt_accounts_open_onto_sub_product_types(client, admin, member, upstream, plan_sheet):
    client.put("/api/v1/settings", json={"account_replacements": [{"suspended": "CuongCafCrochet", "replacement": "AuthenticJJ"}]},
               headers=admin)
    data = client.get(f"{S}/accounts?date_from=2026-10-01&date_to=2026-10-31", headers=member).json()["data"]
    every = len(SHIRT.sub_types)

    # plan stores in sheet order (AuthenticJJ in place of suspended CuongCafCrochet), then the others
    assert [a["shop"] for a in data["accounts"]] == ["PunGanterdesign", "AuthenticJJ", "Daisyfloralsshop", "NewShop"]
    pun, authentic, daisy, new = data["accounts"]
    assert pun["plan"] == 1100 and pun["total_order"] == 3 * every
    assert [c["name"] for c in pun["children"]] == list(SHIRT.sub_types) and all("plan" not in c for c in pun["children"])
    assert authentic["replaces"] == ["CuongCafCrochet"] and authentic["plan"] == 250 and authentic["total_order"] == (2 + 1) * every
    assert daisy["plan"] == 100 and daisy["total_order"] == 0 and daisy["children"] == []
    assert not new["in_plan"] and new["plan"] is None
    assert data["total"]["plan"] == OCT_PLAN
    assert len(upstream) == 1 + every  # store view for every shirt, then one per sub product type
