"""MCP endpoint (/mcp, streamable HTTP) so AI agents can read the ZenE reports.

Auth: personal agent token (Authorization: Bearer rzn_…, created from the avatar menu → "Agent tokens").
The agent acts as the token's owner. Every tool only reads: the Etsy sale report from trackingis and the team's
Lark report sheets (the last synced snapshot, or a fresh sync with sync_sheet).
"""
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy.orm import Session

from app.core.deps import user_from_token
from app.core.errors import AppError
from app.db import SessionLocal
from app.models import User
from app.services import ornament, report, sheets

MAX_ROWS = 200

mcp = MCPServer(
    name="reportzene",
    instructions=(
        "ReportZenE reads ZenE's Etsy sale report from trackingis (production.trackingis.info) and the team's hand-filled "
        "Lark report sheets, with the trackingis rights of the token's owner. Dates are YYYY-MM-DD in Vietnam time; leaving them out means this month so far. "
        "Start with etsy_totals for the headline numbers, then etsy_report with a view: date (per day), store, seller, "
        "product, product_type or order. Filters take trackingis ids: call filter_options first to turn a store, seller, "
        "designer or team name into its id (product types and sub product types are filtered by name). "
        "Teams default to the ZenE teams set by an admin; pass teams=\"\" for every team. "
        "etsy_ornament breaks ornament sales down by the team's ornament product types. "
        "For the team's own reports call list_sheets, then read_sheet (search with q). Everything here is read-only."
    ),
)


class AgentError(ToolError):
    """Shown to the calling agent as-is (plain exceptions are masked by the SDK)."""


def _user(db: Session, ctx: Context) -> User:
    auth = (ctx.headers or {}).get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise AgentError("Missing token (Authorization: Bearer rzn_…). Create one from the avatar menu → Agent tokens.")
    try:
        return user_from_token(db, auth[7:].strip())
    except AppError as exc:
        raise AgentError(exc.message) from exc


def _run(ctx: Context, fn: Callable[[Session, User], Any]) -> Any:
    """Open a session, authenticate, run; turn app errors into readable tool errors."""
    with SessionLocal() as db:
        user = _user(db, ctx)
        try:
            return fn(db, user)
        except AppError as exc:
            db.rollback()
            detail = f" {exc.errors}" if exc.errors else ""
            raise AgentError(f"{exc.message}{detail}") from exc


def _filters(**kw: Any) -> dict[str, Any]:
    """MCP arguments → report params. teams=None keeps the ZenE default; other empty values are dropped."""
    return {k: v for k, v in kw.items() if v is not None and (v != "" or k == "teams")}


@mcp.tool(description="Who am I: name, email and role in ReportZenE.")
def whoami(ctx: Context) -> dict:
    return _run(ctx, lambda db, u: {"name": u.name, "email": u.email, "role": u.role, "code": u.code})


@mcp.tool(description=(
    "Headline Etsy sale numbers for a date range: total_order, total_quantity, total (with tax), sale_tax, total_revenue, "
    "avg_order_value, days. Same filters as etsy_report (comma lists of trackingis ids)."))
def etsy_totals(ctx: Context, date_from: str = "", date_to: str = "", shops: str = "", sellers: str = "", designers: str = "",
                product_types: str = "", sub_product_types: str = "", teams: str | None = None, keyword: str = "") -> dict:
    params = _filters(date_from=date_from, date_to=date_to, shops=shops, sellers=sellers, designers=designers,
                      product_types=product_types, sub_product_types=sub_product_types, teams=teams, keyword=keyword)
    return _run(ctx, lambda db, u: report.etsy_totals(db, params, u))


@mcp.tool(description=(
    "Etsy sale report rows, like the trackingis Report Etsy page. view: date | store | seller | product | product_type | order. "
    "Filters are comma lists of trackingis ids (shops, sellers, designers, teams) or names (product_types, sub_product_types); "
    "keyword searches product names/SKU; total_order + symbol (> >= = <= <) filter by order count. "
    "sort_by: date_at, total_order, total_quantity, total, total_revenue, sale_tax. Returns rows, paging and the query actually used."))
