from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.core.errors import AppError
from app.models import SheetSource
from app.services import report, trackingis
from app.services import account_plan
from app.services.pl2_accounts import parse, parse_account_list
from tests.test_ornament_plan import HEADER as KH_HEADER  # KH Ornament shops: PunGanterdesign, Daisyfloralsshop, OnebyHenry
from tests.test_ornament_plan import ROWS as KH_ROWS
from tests.test_plan import HEADER as PLAN_HEADER  # KHKD: Ornament $6, Blanket $8, Shirt $5.5 PL2/item
from tests.test_plan import ROWS as PLAN_ROWS
from tests.test_report import _save_token
from tests.test_seller_plan import seller_sheet  # noqa: F401  (fixture: seller plan sheet, sellers Linh PT.ETS and Khoa NT)

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
    # one store view per priced product, on its sub types; sent in parallel, so the order they arrive in varies
    assert sorted(a[0] for a in ASKED) == ["Blanket", "Cutout Ornament", "Shirt"]
    rows = {a["shop"]: a for a in data["accounts"]}
    assert list(rows) == ["PunGanterdesign", "Daisyfloralsshop", "OnebyHenry"]  # the KH accounts, in sheet order
    pun = rows["PunGanterdesign"]
    # KH plan to date (01–19/10 of October's 525, 275 and 940 pieces in KH Ornament), for the KH avg/day
    assert pun["plan"] == round(525 * 19 / 31, 1) and rows["OnebyHenry"]["plan"] == round(940 * 19 / 31, 1)
    assert data["total"]["plan"] == round(sum(r["plan"] for r in rows.values()), 1) and data["others"]["plan"] is None
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
    # a seller cuts across stores: only the KH accounts with their sales, without the store plan (Daisyfloralsshop sold nothing)
    assert [a["shop"] for a in seller["accounts"]] == ["PunGanterdesign", "OnebyHenry"] and seller["accounts"][0]["plan"] is None


# "KH theo Acc": the PL2 plan per account. Row 1 (the header) holds the block labels (a title "PL2 theo KT" over the first
# columns, then the real blocks: merged cells keep their label on the first column), row 2 the months, row 3 "Shop Name" | "Team"
# with the totals, then one row per account.
KH_ACC_HEADER = ["PL2 theo KT", "Column 2", "Column 3", "Column 4", "PL2 theo KT (2)", "Column 6", "Column 7", "Column 8",
                 "PL2/item theo CF", "Column 10", "Column 11", "Column 12", "PL2 theo CF", "Column 14", "Column 15", "Column 16"]


def _acc(*cells: object) -> dict[str, str]:
    return dict(zip(KH_ACC_HEADER, [str(c) for c in cells], strict=True))


KH_ACC_ROWS = [
    #     name, team, Sales 11, 12, KT: Total, 10, 11, 12, CF/item: 09, 10, 11, 12, CF: Total, 10, 11, 12
    _acc("", "", "11-2026", "12-2026", "Total", "10-2026", "11-2026", "12-2026", "09-2026", "10-2026", "11-2026", "12-2026", "Total",
         "10-2026", "11-2026", "12-2026"),
    _acc("Shop Name", "Team", 100, 100, "$9,999", "$9,999", "$9,999", "$9,999", "", "", "", "", "$9,999", "$9,999", "$9,999", "$9,999"),
    _acc("PunGanterdesign", "Etsy 1", 10, 10, "$9,300", "$3,100", "$3,100", "$3,100", "$8.2", "$6.2", "$6.4", "$6.5", "$18,600", "$6,200", "$6,200", "$6,200"),
    _acc("Etsy 1", "", "", "", "$3,100", "$3,100", "", "", "", "", "", "", "$6,200", "$6,200", "", ""),  # a team's total: no Team
    _acc("Daisyfloralsshop", "Etsy 2", 10, 10, "$4,650", "$1,550", "$1,550", "$1,550", "", "$0.0", "", "", "$0", "$0", "$0", "$0"),
    _acc("CuongCafCrochet", "Etsy 2", 10, 10, "$1,860", "$620", "$620", "$620", "", "", "", "", "$930", "$310", "$310", "$310"),  # suspended
    _acc("AuthenticJJ", "Etsy 2", "", "", "", "", "", "", "", "", "", "", "", "", "", ""),  # takes over Cuong's plan: no figures of its own
    _acc("OnebyHenry", "Etsy 3", 10, 10, "$2,790", "$930", "$930", "$930", "", "", "", "", "$9,300", "$3,100", "$3,100", "$3,100"),
    _acc("NewPlanShop", "Etsy 1", 10, 10, "$930", "$310", "$310", "$310", "", "", "", "", "$930", "$310", "$310", "$310"),  # no KH store sheet lists it
    _acc("ZeroShop", "Etsy 1", 0, 0, "$0", "$0", "$0", "$0", "", "", "", "", "$0", "$0", "$0", "$0"),  # planned at $0: not a row
    _acc("Total", "", "", "", "$29,999", "$9,999", "", "", "", "", "", "", "$99,999", "$99,999", "", ""),
]


