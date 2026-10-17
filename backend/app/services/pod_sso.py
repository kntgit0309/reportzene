"""Client for "Sign in with POD" (trackingis SSO): authorize URL and code exchange.

All calls are backend-to-backend; app_secret never leaves this process.
"""
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import settings

log = logging.getLogger("rzn.sso")


class PodAuthError(Exception):
    """POD rejected the request (bad code, bad secret, revoked token...)."""


class PodUnavailable(Exception):
    """POD could not be reached or answered with a server error."""


@dataclass(frozen=True)
class PodProfile:
    user_id: int
    name: str | None
    email: str | None
    avatar_url: str | None


def _client() -> httpx.Client:
    """Factory so tests can swap in a MockTransport."""
    return httpx.Client(base_url=settings.pod_url, timeout=settings.pod_timeout_seconds, headers={"Accept": "application/json"})


def authorize_url(state: str) -> str:
    query = urlencode({"app": settings.pod_app_key, "redirect_url": settings.pod_redirect_url, "state": state})
    return f"{settings.pod_url.rstrip('/')}/sso/authorize?{query}"


def _parse(data: dict[str, Any]) -> PodProfile:
    user = data.get("user") or {}
    if not isinstance(user.get("id"), int):
        raise PodAuthError("POD response is missing user.id")
    return PodProfile(
        user_id=user["id"],
        name=(user.get("name") or "").strip() or None,
        email=(user.get("email") or "").strip().lower() or None,
        avatar_url=user.get("url_avatar"),
    )


def exchange(code: str) -> PodProfile:
    payload = {"app": settings.pod_app_key, "app_secret": settings.pod_app_secret, "code": code}
    try:
        with _client() as c:
            res = c.post("/api/v2/sso/exchange", json=payload)
    except httpx.HTTPError as exc:
        log.warning("POD exchange unreachable: %s", exc)
        raise PodUnavailable(str(exc)) from exc
    if res.status_code >= 500:
        raise PodUnavailable(f"POD error {res.status_code}")
    try:
        body = res.json()
    except ValueError as exc:
        raise PodUnavailable("POD returned non-JSON") from exc
    if res.status_code >= 400 or body.get("success") is False:
        raise PodAuthError(body.get("message") or f"POD error {res.status_code}")
    return _parse(body.get("data") or {})
