"""Etsy › Report, PL2 per seller: KT (seller view × PL2/item) next to the seller plan sheet and the seller CF sheets."""
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.models import SheetSource
from app.services import report, seller_plan, trackingis
from tests.test_overview import business_plan  # noqa: F401  (fixture: KHKD with Ornament $6, Blanket $8, Shirt $5.5 PL2/item)
from tests.test_seller_cf import HEADER as CF_HEADER  # "1.2 P&L Seller (Sau IP)_Monthly": Anh NTM, Linh PT, AN NTT
from tests.test_seller_cf import _row as cf_row
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


def test_without_the_seller_sheets_it_shows_kt_against_the_built_in_plan(client, member, upstream, business_plan, sellers):  # noqa: F811
    data = client.get(S, headers=member).json()["data"]
    assert "seller CF sheets" in data["cf"]["error"]
    # no seller plan sheet: the built-in copy of the Q4 plan stands in, and says why
    assert data["plan"]["built_in"] is True and "seller plan sheet" in data["plan"]["reason"] and "error" not in data["plan"]
    assert data["plan"]["months"] == ["T10", "T11", "T12"] and data["plan"]["missing"] == [] and "sheet" not in data["plan"]
    # the plan's sellers in the sheet's order (Mai has no figures), then the trackingis sellers outside it with a PL2
    assert [r["seller"] for r in data["sellers"]] == [*seller_plan.BUILT_IN, "Khoa NT"]
    rows = {r["seller"]: r for r in data["sellers"]}
    assert rows["Linh"]["sellers"] == ["Linh PT.ETS"] and rows["Linh"]["plan"] == round(8938 * TO_DATE, 2)  # Linh's T10 of the sheet
    assert rows["Linh"]["kt"] == 10 * KT_PER_PIECE and rows["Huyền"]["kt"] == 4 * KT_PER_PIECE and rows["Thuỷ"]["kt"] == 0
    assert rows["Khoa NT"]["plan"] is None and rows["Khoa NT"]["kt_gap"] == rows["Khoa NT"]["kt"]
    assert data["total"]["kt"] == 17 * KT_PER_PIECE
    assert data["total"]["plan"] == round(sum(r["plan"] for r in data["sellers"] if r["plan"] is not None), 2)


def test_a_seller_plan_sheet_without_its_label_row_falls_back_too(client, db_factory, admin, member, upstream, business_plan, sellers):  # noqa: F811
    # imported with a Header row below the "PL2 T10 | T11 | T12" labels: the labels are not in the snapshot
    header = ["Column 1", "$445,045", "$64,798", "$209,331", "$170,917"]
    rows = [dict(zip(header, r, strict=True)) for r in (["Huyền", "$55,747", "$9,149", "$25,598", "$21,000"], ["Linh", "$57,445", "8,938", "25,150", "23,357"])]
    with db_factory() as s:
        sheet = SheetSource(name="KH quý 4.2026 theo seller", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="KH PL2_Seller",
                            header=header, rows=rows, row_count=len(rows))
        s.add(sheet)
        s.commit()
    client.put("/api/v1/settings", json={"seller_plan_sheet_id": sheet.id}, headers=admin)
    plan = client.get(S, headers=member).json()["data"]["plan"]
    assert plan["built_in"] is True and "label row" in plan["reason"]


def test_the_sheet_is_used_again_when_it_can_be_read(client, member, upstream, business_plan, seller_sheet, sellers):  # noqa: F811
    plan = client.get(S, headers=member).json()["data"]["plan"]
    assert "built_in" not in plan and plan["sheet"]["name"] == "KH quý 4.2026 theo seller"


def test_the_built_in_plan_matches_the_figures_it_was_copied_from():
    # the sheet's own totals (T10, T11, T12) and each seller's "Quý IV", as read from the screenshot of 2026-11-16
    table = seller_plan.built_in()
    assert table["months"] == [10, 11, 12]
    assert [round(table["total"][m]) for m in (10, 11, 12)] == [64798, 209331, 170918]  # the sheet shows 170,917: its cells have cents
    quarter = {"Huyền": 55747, "Thuỷ": 60928, "Phương": 23216, "Uyển": 49607, "Nga": 44819, "Vân": 14572, "Vy": 10300, "Linh": 57445,
               "An": 57371, "Châu": 34717, "Trang": 25299, "Dung": 11025}
    assert list(quarter) == list(seller_plan.BUILT_IN)
    for name, q4 in quarter.items():
        assert abs(sum(seller_plan.BUILT_IN[name]) - q4) <= 1, name  # within the rounding of the sheet's cells
    assert seller_plan.match(table["sellers"], "Thùy NT.ETS")["name"] == "Thuỷ"  # trackingis spells it Thùy