def test_the_account_plan_is_read_from_the_labels_and_months_of_the_tab():
    got = account_plan.parse(KH_ACC_HEADER, KH_ACC_ROWS)
    # the title "PL2 theo KT" over the first columns has no months of its own: the block is the one over its Total / months
    assert got["months"] == {"kt": ["10-2026", "11-2026", "12-2026"], "cf": ["10-2026", "11-2026", "12-2026"]}
    by_shop = {a["shop"]: a for a in got["accounts"]}
    assert list(by_shop) == ["PunGanterdesign", "Daisyfloralsshop", "CuongCafCrochet", "OnebyHenry", "NewPlanShop", "ZeroShop"]
    assert by_shop["PunGanterdesign"]["kt"] == {"10-2026": 3100, "11-2026": 3100, "12-2026": 3100}  # "Total" and PL2/item left out
    assert by_shop["PunGanterdesign"]["cf"]["10-2026"] == 6200 and by_shop["Daisyfloralsshop"]["cf"]["10-2026"] == 0
    merged = account_plan.replace(got["accounts"], (("CuongCafCrochet", "AuthenticJJ"),))
    assert "cuongcafcrochet" not in merged and merged["authenticjj"]["kt"]["10-2026"] == 620 and merged["authenticjj"]["team"] == "Etsy 2"
    # each month pro rata of the report's days; a month the sheet does not plan has none, nor does a seller's month without a share
    days = {"09-2026": (10, 30), "10-2026": (19, 31)}
    assert account_plan.to_date({"10-2026": 3100.0}, ["10-2026"], days) == 1900.0  # September is not in the sheet
    assert account_plan.to_date({}, ["10-2026"], days) == 0.0  # planned month, no figure: $0
    assert account_plan.to_date({"10-2026": 3100.0}, ["11-2026"], days) is None
    assert account_plan.to_date({"10-2026": 3100.0}, ["10-2026"], days, {"10-2026": 0.5}) == 950.0
    assert account_plan.to_date({"10-2026": 3100.0}, ["10-2026"], days, {"09-2026": 0.5}) is None


def test_the_account_plan_layout_errors_name_what_is_missing():
    with pytest.raises(AppError) as err:  # the tab of the other plans: no PL2 theo KT / CF blocks
        account_plan.parse(["Shop Name", "Team", "10-2026"], [{"Shop Name": "A", "Team": "Etsy 1", "10-2026": "5"}])
    assert err.value.code == "ACCOUNT_PLAN_LAYOUT" and "PL2 theo KT" in err.value.message
    no_names = [{k: ("Name" if v == "Shop Name" else v) for k, v in r.items()} for r in KH_ACC_ROWS]
    with pytest.raises(AppError) as err:
        account_plan.parse(KH_ACC_HEADER, no_names)
    assert "Shop Name" in err.value.message


@pytest.fixture()
def kh_theo_acc(client, db_factory, admin, sheets):
    with db_factory() as s:
        sheet = SheetSource(name="KHKD", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="KH theo Acc",
                            header=KH_ACC_HEADER, rows=KH_ACC_ROWS, row_count=len(KH_ACC_ROWS))
        s.add(sheet)
        s.commit()
    client.put("/api/v1/settings", json={"account_plan_sheet_id": sheet.id}, headers=admin)
    return sheet


