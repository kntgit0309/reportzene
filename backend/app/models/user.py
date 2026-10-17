from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import utcnow

ROLES = ("member", "admin")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(16), unique=True)  # short uppercase name
    role: Mapped[str] = mapped_column(String(16), default="member")
    password_hash: Mapped[str] = mapped_column(String(255))  # NO_PASSWORD for POD-only users
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # POD SSO identity: pod_user_id is the stable key (email may change)
    pod_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    # trackingis token handed over by the last SSO sign-in, encrypted (settings_store.encrypt); None = use the shared token
    pod_token: Mapped[str | None] = mapped_column(Text)
    pod_token_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


NO_PASSWORD = "!"  # never matches verify_password: the user signs in through POD only


class OAuthState(Base):
    """One-time `state` for the POD sign-in round trip (CSRF protection)."""

    __tablename__ = "oauth_states"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    next_path: Mapped[str] = mapped_column(String(300), default="/etsy/report")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserSession(Base):
    __tablename__ = "user_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
