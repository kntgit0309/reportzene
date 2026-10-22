"""PL2 theo CF of a seller: their "Profit tính KPI" from each team's seller P&L tab, next to their PL2 plan and KT."""
import pytest

from app.core.errors import AppError
from app.models import SheetSource
from app.services.seller_cf import parse
from tests.test_overview import business_plan, upstream  # noqa: F401  (fixtures)
from tests.test_seller_plan import seller_sheet  # noqa: F401  (fixture: seller plan sheet, Linh PT = trackingis seller 41)

P = "/api/v1/report/etsy/pl2?date_from=2026-10-01&date_to=2026-10-02"
MONTHS = [f"{m:02d}-2026" for m in range(1, 13)]
HEADER = ["Column 1", "Column 2", *MONTHS, "Jan-26"]  # "1.2 P&L Seller (Sau IP)_Monthly": months, then another block


def _row(label: str, name: str, *values: object) -> dict[str, str]:
    cells = [label, name, *(str(v) for v in values)]
    return dict(zip(HEADER, cells + [""] * (len(HEADER) - len(cells)), strict=True))


ROWS = [
    _row("Tổng hợp", "214656", 37657, 30165),  # another section above
    _row("Profit tính KPI", "Anh NTM", 318.7, 737.3, 750.2, -897.7, -600.5, -686.1, -1452.3, -700.2, -1309.6, 0, 0, 0),
    _row("", "Linh PT", 12682.78, 11009.87, 24318.39, 6234.59, 1249.93, 10622.49, 1694.58, -112.21, 2692.46, 2571.47, 0, 0, 1.2),
    _row("", "AN NTT", 13148.08, 10177.77, 19992.51, 5928.22, 1895.59, 11948.64, 1408.42, -1494.17, 3304.91, 13514.58, 0, 0),
    _row("", "", *[0] * 12),  # the section ends at a row without a seller
    _row("Tỷ trọng profit", "Anh NTM", 0.0095, 0.0273),
]


def test_sellers_profit_per_month_is_read_from_the_kpi_section():
    sellers = parse(HEADER, ROWS)
    assert set(sellers) == {"anh", "linh", "an"} and sellers["linh"]["name"] == "Linh PT"
    assert sellers["linh"]["actual"]["10-2026"] == 2571.47 and len(sellers["linh"]["actual"]) == 12  # not the Jan-26 block
    assert sellers["anh"]["actual"]["01-2026"] == 318.7  # not the share rows below

    # finance's summary tab ("PL Seller Etsy_Monthly": team, seller, then the label) cannot be read: say which tabs to pick
    summary = [_row("Etsy 1", "Mai VTT", "x")]
    summary[0]["Column 1"], summary[0]["Column 2"], summary[0]["01-2026"] = "Etsy 1", "Mai VTT", "Profit tính KPI"
    with pytest.raises(AppError, match="1.2 P&L Seller"):
        parse(HEADER, summary)


def test_pl2_kt_vs_cf_for_a_seller(client, db_factory, admin, member, upstream, business_plan, seller_sheet):  # noqa: F811
    assert "seller CF sheets" in client.get(f"{P}&sellers=41", headers=admin).json()["data"]["cf"]["error"]
    with db_factory() as s:
        sheet = SheetSource(name="Etsy 2 P&L Seller", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="1.2 P&L Seller (Sau IP)_Monthly",
                            header=HEADER, rows=ROWS, row_count=len(ROWS))
        s.add(sheet)
        s.commit()
    client.put("/api/v1/settings", json={"seller_cf_sheets": [str(sheet.id)]}, headers=admin)

    data = client.get(f"{P}&sellers=41", headers=admin).json()["data"]
    assert data["cf"]["scope"] == "Linh PT" and data["cf"]["sheet"]["name"] == "Etsy 2 P&L Seller"
    [octo] = data["months"]
    assert octo["actual"] == 2571.47 and octo["plan"] == 8938  # her PL2 plan for T10 in the seller plan sheet
    assert octo["plan_to_date"] == round(8938 * 2 / 31, 2) and octo["gap"] == round(2571.47 - octo["plan_to_date"], 2)
    assert octo["kt"] is not None and "teams" not in octo

    me = client.get("/api/v1/auth/me", headers=member).json()["data"]  # Linh herself sees the same
    client.patch(f"/api/v1/users/{me['id']}", json={"scope_sellers": ["41"]}, headers=admin)
    assert client.get(P, headers=member).json()["data"]["months"][0]["actual"] == 2571.47
