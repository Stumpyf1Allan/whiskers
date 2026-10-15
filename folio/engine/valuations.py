"""Valuations typed in by hand: the market-context card.

Some of the most quoted measures of how expensive shares are have no dependable free
daily feed: Shiller's CAPE, forward P/E ratios, Damodaran's implied equity risk premium.
They change slowly, so a figure typed in once a month, or during a review with Claude,
is enough. Each keeps the date it was typed in and says so, and a figure more than three
months old is marked as old rather than passed off as current.

None of them times the market. High valuations have come before poor ten-year returns
but say little about the next year; they belong beside a plan, not in place of one.
"""

from __future__ import annotations

import datetime as dt

from .. import db

FIELDS = [
    {"key": "cape_us", "label": "US shares: cyclically adjusted P/E (CAPE)", "unit": "x",
     "about": "Robert Shiller's measure: the S&P 500's price against ten years of earnings after "
              "inflation. Its long-run average is about 17. High readings have come before poor "
              "ten-year returns, but say little about the next year.",
     "where": "multpl.com (Shiller PE), or Robert Shiller's own data page"},
    {"key": "fpe_us", "label": "US shares: forward P/E (S&P 500)", "unit": "x",
     "about": "Price against the next twelve months' expected earnings. Its 25-year average is "
              "about 16 to 17.",
     "where": "Yardeni Research, or FactSet's weekly Earnings Insight"},
    {"key": "fpe_world", "label": "World shares: forward P/E (MSCI ACWI)", "unit": "x",
     "about": "The same measure for the whole world's stock markets, which a global index fund "
              "owns.",
     "where": "Yardeni Research's global valuation charts, or MSCI's factsheet"},
    {"key": "fpe_uk", "label": "UK shares: forward P/E (FTSE 100)", "unit": "x",
     "about": "UK companies have long been priced lower than American ones, partly because of "
              "what they do (banks, oil, miners) rather than where they are.",
     "where": "Yardeni Research, or a broker's market commentary"},
    {"key": "erp", "label": "Equity risk premium, implied (US)", "unit": "%",
     "about": "Aswath Damodaran's monthly estimate of the extra yearly return shares are priced "
              "to give over US government bonds. Lower means shares are dearer against bonds.",
     "where": "Damodaran Online, updated at the start of each month"},
]
BY_KEY = {f["key"]: f for f in FIELDS}
#: Older than this and a figure is marked as old.
OLD_AFTER_DAYS = 92


class ValuationError(ValueError):
    pass


def values() -> dict:
    """{key: {"value", "on", "note", "old"}} for every field that has been typed in."""
    stored = db.get_meta("valuations", {}) or {}
    today = dt.date.today()
    out = {}
    for k, v in stored.items():
        if k not in BY_KEY or not isinstance(v, dict) or v.get("value") is None:
            continue
        try:
            age = (today - dt.date.fromisoformat(str(v.get("on"))[:10])).days
        except ValueError:
            age = None
        out[k] = {"value": v["value"], "on": v.get("on"), "note": v.get("note") or "",
                  "old": age is None or age > OLD_AFTER_DAYS}
    return out


def save(changes: dict) -> dict:
    """Each change is {"value": number or blank, "on": "YYYY-MM-DD", "note": text}. A blank
    value removes the figure; a missing date means today."""
    stored = db.get_meta("valuations", {}) or {}
    for k, v in (changes or {}).items():
        if k not in BY_KEY:
            raise ValuationError(f"Unknown measure: {k}")
        v = v if isinstance(v, dict) else {"value": v}
        raw = v.get("value")
        if raw in (None, ""):
            stored.pop(k, None)
            continue
        try:
            value = float(str(raw).replace("%", "").replace("x", "").strip())
        except ValueError:
            raise ValuationError(f"{BY_KEY[k]['label']}: type a number, like 35.2.") from None
        if not 0 < value < 200:
            raise ValuationError(f"{BY_KEY[k]['label']}: {value:g} doesn't look right.")
        on = str(v.get("on") or "").strip()[:10] or dt.date.today().isoformat()
        try:
            when = dt.date.fromisoformat(on)
        except ValueError:
            raise ValuationError(f"{BY_KEY[k]['label']}: the date should look like 2026-10-01.") from None
        if when > dt.date.today():
            raise ValuationError(f"{BY_KEY[k]['label']}: the date is in the future.")
        stored[k] = {"value": round(value, 2), "on": on, "note": str(v.get("note") or "").strip()[:200]}
    db.set_meta("valuations", stored)
    return values()


def lines() -> list[str]:
    """For the review pack: one line a figure, with its date."""
    v = values()
    out = []
    for f in FIELDS:
        x = v.get(f["key"])
        if not x:
            continue
        unit = "%" if f["unit"] == "%" else "x"
        out.append(f"- {f['label']}: {x['value']:g}{unit} (typed in for {x['on']}"
                   + (", now old" if x["old"] else "") + (f"; {x['note']}" if x["note"] else "") + ")")
    return out
