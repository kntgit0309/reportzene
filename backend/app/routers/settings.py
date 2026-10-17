"""Settings (admins): trackingis service token + Lark app (write-only, shown as a hint), default ZenE teams."""
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import admin
from app.core.responses import ok
from app.db import get_db
from app.models import User
from app.schemas import SettingsIn
from app.services import report, settings_store
from app.services.lark_sheets import LarkClient, LarkError
from app.services.trackingis import TrackingisClient, TrackingisError

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(request: Request, db: Session = Depends(get_db), _: User = Depends(admin)) -> dict[str, Any]:
    return ok(settings_store.status(db), request)


@router.put("")
def save_settings(body: SettingsIn, request: Request, db: Session = Depends(get_db), _: User = Depends(admin)) -> dict[str, Any]:
    settings_store.save(db, body.model_dump())
    db.commit()
    report.clear_cache()
    return ok(settings_store.status(db), request, "Saved")


@router.post("/test")
def test_connections(request: Request, db: Session = Depends(get_db), _: User = Depends(admin)) -> dict[str, Any]:
    """Try the saved trackingis token and Lark app: {trackingis: {ok, message}, lark: {ok, message}}."""
    rt = settings_store.runtime(db)
    out: dict[str, Any] = {}
    try:
        teams = TrackingisClient(rt.trackingis_token).options("teams")
        out["trackingis"] = {"ok": True, "message": f"Token works ({len(teams)} teams visible)"}
    except TrackingisError as exc:
        out["trackingis"] = {"ok": False, "message": str(exc)}
    if not rt.lark_ready:
        out["lark"] = {"ok": False, "message": "Lark App ID / App Secret not set"}
    else:
        try:
            LarkClient(rt.lark_app_id, rt.lark_app_secret, settings.lark_base_url).check()
            out["lark"] = {"ok": True, "message": "Lark app credentials work"}
        except LarkError as exc:
            out["lark"] = {"ok": False, "message": str(exc)}
    return ok(out, request)
