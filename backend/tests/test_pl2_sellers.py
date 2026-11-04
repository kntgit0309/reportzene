"""Etsy › Report, PL2 per seller: KT (seller view × PL2/item) next to the seller plan sheet and the seller CF sheets."""
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.models import SheetSource
from app.services import report, trackingis
from tests.test_overview import business_plan  # noqa: F401  (fixture: KHKD with Ornament $6, Blanket $8, Shirt $5.5 PL2/item)
from tests.test_seller_cf import HEADER as CF_HEADER  # "1.2 P&L Seller (Sau IP)_Monthly": Anh NTM, Linh PT, AN NTT
from tests.test_seller_cf import ROWS as CF_ROWS
from tests.test_seller_plan import seller_sheet  # noqa: F401  (fixture: plan sheet with Huyền, Vân and Linh)

S = "/api/v1/report/etsy/pl2/sellers?date_from=2026-10-01&date_to=2026-10-02"
SUBS = ["Cutout Ornament", "Blanket", "Shirt"]
SELLERS = [{"id": "41", "name": "Linh PT.ETS"}, {"id": "42", "name": "Khoa NT"}, {"id": "43", "name": "Huyền HTN.ETS"},
           {"id": "44", "name": "Mai VTT"}]
SOLD = {"Linh PT.ETS": 10, "Huyền HTN.ETS": 4, "Khoa NT": 3, "Mai VTT": 0}  # pieces of each priced product; Khoa has no sheet row
ASKED: list[dict[str, list[str]]] = []
MONTH_PLAN = {"Huyền": 9149, "Vân": 0, "Linh": 8938}  # PL2 T10 of the seller plan sheet
TO_DATE = 2 / 31  # 01–02/10 of October's 31 days
KT_PER_PIECE = 6 + 8 + 5.5  # one piece of each priced product


