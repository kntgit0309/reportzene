from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import utcnow


class AppSetting(Base):
    """Key/value settings saved from the Settings page (secrets are encrypted inside `value`)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SheetSource(Base):
    """A Lark Sheet tab the team fills by hand. Synced on demand; the last read is kept as a snapshot."""

    __tablename__ = "sheet_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(1000))
    tab_id: Mapped[str] = mapped_column(String(40), default="")  # "" = the tab in the link, else the first tab
    tab_title: Mapped[str] = mapped_column(String(200), default="")
    header_row: Mapped[int] = mapped_column(Integer, default=1)
    header: Mapped[list[str]] = mapped_column(JSON, default=list)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)  # [{"_row": n, header: text}]
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
