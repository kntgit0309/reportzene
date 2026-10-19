from datetime import date, datetime

from app.models import SheetSource
from app.services import sheet_sync
from app.services.lark_sheets import LarkError
from tests.test_sheets import URL, lark  # noqa: F401  (fixture)

S = "/api/v1/sheets"


def test_due_once_a_day_after_the_time():
    assert not sheet_sync.due(datetime(2026, 10, 20, 9, 59), "10:00", None)
    assert sheet_sync.due(datetime(2026, 10, 20, 10, 0), "10:00", None)
    assert sheet_sync.due(datetime(2026, 10, 20, 15, 30), "10:00", date(2026, 10, 19))  # started late: catches up once
    assert not sheet_sync.due(datetime(2026, 10, 20, 15, 30), "10:00", date(2026, 10, 20))  # already ran today
    assert not sheet_sync.due(datetime(2026, 10, 20, 12, 0), "", None)  # turned off


def test_daily_sync_reads_every_sheet_again(client, db_factory, admin, member, lark, monkeypatch):  # noqa: F811
    monkeypatch.setattr(sheet_sync, "SessionLocal", db_factory)
    ok = client.post(S, json={"name": "KH", "url": URL, "header_row": 2}, headers=admin).json()["data"]["id"]
    bad = client.post(S, json={"name": "PL", "url": URL, "header_row": 2}, headers=admin).json()["data"]["id"]
    with db_factory() as s:
        s.get(SheetSource, ok).last_synced_at = s.get(SheetSource, bad).last_synced_at = datetime(2026, 10, 1)
        s.get(SheetSource, bad).url = "https://isuccess.sg.larksuite.com/wiki/NoAccess123"
        s.commit()
    real_read = lark.read_tab

    def read_tab(self, url, tab_id, header_row, max_rows):  # Lark refuses the second sheet
        if "NoAccess" in url:
            raise LarkError("no permission")
        return real_read(self, url, tab_id, header_row, max_rows)

    monkeypatch.setattr(lark, "read_tab", read_tab)

    assert sheet_sync.tick(datetime(2026, 10, 20, 9, 0)) is None  # before 10:00
    assert sheet_sync.tick(datetime(2026, 10, 20, 10, 1)) == {"synced": 1, "failed": 1}
    assert sheet_sync.tick(datetime(2026, 10, 20, 16, 0)) is None  # once a day
    with db_factory() as s:
        synced = s.get(SheetSource, ok)
        assert synced.last_error is None and synced.last_synced_at.replace(tzinfo=None) > datetime(2026, 10, 1)
        assert s.get(SheetSource, bad).last_error == "no permission" and s.get(SheetSource, bad).row_count == 2  # old rows kept
    last = client.get("/api/v1/settings", headers=admin).json()["data"]["sheet_sync_last"]
    assert last["day"] == "2026-10-20" and last["synced"] == 1 and last["failed"] == 1


def test_sync_time_is_a_setting(client, admin):
    assert client.get("/api/v1/settings", headers=admin).json()["data"]["sheet_sync_at"] == "10:00"
    assert client.put("/api/v1/settings", json={"sheet_sync_at": "07:30"}, headers=admin).json()["data"]["sheet_sync_at"] == "07:30"
    assert client.put("/api/v1/settings", json={"sheet_sync_at": "25:00"}, headers=admin).status_code == 422
    assert client.put("/api/v1/settings", json={"sheet_sync_at": ""}, headers=admin).json()["data"]["sheet_sync_at"] == ""
