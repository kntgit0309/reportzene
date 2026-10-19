from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.models import SheetSource
from app.services import report, trackingis
from app.services.families import FAMILIES, PLAN_PRODUCTS
from tests.test_plan import HEADER, ROWS  # KHKD "KH theo Product": Ornament, Blanket, Shirt from column Q
from tests.test_report import _save_token

V = "/api/v1/report/etsy/overview?date_from=2026-10-01&date_to=2026-10-02"
TRACKINGIS_SUBS = ["Cutout Ornament", "Shirt", "Blanket", "Quilted Tote Bag", "Peeker Sticker", "Crochet", "Digital"]


@pytest.fixture()
def upstream(monkeypatch):
    """Fake trackingis: the sub product type list, and a date view selling 1 order (2 pieces) a day per sub type asked."""
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.url.path.endswith("/filter/sub-product-type"):
            return httpx.Response(200, json={"success": True, "data": [{"value": n, "label": n} for n in TRACKINGIS_SUBS]})
        n = len(parse_qs(urlparse(str(req.url)).query).get("sub_product_types[]", []))
        rows = [{"date_at": d, "total_order": n, "total_quantity": 2 * n, "total": 11.0 * n, "sale_tax": 1.0 * n, "total_revenue": 10.0 * n}
                for d in ("2026-10-01", "2026-10-02")]
        return httpx.Response(200, json={"success": True, "data": {"data": rows, "paging": {"current_page": 1, "per_page": 31,
                                                                                              "total": len(rows), "last_page": 1}}})

    monkeypatch.setattr(trackingis, "TEST_TRANSPORT", httpx.MockTransport(handler))
    return calls


@pytest.fixture()
def business_plan(client, db_factory, admin):
    _save_token(client, admin, teams=["12", "13", "23"])
    with db_factory() as s:
        sheet = SheetSource(name="KHKD Quý 4/2026", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="KH theo Product",
                            header=HEADER, rows=ROWS, row_count=len(ROWS))
        s.add(sheet)
        s.commit()
    client.put("/api/v1/settings", json={"plan_sheet_id": sheet.id}, headers=admin)
    return sheet


def test_overview_rows_follow_the_plan_then_every_other_product(client, member, upstream, business_plan):
    data = client.get(V, headers=member).json()["data"]

    # the plan's products, the products with a page the plan does not list, then Other products
    assert [r["name"] for r in data["rows"]] == ["Ornament", "Blanket", "Shirt", "Flag", "Wooden Block", "Badge Reel", "Quilted",
                                                 "Sticker", "Scrub cap", "Fabric Welcome Sign", "Baseball Jersey", "Other products"]
    rows = {r["name"]: r for r in data["rows"]}
    ornament = rows["Ornament"]
    assert ornament["page"] == "ornament" and ornament["sub_types"] == list(FAMILIES["ornament"].sub_types)
    n = len(ornament["sub_types"])
    felt = sum(FAMILIES["ornament"].quantity_fixes["Felt Ornament"][d] for d in ("2026-10-01", "2026-10-02"))  # added by hand
    assert ornament["total_quantity"] == 2 * 2 * n + felt and ornament["fix_quantity"] == felt and data["total"]["fix_quantity"] == felt
    assert ornament["plan"] == round(5535 * 2 / 31, 1) and ornament["plan_month"] == 5535
    assert ornament["achieved"] == round(ornament["total_quantity"] / (5535 * 2 / 31), 4)
    assert ornament["pl2_per_item"] == 6 and ornament["pl2_est"] == ornament["total_quantity"] * 6
    assert ornament["pl2_plan"] == round(33210 * 2 / 31, 2)
    assert rows["Quilted"]["page"] is None and rows["Quilted"]["sub_types"] == list(PLAN_PRODUCTS["Quilted"])
    assert rows["Sticker"]["page"] == "others" and rows["Flag"]["plan"] is None  # a page without a plan line
    assert rows["Other products"]["sub_types"] == ["Crochet", "Digital"]  # Quilted Tote Bag is Quilted's, not left over

    total = data["total"]
    assert total["plan"] == round((5535 + 1750 + 3250) * 2 / 31, 1) and total["plan_month"] == 5535 + 1750 + 3250
    assert total["pl2_plan"] == round((33210 + 14000 + 17875) * 2 / 31, 2)
    assert data["plan"]["sheet"]["name"] == "KHKD Quý 4/2026" and data["plan"]["scope"] == "ZenE"
    reports = [r for r in upstream if r.url.path.endswith("/etsy/report")]
    assert len(reports) == 1 + len(data["rows"])  # one query per product and one for all of them


def test_overview_plan_is_for_zene_as_a_whole(client, member, upstream, business_plan, monkeypatch):
    monkeypatch.setattr(report, "filter_options", lambda db, kind, user=None: (
        [{"id": n, "name": n} for n in TRACKINGIS_SUBS] if kind == "sub_product_types" else [{"id": 13, "name": "Etsy 2.ZenE"}]))
    data = client.get(f"{V}&teams=13", headers=member).json()["data"]
    assert "ZenE as a whole" in data["plan"]["error"] and "plan" not in data["rows"][0]
    assert "fix_quantity" not in data["rows"][0]  # pieces added by hand are not tied to a team
    ornament = data["rows"][0]
    assert ornament["pl2_est"] == ornament["total_quantity"] * 6 and data["total"]["pl2_est"] is not None  # PL2 KT for any filters
    assert data["rows"][0]["name"] == "Ornament"  # still in the plan's order


def test_overview_without_a_plan_still_lists_every_product(client, admin, member, upstream):
    _save_token(client, admin, teams=["12", "13", "23"])
    data = client.get(V, headers=member).json()["data"]
    assert "Settings" in data["plan"]["error"]
    assert [r["name"] for r in data["rows"]][:3] == ["Ornament", "Shirt", "Blanket"] and data["rows"][-1]["name"] == "Other products"
