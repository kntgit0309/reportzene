"""Daily sync of every team sheet, at the time set in Settings (default 10:00, Vietnam time).

The team sheets are live Lark files (plans, finance's PL…) that people keep filling in; ReportZenE reads their last sync, so
each day it reads them all again. A sheet Lark refuses keeps its previous rows and shows the error in Lark › Team sheets.
The day of the last run is saved, so a restart (each deploy) does not sync again the same day; a server started after the
time catches up once.
"""
import asyncio
import logging
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AppError
from app.db import SessionLocal
from app.models import AppSetting, SheetSource
from app.models.base import utcnow
from app.services import settings_store, sheets

log = logging.getLogger("rzn.sheet_sync")
KEY = "sheet_sync"  # AppSetting holding the last run: {day, finished_at, synced, failed}
CHECK_EVERY_S = 30


def due(now: datetime, at: str, last_day: date | None) -> bool:
    """Whether the daily sync should run now: the time ("HH:MM", "" = never) has passed today and it has not run today."""
    if not at:
        return False
    hour, minute = (int(x) for x in at.split(":"))
    return (now.hour, now.minute) >= (hour, minute) and last_day != now.date()


def last_run(db: Session) -> dict[str, Any]:
    row = db.get(AppSetting, KEY)
    return dict(row.value) if row else {}


def _save(db: Session, value: dict[str, Any]) -> None:
    row = db.get(AppSetting, KEY)
    if row is None:
        db.add(AppSetting(key=KEY, value=value))
    else:
        row.value = value
    db.commit()


def sync_all(db: Session) -> dict[str, int]:
    """Read every team sheet again: {synced, failed}."""
    done = failed = 0
    for source in db.scalars(select(SheetSource).order_by(SheetSource.id)).all():
        try:
            sheets.sync(db, source)
            done += 1
        except AppError as exc:
            failed += 1
            log.warning("Daily sync: sheet %s (%s) failed: %s", source.id, source.name, exc.message)
    return {"synced": done, "failed": failed}


def tick(now: datetime | None = None) -> dict[str, int] | None:
    """Run the daily sync when it is due; the result, or None when it was not due."""
    now = now or datetime.now(ZoneInfo(settings.timezone))
    with SessionLocal() as db:
        previous = last_run(db).get("day")
        if not due(now, settings_store.runtime(db).sheet_sync_at, date.fromisoformat(previous) if previous else None):
            return None
        _save(db, {"day": now.date().isoformat(), "started_at": utcnow().isoformat()})  # first, so a slow run is not started twice
        result = sync_all(db)
        _save(db, {"day": now.date().isoformat(), "finished_at": utcnow().isoformat(), **result})
    log.info("Daily sync of the team sheets: %s synced, %s failed", result["synced"], result["failed"])
    return result


async def run_forever() -> None:
    """Background task of the server (started in main.create_app): check every CHECK_EVERY_S seconds."""
    while True:
        try:
            await asyncio.to_thread(tick)
        except Exception:  # never let one bad run stop the daily sync
            log.exception("Daily sync of the team sheets failed")
        await asyncio.sleep(CHECK_EVERY_S)
