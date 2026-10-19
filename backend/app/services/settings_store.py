"""Runtime settings saved from the Settings page: trackingis token + Lark app (secrets encrypted at rest), ZenE teams, plan sheet."""
import base64
import hashlib
import os
from dataclasses import dataclass, field
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config import BASE_DIR, settings
from app.models import AppSetting

KEY = "runtime"
SECRET_FIELDS = ("trackingis_token", "lark_app_secret")
PLAIN_FIELDS = ("lark_app_id", "sheet_sync_at")  # sheet_sync_at "" = no daily sync
LIST_FIELDS = ("default_teams",)
INT_FIELDS = ("plan_sheet_id", "plan_start_column", "plan_products", "pl2_cf_sheet_id")  # sheet ids: 0 = none
LEGACY_PLAN_FAMILIES = ("ornament", "shirt")  # saved as <family>_plan_sheet_id before family_plan_sheets
SECRET_FILE = BASE_DIR / "data" / "secret.key"


@dataclass(frozen=True)
class Runtime:
    trackingis_token: str
    default_teams: list[str]
    lark_app_id: str = ""
    lark_app_secret: str = ""
    sheet_sync_at: str = "10:00"  # daily sync of every team sheet ("HH:MM", Vietnam time; "" = off)
    plan_sheet_id: int | None = None
    plan_start_column: int = 17
    plan_products: int = 11
    pl2_cf_sheet_id: int | None = None  # finance's monthly PL2 ("Tổng kết PL Monthly", PL2 theo CF) for Etsy › Report
    family_plan_sheets: dict[str, int] = field(default_factory=dict)  # product family (Etsy › Ornament…) → its plan sheet id
    account_replacements: tuple[tuple[str, str], ...] = ()  # (suspended store, store that takes over its plan and sales)

    @property
    def trackingis_ready(self) -> bool:
        return bool(self.trackingis_token)

    @property
    def lark_ready(self) -> bool:
        return bool(self.lark_app_id and self.lark_app_secret)


def _secret() -> bytes:
    """SECRET_KEY from the environment, else a random key kept in data/secret.key (created once, chmod 600)."""
    if settings.secret_key:
        return settings.secret_key.encode()
    if not SECRET_FILE.exists():
        SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(base64.urlsafe_b64encode(os.urandom(32)).decode())
    return SECRET_FILE.read_text().strip().encode()


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(_secret()).digest()))


def _stored(db: Session) -> dict[str, Any]:
    row = db.get(AppSetting, KEY)
    return dict(row.value) if row else {}


def _decrypt(token: str | None) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:  # secret key changed: the saved value is unusable, Settings shows it as missing
        return ""


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str | None) -> str:
    return _decrypt(token)


def _split(value: str | list[str] | None) -> list[str]:
    items = value if isinstance(value, list) else (value or "").split(",")
    return [str(i).strip() for i in items if str(i).strip()]


def runtime(db: Session) -> Runtime:
    s = _stored(db)
    return Runtime(
        trackingis_token=_decrypt(s.get("trackingis_token")) or settings.trackingis_token,
        default_teams=_split(s.get("default_teams") if "default_teams" in s else settings.default_teams),
        lark_app_id=s.get("lark_app_id") or settings.lark_app_id,
        lark_app_secret=_decrypt(s.get("lark_app_secret")) or settings.lark_app_secret,
        sheet_sync_at=s.get("sheet_sync_at", settings.sheet_sync_at),  # "" saved = off
        plan_sheet_id=int(s.get("plan_sheet_id") or 0) or None,
        plan_start_column=int(s.get("plan_start_column") or settings.plan_start_column),
        plan_products=int(s.get("plan_products") or settings.plan_products),
        pl2_cf_sheet_id=int(s.get("pl2_cf_sheet_id") or 0) or None,
        family_plan_sheets=_plan_sheets(s),
        account_replacements=tuple((r["suspended"], r["replacement"]) for r in s.get("account_replacements") or []),
    )


def _plan_sheets(s: dict[str, Any]) -> dict[str, int]:
    """Family → plan sheet id; settings saved before family_plan_sheets kept one field per family."""
    saved = s.get("family_plan_sheets")
    if saved is None:
        saved = {key: s.get(f"{key}_plan_sheet_id") for key in LEGACY_PLAN_FAMILIES}
    return {key: int(v) for key, v in saved.items() if int(v or 0)}


def _hint(value: str) -> str:
    return f"{value[:4]}…{value[-4:]}" if len(value) > 12 else ("saved" if value else "")


def status(db: Session) -> dict[str, Any]:
    rt = runtime(db)
    return {"trackingis_token": _hint(rt.trackingis_token), "trackingis_url": settings.trackingis_url,
            "default_teams": rt.default_teams, "lark_app_id": rt.lark_app_id, "lark_app_secret": _hint(rt.lark_app_secret),
            "sheet_sync_at": rt.sheet_sync_at,
            "plan_sheet_id": rt.plan_sheet_id, "plan_start_column": rt.plan_start_column, "plan_products": rt.plan_products,
            "pl2_cf_sheet_id": rt.pl2_cf_sheet_id,
            "family_plan_sheets": rt.family_plan_sheets,
            "account_replacements": [{"suspended": old, "replacement": new} for old, new in rt.account_replacements]}


def save(db: Session, changes: dict[str, Any]) -> None:
    """Secret fields: "" keeps the saved value, None removes it. Plain/list/int fields: None keeps."""
    value = _stored(db)
    for f in SECRET_FIELDS:
        new = changes.get(f, "")
        if new is None:
            value.pop(f, None)
        elif new.strip():
            value[f] = _fernet().encrypt(new.strip().encode()).decode()
    for f in PLAIN_FIELDS:
        if changes.get(f) is not None:
            value[f] = changes[f].strip()
    for f in LIST_FIELDS:
        if changes.get(f) is not None:
            value[f] = _split(changes[f])
    for f in INT_FIELDS:
        if changes.get(f) is not None:
            value[f] = int(changes[f])
    if changes.get("family_plan_sheets") is not None:  # only the families given change; 0 = no plan sheet
        sheets = {**_plan_sheets(value), **{key: int(v) for key, v in changes["family_plan_sheets"].items()}}
        value["family_plan_sheets"] = {key: v for key, v in sheets.items() if v}
        for key in LEGACY_PLAN_FAMILIES:
            value.pop(f"{key}_plan_sheet_id", None)
    if changes.get("account_replacements") is not None:  # the whole list is replaced; [] clears it
        value["account_replacements"] = [{"suspended": r["suspended"].strip(), "replacement": r["replacement"].strip()}
                                         for r in changes["account_replacements"]]
    row = db.get(AppSetting, KEY)
    if row is None:
        db.add(AppSetting(key=KEY, value=value))
    else:
        row.value = value
