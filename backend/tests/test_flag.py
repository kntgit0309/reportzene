from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.models import SheetSource
from app.services import trackingis
from app.services.families import FLAG
from app.services.family_plan import parse, plan_for
from tests.test_report import _save_token

F = "/api/v1/report/etsy/flag"
ORDERS = {s: i + 1 for i, s in enumerate(FLAG.sub_types)}  # orders per day of each sub product type
DAYS = ("2026-10-01", "2026-10-02")

HEADER = [f"Column {i}" for i in range(1, 14)]
HEADER[8], HEADER[10], HEADER[12] = "10-2026", "11-2026", "12-2026"  # the month sits over its Total, as in "KH Flag"
LABELS = dict(zip(HEADER, ["Shop Name", "Team", "Ngày 1st sale", "Ngày gỡ hold 100%", "Ngày reserve", "Ngày gỡ reserve", "% Reserve", "",
                           "Total", "", "Total", "", "Total"], strict=True))


def _row(first: list[str], *totals: int) -> dict[str, str]:
    """First 8 columns, then per month only its Total, a blank column between months (layout of "KH Flag")."""
    cells = first + [""] * (8 - len(first))
    for i, total in enumerate(totals):
        cells += ([""] if i else []) + [str(total)]
    return dict(zip(HEADER, cells + [""] * (13 - len(cells)), strict=True))


ROWS = [
    LABELS,
    _row([], 950, 1300, 1350),  # all-shops total row: not a shop
    _row(["PunGanterdesign", "Etsy 1", "", "", "", "", "", "x"], 300, 450, 500),
    _row(["ToochaStore", "Etsy 1", "7/24/2026"]),  # no flag plan
    _row(["Daisyfloralsshop", "Etsy 2"], 50, 50, 50),
    _row(["", "Etsy 1", "2500", "600"], 600, 900, 1000),  # per-team summary: not a shop
]


@pytest.fixture()
def upstream(monkeypatch):
    """Fake trackingis date view: each day sells ORDERS[s] orders of every sub product type in the filter."""
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        n = sum(ORDERS.get(s, 0) for s in parse_qs(urlparse(str(req.url)).query).get("sub_product_types[]", []))
        rows = [{"date_at": d, "total_order": n, "total_quantity": n, "total": 11.0 * n, "sale_tax": 1.0 * n, "total_revenue": 10.0 * n}
                for d in DAYS]
        return httpx.Response(200, json={"success": True, "data": {"data": rows, "paging": {"current_page": 1, "per_page": 31,
                                                                                              "total": len(rows), "last_page": 1}}})

    monkeypatch.setattr(trackingis, "TEST_TRANSPORT", httpx.MockTransport(handler))
    return calls


def test_flag_plan_reads_a_month_with_only_its_total():
    plan = parse(HEADER, ROWS, FLAG)
    assert plan["months"] == ["10-2026", "11-2026", "12-2026"]
    assert [s["shop"] for s in plan["shops"]] == ["PunGanterdesign", "ToochaStore", "Daisyfloralsshop"]
    assert plan["shops"][0]["plan"] == {"10-2026": {"Flag": 300}, "11-2026": {"Flag": 450}, "12-2026": {"Flag": 500}}
    assert plan_for(plan, "2026-11-01", "2026-11-30")["groups"] == {"Flag": {"plan": 500, "plan_month": 500}}


def test_flag_report_is_one_product_type_against_the_plan_total(client, db_factory, admin, member, upstream):
    _save_token(client, admin, teams=["12", "13", "23"])
    with db_factory() as s:
        sheet = SheetSource(name="KH Flag", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="Flag",
                            header=HEADER, rows=ROWS, row_count=len(ROWS))
        s.add(sheet)
        s.commit()
    client.put("/api/v1/settings", json={"family_plan_sheets": {"flag": sheet.id}}, headers=admin)

    data = client.get(f"{F}?date_from=2026-10-01&date_to=2026-10-02", headers=member).json()["data"]
    [flag] = data["groups"]
    assert [c["name"] for c in flag["children"]] == ["Garden Flag", "House Flag", "Flag", "Patchwork Garden Flag", "fan flag", "Banner"]
    assert flag["total_quantity"] == data["total"]["total_quantity"] == 2 * sum(ORDERS.values())
    assert flag["plan"] == data["total"]["plan"] == round(350 * 2 / 31, 1) and flag["plan_month"] == 350
    assert data["plan"]["sheet"]["name"] == "KH Flag" and len(upstream) == 1 + 1 + len(FLAG.sub_types)
