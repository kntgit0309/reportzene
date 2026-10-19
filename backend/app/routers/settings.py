"""Settings (admins): trackingis service token + Lark app (write-only, shown as a hint), default ZenE teams."""
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import admin
from app.core.responses import ok
from app.db import get_db
from app.models import User
from app.schemas import SettingsIn
from app.services import report, settings_store, sheet_sync
from app.services.lark_sheets import LarkClient, LarkError
from app.services.trackingis import TrackingisClient, TrackingisError

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(request: Request, db: Session = Depends(get_db), _: User = Depends(admin)) -> dict[str, Any]:
    connected = db.scalar(select(func.count(User.id)).where(User.pod_token.is_not(None)))
    return ok({**settings_store.status(db), "users_with_sso_token": connected, "sheet_sync_last": sheet_sync.last_run(db)}, request)


@router.put("")
def save_settings(body: SettingsIn, request: Request, db: Session = Depends(get_db), _: User = Depends(admin)) -> dict[str, Any]:
    settings_store.save(db, body.model_dump())
    db.commit()
    report.clear_cache()
    return ok({**settings_store.status(db), "sheet_sync_last": sheet_sync.last_run(db)}, request, "Saved")


@router.post("/test")
def test_connections(request: Request, db: Session = Depends(get_db), user: User = Depends(admin)) -> dict[str, Any]:
    """Try the saved trackingis token, the admin's own SSO token and the Lark app: {name: {ok, message}}."""
    rt = settings_store.runtime(db)
    out: dict[str, Any] = {}
    try:
        teams = TrackingisClient(rt.trackingis_token).options("teams")
        out["trackingis"] = {"ok": True, "message": f"Token works ({len(teams)} teams visible)"}
    except TrackingisError as exc:
        out["trackingis"] = {"ok": False, "message": str(exc)}
    own = settings_store.decrypt(user.pod_token) if user.pod_token else ""
    if own:  # reports try it first: a refused one means they run on the shared token
        try:
            teams = TrackingisClient(own).options("teams")
            out["trackingis (your SSO token)"] = {"ok": True, "message": f"Your Isuccess System token works ({len(teams)} teams visible)"}
        except TrackingisError as exc:
            out["trackingis (your SSO token)"] = {"ok": False, "message": f"{exc}. Reports use the shared token for you meanwhile."}
    if not rt.lark_ready:
        out["lark"] = {"ok": False, "message": "Lark App ID / App Secret not set"}
    else:
        try:
            LarkClient(rt.lark_app_id, rt.lark_app_secret, settings.lark_base_url).check()
            out["lark"] = {"ok": True, "message": "Lark app credentials work"}
        except LarkError as exc:
            out["lark"] = {"ok": False, "message": str(exc)}
    return ok(out, request)
