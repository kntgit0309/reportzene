"""Read-only client for the trackingis Etsy sale report (internal /api/v2 routes, service Bearer token).

Same query the trackingis "Report Etsy" page sends: GET /api/v2/etsy/report with view, from/to and the filters.
List filters go out as `name[]=v` (axios style), which Laravel reads as arrays.
"""
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger("rzn.trackingis")

VIEWS = ("date", "order", "product", "store", "seller", "product_type")
LIST_FILTERS = ("shops", "sellers", "designers", "product_types", "sub_product_types", "teams")
TEXT_FILTERS = ("keyword", "total_order", "symbol", "tm_status", "tm_flagged", "ai_generate", "product_type_level")
SORT_FIELDS = ("date_at", "total_order", "total_quantity", "total", "total_revenue", "sale_tax")
FILTER_ROUTES = {"shops": "/filter/shop", "sellers": "/filter/seller", "designers": "/filter/designers",
                 "product_types": "/filter/product-type", "teams": "/filter/teams"}
MAX_PER_PAGE = 200
SUM_FIELDS = ("total_order", "total_quantity", "total", "sale_tax", "total_revenue")
MAX_TOTAL_PAGES = 13  # 13 × 31 days ≈ a year; the API caps a date page at 31 days
TEST_TRANSPORT: httpx.BaseTransport | None = None  # tests swap in a MockTransport
USER_AGENT = "reportzene/0.1 (+https://reportzene.trackingis.info)"  # Cloudflare blocks the default python agents


class TrackingisError(Exception):
    """Readable error for the UI / MCP (missing token, expired token, upstream down)."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ReportQuery:
    date_from: str
    date_to: str
    view: str = "date"
    page: int = 1
    per_page: int = 20
    sort_by: str = "date_at"
    sort_order: str = "desc"
    lists: dict[str, list[str]] = field(default_factory=dict)
    texts: dict[str, str] = field(default_factory=dict)

    def params(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = [
            ("view", self.view), ("from", self.date_from), ("to", self.date_to),
            ("date_range[]", self.date_from), ("date_range[]", self.date_to),
            ("page", str(self.page)), ("per_page", str(min(max(self.per_page, 1), MAX_PER_PAGE))),
            ("sort_by", self.sort_by), ("sort_order", self.sort_order),
        ]
        for name in LIST_FILTERS:
            out += [(f"{name}[]", str(v)) for v in self.lists.get(name, []) if str(v).strip()]
        out += [(name, str(self.texts[name])) for name in TEXT_FILTERS if str(self.texts.get(name) or "").strip()]
        return out


class TrackingisClient:
    def __init__(self, token: str, base_url: str | None = None, transport: httpx.BaseTransport | None = None):
        if not token:
            raise TrackingisError("The trackingis token is not set: an admin pastes it in Settings → trackingis", 503)
        self.token = token
        self.base = (base_url or settings.trackingis_url).rstrip("/") + "/api/v2"
        self.transport = transport or TEST_TRANSPORT

    def _get(self, path: str, params: list[tuple[str, str]] | dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.token}",
                   "X-Requested-With": "XMLHttpRequest", "User-Agent": USER_AGENT}
        try:
            with httpx.Client(timeout=settings.trackingis_timeout_seconds, transport=self.transport) as c:
                res = c.get(self.base + path, params=params, headers=headers)
        except httpx.HTTPError as exc:
            log.warning("trackingis unreachable on %s: %s", path, exc)
            raise TrackingisError(f"Cannot reach trackingis: {str(exc)[:120]}") from exc
        if res.status_code == 401:
            raise TrackingisError("trackingis refused the token (expired or revoked): an admin pastes a new one in Settings", 502)
        if res.status_code == 403:
            raise TrackingisError("The trackingis token has no permission for this report (needs view_report)", 502)
        if res.status_code >= 400:
            log.warning("trackingis %s on %s: %s", res.status_code, path, res.text[:300])
            raise TrackingisError(f"trackingis error {res.status_code}")
        try:
            body = res.json()
        except ValueError as exc:
            raise TrackingisError("trackingis answered with something that is not JSON") from exc
        if body.get("success") is False:
            raise TrackingisError(str(body.get("message") or "trackingis refused the request")[:200])
        return body

    def report(self, q: ReportQuery) -> dict[str, Any]:
        """{rows, total, paging} for one view."""
        data = self._get("/etsy/report", q.params()).get("data") or {}
        paging = data.get("paging") or {}
        return {"rows": data.get("data") or [], "total": data.get("total") or {},
                "paging": {"page": paging.get("current_page", q.page), "per_page": paging.get("per_page", q.per_page),
                           "total": paging.get("total", 0), "last_page": paging.get("last_page", 1)}}

    def totals(self, q: ReportQuery) -> dict[str, Any]:
        """Summary cards for the same filters: the sum of the per-day rows (trackingis' own /etsy/report/totals answers 500).

        The date view returns at most 31 days per page whatever per_page says, so long ranges are paged through."""
        sums = dict.fromkeys(SUM_FIELDS, 0.0)
        days, page = 0, 1
        while page <= MAX_TOTAL_PAGES:
            got = self.report(ReportQuery(q.date_from, q.date_to, "date", page, MAX_PER_PAGE, "date_at", "asc", q.lists, q.texts))
            for row in got["rows"]:
                days += 1
                for f in SUM_FIELDS:
                    sums[f] += float(row.get(f) or 0)
            if page >= int(got["paging"].get("last_page") or 1):
                break
            page += 1
        out: dict[str, Any] = {f: round(v, 2) for f, v in sums.items()}
        out["total_order"], out["total_quantity"], out["days"] = int(sums["total_order"]), int(sums["total_quantity"]), days
        out["avg_order_value"] = round(sums["total_revenue"] / sums["total_order"], 2) if sums["total_order"] else 0.0
        return out

    def options(self, kind: str) -> list[dict[str, Any]]:
        """Filter dropdown values: shops, sellers, designers, product_types, teams."""
        if kind not in FILTER_ROUTES:
            raise TrackingisError(f"Unknown filter {kind}", 422)
        params = {"platform": "etsy"} if kind in ("shops", "product_types") else {}
        if kind == "sellers":
            params = {"platform[]": "etsy"}
        data = self._get(FILTER_ROUTES[kind], params).get("data")
        return data if isinstance(data, list) else []


