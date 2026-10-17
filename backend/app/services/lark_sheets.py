"""Read a team report Lark Sheet through the Lark Open API (read-only), with the tool's own Lark custom app.

The app needs the `sheets:spreadsheet:readonly` scope (+ `wiki:wiki:readonly` for sheets inside a wiki), and every sheet
must have the app added as a collaborator (sheet → … → Add document app), otherwise Lark answers "no permission".
"""
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse

import httpx

log = logging.getLogger("rzn.lark")

TIMEOUT = 30
TOKEN_MARGIN_S = 300  # renew the tenant token this long before it expires
CHUNK_ROWS = 1000  # rows per values request
LAST_COLUMN = "AZ"  # 52 columns is plenty for a report sheet
_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{10,64}$")
PERMISSION_CODES = {91403, 1310213, 131006, 99991672, 99991663}


class LarkError(Exception):
    """Readable error for the Sheets page (bad link, no access, wrong app credentials...)."""


@dataclass(frozen=True)
class SheetRef:
    kind: str  # sheets | wiki
    token: str
    sheet_id: str  # "" = first tab


def parse_url(url: str) -> SheetRef:
    """https://x.larksuite.com/sheets/<token>?sheet=<id> or /wiki/<token>?sheet=<id>."""
    u = urlparse((url or "").strip())
    parts = [p for p in u.path.split("/") if p]
    sheet_id = (parse_qs(u.query).get("sheet") or [""])[0]
    for kind in ("sheets", "wiki"):
        if kind in parts and parts.index(kind) + 1 < len(parts):
            token = parts[parts.index(kind) + 1]
            if _TOKEN_RE.match(token):
                return SheetRef(kind, token, sheet_id)
    raise LarkError("Not a Lark Sheet link: open the sheet and copy the address bar (…larksuite.com/sheets/… or …/wiki/…)")