def test_a_seller_filter_keeps_their_rows_only_and_a_member_limited_to_their_sales_sees_nothing_else(
        client, admin, member, upstream, business_plan, seller_sheet, cf_sheet, sellers):  # noqa: F811
    one = client.get(f"{S}&sellers=41", headers=admin).json()["data"]
    assert [r["seller"] for r in one["sellers"]] == ["Linh"] and one["total"]["cf"] == 2571.47

    me = client.get("/api/v1/auth/me", headers=member).json()["data"]
    client.patch(f"/api/v1/users/{me['id']}", json={"scope_sellers": ["41"]}, headers=admin)
    mine = client.get(S, headers=member).json()["data"]  # Linh herself: not Huyền's or Vân's plan, nor anybody's CF
    assert [r["seller"] for r in mine["sellers"]] == ["Linh"]
    assert mine["total"]["plan"] == round(8938 * TO_DATE, 2) and mine["total"]["cf"] == 2571.47


def test_a_seller_with_rows_in_several_teams_files_gets_the_sum_of_their_pl2_cf(client, db_factory, admin, member, upstream, business_plan,
                                                                                  seller_sheet, cf_sheet, sellers):  # noqa: F811
    # Etsy 1's file lists Huyền (only there) and Linh too (she sells from Etsy 1 stores as well as Etsy 2's: her PL2 is both)
    etsy1 = [cf_row("Tổng hợp", "1"), cf_row("Profit tính KPI", "Huyền HTN", *[0] * 9, 1000.0, 50.0), cf_row("", "Linh PT", *[0] * 9, 100.0, 5.0),
             cf_row("", "", *[0] * 12)]
    with db_factory() as s:
        sheet = SheetSource(name="Etsy 1 P&L Seller", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="1.2 P&L Seller (Sau IP)_Monthly",
                            header=CF_HEADER, rows=etsy1, row_count=len(etsy1))
        s.add(sheet)
        s.commit()
    for order in ([sheet.id, cf_sheet.id], [cf_sheet.id, sheet.id]):  # the sum does not depend on which file comes first
        client.put("/api/v1/settings", json={"seller_cf_sheets": [str(i) for i in order]}, headers=admin)
        data = client.get(S, headers=member).json()["data"]
        rows = {r["seller"]: r for r in data["sellers"]}
        assert rows["Linh"]["cf"] == round(2571.47 + 100.0, 2)  # Etsy 2's file + Etsy 1's
        assert rows["Huyền"]["cf"] == 1000.0 and rows["AN NTT"]["cf"] == 13514.58  # one file each
        assert data["total"]["cf"] == round(2571.47 + 100.0 + 1000.0 + 13514.58, 2) and len(data["cf"]["sheets"]) == 2


def test_each_seller_has_the_plan_of_the_quarter_and_their_pl2_per_month(client, member, upstream, business_plan, seller_sheet, cf_sheet, sellers):  # noqa: F811
    data = client.get(S, headers=member).json()["data"]  # 01–02/10
    rows = {r["seller"]: r for r in data["sellers"]}
    linh = rows["Linh"]
    assert linh["plan_total"] == 8938 + 25150 + 23357  # KH quý: T10 + T11 + T12 of the seller plan sheet
    assert [m["month"] for m in linh["months"]] == ["10-2026", "11-2026", "12-2026"]
    octo, nov, dec = linh["months"]
    # October is in the range: its plan, plan to date, KT, quantity and CF (finance books October whole)
    assert octo == {"month": "10-2026", "plan": 8938, "plan_to_date": round(8938 * TO_DATE, 2), "quantity": 30, "kt": 10 * KT_PER_PIECE, "cf": 2571.47}
    # November and December only have their plan: nothing sold or booked there as far as the range goes
    assert nov == {"month": "11-2026", "plan": 25150, "plan_to_date": None, "quantity": None, "kt": None, "cf": None}
    assert dec["plan"] == 23357 and dec["kt"] is None
    assert data["total"]["plan_total"] == round(sum(r["plan_total"] for r in data["sellers"] if r["plan_total"] is not None), 2)
    # a seller outside the plan has no plan, but their KT per month
    khoa = rows["Khoa NT"]
    assert khoa["plan_total"] is None and [m["plan"] for m in khoa["months"]][:1] == [None]
    assert khoa["months"][0]["kt"] == 3 * KT_PER_PIECE and khoa["months"][0]["plan_to_date"] is None


