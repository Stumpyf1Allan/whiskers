"""The Budget tab's figures: a month's money in, out and saved, by category, against the
budgets set; twelve months of history; and the tile on the Overall tab.

Money moved into savings or investments is "saved", not spent, and money moving between
your own accounts counts as neither (Mittens & Pence's rule). Amounts in another currency
are converted at that day's rate; a row with no rate yet is left out and counted.
"""

from __future__ import annotations

import calendar
import datetime as dt

from .. import db
from ..market import store
from . import categories


def current_period(today: dt.date | None = None) -> str:
    return (today or dt.date.today()).strftime("%Y-%m")


def bounds(period: str) -> tuple[str, str]:
    y, m = (int(x) for x in period.split("-"))
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def shift(period: str, months: int) -> str:
    y, m = (int(x) for x in period.split("-"))
    k = y * 12 + (m - 1) + months
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def _gbp(row: dict) -> float | None:
    ccy = (row.get("currency") or "GBP").upper()
    return row["amount"] if ccy == "GBP" else store.to_gbp(row["amount"], ccy, row["posted_on"])


def _rows(start: str, end: str) -> list[dict]:
    return db.rows("SELECT t.*, c.parent, c.name AS category, c.kind, p.name AS account FROM txns t "
                   "LEFT JOIN txn_categories c ON c.id=t.category_id JOIN platforms p ON p.id=t.platform_id "
                   "WHERE t.posted_on BETWEEN ? AND ? ORDER BY t.posted_on DESC, t.id DESC", (start, end))


def month(period: str | None = None) -> dict:
    period = period or current_period()
    start, end = bounds(period)
    cats = {c["id"]: c for c in categories.all_categories()}
    spent: dict[int | None, float] = {}
    money_in = out = saved = 0.0
    unconverted = 0
    for r in _rows(start, end):
        v = _gbp(r)
        if v is None:
            unconverted += 1
            continue
        kind = r["kind"] or ("in" if v > 0 else "out")
        if kind == "transfer":
            continue
        if kind == "in":
            money_in += v
        elif kind == "save":
            saved += -v
        else:
            out += -v
            spent[r["category_id"]] = spent.get(r["category_id"], 0.0) + (-v)
    lines = []
    for cid, c in cats.items():
        if c["kind"] != "out":
            continue
        s = spent.get(cid, 0.0)
        if s or c["budget"]:
            lines.append({"id": cid, "parent": c["parent"], "name": c["name"], "spent": round(s, 2),
                          "budget": c["budget"], "left": round(c["budget"] - s, 2) if c["budget"] else None})
    if spent.get(None):
        lines.append({"id": None, "parent": "Not sorted yet", "name": "Not sorted yet",
                      "spent": round(spent[None], 2), "budget": None, "left": None})
    lines.sort(key=lambda x: -(x["spent"] or 0))
    budget_total = sum(c["budget"] or 0 for c in cats.values() if c["kind"] == "out")
    y, m = (int(x) for x in period.split("-"))
    days = calendar.monthrange(y, m)[1]
    today = dt.date.today()
    through = 1.0 if period < current_period(today) else (today.day / days if period == current_period(today) else 0.0)
    return {"period": period, "label": dt.date(y, m, 1).strftime("%B %Y"), "in": round(money_in, 2),
            "out": round(out, 2), "saved": round(saved, 2), "left": round(money_in - out - saved, 2),
            "lines": lines, "budget_total": round(budget_total, 2), "through": round(through, 3),
            "uncategorised": db.scalar("SELECT COUNT(*) FROM txns WHERE category_id IS NULL AND posted_on BETWEEN ? AND ?",
                                       (start, end), 0),
            "unconverted": unconverted}


def history(months: int = 12) -> list[dict]:
    cur = current_period()
    out = []
    for k in range(months - 1, -1, -1):
        p = shift(cur, -k)
        m = month(p)
        out.append({"period": p, "in": m["in"], "out": m["out"], "saved": m["saved"]})
    return out


def suggest_budgets(months: int = 3) -> list[dict]:
    """Each spending category's average over the last few whole months, rounded up to £5."""
    cur = current_period()
    totals: dict[int, float] = {}
    for k in range(1, months + 1):
        for ln in month(shift(cur, -k))["lines"]:
            if ln["id"]:
                totals[ln["id"]] = totals.get(ln["id"], 0.0) + ln["spent"]
    cats = {c["id"]: c for c in categories.all_categories()}
    out = []
    for cid, t in totals.items():
        avg = t / months
        if avg >= 5:
            out.append({"id": cid, "parent": cats[cid]["parent"], "name": cats[cid]["name"],
                        "suggested": float(int((avg + 4.99) // 5 * 5))})
    return sorted(out, key=lambda x: -x["suggested"])


def set_budget(category_id: int, amount: float | None) -> None:
    db.execute("UPDATE txn_categories SET budget=? WHERE id=?", (amount, category_id))


def accounts() -> list[dict]:
    return db.rows("SELECT p.id, p.name, p.currency, MIN(t.posted_on) AS first, MAX(t.posted_on) AS last, "
                   "COUNT(t.id) AS n FROM platforms p LEFT JOIN txns t ON t.platform_id=p.id "
                   "WHERE p.provider='bank' GROUP BY p.id ORDER BY p.sort, p.id")


def tile() -> dict:
    """The Budget's square on the Overall tab: this month so far, against the budgets."""
    m = month()
    lines = []
    lvl = "none"
    if not db.scalar("SELECT COUNT(*) FROM txns", (), 0):
        return {"key": "budget", "title": "Budget", "go": "budget", "level": "none", "value": None,
                "lines": ["No statements imported yet"]}
    if m["budget_total"]:
        pace = m["budget_total"] * m["through"]
        lvl = "red" if m["out"] > m["budget_total"] else "amber" if m["out"] > pace * 1.1 else "green"
        lines.append(f"[[£{m['out']:,.0f}]] of [[£{m['budget_total']:,.0f}]] spent")
    else:
        lines.append(f"[[£{m['out']:,.0f}]] spent so far; no budgets set")
        lvl = "green"
    if m["uncategorised"]:
        lines.append(f"{m['uncategorised']} transaction{'s' if m['uncategorised'] != 1 else ''} to sort")
    return {"key": "budget", "title": "Budget", "go": "budget", "level": lvl, "value": m["left"],
            "value_label": f"left in {m['label'].split()[0]}", "lines": lines}


def transactions(period: str | None = None, q: str = "", category: str = "", platform: str = "",
                 uncategorised: bool = False, limit: int = 400) -> list[dict]:
    where, params = ["1=1"], []
    if period:
        start, end = bounds(period)
        where.append("t.posted_on BETWEEN ? AND ?")
        params += [start, end]
    if q:
        where.append("LOWER(t.description) LIKE ?")
        params.append(f"%{q.lower()}%")
    if category.isdigit():
        where.append("t.category_id=?")
        params.append(int(category))
    if platform.isdigit():
        where.append("t.platform_id=?")
        params.append(int(platform))
    if uncategorised:
        where.append("t.category_id IS NULL")
    sql = ("SELECT t.*, c.parent, c.name AS category, c.kind, p.name AS account FROM txns t "
           "LEFT JOIN txn_categories c ON c.id=t.category_id JOIN platforms p ON p.id=t.platform_id "
           f"WHERE {' AND '.join(where)} ORDER BY t.posted_on DESC, t.id DESC LIMIT ?")  # nosec B608  # fixed clauses
    return db.rows(sql, (*params, int(limit)))
