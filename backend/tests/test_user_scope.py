"""A member limited to some trackingis sellers (Settings › Users) sees only their sales, wherever they ask from."""
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.services import trackingis
from tests.test_mcp import _call, _data, _token
from tests.test_report import _save_token

R = "/api/v1/report/etsy"
LINH, MAI = "41", "44"


@pytest.fixture()
def upstream(monkeypatch):
    """Fake trackingis: the seller list, and one store row for any report; records each report request."""
    calls: list[dict[str, list[str]]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/filter/seller"):
            return httpx.Response(200, json={"success": True, "data": [{"id": int(LINH), "name": "Linh PT"}, {"id": int(MAI), "name": "Mai VTT"}]})
        if "/filter/" in req.url.path:
            return httpx.Response(200, json={"success": True, "data": []})
        calls.append(parse_qs(urlparse(str(req.url)).query))
        return httpx.Response(200, json={"success": True, "data": {"data": [{"date_at": "2026-10-01", "shop_name": "Daisyfloralsshop", "total_order": 3,
                                                                              "total_quantity": 4, "total": 0, "sale_tax": 0, "total_revenue": 40.0}],
                                                                   "paging": {"current_page": 1, "per_page": 31, "total": 1, "last_page": 1}}})

    monkeypatch.setattr(trackingis, "TEST_TRANSPORT", httpx.MockTransport(handler))
    return calls


def _limit(client, admin, member, sellers):
    me = client.get("/api/v1/auth/me", headers=member).json()["data"]
    res = client.patch(f"/api/v1/users/{me['id']}", json={"scope_sellers": sellers}, headers=admin)
    assert res.status_code == 200 and res.json()["data"]["scope_sellers"] == sellers
    return me["id"]


def test_a_limited_member_always_gets_their_own_sellers(client, admin, member, upstream):
    _save_token(client, admin)
    _limit(client, admin, member, [LINH])
    for query in ("", f"&sellers={MAI}", f"&sellers={MAI},{LINH}"):  # nothing, someone else, or someone else too
        client.get(f"{R}?view=store&date_from=2026-10-01&date_to=2026-10-02{query}", headers=member)
        assert upstream[-1]["sellers[]"] == [LINH]
    client.get(f"{R}/totals?date_from=2026-10-01&date_to=2026-10-02", headers=member)
    assert upstream[-1]["sellers[]"] == [LINH]
    assert [s["name"] for s in client.get(f"{R}/options/sellers", headers=member).json()["data"]] == ["Linh PT"]
    # the admin is never limited, whatever the users table says
    client.get(f"{R}?view=store&date_from=2026-10-01&date_to=2026-10-02", headers=admin)
    assert "sellers[]" not in upstream[-1]
    assert len(client.get(f"{R}/options/sellers", headers=admin).json()["data"]) == 2


def test_a_limited_member_cannot_open_the_whole_of_zene(client, admin, member, upstream):
    _save_token(client, admin)
    assert client.get("/api/v1/sheets", headers=member).status_code == 200  # not limited yet
    _limit(client, admin, member, [LINH])
    for path in ("/api/v1/sheets", "/api/v1/sheets/1/rows", "/api/v1/plan/products"):
        res = client.get(path, headers=member)
        assert res.status_code == 403 and "your own sales" in res.json()["meta"]["message"]
    assert client.post("/api/v1/sheets/1/sync", headers=member).status_code == 403
    token = _token(client, member)
    for tool, args in (("list_sheets", {}), ("read_sheet", {"sheet": "1"}), ("sync_sheet", {"sheet": "1"})):
        out = _call(client, token, tool, args)
        assert out["isError"] and "your own sales" in out["content"][0]["text"]
    assert _data(_call(client, token, "etsy_totals", {"date_from": "2026-10-01", "date_to": "2026-10-02", "sellers": MAI}))
    assert upstream[-1]["sellers[]"] == [LINH]  # agents are limited the same way


def test_the_scope_is_cleared_with_an_empty_list(client, admin, member, upstream):
    _save_token(client, admin)
    user_id = _limit(client, admin, member, [LINH])
    res = client.patch(f"/api/v1/users/{user_id}", json={"scope_sellers": []}, headers=admin)
    assert res.json()["data"]["scope_sellers"] == []
    client.get(f"{R}?view=store&date_from=2026-10-01&date_to=2026-10-02", headers=member)
    assert "sellers[]" not in upstream[-1] and client.get("/api/v1/sheets", headers=member).status_code == 200
