import json

import httpx

from app.services import trackingis
from tests.test_sheets import URL, FakeLark

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _token(client, who) -> str:
    return client.post("/api/v1/auth/tokens", json={"name": "agent"}, headers=who).json()["data"]["token"]


def _call(client, token, name, args=None):
    h = {**HEADERS, "Authorization": f"Bearer {token}"}
    client.post("/mcp", json=INIT, headers=h)
    res = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": args or {}}}, headers=h)
    assert res.status_code == 200, res.text
    return res.json()["result"]


def _data(result):
    """Tool output: structuredContent when the SDK sends it, else the JSON text block."""
    assert not result.get("isError"), result
    if "structuredContent" in result:
        return result["structuredContent"]
    return json.loads(result["content"][0]["text"])


def test_mcp_lists_read_only_tools(client, member):
    h = {**HEADERS, "Authorization": f"Bearer {_token(client, member)}"}
    tools = client.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, headers=h).json()["result"]["tools"]
    assert {t["name"] for t in tools} == {"whoami", "etsy_totals", "etsy_overview", "etsy_pl2", "etsy_report", "etsy_ornament", "etsy_ornament_accounts", "etsy_shirt",
                                          "etsy_shirt_accounts", "etsy_blanket", "etsy_blanket_accounts", "etsy_flag", "etsy_flag_accounts",
                                          "etsy_wooden_block", "etsy_wooden_block_accounts", "etsy_badge_reel", "etsy_badge_reel_accounts",
                                          "etsy_others", "etsy_others_accounts",
                                          "filter_options", "list_sheets", "read_sheet", "sync_sheet"}


def test_mcp_rejects_missing_or_bad_token(client):
    out = _call(client, "rzn_nope", "whoami")
    assert out["isError"] and "Invalid" in out["content"][0]["text"]


def test_mcp_whoami_and_report(client, admin, member, monkeypatch):
    monkeypatch.setattr(trackingis, "TEST_TRANSPORT", httpx.MockTransport(lambda r: httpx.Response(200, json={
        "success": True, "data": {"data": [{"seller_name": "Mai VTT.ETS", "total_order": 15}], "paging": {"total": 1, "last_page": 1}}})))
    client.put("/api/v1/settings", json={"trackingis_token": "tis-token"}, headers=admin)
    assert _data(_call(client, _token(client, member), "whoami"))["role"] == "member"
    out = _call(client, _token(client, member), "etsy_report", {"view": "seller", "date_from": "2026-10-16", "date_to": "2026-10-16"})
    assert _data(out)["rows"][0]["seller_name"] == "Mai VTT.ETS"
    bad = _call(client, _token(client, member), "etsy_report", {"view": "nope"})
    assert bad["isError"] and "Unknown view" in bad["content"][0]["text"]


def test_mcp_reads_sheet_by_name(client, admin, member, monkeypatch):
    monkeypatch.setattr("app.services.sheets.LarkClient", FakeLark)
    FakeLark.fail = None
    client.put("/api/v1/settings", json={"lark_app_id": "cli_test", "lark_app_secret": "secret-123"}, headers=admin)
    client.post("/api/v1/sheets", json={"name": "Báo cáo tuần", "url": URL, "header_row": 2}, headers=admin)
    out = _call(client, _token(client, member), "read_sheet", {"sheet": "báo cáo tuần", "q": "mai"})
    data = _data(out)
    assert data["paging"]["total"] == 1 and data["rows"][0]["Doanh số"] == "1200"
