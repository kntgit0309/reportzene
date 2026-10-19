from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.models import SheetSource
from app.services import report, trackingis
from app.services.families import ORNAMENT
from tests.test_ornament_plan import HEADER, ROWS
from tests.test_report import _save_token

A = "/api/v1/report/etsy/ornament/accounts"
GROUPS = ORNAMENT.groups
SHOPS = [("PunGanterdesign", 1, 3), ("OnebyHenry", 2, 2), ("NewShop", 9, 1)]  # name, id, orders per sub product type


@pytest.fixture()
def upstream(monkeypatch):
    """Fake trackingis store view: each store sells k orders (2k pieces, $10k) of every sub product type in the filter."""
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        q = parse_qs(urlparse(str(req.url)).query)
        n = len(q.get("sub_product_types[]", []))
        rows = [{"shop_name": name, "shop_id": i, "total_order": k * n, "total_quantity": 2 * k * n, "total": 11.0 * k * n,
                 "sale_tax": 1.0 * k * n, "total_revenue": 10.0 * k * n} for name, i, k in SHOPS] if q["view"] == ["store"] else []
        return httpx.Response(200, json={"success": True, "data": {"data": rows, "paging": {"current_page": 1, "per_page": 200,
                                                                                              "total": len(rows), "last_page": 1}}})

    monkeypatch.setattr(trackingis, "TEST_TRANSPORT", httpx.MockTransport(handler))
    return calls


@pytest.fixture()
def plan_sheet(client, db_factory, admin):
    _save_token(client, admin, teams=["12", "13", "23"])
    with db_factory() as s:
        sheet = SheetSource(name="KH Ornament", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="Ornament",
                            header=HEADER, rows=ROWS, row_count=len(ROWS))
        s.add(sheet)
        s.commit()
    client.put("/api/v1/settings", json={"ornament_plan_sheet_id": sheet.id}, headers=admin)
    return sheet


def test_accounts_put_each_stores_ornament_sales_next_to_its_plan_line(client, member, upstream, plan_sheet):
    data = client.get(f"{A}?date_from=2026-10-01&date_to=2026-10-31", headers=member).json()["data"]
    every = sum(len(subs) for _, subs in GROUPS)

    assert [a["shop"] for a in data["accounts"]] == ["PunGanterdesign", "Daisyfloralsshop", "OnebyHenry", "NewShop"]
    pun, daisy, henry, new = data["accounts"]
    assert pun["team"] == "Etsy 1" and pun["in_plan"] and pun["total_quantity"] == 2 * 3 * every
    assert pun["plan"] == 525 and pun["plan_month"] == 525 and pun["achieved"] == round(pun["total_quantity"] / 525, 4)
    acrylic_wood = next(c for c in pun["children"] if c["name"] == "Acrylic + Wood")
    assert acrylic_wood["plan"] == 295 and acrylic_wood["total_order"] == 3 * len(dict(GROUPS)["Acrylic + Wood"])
    assert daisy["total_quantity"] == 0 and daisy["plan"] == 275 and {c["name"] for c in daisy["children"]} == {
        "Acrylic + Wood", "Shaker", "Ceramic", "Glass", "Felt", "Others"}
    assert henry["plan"] == 940 and next(c for c in henry["children"] if c["name"] == "Felt")["plan"] == 800
    assert not new["in_plan"] and new["team"] is None and new["plan"] is None
    assert data["total"]["plan"] == 525 + 275 + 940
    assert data["total"]["total_quantity"] == sum(a["total_quantity"] for a in data["accounts"])
    assert data["plan"]["scope"] == "ZenE" and {r.url.params.get("view") for r in upstream} == {"store"}
    assert len(upstream) == 1 + len(GROUPS)  # one store-view query for every ornament, one per product type


