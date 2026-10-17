import pytest

from app.services import lark_sheets
from app.services.lark_sheets import LarkError, unique_header

URL = "https://isuccess.sg.larksuite.com/sheets/AbCdEfGhIjKlMn123?sheet=t1"
S = "/api/v1/sheets"


class FakeLark:
    """Stands in for LarkClient: one spreadsheet with a title row, a header row and data."""

    fail: str | None = None

    def __init__(self, app_id, app_secret, base_url=""):
        if not (app_id and app_secret):
            raise LarkError("Lark App ID / App Secret not set (Settings → Lark)")

    def check(self):
        return None

    def tabs(self, url):
        return [{"sheet_id": "t1", "title": "T10", "rows": 5}, {"sheet_id": "t2", "title": "T11", "rows": 0}], "t1"

    def read_tab(self, url, tab_id, header_row, max_rows):
        if FakeLark.fail:
            raise LarkError(FakeLark.fail)
        header = ["Seller", "Doanh số", "Ghi chú"] if header_row == 2 else ["BÁO CÁO TUẦN", "Column 2", "Column 3"]
        rows = [{"_row": "3", "Seller": "Mai", "Doanh số": "1200", "Ghi chú": "ok"},
                {"_row": "4", "Seller": "Thủy", "Doanh số": "900", "Ghi chú": "thiếu flag"}]
        return {"sheet_id": tab_id or "t1", "title": "T10"}, header, rows


@pytest.fixture()
def lark(monkeypatch, client, admin):
    monkeypatch.setattr("app.services.sheets.LarkClient", FakeLark)
    FakeLark.fail = None
    client.put("/api/v1/settings", json={"lark_app_id": "cli_test", "lark_app_secret": "secret-123"}, headers=admin)
    return FakeLark


def test_lark_link_parsing_and_header_cleanup():
    assert lark_sheets.parse_url(URL).sheet_id == "t1"
    with pytest.raises(LarkError):
        lark_sheets.parse_url("https://google.com/x")
    assert unique_header(["Seller", "", "Seller", "_row"]) == ["Seller", "Column 2", "Seller (2)", "_row (2)"]


def test_admin_adds_sheet_and_everyone_reads_the_snapshot(client, admin, member, lark):
    assert client.post("/api/v1/sheets/tabs", json={"url": URL}, headers=admin).json()["data"]["linked_tab_id"] == "t1"
    res = client.post(S, json={"name": "Báo cáo tuần", "url": URL, "header_row": 2}, headers=admin)
    assert res.status_code == 200 and res.json()["data"]["row_count"] == 2 and res.json()["data"]["header"][0] == "Seller"
    sid = res.json()["data"]["id"]
    assert client.post(S, json={"name": "x", "url": URL}, headers=member).status_code == 403
    page = client.get(f"{S}/{sid}/rows?q=flag", headers=member).json()
    assert page["paging"]["total"] == 1 and page["data"][0]["Seller"] == "Thủy"


def test_sync_error_keeps_old_rows_and_records_it(client, admin, member, lark):
    sid = client.post(S, json={"name": "Tuần", "url": URL, "header_row": 2}, headers=admin).json()["data"]["id"]
    lark.fail = "The Lark app has no access to this sheet"
    assert client.post(f"{S}/{sid}/sync", headers=member).status_code == 422
    sheet = client.get(S, headers=member).json()["data"][0]
    assert sheet["row_count"] == 2 and "no access" in sheet["last_error"]


def test_sheet_link_must_be_lark(client, admin, lark):
    assert client.post(S, json={"name": "x", "url": "https://evil.example.com/sheets/abc"}, headers=admin).status_code == 422


def test_sheets_without_lark_app_say_so(client, admin):
    res = client.post("/api/v1/sheets/tabs", json={"url": URL}, headers=admin)
    assert res.status_code == 503 and "Settings" in res.json()["meta"]["message"]
