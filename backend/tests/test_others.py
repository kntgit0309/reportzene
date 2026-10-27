from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.models import SheetSource
from app.services import report, trackingis
from app.services.families import OTHERS, SHIRT, with_rest
from app.services.family_plan import parse, plan_for
from tests.test_overview import business_plan  # noqa: F401  (fixture: KHKD "KH theo Product": no line for Others' products)
from tests.test_report import _save_token

O = "/api/v1/report/etsy/others"
# trackingis' sub product types: a few of other families, the ones Others lists, and two no family lists
TRACKINGIS_SUBS = ["Cutout Ornament", "Shirt", "Peeker Sticker", "Sticker", "Scrub cap", "Crochet", "Digital", "Baseball Jersey",
                   "Fabric Welcome Sign"]
REST = ["Crochet", "Digital"]
TYPE_ROWS = [{"product_type": "Crochet", "total_order": 5, "total_quantity": 6, "total_revenue": 50.0},
             {"product_type": "Digital", "total_order": 2, "total_quantity": 2, "total_revenue": 8.0}]

# "KH SP khác", tab Others: one row per product for ZenE as a whole; months of Sales/mo, then Sales/day and PL2
HEADER = [f"Column {i}" for i in range(1, 15)]
HEADER[6], HEADER[9], HEADER[12] = "Sales/mo", "Sales/day", "PL2"
LABELS = dict(zip(HEADER, ["Product", "PL2/item", "Total Sales", "Total PL2", "Tỷ trọng", "10-2026", "11-2026", "12-2026",
                           "10-2026", "11-2026", "12-2026", "10-2026", "11-2026", "12-2026"], strict=True))


def _row(product: str, monthly: int) -> dict[str, str]:
    cells = [product, "4.5", str(3 * monthly), "", "", str(monthly), str(monthly), str(monthly), "10", "10", "10", "1350", "1350", "1350"]
    return dict(zip(HEADER, cells, strict=True))


ROWS = [LABELS, _row("", 15455),  # total row of the whole plan: not a product
        _row("Sticker", 300), _row("Scrub cap", 300), _row("Fabric Welcome Sign", 150), _row("Baseball Jersey", 150)]


@pytest.fixture()
def upstream(monkeypatch):
    """Fake trackingis: sub product type filter, date view (1 order a day per sub type), product type and store views."""
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.url.path.endswith("/filter/sub-product-type"):
            return httpx.Response(200, json={"success": True, "data": [{"value": n, "label": n} for n in TRACKINGIS_SUBS]})
        q = parse_qs(urlparse(str(req.url)).query)
        n = len(q.get("sub_product_types[]", []))
        view = q["view"][0]
        if view == "product_type":
            rows = TYPE_ROWS if set(q["sub_product_types[]"]) == set(REST) else []
        elif view == "store":
            rows = [{"shop_name": "PunGanterdesign", "shop_id": 1, "total_order": n, "total_quantity": n, "total": 11.0 * n,
                     "sale_tax": 1.0 * n, "total_revenue": 10.0 * n}]
        else:
            rows = [{"date_at": d, "total_order": n, "total_quantity": n, "total": 11.0 * n, "sale_tax": 1.0 * n, "total_revenue": 10.0 * n}
                    for d in ("2026-10-01", "2026-10-02")]
        return httpx.Response(200, json={"success": True, "data": {"data": rows, "paging": {"current_page": 1, "per_page": 200,
                                                                                              "total": len(rows), "last_page": 1}}})

    monkeypatch.setattr(trackingis, "TEST_TRANSPORT", httpx.MockTransport(handler))
    return calls


@pytest.fixture()
def plan_sheet(client, db_factory, admin):
    _save_token(client, admin, teams=["12", "13", "23"])
    with db_factory() as s:
        sheet = SheetSource(name="KH SP khác", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="Others",
                            header=HEADER, rows=ROWS, row_count=len(ROWS))
        s.add(sheet)
        s.commit()
    client.put("/api/v1/settings", json={"family_plan_sheets": {"others": sheet.id}}, headers=admin)
    return sheet


