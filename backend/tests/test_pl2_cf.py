from app.models import SheetSource
from app.services import report
from app.services.pl2_cf import parse
from tests.test_overview import TRACKINGIS_SUBS, business_plan, upstream  # noqa: F401  (fixtures)

P = "/api/v1/report/etsy/pl2"
# "Tổng kết PL Monthly": the header row is "B.U | TỔNG | months"
HEADER = ["B.U", "TỔNG", "09-2026", "10-2026", "11-2026"]


def _row(label: str, *values: object) -> dict[str, str]:
    return dict(zip(HEADER, [label, *(str(v) for v in values)] + [""] * (len(HEADER) - 1 - len(values)), strict=True))


ROWS = [
    _row("", "", "", "", "445000"),  # quarter totals without a label: not read
    _row("KẾ HOẠCH B.U ZenE", 904600, 78200, 64800, 209300),
    _row("- Kế hoạch PL2_Etsy 1", 444728.25, 32200, 38022.5, 109964.75),
    _row("- Kế hoạch PL2_Etsy 2", 396957, 33700, 26775, 82446.5),
    _row("- Kế hoạch PL2_Support Account"),
    _row("THỰC ĐẠT B.U ZenE", 503239.05, 34514.64, 18236.89, -2340),
    _row("- Thực đạt Profit PL2 _Etsy 1", 292922.38, 27636.29, 14816.95, -300),
    _row("- Thực đạt Profit PL2 _Etsy 2", 196847.84, 9809.28, 4855.08, -1000),
    _row("- Thực đạt Profit PL2 _Support", 6133.93, 0, 0, 0),
    _row("- TiktokShop Received", 44792.52),  # not a PL2 line
    _row("CHÊNH LỆCH B.U ZenE", -17141.03, -43685.36, -46560.61, 0),  # actual − the whole month's plan: computed to date here
    _row("- Chênh lệch PL2_Etsy 1", 48299.88, -4563.71, -23205.55),
    _row("- Chênh lệch PL2_Etsy 2", -39027.16, -23890.72, -21919.92),
    _row("TỶ LỆ HOÀN THÀNH KH B.U", 0.56, 0.44, 0.28),  # computed here, not read
]


def test_cf_sheet_is_read_per_line_and_month():
    cf = parse(HEADER, ROWS)
    assert cf["months"] == ["09-2026", "10-2026", "11-2026"]
    assert set(cf["lines"]) == {"zene", "etsy 1", "etsy 2", "support"}
    assert cf["lines"]["zene"]["plan"]["10-2026"] == 64800 and "gap" not in cf["lines"]["zene"]
    assert cf["lines"]["etsy 1"]["actual"]["10-2026"] == 14816.95 and cf["lines"]["support"]["actual"]["09-2026"] == 0


def _cf_sheet(client, db_factory, admin):
    with db_factory() as s:
        sheet = SheetSource(name="Tổng kết PL Monthly", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title=" Tổng kết PL Monthly",
                            header=HEADER, rows=ROWS, row_count=len(ROWS))
        s.add(sheet)
        s.commit()
    assert client.put("/api/v1/settings", json={"pl2_cf_sheet_id": sheet.id}, headers=admin).json()["data"]["pl2_cf_sheet_id"] == sheet.id


def test_pl2_kt_vs_cf_per_month(client, db_factory, admin, member, upstream, business_plan):  # noqa: F811
    assert "Settings" in client.get(f"{P}?date_from=2026-10-01&date_to=2026-10-02", headers=member).json()["data"]["cf"]["error"]
    _cf_sheet(client, db_factory, admin)

    data = client.get(f"{P}?date_from=2026-09-30&date_to=2026-10-02", headers=member).json()["data"]
    assert data["cf"]["scope"] == "B.U ZenE" and [m["month"] for m in data["months"]] == ["09-2026", "10-2026"]
    sep, octo = data["months"]
    to_date = round(64800 * 2 / 31, 2)
    assert octo["plan"] == 64800 and octo["actual"] == 18236.89 and octo["plan_to_date"] == to_date
    assert octo["gap"] == round(18236.89 - to_date, 2) and octo["achieved"] == round(18236.89 / to_date, 4)  # against plan to date
    kt = client.get("/api/v1/report/etsy/overview?date_from=2026-10-01&date_to=2026-10-02", headers=member).json()["data"]["total"]["pl2_est"]
    assert octo["kt"] == kt and octo["kt_minus_cf"] == round(kt - 18236.89, 2)  # KT for the report's days of the month
    assert sep["days"] == 1 and sep["plan"] == 78200
    assert [t["team"] for t in octo["teams"]] == ["Etsy 1", "Etsy 2", "Support Account"]
    etsy1 = octo["teams"][0]
    assert etsy1["actual"] == 14816.95 and etsy1["gap"] == round(14816.95 - round(38022.5 * 2 / 31, 2), 2)
    assert octo["teams"][2]["plan"] is None and octo["teams"][2]["gap"] is None
    assert data["total"]["actual"] == round(34514.64 + 18236.89, 2) and data["total"]["plan"] == 78200 + 64800
    assert data["total"]["gap"] == round(sep["gap"] + octo["gap"], 2)


def test_pl2_cf_follows_the_team_filter(client, db_factory, admin, member, upstream, business_plan, monkeypatch):  # noqa: F811
    _cf_sheet(client, db_factory, admin)
    monkeypatch.setattr(report, "filter_options", lambda db, kind, user=None: (
        [{"id": n, "name": n} for n in TRACKINGIS_SUBS] if kind == "sub_product_types" else [{"id": 12, "name": "Etsy 1.ZenE"}]))
    data = client.get(f"{P}?date_from=2026-10-01&date_to=2026-10-02&teams=12", headers=member).json()["data"]
    [octo] = data["months"]
    assert data["cf"]["scope"] == "Etsy 1" and octo["plan"] == 38022.5 and octo["actual"] == 14816.95 and "teams" not in octo
    assert octo["kt"] is not None  # PL2 theo KT also for one team

    store = client.get(f"{P}?date_from=2026-10-01&date_to=2026-10-02&shops=5", headers=member).json()["data"]
    assert "per team" in store["cf"]["error"] and store["months"][0]["kt"] is not None