@pytest.fixture()
def upstream(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/filter/sub-product-type"):
            return httpx.Response(200, json={"success": True, "data": [{"value": n, "label": n} for n in SUBS]})
        query = parse_qs(urlparse(str(req.url)).query)
        ASKED.append(query)
        rows = [{"seller_name": name, "total_order": k, "total_quantity": k, "total": 0, "sale_tax": 0, "total_revenue": 10.0 * k}
                for name, k in SOLD.items()]
        return httpx.Response(200, json={"success": True, "data": {"data": rows, "paging": {"current_page": 1, "per_page": 200,
                                                                                              "total": len(rows), "last_page": 1}}})

    monkeypatch.setattr(trackingis, "TEST_TRANSPORT", httpx.MockTransport(handler))


@pytest.fixture()
def sellers(monkeypatch):
    monkeypatch.setattr(report, "filter_options", lambda db, kind, user=None: (
        [{"id": n, "name": n} for n in SUBS] if kind == "sub_product_types" else SELLERS if kind == "sellers" else []))


@pytest.fixture()
def cf_sheet(client, db_factory, admin):
    with db_factory() as s:
        sheet = SheetSource(name="Etsy 2 P&L Seller", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="1.2 P&L Seller (Sau IP)_Monthly",
                            header=CF_HEADER, rows=CF_ROWS, row_count=len(CF_ROWS))
        s.add(sheet)
        s.commit()
    client.put("/api/v1/settings", json={"seller_cf_sheets": [str(sheet.id)]}, headers=admin)
    return sheet


def test_pl2_per_seller_kt_plan_and_cf(client, member, upstream, business_plan, seller_sheet, cf_sheet, sellers):  # noqa: F811
    ASKED.clear()
    data = client.get(S, headers=member).json()["data"]
    # one seller view per priced product, on its sub product types
    assert sorted(a["sub_product_types[]"][0] for a in ASKED) == ["Blanket", "Cutout Ornament", "Shirt"]
    assert all(a["view"] == ["seller"] for a in ASKED)

    rows = {r["seller"]: r for r in data["sellers"]}
    # the plan sheet's sellers first in its order (Mai has no figures there), then the others by the size of their PL2
    assert [r["seller"] for r in data["sellers"]] == ["Huyền", "Vân", "Linh", "AN NTT", "Khoa NT"]
    assert [r["in_plan"] for r in data["sellers"]] == [True, True, True, False, False]
    linh = rows["Linh"]
    plan = 8938 * TO_DATE
    assert linh["sellers"] == ["Linh PT.ETS"] and linh["quantity"] == 30  # 10 pieces of each of the 3 priced products
    assert linh["plan"] == round(plan, 2) and linh["kt"] == 10 * KT_PER_PIECE and linh["cf"] == 2571.47  # "Profit tính KPI", October
    assert linh["kt_gap"] == round(10 * KT_PER_PIECE - plan, 2) and linh["cf_gap"] == round(2571.47 - plan, 2)
    assert linh["kt_pct"] == round(10 * KT_PER_PIECE / plan, 4) and linh["cf_pct"] == round(2571.47 / plan, 4)
    assert linh["cf_minus_kt"] == round(2571.47 - 10 * KT_PER_PIECE, 2)
    huyen = rows["Huyền"]
    assert huyen["sellers"] == ["Huyền HTN.ETS"] and huyen["kt"] == 4 * KT_PER_PIECE and huyen["cf"] is None  # finance has no row for her
    assert huyen["plan"] == round(9149 * TO_DATE, 2) and huyen["cf_gap"] is None and huyen["cf_minus_kt"] is None
    assert rows["Vân"]["plan"] == 0 and rows["Vân"]["kt"] == 0 and rows["Vân"]["kt_pct"] is None  # a plan of $0: no percentage
    # outside the plan sheet: listed for the PL2 they have (KT or CF), and their whole PL2 is the gap against a plan of $0
    assert "Anh NTM" not in rows and "Mai" not in rows and "Mai VTT" not in rows  # nothing booked, nothing sold
    khoa, an = rows["Khoa NT"], rows["AN NTT"]
    assert khoa["plan"] is None and khoa["kt"] == 3 * KT_PER_PIECE and khoa["kt_gap"] == khoa["kt"]
    assert an["quantity"] == 0 and an["kt"] == 0 and an["cf"] == 13514.58 and an["cf_gap"] == 13514.58

    total = data["total"]
    assert total["seller"] == "All sellers" and total["quantity"] == 30 + 12 + 9
    assert total["plan"] == round(sum(r["plan"] for r in data["sellers"] if r["plan"] is not None), 2)
    assert total["kt"] == round(sum(r["kt"] for r in data["sellers"]), 2)
    assert total["cf"] == round(2571.47 + 13514.58, 2)
    assert total["kt_gap"] == round(total["kt"] - total["plan"], 2) == round(sum(r["kt_gap"] for r in data["sellers"]), 2)
    assert data["plan"]["months"] == ["T10", "T11", "T12"] and data["plan"]["missing"] == [] and data["kt"] == {}
    assert data["cf"]["sheets"][0]["name"] == "Etsy 2 P&L Seller" and data["cf"]["missing"] == []


def test_a_range_outside_the_sheets_months_has_no_plan_or_cf(client, member, upstream, business_plan, seller_sheet, cf_sheet, sellers):  # noqa: F811
    data = client.get("/api/v1/report/etsy/pl2/sellers?date_from=2027-03-01&date_to=2027-03-02", headers=member).json()["data"]
    assert data["plan"]["missing"] == ["03-2027"]  # the plan sheet only has T10–T12
    linh = next(r for r in data["sellers"] if r["seller"] == "Linh")
    assert linh["plan"] is None and linh["kt_gap"] is None and linh["kt"] == 10 * KT_PER_PIECE


def test_filters_that_cut_across_stores_leave_plan_and_cf_out(client, member, upstream, business_plan, seller_sheet, cf_sheet, sellers):  # noqa: F811
    data = client.get(f"{S}&shops=5", headers=member).json()["data"]
    assert "per seller" in data["plan"]["error"] and "per seller" in data["cf"]["error"]
    assert all(r["plan"] is None and r["cf"] is None and r["kt_gap"] is None for r in data["sellers"])
    # no sheet to compare with: sellers are the trackingis ones with a PL2, the biggest first
    assert [r["seller"] for r in data["sellers"]] == ["Linh PT.ETS", "Huyền HTN.ETS", "Khoa NT"]
    assert data["sellers"][0]["kt"] == 10 * KT_PER_PIECE and data["total"]["plan"] is None


def test_without_the_seller_sheets_it_still_shows_kt(client, member, upstream, business_plan, sellers):  # noqa: F811
    data = client.get(S, headers=member).json()["data"]
    assert "seller plan sheet" in data["plan"]["error"] and "seller CF sheets" in data["cf"]["error"]
    assert [r["seller"] for r in data["sellers"]] == ["Linh PT.ETS", "Huyền HTN.ETS", "Khoa NT"] and data["total"]["kt"] == 17 * KT_PER_PIECE


def test_a_seller_filter_keeps_their_rows_only_and_a_member_limited_to_their_sales_sees_nothing_else(
        client, admin, member, upstream, business_plan, seller_sheet, cf_sheet, sellers):  # noqa: F811
    one = client.get(f"{S}&sellers=41", headers=admin).json()["data"]
    assert [r["seller"] for r in one["sellers"]] == ["Linh"] and one["total"]["cf"] == 2571.47

    me = client.get("/api/v1/auth/me", headers=member).json()["data"]
    client.patch(f"/api/v1/users/{me['id']}", json={"scope_sellers": ["41"]}, headers=admin)
    mine = client.get(S, headers=member).json()["data"]  # Linh herself: not Huyền's or Vân's plan, nor anybody's CF
    assert [r["seller"] for r in mine["sellers"]] == ["Linh"]
    assert mine["total"]["plan"] == round(8938 * TO_DATE, 2) and mine["total"]["cf"] == 2571.47
