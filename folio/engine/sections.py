"""The optional sections: Mortgage and Retirement.

Both are off until somebody wants them. A section that is off shows nothing and counts
towards nothing, so a copy that never switches one on looks and adds up exactly as 1.0
did. When either is on, the Overview gains one line for each section and a line for net
worth, counting what the switched-on sections hold: the home and the mortgage with
Mortgage, pension pots with Retirement.

A final-salary pension is not a pot and is never added in as though it could be spent
tomorrow; it is shown as the income it is.
"""

from __future__ import annotations

import datetime as dt
import json

from .. import config, db
from ..market import store
from . import mortgage as mort, portfolio, retirement


def on() -> dict:
    s = config.settings
    return {"mortgage": bool(s.get("show_mortgage")), "retirement": bool(s.get("show_retirement"))}


def any_on() -> bool:
    return any(on().values())


def _gbp(value, ccy) -> float | None:
    if value is None:
        return None
    ccy = (ccy or "GBP").upper()
    return float(value) if ccy == "GBP" else store.to_gbp(value, ccy)


def balance_sheet(pos: list[dict] | None = None, tot: dict | None = None) -> dict:
    """What is owned and owed, counting only the sections that are switched on."""
    pos = portfolio.positions() if pos is None else pos
    tot = portfolio.totals(pos) if tot is None else tot
    sec = on()
    plats = tot["platforms"]
    investments = sum(p["total"] for p in plats if p["kind"] == "platform")
    cash = sum((p["cash"] or 0.0) for p in plats if p["kind"] == "bank" and not p["fx_missing"])
    cash_abroad = sum((p["cash"] or 0.0) for p in plats if p["kind"] == "bank" and p["currency"] != "GBP"
                      and not p["fx_missing"])
    owed_cards = sum(-(p["cash"] or 0.0) for p in plats if p["kind"] == "card")
    unconverted = [p["name"] for p in plats if p["fx_missing"]]
    pots, promised = 0.0, []
    if sec["retirement"]:
        for r in db.rows("SELECT * FROM pensions ORDER BY sort, id"):
            if r["kind"] in ("dc", "sa_ra") and r["pot"] is not None:
                v = _gbp(r["pot"], r.get("currency"))
                if v is None:
                    unconverted.append(r["name"])
                else:
                    pots += v
            elif r["kind"] in ("db", "annuity") and r["yearly"] is not None:
                promised.append({"name": r["name"], "yearly": r["yearly"],
                                 "from": r["start_age"] or r["normal_age"], "kind": r["kind"]})
    property_, other = 0.0, 0.0
    if any(sec.values()):
        for a in db.rows("SELECT * FROM assets ORDER BY sort, id"):
            v = _gbp(a["value"], a["currency"])
            if v is None:
                continue
            if a["kind"] == "property":
                property_ += v
            else:
                other += v
    mortgages, owed_mortgage = [], 0.0
    if sec["mortgage"]:
        for rec in mort.all_mortgages():
            m = mort.summarise(rec)
            mortgages.append(m)
            if m["balance"] is not None:
                owed_mortgage += _gbp(m["balance"], m.get("currency")) or 0.0
            if not rec.get("property_asset_id") and m.get("property_value"):
                property_ += m["property_value"]
    own = {"Investments": investments, "Cash": cash, "Pensions": pots, "Home and property": property_,
           "Other things": other}
    owe = {"Mortgage": owed_mortgage, "Cards": owed_cards}
    total_own, total_owe = sum(own.values()), sum(owe.values())
    return {"own": {k: round(v, 2) for k, v in own.items() if v},
            "owe": {k: round(v, 2) for k, v in owe.items() if v},
            "total_own": round(total_own, 2), "total_owe": round(total_owe, 2),
            "net": round(total_own - total_owe, 2), "promised": promised,
            "cash_abroad": round(cash_abroad, 2), "unconverted": unconverted, "mortgages": mortgages,
            "sections": sec}


def take_snapshot(bs: dict | None = None) -> None:
    """Net worth once a day, while a section is on (otherwise the Overview's own daily
    record of the portfolio already says it all)."""
    if not any_on():
        return
    bs = bs or balance_sheet()
    if not bs["total_own"] and not bs["total_owe"]:
        return
    with db.tx() as c:
        c.execute("INSERT INTO networth(d,own,owe,net,detail) VALUES(?,?,?,?,?) ON CONFLICT(d) DO UPDATE SET "
                  "own=excluded.own, owe=excluded.owe, net=excluded.net, detail=excluded.detail",
                  (db.today(), bs["total_own"], bs["total_owe"], bs["net"],
                   json.dumps({"own": bs["own"], "owe": bs["owe"]})))


def history() -> list[list]:
    return [[r["d"], r["net"]] for r in db.rows("SELECT d, net FROM networth ORDER BY d")]


def _clear_by(payoff: dt.date) -> str:
    """'clears July 2039, 3 years after you stop': whether the mortgage outlives the salary
    is the question that matters."""
    words = "clears " + payoff.strftime("%B %Y")
    s = retirement.settings()
    dob = retirement.dob_of(s)
    if not dob or not s.get("stop_age") or not on()["retirement"]:
        return words
    stop = dob + dt.timedelta(days=round(float(s["stop_age"]) * 365.25))
    years = (payoff - stop).days / 365.25
    if years >= 0.5:
        n = round(years)
        return words + f", {n} year{'s' if n != 1 else ''} after you stop work"
    if years <= -0.5:
        return words + ", before you stop work"
    return words + ", about when you stop work"