def test_others_plan_is_per_product_for_zene_as_a_whole():
    plan = parse(HEADER, ROWS, OTHERS)
    assert not plan["per_store"] and plan["months"] == ["10-2026", "11-2026", "12-2026"]
    october = plan_for(plan, "2026-10-01", "2026-10-31")["groups"]
    assert {k: v["plan_month"] for k, v in october.items()} == {"Sticker": 300, "Scrub cap": 300, "Fabric Welcome Sign": 150,
                                                                 "Baseball Jersey": 150}


def test_the_rest_group_takes_what_no_family_lists():
    others = with_rest(OTHERS, TRACKINGIS_SUBS)
    assert others.groups[-1] == ("Other products", tuple(REST))
    assert with_rest(OTHERS, ["Shirt", "Sticker"]) == OTHERS  # nothing left over: no rest group (it would filter nothing)
    assert with_rest(SHIRT, TRACKINGIS_SUBS) == SHIRT


def test_others_report(client, member, upstream, plan_sheet, monkeypatch):
    data = client.get(f"{O}?date_from=2026-10-01&date_to=2026-10-02", headers=member).json()["data"]

    assert [g["name"] for g in data["groups"]] == ["Sticker", "Scrub cap", "Fabric Welcome Sign", "Baseball Jersey", "Other products"]
    rest = data["groups"][-1]
    assert [(c["name"], c["total_quantity"]) for c in rest["children"]] == [("Crochet", 6), ("Digital", 2)]
    assert rest["total_order"] == 2 * len(REST) and rest["plan"] == 0  # no plan line for them
    sticker = data["groups"][0]
    assert sticker["plan"] == round(300 * 2 / 31, 1) and sticker["plan_month"] == 300
    assert [c["name"] for c in sticker["children"]] == list(OTHERS.groups[0][1])
    assert data["total"]["plan"] == round(sum(g["plan"] for g in data["groups"]), 1) and data["total"]["plan_month"] == 900
    assert set(REST) <= set(data["family"]["sub_types"]) and "Shirt" not in data["family"]["sub_types"]
    product_type_views = [r for r in upstream if r.url.params.get("view") == "product_type"]
    assert len(product_type_views) == 1  # the rest group's rows: one query, not one per sub product type

    monkeypatch.setattr(report, "filter_options", lambda db, kind, user=None: (
        [{"id": n, "name": n} for n in TRACKINGIS_SUBS] if kind == "sub_product_types" else [{"id": 13, "name": "Etsy 2.ZenE"}]))
    one_team = client.get(f"{O}?date_from=2026-10-01&date_to=2026-10-02&teams=13", headers=member).json()["data"]
    assert "ZenE as a whole" in one_team["plan"]["error"]


def test_others_accounts_have_no_store_plan(client, member, upstream, plan_sheet):
    data = client.get(f"{O}/accounts?date_from=2026-10-01&date_to=2026-10-31", headers=member).json()["data"]
    assert "not per store" in data["plan"]["error"]
    [pun] = data["accounts"]
    assert pun["shop"] == "PunGanterdesign" and "plan" not in pun
    assert [c["name"] for c in pun["children"]] == ["Sticker", "Scrub cap", "Fabric Welcome Sign", "Baseball Jersey", "Other products"]


def test_others_pl2_est_is_per_product_type_and_other_products_use_settings_rate(client, member, upstream, plan_sheet, business_plan):  # noqa: F811
    data = client.get(f"{O}?date_from=2026-10-01&date_to=2026-10-02", headers=member).json()["data"]
    sticker, *_, rest = data["groups"]
    assert sticker["pl2_per_item"] is None and sticker["pl2_est"] is None  # KHKD has no line for Sticker
    assert rest["pl2_per_item"] == 7 and rest["pl2_est"] == rest["total_quantity"] * 7  # Settings › Plan, $7 per item
    assert [c["pl2_est"] for c in rest["children"]] == [6 * 7, 2 * 7]
    assert data["total"]["pl2_est"] == rest["pl2_est"] and "pl2_per_item" not in data["total"]  # the product types' own rates added up
    accounts = client.get(f"{O}/accounts?date_from=2026-10-01&date_to=2026-10-02", headers=member).json()["data"]
    assert accounts["accounts"][0]["pl2_est"] == sum(c.get("pl2_est") or 0 for c in accounts["accounts"][0]["children"])
