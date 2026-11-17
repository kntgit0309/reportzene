"""Etsy › Report, product cards: each product's PL2 theo KT next to its PL2 plan per month, and a product opened onto its types."""
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.services import trackingis
from app.services.families import FAMILIES
from tests.test_overview import TRACKINGIS_SUBS, business_plan, upstream  # noqa: F401  (fixtures: KHKD plan; fake trackingis date view)
from tests.test_seller_plan import OCT_LINH, seller_sheet  # noqa: F401  (fixture: seller plan sheet, Linh PT = trackingis seller 41)

M = "/api/v1/report/etsy/overview/months"
ONE = f"{M}?date_from=2026-10-01&date_to=2026-10-02"
FELT = sum(FAMILIES["ornament"].quantity_fixes["Felt Ornament"][d] for d in ("2026-10-01", "2026-10-02"))  # pieces added by hand
KHKD = {"Ornament": ([5535, 16290, 13900], [33210, 97740, 83400], 6), "Blanket": ([1750, 3130, 3220], [14000, 25040, 25760], 8),
        "Shirt": ([3250, 2700, 2150], [17875, 14850, 11825], 5.5)}  # sales, PL2 per month of the sheet, and PL2 per item


def test_each_product_has_its_plan_and_kt_per_month(client, member, upstream, business_plan):  # noqa: F811
    data = client.get(ONE, headers=member).json()["data"]
    assert data["plan"]["months"] == ["10-2026", "11-2026", "12-2026"] and data["plan"]["missing"] == [] and "error" not in data["plan"]
    rows = {r["name"]: r for r in data["products"]}
    # the products with a KHKD line (the others have no PL2 per item), then Other products
    assert list(rows) == ["Ornament", "Blanket", "Shirt", "Other products"]
    assert [rows[n]["in_plan"] for n in rows] == [True, True, True, False]

    ornament = rows["Ornament"]
    pcs = 2 * 2 * len(FAMILIES["ornament"].sub_types) + FELT  # 2 days of 2 pieces per sub type, and the Felt pieces added by hand
    sales, pl2, rate = KHKD["Ornament"]
    assert ornament["quantity"] == pcs and ornament["kt"] == pcs * 6
    assert ornament["plan_total"] == sum(pl2)  # KH quý: T10 + T11 + T12
    assert ornament["plan"] == round(pl2[0] * 2 / 31, 2) and ornament["kt_pct"] == round(pcs * 6 / (pl2[0] * 2 / 31), 4)
    octo, nov, dec = ornament["months"]
    assert octo == {"month": "10-2026", "plan": pl2[0], "plan_to_date": round(pl2[0] * 2 / 31, 2), "quantity": pcs, "kt": pcs * 6}
    # November and December are not in the range: only their plan
    assert nov == {"month": "11-2026", "plan": pl2[1], "plan_to_date": None, "quantity": None, "kt": None} and dec["plan"] == pl2[2]

    other = rows["Other products"]  # no plan line: its KT counts at the PL2 per item of Settings › Plan ($7)
    assert other["plan"] is None and other["plan_total"] is None and other["kt_pct"] is None and other["months"][0]["plan"] is None
    assert other["kt"] == other["quantity"] * 7 and other["quantity"] > 0

    total = data["total"]
    assert total["name"] == "All products" and total["plan_total"] == sum(sum(v[1]) for v in KHKD.values())
    assert total["kt"] == round(sum(r["kt"] for r in data["products"]), 2) and total["quantity"] == sum(r["quantity"] for r in data["products"])
    assert total["plan"] == round(sum(v[1][0] for v in KHKD.values()) * 2 / 31, 2)  # the three products' October PL2, 2 of 31 days
    assert total["months"][0]["kt"] == round(sum(r["months"][0]["kt"] for r in data["products"]), 2)


def test_a_range_over_two_months_asks_trackingis_per_month(client, member, upstream, business_plan):  # noqa: F811
    upstream.clear()
    data = client.get(f"{M}?date_from=2026-10-30&date_to=2026-11-02", headers=member).json()["data"]
    asked = [parse_qs(urlparse(str(r.url)).query) for r in upstream if "sub_product_types[]" in parse_qs(urlparse(str(r.url)).query)]
    spans = {(a["from"][0], a["to"][0]) for a in asked}
    assert spans == {("2026-10-30", "2026-10-31"), ("2026-11-01", "2026-11-02")}  # each month's own days
    ornament = next(r for r in data["products"] if r["name"] == "Ornament")
    octo, nov, dec = ornament["months"]
    sales, pl2, rate = KHKD["Ornament"]
    assert octo["plan_to_date"] == round(pl2[0] * 2 / 31, 2) and nov["plan_to_date"] == round(pl2[1] * 2 / 30, 2) and dec["quantity"] is None
    assert octo["kt"] is not None and nov["kt"] is not None
    assert ornament["quantity"] == octo["quantity"] + nov["quantity"] and ornament["kt"] == round(octo["kt"] + nov["kt"], 2)  # the months add up
    assert ornament["plan"] == round(octo["plan_to_date"] + nov["plan_to_date"], 2)


