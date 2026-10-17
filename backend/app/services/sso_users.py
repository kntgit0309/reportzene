"""Map a POD profile onto a local user. New POD users start as members, locked unless their email is allow-listed."""
import logging
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import NO_PASSWORD, User
from app.services.naming import clean_code
from app.services.pod_sso import PodProfile

log = logging.getLogger("rzn.sso")
DEFAULT_ROLE = "member"
CODE_LEN = 8
MIN_CODE = 2


def _ascii(text: str) -> str:
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def suggest_code(db: Session, name: str | None, email: str | None, pod_user_id: int) -> str:
    """Given name (last word of a Vietnamese full name) → KHOA, KHOA2, … unique among users."""
    words = _ascii(name or "").split()
    base = clean_code(words[-1] if words else "", CODE_LEN)
    if len(base) < MIN_CODE:
        base = clean_code(_ascii((email or "").split("@")[0]), CODE_LEN)
    if len(base) < MIN_CODE:
        base = f"POD{pod_user_id}"[:CODE_LEN]
    taken = set(db.scalars(select(User.code).where(User.code.like(f"{base}%"))))
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def _free_email(db: Session, email: str | None, user_id: int | None, pod_user_id: int) -> str:
    """POD email unless another local user already owns it (then a placeholder)."""
    if email:
        owner = db.scalar(select(User.id).where(User.email == email))
        if owner is None or owner == user_id:
            return email
    return f"pod-{pod_user_id}@pod.local"


def upsert_from_pod(db: Session, p: PodProfile) -> User:
    user = db.scalar(select(User).where(User.pod_user_id == p.user_id))
    if user is None and p.email:
        # First SSO login of an account created by hand with the same email: link it, keep its role.
        user = db.scalar(select(User).where(User.email == p.email, User.pod_user_id.is_(None)))
    if user is None:
        user = User(
            email=_free_email(db, p.email, None, p.user_id),
            name=p.name or (p.email or f"POD {p.user_id}").split("@")[0],
            code=suggest_code(db, p.name, p.email, p.user_id),
            role=DEFAULT_ROLE,
            password_hash=NO_PASSWORD,
            is_active=(p.email or "") in settings.allowed_emails,  # sales data: an admin unlocks everyone else
        )
        db.add(user)
        log.info("New POD user %s → %s (%s)", p.user_id, user.email, user.code)
    user.pod_user_id = p.user_id
    if p.email and user.email != p.email:
        user.email = _free_email(db, p.email, user.id, p.user_id) if user.id else user.email
    if p.name:
        user.name = p.name
    user.avatar_url = p.avatar_url
    db.flush()
    return user