def _money(v: float | None) -> str:
    return "[[£{:,.0f}]]".format(v) if v is not None else "an unknown amount"


def mortgage_line(bs: dict) -> dict:
    ms = bs["mortgages"]
    if not ms:
        return {"key": "mortgage", "title": "Mortgage", "level": "none", "go": "mortgage",
                "words": "None added yet. Add it from its latest statement to see when the fixed rate ends "
                         "and what paying more would save."}
    m = ms[0]
    owed = sum((x["balance"] or 0.0) for x in ms)
    bits = [f"{_money(owed)} owed"]
    d = m.get("days_to_rate_change")
    level = "green"
    if d is not None and d >= 0:
        bits.append(f"the fixed rate ends in {d} days")
        if d <= 200:
            level = "amber"
    elif d is not None:
        bits.append(f"the fixed rate ended {-d} days ago")
        level = "red"
    if m.get("payoff_on") and m.get("repayment_type") == "interest_only":
        end = dt.date.fromisoformat(m["payoff_on"][:7] + "-01")
        bits.append(f"interest only, {_money(m['balance'])} to repay in {end.strftime('%B %Y')}")
    elif m.get("payoff_on"):
        bits.append(_clear_by(dt.date.fromisoformat(m["payoff_on"][:7] + "-01")))
    if m.get("never_clears") or m.get("term_mismatch"):
        level = "red"
        bits.append("the payment and the term don't add up")
    more = f" ({len(ms)} mortgages)" if len(ms) > 1 else ""
    words = "; ".join(bits)
    # The first letter only: str.capitalize() would also lower "July" and "£93,260 owed".
    return {"key": "mortgage", "title": "Mortgage", "level": level, "go": "mortgage",
            "words": words[:1].upper() + words[1:] + more + "."}


def retirement_line() -> dict:
    try:
        ret = retirement.analyse(full=False)
    except Exception as e:                    # a summary line is never worth a broken Overview
        db.log("sections.retirement", str(e))
        return {"key": "retirement", "title": "Retirement", "level": "none", "go": "retirement",
                "words": "The year-by-year plan couldn't run. Open the section to see why."}
    if not ret.get("ready"):
        need = ", ".join(ret.get("missing") or ["a few details"])
        return {"key": "retirement", "title": "Retirement", "level": "none", "go": "retirement",
                "words": f"Needs {need} for the year-by-year plan."}
    pl = ret["plan"]
    fl = pl.get("income_floor") or {}
    first = (f"On its assumptions the money lasts to {int(pl['horizon'])}" if pl["lasts"] else
             f"On its assumptions the money runs short at about {int(pl['runs_out_at'])}")
    second = (f"guaranteed income covers {min(fl['covers'], 9.99) * 100:.0f}% of essential spending"
              if fl.get("covers") is not None else None)
    level = "green" if pl["lasts"] else ("amber" if (pl["runs_out_at"] or 0) >= 85 else "red")
    return {"key": "retirement", "title": "Retirement", "level": level, "go": "retirement",
            "words": first + (f"; {second}" if second else "") + "."}


def overview(pos: list[dict] | None = None, tot: dict | None = None) -> dict | None:
    """The Overview's extra lines: nothing at all while every section is off."""
    sec = on()
    if not any(sec.values()):
        return None
    bs = balance_sheet(pos, tot)
    if not db.one("SELECT 1 FROM networth WHERE d=?", (db.today(),)):
        try:
            take_snapshot(bs)
        except Exception as e:
            db.log("networth.error", str(e))
    lines = []
    if sec["mortgage"]:
        lines.append(mortgage_line(bs))
    if sec["retirement"]:
        lines.append(retirement_line())
    change = None
    h = history()
    if len(h) >= 2:
        month_ago = (dt.date.today() - dt.timedelta(days=30)).isoformat()
        then = next((v for d, v in reversed(h) if d <= month_ago), None)
        if then is not None:
            change = bs["net"] - then
    return {"net": bs["net"], "own": bs["own"], "owe": bs["owe"], "total_own": bs["total_own"],
            "total_owe": bs["total_owe"], "promised": bs["promised"], "month_change": change,
            "unconverted": bs["unconverted"], "lines": lines, "sections": sec}


def advice(age: float | None, has_mortgage: bool | None, years_to_need: float | None,
           drawing: bool) -> dict:
    """Which sections fit somebody, and why: what the plan builder offers to switch on. A
    long way from needing the money, with no mortgage, nothing is suggested."""
    out = {}
    if has_mortgage:
        out["mortgage"] = "You have a mortgage: the section shows when the fixed rate ends, what paying " \
                          "more would save, and how much of the home you own."
    reasons = []
    if age is not None and age >= 55:
        reasons.append(f"at {int(age)}, pensions and when to draw on them shape the plan")
    if drawing:
        reasons.append("you're already spending from your investments")
    elif years_to_need is not None and years_to_need <= 10:
        reasons.append("you'll start spending from this money within ten years")
    if reasons:
        out["retirement"] = ("Because " + " and ".join(reasons) + ", the year-by-year plan, your pensions "
                             "and the State Pension are worth having beside your investments.")
    return out