def test_a_range_over_two_months_asks_trackingis_per_month_and_splits_each_sellers_pl2(client, member, upstream, business_plan, seller_sheet,
                                                                                         cf_sheet, sellers):  # noqa: F811
    ASKED.clear()
    data = client.get("/api/v1/report/etsy/pl2/sellers?date_from=2026-10-30&date_to=2026-11-02", headers=member).json()["data"]
    # one seller view per priced product and month, each on the range's days of that month
    assert sorted((a["from"][0], a["to"][0], a["sub_product_types[]"][0]) for a in ASKED) == sorted(
        (f, t, sub) for f, t in (("2026-10-30", "2026-10-31"), ("2026-11-01", "2026-11-02")) for sub in ("Blanket", "Cutout Ornament", "Shirt"))
    linh = next(r for r in data["sellers"] if r["seller"] == "Linh")
    octo, nov, dec = linh["months"]
    # the fake trackingis answers each query with the same pieces, so each month has Linh's 10 pieces of each product
    assert octo["quantity"] == nov["quantity"] == 30 and linh["quantity"] == 60
    assert octo["kt"] == nov["kt"] == 10 * KT_PER_PIECE and linh["kt"] == 2 * 10 * KT_PER_PIECE  # the months add up to the range
    assert octo["plan_to_date"] == round(8938 * 2 / 31, 2) and nov["plan_to_date"] == round(25150 * 2 / 30, 2)
    assert linh["plan"] == round(8938 * 2 / 31 + 25150 * 2 / 30, 2) and dec["plan_to_date"] is None
    assert octo["cf"] == 2571.47 and nov["cf"] == 0  # finance's November row of Linh is 0


def test_each_seller_has_their_pieces_and_kt_per_product_in_all_and_per_month(client, member, upstream, business_plan, seller_sheet, sellers):  # noqa: F811
    data = client.get("/api/v1/report/etsy/pl2/sellers?date_from=2026-10-30&date_to=2026-11-02", headers=member).json()["data"]
    linh = next(r for r in data["sellers"] if r["seller"] == "Linh")
    # the plan's products (Ornament $6, Blanket $8, Shirt $5.5 per item), in the plan's order; 10 pieces of each in each month
    assert [p["name"] for p in linh["products"]] == ["Ornament", "Blanket", "Shirt"]
    ornament, blanket, shirt = linh["products"]
    assert ornament["months"] == {"10-2026": {"quantity": 10, "kt": 60.0}, "11-2026": {"quantity": 10, "kt": 60.0}}
    assert (ornament["quantity"], ornament["kt"]) == (20, 120.0) and (blanket["quantity"], blanket["kt"]) == (20, 160.0)
    assert (shirt["quantity"], shirt["kt"]) == (20, 110.0)
    # the products add up to the seller's pieces and PL2 KT, month by month too
    assert sum(p["quantity"] for p in linh["products"]) == linh["quantity"] and round(sum(p["kt"] for p in linh["products"]), 2) == linh["kt"]
    for month in linh["months"][:2]:
        assert round(sum(p["months"][month["month"]]["kt"] for p in linh["products"]), 2) == month["kt"]
    # a seller of the plan that sold nothing still lists the products, at zero
    vân = next(r for r in data["sellers"] if r["seller"] == "Vân")
    assert [p["quantity"] for p in vân["products"]] == [0, 0, 0] and all(p["months"] == {} for p in vân["products"])


def test_a_card_knows_its_trackingis_seller_ids(client, member, upstream, business_plan, seller_sheet, sellers):  # noqa: F811
    rows = {r["seller"]: r for r in client.get(S, headers=member).json()["data"]["sellers"]}
    assert rows["Linh"]["seller_ids"] == ["41"] and rows["Huyền"]["seller_ids"] == ["43"] and rows["Khoa NT"]["seller_ids"] == ["42"]
    assert rows["Vân"]["seller_ids"] == []  # a seller of the plan with no trackingis seller of that name


@pytest.fixture()
def by_type(monkeypatch):
    """Fake trackingis product type view: pieces per sub product type, per month of the query."""
    asked: list[dict[str, list[str]]] = []
    oct_, nov = {"Cutout Ornament": 5, "Ornament": 3, "Shell ornament": 2, "Blanket": 4, "Shirt": 7}, {"Cutout Ornament": 1, "Woven Blanket": 2}

    def handler(req: httpx.Request) -> httpx.Response:
        query = parse_qs(urlparse(str(req.url)).query)
        asked.append(query)
        sold = oct_ if query["from"][0].startswith("2026-10") else nov
        rows = [{"product_type": name, "total_order": k, "total_quantity": k, "total": 0, "sale_tax": 0, "total_revenue": 10.0 * k} for name, k in sold.items()]
        return httpx.Response(200, json={"success": True, "data": {"data": rows, "paging": {"current_page": 1, "per_page": 200,
                                                                                              "total": len(rows), "last_page": 1}}})

    monkeypatch.setattr(trackingis, "TEST_TRANSPORT", httpx.MockTransport(handler))
    return asked


