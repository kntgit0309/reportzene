"""Response envelope: {data, paging?, meta:{message, request_id}}."""
from typing import Any

from fastapi import Request


def _meta(request: Request | None, message: str) -> dict[str, Any]:
    rid = getattr(request.state, "request_id", None) if request else None
    return {"message": message, "request_id": rid}


def ok(data: Any, request: Request | None = None, message: str = "OK") -> dict[str, Any]:
    return {"data": data, "meta": _meta(request, message)}


def paged(items: list[Any], total: int, page: int, per_page: int, request: Request | None = None) -> dict[str, Any]:
    return {"data": items, "paging": {"page": page, "per_page": per_page, "total": total}, "meta": _meta(request, "OK")}
