from app.services.ornament import GROUPS, QUANTITY_FIXES
from tests.test_ornament import O, ORDERS, upstream  # noqa: F401  (fixture)
from tests.test_report import _save_token

FELT = QUANTITY_FIXES["Felt Ornament"]


def test_name_ornament_counts_in_acrylic_wood():
    assert "Name ornament" in dict(GROUPS)["Acrylic + Wood"]


def test_unlisted_ornament_sub_types_count_in_others():
    others = dict(GROUPS)["Others"]
    for sub in ("2-layer Wood Orn", "ball ornament", "embroidered ornament", "Embroidery Hoop Ornament", "Wooden Garland"):
        assert sub in others
    every = [s for _, subs in GROUPS for s in subs]
    assert len(every) == len(set(every))  # each sub product type in one product type only: nothing counted twice


def test_felt_fix_is_170_pieces_spread_over_01_to_18_october():
    assert sum(FELT.values()) == 170 and len(FELT) == 18
    assert min(FELT) == "2026-10-01" and max(FELT) == "2026-10-18" and set(FELT.values()) == {9, 10}


def test_team_wide_view_adds_the_missing_felt_pieces(client, admin, member, upstream):  # noqa: F811
    _save_token(client, admin, teams=["12"])
    data = client.get(f"{O}?date_from=2026-10-01&date_to=2026-10-02", headers=member).json()["data"]
    fix = FELT["2026-10-01"] + FELT["2026-10-02"]
    felt = next(g for g in data["groups"] if g["name"] == "Felt")
    felt_ornament, needle = felt["children"]

    assert felt_ornament["total_quantity"] == 2 * 2 * ORDERS["Felt Ornament"] + fix and felt_ornament["fix_quantity"] == fix
    assert felt_ornament["total_order"] == 2 * ORDERS["Felt Ornament"]  # orders and revenue stay as trackingis sent them
    assert "fix_quantity" not in needle
    assert felt["fix_quantity"] == fix
    assert felt["daily"][0]["total_quantity"] == 2 * (ORDERS["Felt Ornament"] + ORDERS["Needle Felted Ornament"]) + FELT["2026-10-01"]
    assert data["total"]["fix_quantity"] == fix and data["fix_note"]

    again = client.get(f"{O}?date_from=2026-10-01&date_to=2026-10-02", headers=member).json()["data"]
    assert again["total"]["total_quantity"] == data["total"]["total_quantity"]  # added once, not again on the cached answer


def test_fix_left_out_when_narrowed_or_outside_its_days(client, admin, member, upstream):  # noqa: F811
    _save_token(client, admin, teams=["12"])
    for query in ("date_from=2026-10-01&date_to=2026-10-02&shops=5", "date_from=2026-10-01&date_to=2026-10-02&teams=13",
                  "date_from=2026-10-19&date_to=2026-10-20"):
        data = client.get(f"{O}?{query}", headers=member).json()["data"]
        assert data["fix_note"] is None and "fix_quantity" not in data["total"], query
