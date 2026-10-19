from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.services import trackingis
from app.services.ornament import ALL_SUB_TYPES, GROUPS
from tests.test_report import _save_token

O = "/api/v1/report/etsy/ornament"
ORDERS = {s: i + 1 for i, s in enumerate(ALL_SUB_TYPES)}  # orders per day of each sub product type in the fake trackingis
DAYS = ("2026-10-01", "2026-10-02")


@pytest.fixture()
def upstream(monkeypatch):
    """Fake trackingis date view: each day sells ORDERS[s] orders of every sub product type in the filter."""
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        n = sum(ORDERS[s] for s in parse_qs(urlparse(str(req.url)).query).get("sub_product_types[]", []))
        rows = [{"date_at": d, "total_order": n, "total_quantity": 2 * n, "total": 11.0 * n, "sale_tax": 1.0 * n, "total_revenue": 10.0 * n}
                for d in DAYS]
        return httpx.Response(200, json={"success": True, "data": {"data": rows, "paging": {"current_page": 1, "per_page": 31,
                                                                                              "total": len(rows), "last_page": 1}}})

    monkeypatch.setattr(trackingis, "TEST_TRANSPORT", httpx.MockTransport(handler))
    return calls


def test_ornament_needs_sign_in(client):
    assert client.get(O).status_code == 401


def test_ornament_groups_sub_product_types(client, admin, member, upstream):
    _save_token(client, admin, teams=["12"])
    url = f"{O}?date_from=2026-10-01&date_to=2026-10-02&shops=5&product_types=Shirt"
    data = client.get(url, headers=member).json()["data"]

    assert [g["name"] for g in data["groups"]] == [name for name, _ in GROUPS]
    assert data["groups"][-1]["name"] == "Others" and data["groups"][-1]["children"][-1]["name"] == "Wooden Garland"
    felt = next(g for g in data["groups"] if g["name"] == "Felt")
    n = ORDERS["Felt Ornament"] + ORDERS["Needle Felted Ornament"]
    assert felt["total_order"] == 2 * n and felt["total_revenue"] == 20.0 * n and [d["date_at"] for d in felt["daily"]] == list(DAYS)
    assert [c["total_order"] for c in felt["children"]] == [2 * ORDERS["Felt Ornament"], 2 * ORDERS["Needle Felted Ornament"]]
    assert data["total"]["total_order"] == 2 * sum(ORDERS.values())
    assert felt["share"] == round(felt["total_revenue"] / data["total"]["total_revenue"], 4)

    # one query for the total, one per product type, one per sub product type: page filters kept, product type replaced
    assert len(upstream) == 1 + len(GROUPS) + len(ALL_SUB_TYPES)
    for req in upstream:
        q = parse_qs(urlparse(str(req.url)).query)
        assert q["view"] == ["date"] and q["shops[]"] == ["5"] and q["teams[]"] == ["12"] and "product_types[]" not in q
    client.get(url, headers=member)
    assert len(upstream) == 1 + len(GROUPS) + len(ALL_SUB_TYPES)  # same filters within a minute: cached
