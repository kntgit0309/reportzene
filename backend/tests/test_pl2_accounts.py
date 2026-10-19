from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.core.errors import AppError
from app.models import SheetSource
from app.services import report, trackingis
from app.services.pl2_accounts import parse, parse_account_list
from tests.test_ornament_plan import HEADER as KH_HEADER  # KH Ornament shops: PunGanterdesign, Daisyfloralsshop, OnebyHenry
from tests.test_ornament_plan import ROWS as KH_ROWS
from tests.test_plan import HEADER as PLAN_HEADER  # KHKD: Ornament $6, Blanket $8, Shirt $5.5 PL2/item
from tests.test_plan import ROWS as PLAN_ROWS
from tests.test_report import _save_token

A = "/api/v1/report/etsy/pl2/accounts?date_from=2026-10-01&date_to=2026-10-19"
SUBS = ["Cutout Ornament", "Blanket", "Shirt"]
# trackingis store view: pieces of each store, per query (one query per priced product)
ASKED: list[tuple[str, ...]] = []
SOLD = {"PunGanterdesign": 10, "OnebyHenry": 3, "CuongCafCrochet": 2, "NotInPlanShop": 5}

# "Acc đã bàn giao Seller": the list the PL sheet's QUERY names its rows from
LIST_HEADER = ["No.", "Dealer", "Ngày nhận acc", "ID", "Shop Name", "Seller", "Team"]
LIST_ROWS = [dict(zip(LIST_HEADER, r, strict=True)) for r in [
    ["1", "x", "", "A1", "PunGanterdesign", "Mai VTT", "Etsy 1"],
    ["2", "x", "", "A2", "Daisyfloralsshop", "Linh PT", "Etsy 2"],
    ["3", "x", "", "A3", "OldShop", "Mai VTT", "Etsy 1"],
    ["4", "x", "", "A4", "CuongCafCrochet", "Linh PT", "Etsy 2"],
    ["5", "x", "", "A5", "OnebyHenry", "Vy", "Etsy 3"],
]]
# "PL Account Etsy_Monthly": months in the header, PROFIT THỰC ĐẠT then a block per team; only a block's first name shows
PL_HEADER = ["tha", "Column 2", "Column 3", "09-2026", "10-2026", "11-2026"]


def _pl(label: str, *values: object) -> dict[str, str]:
    return dict(zip(PL_HEADER, [label, "", "", *(str(v) for v in values)], strict=True))


PL_ROWS = [
    _pl("Profit kế hoạch", 64290, 75196, 108156),
    _pl("PROFIT THỰC ĐẠT", 35412.26, 18661.64, 0),
    _pl("Profit thực đạt Etsy 1", 28135.74, 14826.19, 0),
    _pl("PunGanterdesign", 14129.36, 8047.98, 0),
    _pl("", 500, 120.5, 0),  # OldShop: not in a KH sheet
    _pl("", 0, 0, 0),  # a row past the team's accounts
    _pl("Profit thực đạt Etsy 2", 9988.16, 5077.04, 0),
    _pl("Daisyfloralsshop", -426.64, -2497.19, 0),
    _pl("", 9647.31, 380.80, 0),  # CuongCafCrochet: suspended, replaced by AuthenticJJ
    _pl("Profit thực đạt Etsy 3", -2711.63, -1241.59, 0),
    _pl("OnebyHenry", -1214.55, -435.14, 0),
    _pl("PROFIT/SALE", "", "", ""),
    _pl("Profit/sale Etsy 1", 6.9, 3.8, 0),
]


def test_account_names_are_rebuilt_from_the_list():
    names = parse_account_list(LIST_HEADER, LIST_ROWS)
    assert names == {"etsy 1": ["PunGanterdesign", "OldShop"], "etsy 2": ["Daisyfloralsshop", "CuongCafCrochet"], "etsy 3": ["OnebyHenry"]}
    pl = parse(PL_HEADER, PL_ROWS, names)
    assert [(a["team"], a["name"], a["actual"]["10-2026"]) for a in pl["accounts"]] == [
        ("Etsy 1", "PunGanterdesign", 8047.98), ("Etsy 1", "OldShop", 120.5), ("Etsy 2", "Daisyfloralsshop", -2497.19),
        ("Etsy 2", "CuongCafCrochet", 380.8), ("Etsy 3", "OnebyHenry", -435.14)]
    with pytest.raises(AppError) as err:  # the sheet's first name must be the list's first name of the team
        parse(PL_HEADER, PL_ROWS, {**names, "etsy 2": ["SomeoneElse", "CuongCafCrochet"]})
    assert err.value.code == "PL2_ACCOUNT_NAMES"