def test_pl2_per_account_next_to_its_plan_on_the_kt_and_cf_basis(client, member, upstream, kh_theo_acc):
    data = client.get(A, headers=member).json()["data"]
    rows = {a["shop"]: a for a in data["accounts"]}
    # the KH store sheets' accounts, then the plan sheet's accounts that none of them lists (not ZeroShop: planned $0)
    assert list(rows) == ["PunGanterdesign", "Daisyfloralsshop", "OnebyHenry", "AuthenticJJ", "NewPlanShop"]
    pun, daisy, henry, jj, new = (rows[k] for k in rows)
    # 01–19/10: 19 of October's 31 days. KT: 10 pieces of each priced product × $19.5
    assert pun["kt"] == 195 and pun["kt_plan"] == 1900 and pun["kt_gap"] == 195 - 1900 and pun["kt_pct"] == round(195 / 1900, 4)
    assert pun["cf"] == 8047.98 and pun["cf_plan"] == 3800 and pun["cf_gap"] == round(8047.98 - 3800, 2) and pun["cf_pct"] == round(8047.98 / 3800, 4)
    assert daisy["kt_plan"] == 950 and daisy["kt_gap"] == -950 and daisy["kt_pct"] == 0
    assert daisy["cf_plan"] == 0 and daisy["cf_gap"] == -2497.19 and daisy["cf_pct"] is None  # a plan of $0: no percentage
    assert henry["kt_plan"] == 570 and henry["cf_plan"] == 1900 and henry["kt"] == 58.5 and henry["cf"] == -435.14
    assert jj["kt_plan"] == 380 and jj["cf_plan"] == 190 and jj["kt"] == 39 and jj["cf"] == 380.8  # CuongCafCrochet's plan, sales and CF
    assert new["kt_plan"] == 190 and new["cf_plan"] == 190 and new["kt"] == 0 and new["cf"] == 0 and new["plan"] is None
    # outside every plan: a plan of $0, so the whole PL2 is the gap
    others = {c["shop"]: c for c in data["others"]["children"]}
    assert set(others) == {"OldShop", "NotInPlanShop"} and data["others"]["count"] == 2
    assert others["OldShop"]["cf_plan"] == 0 and others["OldShop"]["cf_gap"] == 120.5 and others["NotInPlanShop"]["kt_gap"] == 97.5
    total = data["total"]
    assert total["kt_plan"] == 1900 + 950 + 570 + 380 + 190 and total["cf_plan"] == 3800 + 0 + 1900 + 190 + 190
    assert total["kt_gap"] == round(total["kt"] - total["kt_plan"], 2) == round(sum(r["kt_gap"] for r in [*rows.values(), data["others"]]), 2)
    assert total["cf_gap"] == round(total["cf"] - total["cf_plan"], 2) == round(sum(r["cf_gap"] for r in [*rows.values(), data["others"]]), 2)
    info = data["kh_pl2"]
    assert info["sheet"]["tab_title"] == "KH theo Acc" and info["months"]["kt"] == ["10-2026", "11-2026", "12-2026"] and info["missing"] == []


def test_a_month_the_plan_sheet_does_not_have_is_left_out_and_named(client, member, upstream, kh_theo_acc):
    data = client.get("/api/v1/report/etsy/pl2/accounts?date_from=2026-09-29&date_to=2026-10-02", headers=member).json()["data"]
    pun = next(a for a in data["accounts"] if a["shop"] == "PunGanterdesign")
    assert pun["kt_plan"] == round(3100 * 2 / 31, 2) and pun["cf_plan"] == round(6200 * 2 / 31, 2)  # October's 2 days only
    assert data["kh_pl2"]["missing"] == ["09-2026"]
    out = client.get("/api/v1/report/etsy/pl2/accounts?date_from=2027-03-01&date_to=2027-03-02", headers=member).json()["data"]
    assert all(a["kt_plan"] is None and a["kt_gap"] is None for a in out["accounts"]) and out["kh_pl2"]["missing"] == ["03-2027"]


def test_without_the_plan_sheet_or_with_a_seller_filter_there_is_no_plan(client, member, upstream, sheets, kh_theo_acc, db_factory, admin):
    seller = client.get(f"{A}&sellers=7", headers=member).json()["data"]
    assert "seller" in seller["kh_pl2"]["error"] and all(a["kt_plan"] is None for a in seller["accounts"])
    client.put("/api/v1/settings", json={"account_plan_sheet_id": 0}, headers=admin)
    data = client.get(A, headers=member).json()["data"]
    assert "account PL2 plan sheet" in data["kh_pl2"]["error"]
    assert all(a["kt_plan"] is None and a["cf_plan"] is None for a in data["accounts"])
    assert [a["shop"] for a in data["accounts"]] == ["PunGanterdesign", "Daisyfloralsshop", "OnebyHenry"]  # no extra accounts either


def test_an_admin_filtered_by_seller_gets_the_plan_scaled_by_the_sellers_share(client, admin, upstream, sheets, kh_theo_acc, seller_sheet):  # noqa: F811
    from tests.test_seller_plan import OCT_LINH
    data = client.get(f"{A}&sellers=41", headers=admin).json()["data"]
    pun = next(a for a in data["accounts"] if a["shop"] == "PunGanterdesign")
    assert pun["kt_plan"] == round(1900 * OCT_LINH, 2) and pun["kt_gap"] == round(pun["kt"] - 1900 * OCT_LINH, 2)
    assert pun["cf_plan"] is None and "seller" in data["cf"]["error"]  # CF is per account: the plan on its basis has nothing to meet
    assert "error" not in data["kh_pl2"]