def test_a_product_opens_onto_its_product_types_and_sub_product_types(client, member, by_type, business_plan, sellers):  # noqa: F811
    T = "/api/v1/report/etsy/pl2/sellers/types?date_from=2026-10-30&date_to=2026-11-02&sellers=41"
    data = client.get(T, headers=member).json()["data"]
    # one product type view per month, each on the range's days of that month and the card's sellers
    assert sorted(a["from"][0] for a in by_type) == ["2026-10-30", "2026-11-01"] and all(a["view"] == ["product_type"] for a in by_type)
    assert all(a["sellers[]"] == ["41"] for a in by_type) and data["months"] == ["10-2026", "11-2026"]
    products = {p["name"]: p["children"] for p in data["products"]}
    assert list(products) == ["Ornament", "Blanket", "Shirt"]  # the plan's products ($6, $8, $5.5 per item)

    # Ornament → the team's product types (Acrylic + Wood, Shell, …) → the sub product types that sold
    groups = {g["name"]: g for g in products["Ornament"]}
    assert list(groups) == ["Acrylic + Wood", "Shell", "Shaker", "Ceramic", "Glass", "Felt", "Others"]
    acrylic = groups["Acrylic + Wood"]
    assert (acrylic["quantity"], acrylic["kt"]) == (9, 54.0)  # 5 + 3 in October, 1 in November, at $6
    assert acrylic["months"] == {"10-2026": {"quantity": 8, "kt": 48.0}, "11-2026": {"quantity": 1, "kt": 6.0}}
    assert [(c["name"], c["quantity"]) for c in acrylic["children"]] == [("Cutout Ornament", 6), ("Ornament", 3)]  # no row for what sold nothing
    assert [c["name"] for c in groups["Shell"]["children"]] == ["Shell ornament"] and "children" not in groups["Shaker"]
    assert groups["Shaker"]["quantity"] == 0  # a product type of the page stays, at zero

    blanket = {g["name"]: g for g in products["Blanket"]}
    assert [(c["name"], c["quantity"], c["kt"]) for c in blanket["Velveteen"]["children"]] == [("Blanket", 4, 32.0)]
    assert [(c["name"], c["quantity"]) for c in blanket["Woven"]["children"]] == [("Woven Blanket", 2)]
    # Shirt is one product type: it opens straight onto its sub product types
    assert [(c["name"], c["quantity"], c["kt"]) for c in products["Shirt"]] == [("Shirt", 7, 38.5)]


def test_a_limited_seller_can_only_open_their_own_products(client, admin, member, by_type, business_plan, sellers):  # noqa: F811
    me = client.get("/api/v1/auth/me", headers=member).json()["data"]
    client.patch(f"/api/v1/users/{me['id']}", json={"scope_sellers": ["41"]}, headers=admin)
    client.get("/api/v1/report/etsy/pl2/sellers/types?date_from=2026-10-01&date_to=2026-10-02&sellers=43", headers=member)  # Huyền's id
    assert by_type and all(a["sellers[]"] == ["41"] for a in by_type)  # forced to hers, whatever the card asks


def test_a_seller_limited_to_their_sales_gets_their_own_cards_data_and_nobody_elses(client, admin, member, upstream, business_plan, seller_sheet,
                                                                                    cf_sheet, sellers):  # noqa: F811
    me = client.get("/api/v1/auth/me", headers=member).json()["data"]
    client.patch(f"/api/v1/users/{me['id']}", json={"scope_sellers": ["41"]}, headers=admin)  # Linh herself
    mine = client.get(S, headers=member).json()["data"]
    [linh] = mine["sellers"]
    assert linh["seller"] == "Linh" and linh["plan_total"] == 8938 + 25150 + 23357  # her card: KH quý, KH lũy kế, % HT lũy kế
    assert [m["month"] for m in linh["months"]] == ["10-2026", "11-2026", "12-2026"] and linh["months"][0]["cf"] == 2571.47
    assert [p["name"] for p in linh["products"]] == ["Ornament", "Blanket", "Shirt"] and linh["products"][0]["months"]["10-2026"]["quantity"] == 10
    assert mine["total"]["plan_total"] == linh["plan_total"] and mine["total"]["kt"] == linh["kt"]  # no other seller in the total either
    # nothing of the others anywhere in what she gets: not their names, nor their plan, KT or CF
    text = json.dumps(mine, ensure_ascii=False)
    for other in ("Huyền", "Vân", "Khoa", "AN NTT", "Mai"):
        assert other not in text, other
    for figure in ("9149", "25598", "13514.58"):  # Huyền's T10 / T11 plan, An's CF
        assert f'"{figure}"' not in text and f": {figure}," not in text, figure
    # an admin viewing as her sees the same
    assert client.get(S, headers={**admin, "X-View-As": str(me["id"])}).json()["data"] == mine
