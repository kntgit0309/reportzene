"""Request bodies."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.families import FAMILIES

Role = Literal["member", "admin"]


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+$")
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=2, max_length=16)
    role: Role = "member"
    password: str | None = Field(default=None, min_length=8, max_length=200)  # empty = signs in with POD only
    scope_sellers: list[str] | None = Field(default=None, max_length=50)  # trackingis seller ids it sees only; none = all


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, min_length=2, max_length=16)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)
    scope_sellers: list[str] | None = Field(default=None, max_length=50)  # null keeps, [] = the whole of ZenE


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class AccountReplacement(BaseModel):
    """A suspended store and the store that takes over its line of the plans (and its sales) on Etsy › Ornament, Shirt…"""

    suspended: str = Field(min_length=1, max_length=120)
    replacement: str = Field(min_length=1, max_length=120)

    @field_validator("suspended", "replacement")
    @classmethod
    def _strip(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Store name is empty")
        return v.strip()

    @model_validator(mode="after")
    def _different(self) -> "AccountReplacement":
        if self.suspended.lower() == self.replacement.lower():
            raise ValueError("A store cannot replace itself")
        return self


class SettingsIn(BaseModel):
    """Secrets: empty string = keep the saved value; null = remove it."""

    trackingis_token: str | None = Field(default="", max_length=500)
    default_teams: list[str] | None = Field(default=None, max_length=50)
    lark_app_id: str | None = Field(default=None, max_length=100)
    sheet_sync_at: str | None = Field(default=None, pattern=r"^(|([01]\d|2[0-3]):[0-5]\d)$")  # daily sync "HH:MM"; "" = off
    lark_app_secret: str | None = Field(default="", max_length=200)
    plan_sheet_id: int | None = Field(default=None, ge=0)  # 0 = no plan sheet
    plan_start_column: int | None = Field(default=None, ge=1, le=52)  # Lark sheets are read up to column AZ
    plan_products: int | None = Field(default=None, ge=1, le=100)
    pl2_cf_sheet_id: int | None = Field(default=None, ge=0)  # "Tổng kết PL Monthly" (PL2 theo CF) for Etsy › Report; 0 = none
    pl2_account_sheet_id: int | None = Field(default=None, ge=0)  # "PL Account Etsy_Monthly" (PL2 CF per account); 0 = none
    account_list_sheet_id: int | None = Field(default=None, ge=0)  # "Acc đã bàn giao Seller" (names its account rows); 0 = none
    seller_cf_sheets: list[str] | None = Field(default=None, max_length=10)  # team sheet ids: each team's seller P&L tab
    seller_plan_sheet_id: int | None = Field(default=None, ge=0)  # "KH quý 4.2026 theo seller" (PL2 per seller); 0 = none
    other_pl2_per_item: float | None = Field(default=None, ge=0, le=1000)  # PL2/item of Other products ($); 0 = none
    # Plan sheet of each product family given (KH Ornament for Etsy › Ornament…); 0 = none, families left out keep theirs
    family_plan_sheets: dict[str, int] | None = None
    account_replacements: list[AccountReplacement] | None = Field(default=None, max_length=50)  # null keeps, [] clears

    @field_validator("family_plan_sheets")
    @classmethod
    def _known_families(cls, v: dict[str, int] | None) -> dict[str, int] | None:
        for key, sheet_id in (v or {}).items():
            if key not in FAMILIES:
                raise ValueError(f"No product family {key!r} (one of {', '.join(FAMILIES)})")
            if sheet_id < 0:
                raise ValueError("Sheet id must be 0 (none) or a team sheet id")
        return v


LARK_URL = r"^https://[A-Za-z0-9.\-]+\.(larksuite|feishu)\.(com|cn)/"


class SheetTabsIn(BaseModel):
    url: str = Field(min_length=10, max_length=1000, pattern=LARK_URL)

    @field_validator("url", mode="before")
    @classmethod
    def _strip_url(cls, v: str) -> str:
        return str(v).strip()


class SheetIn(SheetTabsIn):
    name: str = Field(min_length=1, max_length=120)
    tab_id: str = Field(default="", max_length=40, pattern=r"^[A-Za-z0-9]*$")  # "" = the tab in the link, else the first
    header_row: int = Field(default=1, ge=1, le=50)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return v.strip()
