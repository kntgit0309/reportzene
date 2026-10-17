from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.services import trackingis

R = "/api/v1/report/etsy"


@pytest.fixture()
def upstream(monkeypatch):
    """Fake trackingis: records each request, answers like the real /etsy/report and /filter routes."""
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.headers.get("authorization") != "Bearer tis-token":
            return httpx.Response(401, json={"message": "Unauthenticated."})
        q = parse_qs(urlparse(str(req.url)).query)
        if req.url.path.endswith("/filter/teams"):
            return httpx.Response(200, json={"success": True, "data": [
                {"id": 1, "name": "Amazon Eco", "parent_id": None, "type": "bu"},
                {"id": 9, "name": "ZenE", "parent_id": None, "type": "bu"},
                {"id": 12, "name": "Etsy 1.ZenE", "parent_id": 9, "type": "team"}]})
        if req.url.path.endswith("/filter/product-type"):
            return httpx.Response(200, json={"success": True, "data": [{"value": "Shirt", "label": "Shirt"}]})
        if q.get("view") == ["date"]:
            page = int(q["page"][0])
            rows = {1: [{"date_at": "2026-10-01", "total_order": 10, "total_quantity": 15, "total": 110.5, "sale_tax": 10.5, "total_revenue": 100.0}],
                    2: [{"date_at": "2026-11-01", "total_order": 5, "total_quantity": 5, "total": 52.0, "sale_tax": 2.0, "total_revenue": 50.0}]}[page]
            return httpx.Response(200, json={"success": True, "data": {"data": rows, "paging": {"current_page": page, "per_page": 31, "total": 2, "last_page": 2}}})
        return httpx.Response(200, json={"success": True, "data": {"data": [{"shop_name": "PunGanterdesign", "shop_id": 1124, "total_order": 3}],
                                                                   "paging": {"current_page": 1, "per_page": 20, "total": 1, "last_page": 1}}})

    monkeypatch.setattr(trackingis, "TEST_TRANSPORT", httpx.MockTransport(handler))
    return calls


def _save_token(client, admin, token="tis-token", teams=None):
    body = {"trackingis_token": token, **({"default_teams": teams} if teams is not None else {})}
    assert client.put("/api/v1/settings", json=body, headers=admin).status_code == 200


def test_report_needs_sign_in(client):
    assert client.get(R).status_code == 401


def test_report_without_token_explains_what_to_do(client, member, upstream):
    res = client.get(R, headers=member)
    assert res.status_code == 503 and "Settings" in res.json()["meta"]["message"]
    assert upstream == []


def test_report_forwards_view_dates_and_list_filters(client, admin, member, upstream):
    _save_token(client, admin, teams=["12", "13"])
    res = client.get(f"{R}?view=store&date_from=2026-10-01&date_to=2026-10-16&sellers=41,44&keyword=flag&sort_by=total_revenue",
                     headers=member).json()["data"]
    assert res["rows"][0]["shop_name"] == "PunGanterdesign" and res["paging"]["total"] == 1
    assert res["query"] == {"date_from": "2026-10-01", "date_to": "2026-10-16", "view": "store", "teams": ["12", "13"]}
    q = parse_qs(urlparse(str(upstream[-1].url)).query)
    assert q["view"] == ["store"] and q["from"] == ["2026-10-01"] and q["to"] == ["2026-10-16"]
    assert q["sellers[]"] == ["41", "44"] and q["teams[]"] == ["12", "13"] and q["keyword"] == ["flag"]
    assert upstream[-1].headers["user-agent"].startswith("reportzene/")


def test_empty_teams_param_means_every_team(client, admin, member, upstream):
    _save_token(client, admin, teams=["12"])
    client.get(f"{R}?view=store&teams=", headers=member)
    assert "teams[]" not in parse_qs(urlparse(str(upstream[-1].url)).query)


@pytest.mark.parametrize("query", ["view=nope", "date_from=2026-13-01", "date_from=2026-10-10&date_to=2026-10-01",
                                   "date_from=2024-01-01&date_to=2026-01-01", "sort_by=drop", "symbol=!=", "sellers=1;DROP"])
def test_report_rejects_bad_filters(client, admin, member, upstream, query):
    _save_token(client, admin)
    assert client.get(f"{R}?{query}", headers=member).status_code == 422
    assert upstream == []


def test_totals_sum_every_date_page(client, admin, member, upstream):
    _save_token(client, admin)
    t = client.get(f"{R}/totals?date_from=2026-10-01&date_to=2026-11-15", headers=member).json()["data"]
    assert t["total_order"] == 15 and t["total_revenue"] == 150.0 and t["days"] == 2 and t["avg_order_value"] == 10.0


def test_expired_token_is_reported_not_crashing(client, admin, member, upstream):
    _save_token(client, admin, token="old-token")
    res = client.get(R, headers=member)
    assert res.status_code == 502 and "expired" in res.json()["meta"]["message"]


def test_options_put_zene_teams_first_and_map_value_label(client, admin, member, upstream):
    _save_token(client, admin)
    teams = client.get(f"{R}/options/teams", headers=member).json()["data"]
    assert [t["name"] for t in teams][:2] == ["Etsy 1.ZenE", "ZenE"]
    assert client.get(f"{R}/options/product_types", headers=member).json()["data"] == [{"id": "Shirt", "name": "Shirt"}]
    assert client.get(f"{R}/options/users", headers=member).status_code == 422


def test_settings_are_admin_only_and_never_echo_the_token(client, admin, member, upstream):
    assert client.put("/api/v1/settings", json={"trackingis_token": "x"}, headers=member).status_code == 403
    _save_token(client, admin, token="3574|abcdefghijklmnop")
    s = client.get("/api/v1/settings", headers=admin).json()["data"]
    assert s["trackingis_token"] == "3574…mnop" and "abcdefghijk" not in str(s)
