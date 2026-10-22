"""A seller's plan (admin's report filtered by seller): ZenE's plans × the seller's share of each month's PL2 plan."""
import pytest

from app.models import SheetSource
from app.services import report
from app.services.families import ORNAMENT
from app.services.family_plan import parse as parse_kh
from app.services.family_plan import plan_for
from app.services.seller_plan import match, name_key, parse
from tests.test_ornament_plan import HEADER as KH_HEADER
from tests.test_ornament_plan import OCT_FELT
from tests.test_ornament_plan import ROWS as KH_ROWS
from tests.test_overview import TRACKINGIS_SUBS, V, business_plan, upstream  # noqa: F401  (fixtures)

# "KH quý 4.2026 theo seller": names, Quý IV, PL2 T10–T12 in dollars, then the same labels again as percentages
HEADER = ["Seller", "Quý IV", "PL2 T10", "PL2 T11", "PL2 T12", "Column 6", "PL2 T10 (2)", "PL2 T11 (2)", "PL2 T12 (2)"]


def _row(*cells: str) -> dict[str, str]:
    return dict(zip(HEADER, [*cells, *[""] * (len(HEADER) - len(cells))], strict=True))


ROWS = [
    _row("", "$118,409", "$18,087", "$61,988", "$38,334", "", "100%", "100%", "100%"),  # the sellers' total: no name
    _row("Mai"),  # no plan yet
    _row("Huyền", "$55,747", "$9,149", "$25,598", "$21,000", "", "50.6%", "41.3%", "44.4%"),
    _row("Vân", "$14,572", "$0", "$11,240", "$3,332", "", "0%", "18.1%", "7.0%"),
    _row("Linh", "$57,445", "8,938", "25,150", "23,357", "", "49.4%", "40.6%", "48.6%"),
    _row(),  # the sellers' table ends here: what follows (per team) is not sellers
    _row("Etsy 1", "$66,110", "$16,275", "$26,240", "$23,595", "", "25%", "13%", "14%"),
]
OCT_LINH = 0.494  # the sheet's own share (its % columns)


def test_seller_rows_and_months_are_read_from_the_dollar_columns():
    plan = parse(HEADER, ROWS)
    assert plan["months"] == [10, 11, 12] and set(plan["sellers"]) == {"huyen", "van", "linh"}  # Mai has no figures
    assert plan["sellers"]["linh"]["pl2"] == {10: 8938, 11: 25150, 12: 23357} and plan["total"][10] == 9149 + 8938
    assert plan["sellers"]["linh"]["share"] == {10: 0.494, 11: 0.406, 12: 0.486}  # the % block: "49.4%" → 0.494
    # the label row can also sit under the sheet's header row
    labels = [f"Column {i}" for i in range(1, 10)]
    shifted = [dict(zip(labels, [r.get(h, "") for h in HEADER], strict=True)) for r in [dict(zip(HEADER, HEADER, strict=True)), *ROWS]]
    assert parse(labels, shifted)["sellers"]["huyen"]["pl2"][11] == 25598
    assert name_key("Linh PT.ETS") == name_key("linh") == "linh" and name_key("Thuỷ NT") == "thuy"
    # a stray label further left (a team, a note on the total row) does not take the names' place
    # (here a table on the left runs on past the sellers' last row)
    wide = ["Team", *HEADER]
    rows = [dict(zip(wide, [f"note {i}", *[r[h] for h in HEADER]], strict=True)) for i, r in enumerate(ROWS)]
    assert set(parse(wide, rows)["sellers"]) == {"huyen", "van", "linh"}
    # without the % columns, a share is the seller's dollars / the sellers' total
    dollars = parse(HEADER[:5], [{h: r[h] for h in HEADER[:5]} for r in ROWS])
    assert dollars["sellers"]["linh"]["share"] == {} and dollars["total"][10] == 9149 + 8938


def test_trackingis_sellers_match_the_rows_of_their_first_name():
    sellers = parse(HEADER, ROWS)["sellers"]
    for name in ("Linh PT.ETS", "LinhPT", "linh", "Linh"):
        assert match(sellers, name)["name"] == "Linh", name
    assert match(sellers, "Huyen NT") is sellers["huyen"] and match(sellers, "VânPT") is sellers["van"]
    assert match(sellers, "Linhda") is None and match(sellers, "Khoa NT") is None  # a longer name is someone else


def test_a_sellers_share_scales_every_month_of_a_plan():
    kh = parse_kh(KH_HEADER, KH_ROWS, ORNAMENT)
    half = plan_for(kh, "2026-10-01", "2026-10-31", factors={"10-2026": 0.5})
    assert half["groups"]["Felt"] == {"plan": OCT_FELT * 0.5, "plan_month": round(OCT_FELT * 0.5)}
    assert plan_for(kh, "2026-10-01", "2026-10-31", factors={})["missing_months"] == ["10-2026"]  # no share: no plan


@pytest.fixture()
def seller_sheet(client, db_factory, admin, monkeypatch):
    with db_factory() as s:
        sheet = SheetSource(name="KH quý 4.2026 theo seller", url="https://x.larksuite.com/sheets/AbCdEfGhIjKl", tab_title="Seller",
                            header=HEADER, rows=ROWS, row_count=len(ROWS))
        s.add(sheet)
        s.commit()
    client.put("/api/v1/settings", json={"seller_plan_sheet_id": sheet.id}, headers=admin)
    monkeypatch.setattr(report, "filter_options", lambda db, kind, user=None: (
        [{"id": n, "name": n} for n in TRACKINGIS_SUBS] if kind == "sub_product_types"
        else [{"id": "41", "name": "Linh PT.ETS"}, {"id": "42", "name": "Khoa NT"}] if kind == "sellers" else []))
    return sheet


def test_admin_filtered_by_seller_gets_their_share_of_the_plan(client, admin, upstream, business_plan, seller_sheet):  # noqa: F811
    data = client.get(f"{V}&sellers=41", headers=admin).json()["data"]
    assert "Linh" in data["plan"]["scope"] and "10-2026 49.4%" in data["plan"]["scope"]
    ornament = data["rows"][0]
    assert ornament["plan"] == round(5535 * OCT_LINH * 2 / 31, 1) and ornament["plan_month"] == round(5535 * OCT_LINH)
    assert ornament["pl2_plan"] == round(33210 * OCT_LINH * 2 / 31, 2)
    unknown = client.get(f"{V}&sellers=42", headers=admin).json()["data"]["plan"]
    assert "no row for Khoa NT" in unknown["error"]


def test_a_seller_limited_to_their_own_sales_gets_their_share_too(client, admin, member, upstream, business_plan, seller_sheet):  # noqa: F811
    me = client.get("/api/v1/auth/me", headers=member).json()["data"]
    client.patch(f"/api/v1/users/{me['id']}", json={"scope_sellers": ["41"]}, headers=admin)
    data = client.get(V, headers=member).json()["data"]
    assert "Linh" in data["plan"]["scope"] and data["rows"][0]["plan"] == round(5535 * OCT_LINH * 2 / 31, 1)