def test_rows_a_sync_skips_do_not_shift_the_names():
    # a sync skips entirely empty rows (an account with nothing booked yet) but keeps each row's sheet number
    numbered = [{**r, "_row": str(n)} for n, r in enumerate(PL_ROWS, start=2)]
    del numbered[7]  # Daisyfloralsshop's row (sheet row 9), so Etsy 2 shows no name at all
    names = {**parse_account_list(LIST_HEADER, LIST_ROWS), "etsy 3": ["OnebyHenry", "NewShop"]}
    pl = parse(PL_HEADER, numbered, names)
    assert [(a["name"], a["actual"]["10-2026"]) for a in pl["accounts"] if a["team"] == "Etsy 2"] == [("CuongCafCrochet", 380.8)]
    assert pl["warnings"] == ["Etsy 3: 1 account(s) of the list have no row in the PL2 account sheet"]  # NewShop: the block ends


@pytest.fixture()
def upstream(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/filter/sub-product-type"):
            return httpx.Response(200, json={"success": True, "data": [{"value": n, "label": n} for n in SUBS]})
        subs = parse_qs(urlparse(str(req.url)).query).get("sub_product_types[]", [])
        ASKED.append(tuple(subs))
        rows = [{"shop_name": shop, "shop_id": i, "total_order": k, "total_quantity": k, "total": 0, "sale_tax": 0,
                 "total_revenue": 10.0 * k} for i, (shop, k) in enumerate(SOLD.items())]
        return httpx.Response(200, json={"success": True, "data": {"data": rows, "paging": {"current_page": 1, "per_page": 200,
                                                                                              "total": len(rows), "last_page": 1}}})

    monkeypatch.setattr(trackingis, "TEST_TRANSPORT", httpx.MockTransport(handler))


@pytest.fixture()
def sheets(client, db_factory, admin):
    _save_token(client, admin, teams=["12", "13", "23"])
    with db_factory() as s:
        made = [SheetSource(name=n, url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title=n, header=h, rows=r, row_count=len(r))
                for n, h, r in (("KHKD", PLAN_HEADER, PLAN_ROWS), ("KH Ornament", KH_HEADER, KH_ROWS),
                                ("PL Account", PL_HEADER, PL_ROWS), ("Acc list", LIST_HEADER, LIST_ROWS))]
        s.add_all(made)
        s.commit()
        ids = [m.id for m in made]
    client.put("/api/v1/settings", json={"plan_sheet_id": ids[0], "family_plan_sheets": {"ornament": ids[1]}, "pl2_account_sheet_id": ids[2],
                                         "account_list_sheet_id": ids[3],
                                         "account_replacements": [{"suspended": "CuongCafCrochet", "replacement": "AuthenticJJ"}]},
               headers=admin)
    return ids


def test_pl2_per_account_kt_and_cf(client, member, upstream, sheets):
    ASKED.clear()
    data = client.get(A, headers=member).json()["data"]
    assert [a[0] for a in ASKED] == ["Cutout Ornament", "Blanket", "Shirt"]  # one store view per priced product, on its sub types
    rows = {a["shop"]: a for a in data["accounts"]}
    assert list(rows) == ["PunGanterdesign", "Daisyfloralsshop", "OnebyHenry"]  # the KH accounts, in sheet order
    pun = rows["PunGanterdesign"]
    # 10 pieces of each priced product (Ornament $6, Blanket $8, Shirt $5.5), one sub product type each
    assert pun["quantity"] == 30 and pun["kt"] == 10 * (6 + 8 + 5.5) and pun["cf"] == 8047.98
    assert pun["cf_minus_kt"] == round(8047.98 - pun["kt"], 2)  # CF − KT
    assert rows["Daisyfloralsshop"]["kt"] == 0 and rows["Daisyfloralsshop"]["cf"] == -2497.19
    others = {c["shop"]: c for c in data["others"]["children"]}
    assert set(others) == {"OldShop", "AuthenticJJ", "NotInPlanShop"}  # not in a KH sheet, with a PL2
    assert others["AuthenticJJ"]["cf"] == 380.8 and others["AuthenticJJ"]["kt"] == 2 * 19.5  # CuongCafCrochet's, replaced
    assert others["NotInPlanShop"]["cf"] == 0 and others["OldShop"]["kt"] == 0
    assert data["others"]["count"] == 3 and data["others"]["cf"] == round(120.5 + 380.8, 2)
    assert data["total"]["cf"] == round(8047.98 - 2497.19 - 435.14 + 120.5 + 380.8, 2)
    assert data["cf"]["sheet"]["name"] == "PL Account" and data["cf"]["warnings"] == []


def test_pl2_per_account_follows_the_team_filter_and_leaves_cf_out_for_sellers(client, member, upstream, sheets, monkeypatch):
    monkeypatch.setattr(report, "filter_options", lambda db, kind, user=None: (
        [{"id": n, "name": n} for n in SUBS] if kind == "sub_product_types" else [{"id": 12, "name": "Etsy 1.ZenE"}]))
    one = client.get(f"{A}&teams=12", headers=member).json()["data"]
    assert [a["shop"] for a in one["accounts"]] == ["PunGanterdesign"]
    seller = client.get(f"{A}&sellers=7", headers=member).json()["data"]
    assert "seller" in seller["cf"]["error"] and seller["accounts"][0]["cf"] is None and seller["accounts"][0]["kt"] is not None