def etsy_report(ctx: Context, view: str = "date", date_from: str = "", date_to: str = "", page: int = 1, per_page: int = 50,
                sort_by: str = "", sort_order: str = "desc", shops: str = "", sellers: str = "", designers: str = "",
                product_types: str = "", sub_product_types: str = "", teams: str | None = None, keyword: str = "", total_order: str = "",
                symbol: str = "") -> dict:
    sort = sort_by or ("date_at" if view in ("date", "order") else "total_revenue")
    params = _filters(view=view, date_from=date_from, date_to=date_to, page=page, per_page=min(max(per_page, 1), MAX_ROWS),
                      sort_by=sort, sort_order=sort_order, shops=shops, sellers=sellers, designers=designers,
                      product_types=product_types, sub_product_types=sub_product_types, teams=teams, keyword=keyword,
                      total_order=total_order, symbol=symbol)
    return _run(ctx, lambda db, u: report.etsy_report(db, params, u))


@mcp.tool(description=(
    "Ornament sales per product type (Acrylic + Wood, Shell, Shaker, Ceramic, Glass, Felt, Others), each with its sub product "
    "types: total_order, total_quantity, total_revenue, avg_order_value, share of ornament revenue, and per-day rows. "
    "Same filters as etsy_totals; an order with several ornament types counts in each, so use total for the overall numbers. "
    "With the KH Ornament plan sheet set, product types and total also have plan (pieces for the range, months pro rata), "
    "plan_month and achieved (quantity / plan); `plan` says its scope or why there is none."))
def etsy_ornament(ctx: Context, date_from: str = "", date_to: str = "", shops: str = "", sellers: str = "", designers: str = "",
                  teams: str | None = None, keyword: str = "") -> dict:
    params = _filters(date_from=date_from, date_to=date_to, shops=shops, sellers=sellers, designers=designers, teams=teams,
                      keyword=keyword)
    return _run(ctx, lambda db, u: ornament.ornament_report(db, params, u))


@mcp.tool(description="Ids and names for the report filters. kind: shops | sellers | designers | product_types | "
                      "sub_product_types | teams. query narrows by name (case-insensitive).")
def filter_options(ctx: Context, kind: str, query: str = "") -> list[dict]:
    if kind not in ("shops", "sellers", "designers", "product_types", "sub_product_types", "teams"):
        raise AgentError("kind is one of shops, sellers, designers, product_types, sub_product_types, teams")
    needle = query.strip().lower()

    def run(db: Session, u: User) -> list[dict]:
        rows = report.filter_options(db, kind, u)
        return [r for r in rows if needle in str(r["name"]).lower()] if needle else rows
    return _run(ctx, run)


@mcp.tool(description="The team's Lark report sheets: id, name, tab, columns (header), row count, last sync time and last error.")
def list_sheets(ctx: Context) -> list[dict]:
    return _run(ctx, lambda db, u: [sheets.summary(s) for s in sheets.list_all(db)])


@mcp.tool(description=(
    "Rows of one Lark report sheet (by id or exact name) from its last sync. q searches every cell; page/per_page page "
    "through. Each row maps column name → text, plus _row = the row number in the sheet."))
def read_sheet(ctx: Context, sheet: str, q: str = "", page: int = 1, per_page: int = 50) -> dict:
    def run(db: Session, _u: User) -> dict:
        source = sheets.find(db, sheet)
        size = min(max(per_page, 1), MAX_ROWS)
        items, total = sheets.rows(source, q, max(page, 1), size)
        return {"sheet": sheets.summary(source), "rows": items, "paging": {"page": max(page, 1), "per_page": size, "total": total}}
    return _run(ctx, run)


@mcp.tool(description="Read a Lark report sheet again from Lark now (by id or exact name), then return its summary.")
def sync_sheet(ctx: Context, sheet: str) -> dict:
    return _run(ctx, lambda db, u: sheets.summary(sheets.sync(db, sheets.find(db, sheet))))


def http_app():
    """ASGI app mounted at /mcp (stateless JSON responses: simplest for HTTP MCP clients)."""
    return mcp.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True, host="0.0.0.0")
