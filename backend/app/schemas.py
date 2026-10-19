"""Request bodies."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Role = Literal["member", "admin"]


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+$")
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=2, max_length=16)
    role: Role = "member"
    password: str | None = Field(default=None, min_length=8, max_length=200)  # empty = signs in with POD only


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, min_length=2, max_length=16)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class SettingsIn(BaseModel):
    """Secrets: empty string = keep the saved value; null = remove it."""

    trackingis_token: str | None = Field(default="", max_length=500)
    default_teams: list[str] | None = Field(default=None, max_length=50)
    lark_app_id: str | None = Field(default=None, max_length=100)
    lark_app_secret: str | None = Field(default="", max_length=200)
    plan_sheet_id: int | None = Field(default=None, ge=0)  # 0 = no plan sheet
    plan_start_column: int | None = Field(default=None, ge=1, le=52)  # Lark sheets are read up to column AZ
    plan_products: int | None = Field(default=None, ge=1, le=100)
    ornament_plan_sheet_id: int | None = Field(default=None, ge=0)  # KH Ornament sheet for Etsy › Ornament; 0 = none


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