def cell_text(v: Any) -> str:
    """A Lark cell (text, number, rich-text segments, link or mention objects) as plain text. Embedded images -> ""."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "".join(cell_text(x) for x in v)
    if isinstance(v, dict):
        if v.get("type") in ("embed-image", "image"):
            return ""
        return str(v.get("link") or v.get("text") or v.get("name") or "")
    return str(v)


class LarkClient:
    def __init__(self, app_id: str, app_secret: str, base_url: str = "https://open.larksuite.com"):
        if not (app_id and app_secret):
            raise LarkError("Lark App ID / App Secret not set (Settings → Lark)")
        self.app_id, self.app_secret, self.base = app_id, app_secret, base_url.rstrip("/")

    # tenant tokens are shared per app across threads
    _cache: ClassVar[dict[str, tuple[str, float]]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def _token(self) -> str:
        with self._lock:
            tok, until = self._cache.get(self.app_id, ("", 0.0))
            if tok and time.monotonic() < until:
                return tok
            data = self._call("POST", "/open-apis/auth/v3/tenant_access_token/internal", auth=False,
                              json={"app_id": self.app_id, "app_secret": self.app_secret})
            tok = str(data.get("tenant_access_token") or "")
            if not tok:
                raise LarkError("Lark did not return an access token: check App ID / App Secret")
            self._cache[self.app_id] = (tok, time.monotonic() + max(60, int(data.get("expire") or 7200) - TOKEN_MARGIN_S))
            return tok

    def _call(self, method: str, path: str, auth: bool = True, **kw: Any) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._token()}"} if auth else {}
        try:
            res = httpx.request(method, self.base + path, headers=headers, timeout=TIMEOUT, **kw)
        except httpx.HTTPError as exc:
            raise LarkError(f"Cannot reach Lark: {str(exc)[:120]}") from exc
        try:
            body = res.json()
        except ValueError as exc:
            raise LarkError(f"Lark HTTP {res.status_code}") from exc
        code = body.get("code")
        if code not in (0, None):
            msg = str(body.get("msg") or "")
            if code in PERMISSION_CODES or "permission" in msg.lower() or res.status_code == 403:
                raise LarkError(f"The Lark app has no access to this sheet: open the sheet → … → Add document app → add the app ({msg})")
            raise LarkError(f"Lark error {code}: {msg[:200]}")
        return body if not auth else (body.get("data") or {})

    def _resolve(self, ref: SheetRef) -> str:
        if ref.kind == "sheets":
            return ref.token
        node = self._call("GET", "/open-apis/wiki/v2/spaces/get_node", params={"token": ref.token}).get("node") or {}
        if node.get("obj_type") != "sheet" or not node.get("obj_token"):
            raise LarkError("This wiki page is not a Lark Sheet")
        return str(node["obj_token"])

    def _tabs(self, spreadsheet: str) -> list[dict[str, Any]]:
        sheets = self._call("GET", f"/open-apis/sheets/v3/spreadsheets/{spreadsheet}/sheets/query").get("sheets") or []
        if not sheets:
            raise LarkError("The spreadsheet has no tabs")
        return [{"sheet_id": str(t["sheet_id"]), "title": str(t.get("title") or ""),
                 "rows": int((t.get("grid_properties") or {}).get("row_count") or 0)} for t in sheets if t.get("sheet_id")]

    def tabs(self, url: str) -> tuple[list[dict[str, Any]], str]:
        """Every tab of the spreadsheet + the tab the link points at ("" = none, the first tab is meant)."""
        ref = parse_url(url)
        return self._tabs(self._resolve(ref)), ref.sheet_id

    def _values(self, spreadsheet: str, tab: dict[str, Any], max_rows: int) -> list[list[Any]]:
        last = min(tab["rows"] or max_rows + 1, max_rows + 1)
        values: list[list[Any]] = []
        for start in range(1, last + 1, CHUNK_ROWS):
            end = min(start + CHUNK_ROWS - 1, last)
            chunk = self._call("GET", f"/open-apis/sheets/v2/spreadsheets/{spreadsheet}/values/{tab['sheet_id']}!A{start}:{LAST_COLUMN}{end}",
                               params={"valueRenderOption": "ToString", "dateTimeRenderOption": "FormattedString"})
            got = (chunk.get("valueRange") or {}).get("values") or []
            values.extend(got)
            if len(got) < end - start + 1:
                break
        return values

    def check(self) -> None:
        """Raise LarkError when the App ID / App Secret do not work."""
        self._token()

    def read_tab(self, url: str, tab_id: str, header_row: int, max_rows: int) -> tuple[dict[str, Any], list[str], list[dict[str, str]]]:
        """(tab, header, rows) of one tab: `tab_id`, else the tab in the link, else the first tab. Row `header_row` is the
        header (blank names become "Column N", duplicates get a suffix); rows below it that are entirely empty are skipped."""
        ref = parse_url(url)
        spreadsheet = self._resolve(ref)
        all_tabs = self._tabs(spreadsheet)
        wanted = tab_id or ref.sheet_id or all_tabs[0]["sheet_id"]
        tab = next((t for t in all_tabs if t["sheet_id"] == wanted), None)
        if tab is None:
            raise LarkError(f"Tab {wanted} not found in the spreadsheet (renamed or deleted?)")
        values = self._values(spreadsheet, tab, max_rows + header_row)
        if len(values) < header_row:
            raise LarkError(f"The tab has fewer than {header_row} rows: nothing to read")
        header = unique_header([cell_text(c).strip() for c in values[header_row - 1]])
        rows = []
        for i, row in enumerate(values[header_row:], start=header_row + 1):
            cells = [cell_text(c).strip() for c in row]
            if not any(cells):
                continue
            rows.append({"_row": str(i), **{h: (cells[j] if j < len(cells) else "") for j, h in enumerate(header)}})
            if len(rows) >= max_rows:
                break
        while header and header[-1].startswith("Column ") and not any(r.get(header[-1]) for r in rows):
            dropped = header.pop()
            for r in rows:
                r.pop(dropped, None)
        return tab, header, rows


def unique_header(names: list[str]) -> list[str]:
    out: list[str] = []
    for i, name in enumerate(names, start=1):
        base = name or f"Column {i}"
        cand, n = base, 2
        while cand in out or cand == "_row":
            cand, n = f"{base} ({n})", n + 1
        out.append(cand)
    return out
