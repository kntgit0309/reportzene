"""Etsy › Report, PL2 per account: for each account of the plans (the stores of the KH sheets), PL2 theo KT (its quantity of
each plan product × that product's PL2 per item; Other products at theirs from Settings › Plan) next to PL2 theo CF (finance's "PROFIT THỰC ĐẠT" of the account). Accounts
outside the plans that have a PL2 go together under "Other accounts".

PL2 theo CF comes from the "PL Account Etsy_Monthly" tab (Settings › Plan › PL2 account sheet): a header row "… | MM-YYYY…",
then a "PROFIT THỰC ĐẠT" section with, per team, a "Profit thực đạt <team>" row followed by one row per account. The account
names there are the result of a QUERY over the account list, which Lark's API does not return (only its first cell), so they
are rebuilt from that list (Settings › Plan › Account list: "Acc đã bàn giao Seller", Shop Name and Team columns) in the same
order: the k-th row of a team is its k-th account of the list. The first name the sheet does show is checked against the list.
CF is per month as finance books it; a range counts the whole months it touches. A suspended store's KT and CF go to its
replacement (Settings › Plan). Pieces added by hand (Felt) are not tied to an account, so they are not in KT here.

KH theo KT and KH theo CF (Settings › Plan › Account PL2 plan sheet, the "KH theo Acc" tab, see account_plan) are the PL2 plan
of each account on the KT and on the CF basis, each month pro rata of the report's days; the gaps are KT − KH theo KT and
CF − KH theo CF. An account the sheet does not list has a plan of $0 (its whole PL2 is its gap), so the rows add up to the
total; accounts of the sheet with a plan that no KH store sheet lists are rows of their own.
"""
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import SheetSource, User
from app.services import account_plan, family_accounts, family_plan, family_report, overview, report, seller_plan, settings_store
from app.services.families import FAMILIES
from app.services.plan import _num
from app.services.trackingis import ReportQuery, TrackingisClient, TrackingisError

SECTION = "profit thực đạt"
OTHERS = "Other accounts"


def _key(name: Any) -> str:
    return str(name or "").strip().lower()