def test_accounts_without_a_plan_still_list_the_stores(client, member, upstream, plan_sheet, monkeypatch):
    seller = client.get(f"{A}?date_from=2026-10-01&date_to=2026-10-31&sellers=5", headers=member).json()["data"]
    assert "seller" in seller["plan"]["error"] and [a["shop"] for a in seller["accounts"]] == [s[0] for s in SHOPS]
    assert "plan" not in seller["accounts"][0] and "plan" not in seller["total"]

    monkeypatch.setattr(report, "filter_options", lambda db, kind, user=None: [{"id": 23, "name": "Etsy 3.ZenE"}])
    etsy3 = client.get(f"{A}?date_from=2026-10-01&date_to=2026-10-31&teams=23", headers=member).json()["data"]
    assert etsy3["plan"]["scope"] == "Etsy 3" and etsy3["accounts"][0]["shop"] == "OnebyHenry" and etsy3["total"]["plan"] == 940


def test_accounts_plan_total_is_the_product_type_tables(client, member, upstream, plan_sheet):
    """Shop plans pro rata (01–19/10) round row by row; the total adds the unrounded ones like the product type table."""
    url = "?date_from=2026-10-01&date_to=2026-10-19"
    accounts = client.get(f"{A}{url}", headers=member).json()["data"]
    by_type = client.get(f"/api/v1/report/etsy/ornament{url}", headers=member).json()["data"]
    assert accounts["total"]["plan"] == by_type["total"]["plan"] == round((525 + 275 + 940) * 19 / 31, 1)


def test_account_replacements_are_saved_in_settings(client, admin, member):
    body = {"account_replacements": [{"suspended": " OnebyHenry ", "replacement": "NewShop"}]}
    assert client.put("/api/v1/settings", json=body, headers=member).status_code == 403
    saved = client.put("/api/v1/settings", json=body, headers=admin).json()["data"]["account_replacements"]
    assert saved == [{"suspended": "OnebyHenry", "replacement": "NewShop"}]
    assert client.put("/api/v1/settings", json={"plan_products": 11}, headers=admin).json()["data"]["account_replacements"] == saved
    same = {"account_replacements": [{"suspended": "NewShop", "replacement": "newshop"}]}
    assert client.put("/api/v1/settings", json=same, headers=admin).status_code == 422
    assert client.put("/api/v1/settings", json={"account_replacements": []}, headers=admin).json()["data"]["account_replacements"] == []


def test_replacement_takes_the_suspended_stores_plan_line_and_sales(client, admin, member, upstream, plan_sheet):
    client.put("/api/v1/settings", json={"account_replacements": [{"suspended": "OnebyHenry", "replacement": "NewShop"}]}, headers=admin)
    data = client.get(f"{A}?date_from=2026-10-01&date_to=2026-10-31", headers=member).json()["data"]
    every = sum(len(subs) for _, subs in GROUPS)

    assert [a["shop"] for a in data["accounts"]] == ["PunGanterdesign", "Daisyfloralsshop", "NewShop"]  # in OnebyHenry's place
    new = data["accounts"][2]
    assert new["in_plan"] and new["team"] == "Etsy 3" and new["plan"] == 940 and new["replaces"] == ["OnebyHenry"]
    assert new["total_quantity"] == 2 * (2 + 1) * every  # its own sales and the suspended store's
    assert next(c for c in new["children"] if c["name"] == "Felt")["plan"] == 800
    assert data["total"]["plan"] == 525 + 275 + 940


def test_replacing_with_a_store_of_the_plan_adds_the_two_lines_up():
    from app.services.family_plan import parse, plan_for, replace_accounts
    from tests.test_ornament_plan import HEADER as H, ROWS as R
    plan = replace_accounts(parse(H, R, ORNAMENT), (("PunGanterdesign", "Daisyfloralsshop"),))
    assert [s["shop"] for s in plan["shops"]] == ["Daisyfloralsshop", "OnebyHenry"]
    assert plan["shops"][0]["replaces"] == ["PunGanterdesign"]
    assert plan_for(plan, "2026-10-01", "2026-10-31", shops={"daisyfloralsshop"})["groups"]["Acrylic + Wood"]["plan"] == 295 + 70
