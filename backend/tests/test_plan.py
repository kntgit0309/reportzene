import pytest

from app.core.errors import AppError
from app.models import SheetSource
from app.services.plan import column_letter, parse

P = "/api/v1/plan/products"
MONTHS = ["10-2026", "11-2026", "12-2026"]
HEADER = [f"Column {i}" for i in range(1, 34)]


def _at(start: int, values: list) -> dict[int, str]:
    return {start + i: str(v) for i, v in enumerate(values)}


def _row(n: int, cols: dict[int, str]) -> dict[str, str]:
    return {"_row": str(n), **{h: cols.get(i, "") for i, h in enumerate(HEADER, start=1)}}


# Same shape as the "KH theo Product" tab: another table in column G, the plan from column Q, a next table after a gap
ROWS = [
    _row(2, {7: "Product", **_at(17, ["Product", "PL2/item", "Total Sales", "Total PL2", "Tỷ trọng", *(MONTHS * 3)]), 32: "Product"}),
    _row(3, _at(19, [69525, 444900, 1.00005, 15455, 28360, 25710, 515.17, 945.33, 857, 98600, 180800, 165600])),
    _row(4, {7: "Ornament", **_at(17, ["Ornament", 6, 35725, 214350, 0.4818, 5535, 16290, 13900, 184.5, 543, 463.33, 33210, 97740, 83400])}),
    _row(5, _at(17, ["Blanket", 8, 8100, 64800, 0.1457, 1750, 3130, 3220, 58.33, 104.33, 107.33, 14000, 25040, 25760])),
    _row(6, _at(17, ["Shirt", 5.5, 8100, 44550, 0.1001, 3250, 2700, 2150, 108.33, 90, 71.67, 17875, 14850, 11825])),
    _row(7, {7: "Blanket"}),
    _row(8, _at(17, ["Tăng Ornament", "", "", "", "Sales", *MONTHS])),
]


def test_plan_reads_the_block_from_the_start_column():
    plan = parse(HEADER, ROWS, 17, 11)
    assert plan["months"] == MONTHS
    assert [p["product"] for p in plan["products"]] == ["Ornament", "Blanket", "Shirt"]  # stops at the empty product cell
    ornament = plan["products"][0]
    assert ornament["pl2_per_item"] == 6 and ornament["total_pl2"] == 214350 and ornament["share"] == 0.4818
    assert ornament["sales"] == [5535, 16290, 13900] and ornament["pl2"] == [33210, 97740, 83400]
    assert plan["total"]["total_pl2"] == 444900 and plan["total"]["sales_per_day"] == [515.17, 945.33, 857]
    assert [p["product"] for p in parse(HEADER, ROWS, 17, 2)["products"]] == ["Ornament", "Blanket"]


def test_plan_without_total_row_sums_the_products():
    plan = parse(HEADER, [r for r in ROWS if r["_row"] != "3"], 17, 11)
    assert plan["total"]["total_sales"] == 35725 + 8100 + 8100 and plan["total"]["pl2"][0] == 33210 + 14000 + 17875


def test_plan_layout_errors_name_the_column():
    with pytest.raises(AppError) as err:
        parse(HEADER, ROWS, 18, 11)
    assert err.value.code == "PLAN_LAYOUT" and "column R (18)" in err.value.message
    assert column_letter(17) == "Q" and column_letter(27) == "AA" and column_letter(52) == "AZ"


def test_plan_page_uses_the_sheet_picked_in_settings(client, db_factory, admin, member):
    res = client.get(P, headers=member)
    assert res.status_code == 503 and "Settings" in res.json()["meta"]["message"]
    with db_factory() as s:
        sheet = SheetSource(name="KHKD Quý 4/2026", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="KH theo Product",
                            header=HEADER, rows=ROWS, row_count=len(ROWS))
        s.add(sheet)
        s.commit()
    assert client.put("/api/v1/settings", json={"plan_sheet_id": sheet.id}, headers=member).status_code == 403
    saved = client.put("/api/v1/settings", json={"plan_sheet_id": sheet.id}, headers=admin).json()["data"]
    assert saved["plan_sheet_id"] == sheet.id and saved["plan_start_column"] == 17 and saved["plan_products"] == 11

    data = client.get(P, headers=member).json()["data"]
    assert data["sheet"]["name"] == "KHKD Quý 4/2026" and data["column_letter"] == "Q" and len(data["products"]) == 3

    client.put("/api/v1/settings", json={"plan_start_column": 18}, headers=admin)
    assert client.get(P, headers=member).status_code == 422
    client.put("/api/v1/settings", json={"plan_sheet_id": 0}, headers=admin)
    assert client.get(P, headers=member).json()["meta"]["code"] == "PLAN_NOT_CONFIGURED"