def parse_account_list(header: list[str], rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Team (lower case) → its shop names in sheet order, blanks kept (the QUERY that names the PL rows keeps them too)."""
    shop_h = next((h for h in header if h.strip().lower() == "shop name"), None)
    team_h = next((h for h in header if h.strip().lower() == "team"), None)
    if not (shop_h and team_h):
        raise AppError(422, "ACCOUNT_LIST_LAYOUT", 'The account list has no "Shop Name" and "Team" columns in its header row')
    out: dict[str, list[str]] = {}
    for r in rows:
        team = str(r.get(team_h) or "").strip()
        if team:
            out.setdefault(team.lower(), []).append(str(r.get(shop_h) or "").strip())
    return out


def parse(header: list[str], rows: list[dict[str, Any]], names: dict[str, list[str]]) -> dict[str, Any]:
    """{months, accounts: [{name, team, actual: {month: PL2}}], warnings} from the PL account sheet and the account list."""
    months = {j: m for j, m in ((j, family_plan._month_key(h)) for j, h in enumerate(header)) if m}
    if not months:
        raise AppError(422, "PL2_ACCOUNT_LAYOUT", "The PL2 account sheet has no month (MM-YYYY) in its header row")

    def cells(row: dict[str, Any]) -> list[str]:
        return [str(row.get(h) or "").strip() for h in header]

    # sheet row numbers: a sync skips the rows that are entirely empty (an account with nothing booked yet), so the k-th account
    # of a team is the row k + 1 below its label, not the k-th row read
    at = [int(r["_row"]) if str(r.get("_row", "")).isdigit() else i for i, r in enumerate(rows)]
    start = next((i for i, r in enumerate(rows) if cells(r)[0].lower() == SECTION), None)
    if start is None:
        raise AppError(422, "PL2_ACCOUNT_LAYOUT", 'The PL2 account sheet has no "PROFIT THỰC ĐẠT" section')
    blocks: list[dict[str, Any]] = []  # {team, row, body: [(row, cells)], end}
    end = at[-1] + 1
    for i in range(start + 1, len(rows)):
        c = cells(rows[i])
        label = c[0].lower()
        if label.startswith(SECTION):  # "Profit thực đạt Etsy 1": the team's accounts follow
            blocks.append({"team": c[0][len(SECTION):].strip(), "row": at[i], "body": []})
        elif label.startswith(("profit", "chênh lệch")):  # next section (PROFIT/SALE…)
            end = at[i]
            break
        elif blocks:
            blocks[-1]["body"].append((at[i], c))
    for b, after in zip(blocks, [*(b["row"] for b in blocks[1:]), end], strict=True):
        b["end"] = after

    accounts, warnings = [], []
    for b in blocks:
        team, listed = b["team"], names.get(b["team"].lower(), [])
        shown = next(((row - b["row"] - 1, c[0]) for row, c in b["body"] if c[0]), None)
        if shown and listed and (shown[0] >= len(listed) or _key(shown[1]) != _key(listed[shown[0]])):
            expected = listed[shown[0]] if shown[0] < len(listed) else "nothing"
            raise AppError(422, "PL2_ACCOUNT_NAMES", f"The account list does not match {team} of the PL2 account sheet: row "
                                                     f"{shown[0] + 1} of the team is {shown[1]} in the sheet, {expected} in the list")
        if len(listed) > b["end"] - b["row"] - 1:
            warnings.append(f"{team}: {len(listed) - (b['end'] - b['row'] - 1)} account(s) of the list have no row in the PL2 account sheet")
        for row, c in b["body"]:
            k = row - b["row"] - 1
            actual = {m: v for j, m in months.items() if (v := _num(c[j])) is not None}
            if k < len(listed) and listed[k]:
                accounts.append({"name": listed[k], "team": team, "actual": actual})
            elif any(actual.values()):
                warnings.append(f"{team}: row {row} has a PL2 but no account in the list")
    return {"months": list(months.values()), "accounts": accounts, "warnings": warnings}


def _sheet(db: Session, sheet_id: int | None, what: str) -> SheetSource | str:
    if sheet_id is None:
        return f"No {what} yet: an admin picks it in Settings → Plan"
    source = db.get(SheetSource, sheet_id)
    if source is None:
        return f"The {what} was removed from Team sheets: an admin picks another in Settings → Plan"
    if not source.rows:
        return f'"{source.name}" has not been synced yet: sync it in Lark › Team sheets'
    return source


def _cf(db: Session, q: ReportQuery) -> dict[str, Any]:
    """{accounts, info} of the PL account sheet, or {"error"}."""
    rt = settings_store.runtime(db)
    if any(q.lists.get(f) for f in ("sellers", "designers")) or q.texts.get("keyword"):
        return {"error": "PL2 CF is per account: clear the seller, designer and keyword filters to compare with it"}
    pl = _sheet(db, rt.pl2_account_sheet_id, "PL2 account sheet")
    names = _sheet(db, rt.account_list_sheet_id, "account list")
    for got in (pl, names):
        if isinstance(got, str):
            return {"error": got}
    try:
        parsed = parse(pl.header or [], pl.rows, parse_account_list(names.header or [], names.rows))
    except AppError as exc:
        return {"error": exc.message}
    return {"accounts": parsed["accounts"], "info": {"sheet": family_plan.sheet_info(pl), "list": family_plan.sheet_info(names),
                                                      "months": parsed["months"], "warnings": parsed["warnings"]}}


def _kh_pl2(db: Session) -> dict[str, Any]:
    """{accounts: {name: {shop, team, kt: {month: $}, cf: {month: $}}}, months: {kt, cf}, sheet} of the account PL2 plan sheet
    ("KH theo Acc"), suspended stores replaced, or {"error"}."""
    rt = settings_store.runtime(db)
    got = _sheet(db, rt.account_plan_sheet_id, "account PL2 plan sheet")
    if isinstance(got, str):
        return {"error": got}
    try:
        parsed = account_plan.parse(got.header or [], got.rows)
    except AppError as exc:
        return {"error": exc.message}
    return {"accounts": account_plan.replace(parsed["accounts"], rt.account_replacements), "months": parsed["months"],
            "sheet": family_plan.sheet_info(got)}


def _kh_accounts(db: Session, date_from: str, date_to: str, factors: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """The stores of the KH sheets (Settings › Plan, product pages), in sheet order, suspended ones replaced, each with its
    plan for the range (pieces, months pro rata of the days) added up over the sheets; None when no sheet plans those months."""
    rt = settings_store.runtime(db)
    seen: dict[str, dict[str, Any]] = {}
    for key, sheet_id in rt.family_plan_sheets.items():
        source, family = db.get(SheetSource, sheet_id), FAMILIES.get(key)
        if source is None or family is None or not source.rows:
            continue
        try:
            parsed = family_plan.replace_accounts(family_plan.parse(source.header or [], source.rows, family), rt.account_replacements)
        except AppError:
            continue
        if parsed["per_store"]:
            planned = family_plan.shop_plans(parsed, date_from, date_to, factors=factors)
            for s in planned["shops"]:
                a = seen.setdefault(_key(s["shop"]), {"name": s["shop"], "team": s["team"], "plan": None})
                if planned["months"]:  # the sheet plans some month of the range
                    a["plan"] = (a["plan"] or 0.0) + sum(g["plan"] for g in s["groups"].values())
    return list(seen.values())


def _fetch(client: TrackingisClient, lines: list[dict[str, Any]], q: ReportQuery) -> list[list[dict[str, Any]]]:
    """The store view of each priced product (its sub product types only), in parallel."""
    with ThreadPoolExecutor(max_workers=family_report.WORKERS) as pool:
        futures = [pool.submit(family_accounts._stores, client, family_report._only(q, tuple(line["sub_types"]))) for line in lines]
        try:
            return [f.result() for f in futures]
        except TrackingisError:
            pool.shutdown(cancel_futures=True)  # a refused token fails every query: don't send the ones still queued
            raise


def _line(name: str, team: str | None, quantity: int, kt: float | None, cf: float | None, plan: float | None = None,
          kt_plan: float | None = None, cf_plan: float | None = None) -> dict[str, Any]:
    """One row. plan = the KH plan to date in pieces; kt_plan / cf_plan = the PL2 plan to date on the KT / CF basis ($), and
    kt_gap = kt − kt_plan, kt_pct = kt / kt_plan (the same for cf)."""
    def gap(v: float | None, p: float | None) -> float | None:
        return None if v is None or p is None else round(v - p, 2)

    def ratio(v: float | None, p: float | None) -> float | None:
        return round(v / p, 4) if v is not None and p else None

    def money(v: float | None) -> float | None:
        return None if v is None else round(v, 2)

    return {"shop": name, "team": team, "quantity": quantity, "plan": None if plan is None else round(plan, 1),
            "kt": money(kt), "cf": money(cf), "cf_minus_kt": round(cf - kt, 2) if kt is not None and cf is not None else None,
            "kt_plan": money(kt_plan), "kt_gap": gap(kt, kt_plan), "kt_pct": ratio(kt, kt_plan),
            "cf_plan": money(cf_plan), "cf_gap": gap(cf, cf_plan), "cf_pct": ratio(cf, cf_plan)}


def pl2_accounts(db: Session, params: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    """{accounts: [{shop, team, quantity, plan, kt, cf, cf_minus_kt, kt_plan, kt_gap, kt_pct, cf_plan, cf_gap, cf_pct}], others:
    {…, count, children}, total, kt, cf, kh_pl2, query}; plan = the account's KH plan to date (pieces), for its KH avg/day;
    kt_plan / cf_plan = its PL2 plan to date on the KT / CF basis ("KH theo Acc"), None when not available."""
    q = report.build_query(db, {**params, "view": "date"}, user)
    rt = settings_store.runtime(db)
    to = {_key(old): new.strip() for old, new in rt.account_replacements}

    def rename(name: Any) -> str:  # a suspended store counts as its replacement
        return to.get(_key(name)) or str(name or "").strip()

    lines = overview.priced_products(db, user)
    kt_info: dict[str, Any] = {} if lines else {"error": "No plan with PL2/item to estimate from: an admin picks the plan sheet in Settings → Plan"}
    stores: dict[str, dict[str, Any]] = {}  # trackingis stores of the report's filters: quantity and KT
    if lines:
        data = report._call(db, user, report._key("pl2_accounts", q), report.CACHE_TTL_S, lambda c: _fetch(c, lines, q))
        for line, rows in zip(lines, data, strict=True):
            for r in rows:
                name = rename(r.get("shop_name"))
                s = stores.setdefault(_key(name), {"name": name, "quantity": 0, "kt": 0.0})
                pcs = int(r.get("total_quantity") or 0)
                s["quantity"] += pcs
                s["kt"] += pcs * line["rate"]

    cf = _cf(db, q)
    in_range = set(family_plan.month_days(q.date_from, q.date_to))
    booked: dict[str, dict[str, Any]] = {}  # finance's accounts: CF of the months the range touches
    for a in cf.get("accounts", []):
        name = rename(a["name"])
        b = booked.setdefault(_key(name), {"name": name, "team": a["team"], "cf": 0.0})
        b["cf"] += sum(v for m, v in a["actual"].items() if m in in_range)

    # the report's team / store filters narrow the accounts as they narrow the sales
    teams = q.lists.get("teams") or []
    team_names = None if not teams or set(teams) == set(rt.default_teams) else family_plan._names(db, user, "teams", teams)
    shop_names = family_plan._names(db, user, "shops", q.lists["shops"]) if q.lists.get("shops") else None

    def kept(name: str, team: str | None) -> bool:
        return (team_names is None or _key(team) in team_names) and (shop_names is None or _key(name) in shop_names)

    has_kt, has_cf = "error" not in kt_info, "error" not in cf
    # seller / designer / keyword filters (and a member limited to their own sales) cut across stores: then only the KH
    # accounts with such sales are listed, without their store plan
    narrowed = any(q.lists.get(f) for f in ("sellers", "designers")) or bool(q.texts.get("keyword"))
    # filtered by seller (admin): each account's plan × the seller's share of the month (seller_plan); else none when narrowed
    seller = seller_plan.shares(db, q, user) if seller_plan.applies(q, user) else None
    factors = seller["factors"] if seller and "factors" in seller else None
    kh = _kh_accounts(db, q.date_from, q.date_to, factors)

    # the PL2 plan per account ("KH theo Acc"): not with filters that cut across stores (a seller's share scales it, as any plan)
    plan = _kh_pl2(db)
    plan_ok = "error" not in plan and (not narrowed or factors is not None)
    days = family_plan.month_days(q.date_from, q.date_to)

    def plan_of(key: str, kind: str, on: bool) -> float | None:
        """The account's plan to date; an account the sheet does not list has $0 in the months it plans."""
        if not (plan_ok and on):
            return None
        line = plan["accounts"].get(key)
        return account_plan.to_date(line[kind] if line else {}, plan["months"][kind], days, factors)

    if plan_ok:  # accounts of the plan sheet that no KH store sheet lists, with a plan for the range
        listed = {_key(a["name"]) for a in kh}
        for key, line in plan["accounts"].items():
            if key not in listed and (round(plan_of(key, "kt", True) or 0, 2) or round(plan_of(key, "cf", True) or 0, 2)):
                kh.append({"name": line["shop"], "team": line["team"], "plan": None})
    accounts = []
    for a in kh:
        if not kept(a["name"], a["team"]):
            continue
        s, b = stores.get(_key(a["name"]), {}), booked.get(_key(a["name"]), {})
        if narrowed and not s:
            continue
        key = _key(a["name"])
        accounts.append(_line(a["name"], a["team"], s.get("quantity", 0), s.get("kt", 0.0) if has_kt else None,
                              b.get("cf", 0.0) if has_cf else None, a["plan"] if not narrowed or factors is not None else None,
                              plan_of(key, "kt", has_kt), plan_of(key, "cf", has_cf)))
    planned = {_key(a["name"]) for a in kh}  # every account of the plans, whether the filters keep it or not
    children = []
    for key in sorted(set(stores) | set(booked)):
        if key in planned:
            continue
        s, b = stores.get(key, {}), booked.get(key, {})
        team = b.get("team")
        if not s and not kept(b["name"], team):  # sales come already filtered by trackingis; finance's rows are filtered here
            continue
        kt, cf_value = s.get("kt", 0.0), b.get("cf", 0.0)
        if round(kt, 2) or round(cf_value, 2):  # only accounts with a PL2
            children.append(_line(s.get("name") or b.get("name"), team, s.get("quantity", 0), kt if has_kt else None,
                                  cf_value if has_cf else None, kt_plan=plan_of(key, "kt", has_kt), cf_plan=plan_of(key, "cf", has_cf)))
    children.sort(key=lambda c: -abs(c["cf"] or c["kt"] or 0))

    def add(rows: list[dict[str, Any]], field: str, on: bool) -> float | None:
        return round(sum(r[field] or 0 for r in rows), 2) if on else None

    others = {**_line(OTHERS, None, sum(c["quantity"] for c in children), add(children, "kt", has_kt), add(children, "cf", has_cf),
                      kt_plan=add(children, "kt_plan", plan_ok and has_kt), cf_plan=add(children, "cf_plan", plan_ok and has_cf)),
              "count": len(children), "children": children}
    everything = [*accounts, others]
    plans = [a["plan"] for a in accounts if a["plan"] is not None]
    total = _line("All accounts", None, sum(r["quantity"] for r in everything), add(everything, "kt", has_kt), add(everything, "cf", has_cf),
                  sum(plans) if plans else None, add(everything, "kt_plan", plan_ok and has_kt), add(everything, "cf_plan", plan_ok and has_cf))
    if "error" in plan:
        kh_info: dict[str, Any] = {"error": plan["error"]}
    elif not plan_ok:  # same as CF's: one note for the filters that cut across stores
        kh_info = {"error": cf.get("error") or "The PL2 plan is per account: clear the seller, designer and keyword filters to compare with it"}
    else:
        planned_months = {m for kind in account_plan.KINDS for m in plan["months"][kind]}
        kh_info = {"sheet": plan["sheet"], "months": plan["months"], "missing": [m for m in days if m not in planned_months]}
    return {"accounts": accounts, "others": others, "total": total, "kt": kt_info, "cf": cf.get("info") or {"error": cf.get("error")},
            "kh_pl2": kh_info, "query": {"date_from": q.date_from, "date_to": q.date_to, "teams": q.lists["teams"]}}