def test_filters_below_zene_leave_no_products(client, member, upstream, business_plan):  # noqa: F811
    data = client.get(f"{ONE}&shops=5", headers=member).json()["data"]
    assert "ZenE as a whole" in data["plan"]["error"] and data["products"] == [] and data["total"] is None


def test_a_seller_gets_the_plan_by_their_share(client, admin, member, upstream, business_plan, seller_sheet):  # noqa: F811
    me = client.get("/api/v1/auth/me", headers=member).json()["data"]
    client.patch(f"/api/v1/users/{me['id']}", json={"scope_sellers": ["41"]}, headers=admin)  # Linh herself
    data = client.get(ONE, headers=member).json()["data"]
    ornament = next(r for r in data["products"] if r["name"] == "Ornament")
    assert ornament["months"][0]["plan"] == round(33210 * OCT_LINH, 2)  # her share of October's plan (the sheet's own 49.4%)
    assert ornament["plan"] == round(33210 * OCT_LINH * 2 / 31, 2)


@pytest.fixture()
def by_type(monkeypatch):
    """Fake trackingis: pieces per sub product type in the product type view (per month), and daily rows for the rest."""
    asked: list[dict[str, list[str]]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        query = parse_qs(urlparse(str(req.url)).query)
        if req.url.path.endswith("/filter/sub-product-type"):
            return httpx.Response(200, json={"success": True, "data": [{"value": n, "label": n} for n in TRACKINGIS_SUBS]})
        asked.append(query)
        sold = {"Cutout Ornament": 5, "Ornament": 3, "Shell ornament": 2, "Felt Ornament": 4} if query["from"][0].startswith("2026-10") else {"Cutout Ornament": 1}
        rows = [{"product_type": n, "total_order": k, "total_quantity": k, "total": 0, "sale_tax": 0, "total_revenue": 10.0 * k} for n, k in sold.items()]
        return httpx.Response(200, json={"success": True, "data": {"data": rows, "paging": {"current_page": 1, "per_page": 200,
                                                                                              "total": len(rows), "last_page": 1}}})

    monkeypatch.setattr(trackingis, "TEST_TRANSPORT", httpx.MockTransport(handler))
    return asked


def test_a_product_opens_onto_its_product_types_and_sub_types_with_the_pieces_added_by_hand(client, member, by_type, business_plan):  # noqa: F811
    T = "/api/v1/report/etsy/overview/types?date_from=2026-10-30&date_to=2026-11-02&product=Ornament"
    data = client.get(T, headers=member).json()["data"]
    assert data["name"] == "Ornament" and data["months"] == ["10-2026", "11-2026"]
    assert sorted(a["from"][0] for a in by_type) == ["2026-10-30", "2026-11-01"] and all(a["view"] == ["product_type"] for a in by_type)
    groups = {g["name"]: g for g in data["children"]}
    assert list(groups) == ["Acrylic + Wood", "Shell", "Shaker", "Ceramic", "Glass", "Felt", "Others"]
    acrylic = groups["Acrylic + Wood"]
    assert (acrylic["quantity"], acrylic["kt"]) == (9, 54.0)  # 5 + 3 in October, 1 in November, at $6
    assert [(c["name"], c["quantity"]) for c in acrylic["children"]] == [("Cutout Ornament", 6), ("Ornament", 3)]
    # Felt Ornament: trackingis' 4 in October plus the pieces the team adds by hand for 30–31/10 and for 01–02/11
    fixes = FAMILIES["ornament"].quantity_fixes["Felt Ornament"]
    october, november = sum(fixes[d] for d in ("2026-10-30", "2026-10-31")), sum(fixes[d] for d in ("2026-11-01", "2026-11-02"))
    assert october > 0 and november > 0
    assert groups["Felt"]["months"]["10-2026"]["quantity"] == 4 + october and groups["Felt"]["months"]["11-2026"]["quantity"] == november
    assert [(c["name"], c["quantity"]) for c in groups["Felt"]["children"]] == [("Felt Ornament", 4 + october + november)]


def test_an_unknown_product_is_not_found(client, member, by_type, business_plan):  # noqa: F811
    res = client.get("/api/v1/report/etsy/overview/types?product=Nothing", headers=member)
    assert res.status_code == 404 and res.json()["meta"]["code"] == "PRODUCT_NOT_FOUND"
