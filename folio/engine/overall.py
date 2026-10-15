"""The Overall tab: everything owned and owed, how each part is doing, and what needs
doing this year.

Net worth is what is owned (investments, cash in any currency, pension pots, the house)
less what is owed (the mortgage, credit cards). A final-salary pension is not a pot and
is never added in as though it could be spent tomorrow; it is shown as the income it is.
The ring on the screen is what is owned; what is owed sits underneath, so the two can
never be confused for one total.

Each tab that is switched on gets one health tile with a traffic light, and the big
picture pulls the main watch theme, markets, and the person's own plan into three
paragraphs. The Budget tab counts here only when it is switched on.
"""

from __future__ import annotations

import datetime as dt
import json

from .. import config, db
from ..market import store
from . import (allocation, isa, mortgage as mort, narrative, playbook, portfolio, retirement, rules,
               signals, statepension, stress, themes)


def balance_sheet(pos: list[dict] | None = None, tot: dict | None = None) -> dict:
    pos = portfolio.positions() if pos is None else pos
    tot = portfolio.totals(pos) if tot is None else tot
    plats = tot["platforms"]
    investments = sum(p["total"] for p in plats if p["kind"] == "platform")
    cash = sum((p["cash"] or 0.0) for p in plats if p["kind"] == "bank" and not p["fx_missing"])
    cash_abroad = sum((p["cash"] or 0.0) for p in plats if p["kind"] == "bank" and p["currency"] != "GBP"
                      and not p["fx_missing"])
    owed_cards = sum(-(p["cash"] or 0.0) for p in plats if p["kind"] == "card")
    unconverted = [p["name"] for p in plats if p["fx_missing"]]
    pots, promised = 0.0, []
    for r in db.rows("SELECT * FROM pensions ORDER BY sort, id"):
        ccy = (r.get("currency") or "GBP").upper()
        if r["kind"] in ("dc", "sa_ra") and r["pot"] is not None:
            v = r["pot"] if ccy == "GBP" else store.to_gbp(r["pot"], ccy)
            if v is None:
                unconverted.append(r["name"])
            else:
                pots += v
        elif r["kind"] in ("db", "annuity") and r["yearly"] is not None:
            promised.append({"name": r["name"], "yearly": r["yearly"],
                             "from": r["start_age"] or r["normal_age"], "kind": r["kind"]})
    assets = db.rows("SELECT * FROM assets ORDER BY sort, id")
    property_, other = 0.0, 0.0
    for a in assets:
        v = a["value"] if (a["currency"] or "GBP") == "GBP" else store.to_gbp(a["value"], a["currency"])
        if v is None:
            continue
        if a["kind"] == "property":
            property_ += v
        else:
            other += v
    mortgages = [mort.summarise(m) for m in mort.all_mortgages()]
    owed_mortgage = 0.0
    for m, rec in zip(mortgages, mort.all_mortgages()):
        if m["balance"] is not None:
            owed_mortgage += m["balance"] if (m.get("currency") or "GBP") == "GBP" else \
                (store.to_gbp(m["balance"], m["currency"]) or 0.0)
        if not rec.get("property_asset_id") and m.get("property_value"):
            property_ += m["property_value"]
    own = {"Investments": investments, "Cash": cash, "Pensions": pots, "Property": property_, "Other": other}
    owe = {"Mortgage": owed_mortgage, "Cards": owed_cards}
    total_own = sum(own.values())
    total_owe = sum(owe.values())
    return {"own": {k: round(v, 2) for k, v in own.items() if v}, "owe": {k: round(v, 2) for k, v in owe.items() if v},
            "total_own": round(total_own, 2), "total_owe": round(total_owe, 2),
            "net": round(total_own - total_owe, 2), "promised": promised, "cash_abroad": round(cash_abroad, 2),
            "unconverted": unconverted, "mortgages": mortgages}


def take_snapshot(bs: dict | None = None) -> None:
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


def tabs() -> dict:
    s = config.settings
    return {"overall": True, "investments": True, "mortgage": bool(s.get("show_mortgage")),
            "retirement": bool(s.get("show_retirement")), "budget": bool(s.get("budget_on"))}


def _clear_by(payoff: dt.date) -> str:
    """'Clear by July 2039, 3 years after you stop': the question that matters is whether
    the mortgage outlives the salary."""
    words = "Clear by " + payoff.strftime("%B %Y")
    s = retirement.settings()
    dob = retirement.dob_of(s)
    if not dob or not s.get("stop_age"):
        return words
    stop = dob + dt.timedelta(days=round(float(s["stop_age"]) * 365.25))
    years = (payoff - stop).days / 365.25
    if years >= 0.5:
        n = round(years)
        return words + f", {n} year{'s' if n != 1 else ''} after you stop"
    if years <= -0.5:
        return words + ", before you stop"
    return words + ", about when you stop"


def this_year(ret: dict | None, pb: dict | None) -> list[dict]:
    today = dt.date.today()
    out = []
    a = isa.allowance()
    if a["remaining"] > 0:
        out.append({"when": a["end"], "what": f"{narrative._money(a['remaining'])} of ISA allowance left",
                    "detail": f"{a['label']} ends on 5 April; unused allowance doesn't carry over.", "go": "activity"})
    s = retirement.settings()
    dob = retirement.dob_of(s)
    if dob:
        sp = statepension.estimate(s, dob)
        if sp.get("top_up"):
            t = sp["top_up"]
            out.append({"when": f"{int(t['oldest_deadline'][-4:])}-04-05",
                        "what": "Last day to fill the oldest gap in your NI record",
                        "detail": f"The {t['oldest_year']} year. Check your record on gov.uk first.", "go": "statepension"})
        if retirement.age_on(dob, today) < 65:
            out.append({"when": "2027-04-06", "what": "Cash ISAs capped at £12,000 a year for under-65s",
                        "detail": "Stocks and shares ISAs keep the full £20,000.", "go": None})
    if db.scalar("SELECT COUNT(*) FROM pensions", (), 0):
        out.append({"when": "2027-04-06", "what": "Unused pensions start to count for inheritance tax",
                    "detail": "Check each pension's nomination.", "go": "pensions"})
    for m in mort.all_mortgages():
        if m.get("fixed_until"):
            d = (dt.date.fromisoformat(m["fixed_until"][:10]) - today).days
            if -30 <= d <= 400:
                out.append({"when": m["fixed_until"][:10], "what": f"{m['name']}: fixed rate ends",
                            "detail": "Most lenders let you book a new deal three to six months ahead.", "go": "mortgage"})
    for t in db.rows("SELECT t.next_check, i.name FROM theses t JOIN instruments i ON i.id=t.instrument_id "
                     "WHERE t.next_check IS NOT NULL AND t.next_check <> ''"):
        try:
            d = dt.date.fromisoformat(t["next_check"][:10])
        except ValueError:
            continue
        if (d - today).days <= 400:
            out.append({"when": d.isoformat(), "what": f"Check your reason for owning {t['name']}",
                        "detail": "The date you set on its thesis.", "go": "holdings"})
    if pb and pb.get("manual_due"):
        out.append({"when": today.isoformat(), "what": "Hand-filled signals are due",
                    "detail": "Update them on the Market watch screen after each earnings season.", "go": "ai"})
    b = db.get_meta("builder", {}) or {}
    if (b.get("answers") or {}).get("self_assessment") == "yes":
        jan = dt.date(today.year if today.month == 1 else today.year + 1, 1, 31)
        out.append({"when": jan.isoformat(), "what": "Self Assessment: online return and any tax owed",
                    "detail": f"For the {jan.year - 2}/{str(jan.year - 1)[-2:]} tax year.", "go": None})
    if b.get("applied"):
        try:
            nxt = dt.date.fromisoformat(b["applied"]).replace(year=dt.date.fromisoformat(b["applied"]).year + 1)
            out.append({"when": nxt.isoformat(), "what": "Review your plan", "detail": "Once a year, or after a big change.",
                        "go": "plan"})
        except ValueError:
            pass
    out.sort(key=lambda r: r["when"])
    return out


def summary() -> dict:
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    bs = balance_sheet(pos, tot)
    if not db.one("SELECT 1 FROM networth WHERE d=?", (db.today(),)):
        try:
            take_snapshot(bs)
        except Exception as e:
            db.log("networth.error", str(e))
    tb = tabs()
    alloc = allocation.view(pos, tot)
    exp = stress.exposure(pos, tot)
    market = signals.evaluate()
    w = market.get("watch") or {}
    main = w.get("main") or "ai"
    texp = exp if main == "ai" else themes.exposure(pos, tot, main)
    back = portfolio.backdated(5 * 365, pos)
    cash_sleeve = next((r["value"] for r in alloc["sleeves"] if r["is_cash"]), tot["cash"])
    pb = playbook.evaluate(back, cash_sleeve)
    ht = allocation.holding_targets(pos, tot["total"] or 0.0)
    warns = rules.evaluate(pos, tot, alloc, exp, market, pb, ht)
    tiles = []
    red = sum(1 for x in warns if x["level"] == "red")
    amber = sum(1 for x in warns if x["level"] == "amber")
    sleeves = alloc.get("sleeves") or []
    in_band = sum(1 for r in sleeves if r["status"] in ("green", "ok"))
    tiles.append({"key": "investments", "title": "Investments", "go": "overview",
                  "level": "red" if red else "amber" if amber else "green" if tot["total"] else "none",
                  "value": tot["total"], "day": tot.get("day_change"),
                  "lines": [f"{in_band} of {len(sleeves)} sleeves in their band" if sleeves else "No plan set yet",
                            f"{red} to act on, {amber} to look at" if (red or amber) else "Nothing needs a look"],
                  "watch": {"label": market["label"], "regime": market["regime"], "gauge": market["gauge"],
                            "title": w.get("main_title") or "The AI trade", "main": main}})
    ret = None
    if tb["retirement"]:
        try:
            ret = retirement.analyse(full=False)
        except Exception as e:
            db.log("overall.retirement", str(e))
            ret = None
        if ret and ret.get("ready"):
            pl = ret["plan"]
            fl = pl["income_floor"]
            lines = [("Lasts to " + f"{int(pl['horizon'])}+" if pl["lasts"] else
                      f"Runs short at about {int(pl['runs_out_at'])}"),
                     (f"Guaranteed income covers {min(fl['covers'], 9.99) * 100:.0f}% of essentials"
                      if fl.get("covers") is not None else "Essentials not entered")]
            tiles.append({"key": "retirement", "title": "Retirement", "go": "retirement",
                          "level": "green" if pl["lasts"] else ("amber" if (pl["runs_out_at"] or 0) >= 85 else "red"),
                          "value": pl["at_stop"]["liquid"], "value_label": f"at {pl['stop_age']:g}", "lines": lines})
        else:
            tiles.append({"key": "retirement", "title": "Retirement", "go": "retirement", "level": "none",
                          "value": None, "lines": ["Needs " + ", ".join((ret or {}).get("missing") or ["a few details"])]})
    if tb["mortgage"]:
        ms = bs["mortgages"]
        if ms:
            m = ms[0]
            d = m.get("days_to_rate_change")
            lvl = "amber" if (d is not None and 0 <= d <= 200) else "red" if (d is not None and d < 0) else "green"
            if m.get("never_clears") or m.get("term_mismatch"):
                lvl = "red"
            lines = []
            if d is not None:
                lines.append(f"Fixed rate ends in {d} days" if d >= 0 else f"Fixed rate ended {-d} days ago")
            if m.get("payoff_on"):
                lines.append(_clear_by(dt.date.fromisoformat(m["payoff_on"][:7] + "-01")))
            if m.get("ltv") is not None:
                lines.append(f"{m['ltv'] * 100:.0f}% loan to value")
            tiles.append({"key": "mortgage", "title": "Mortgage", "go": "mortgage", "level": lvl,
                          "value": -(sum(x["balance"] or 0 for x in ms)), "lines": lines})
        else:
            tiles.append({"key": "mortgage", "title": "Mortgage", "go": "mortgage", "level": "none", "value": None,
                          "lines": ["No mortgage added"]})
    s = retirement.settings()
    ess = s.get("spend_essential")
    cash_known = bool(bs["own"].get("Cash")) or not any(
        p["kind"] == "bank" and p["fx_missing"] for p in tot["platforms"])
    months = (bs["own"].get("Cash", 0.0) / ess) if (ess and cash_known) else None
    prot = [p for p in tot["platforms"] if p.get("limit") and p["kind"] != "card" and p["total"] > p["limit"] * 0.9]
    tiles.append({"key": "cash", "title": "Cash", "go": "settings",
                  "level": "red" if any(p["total"] > p["limit"] for p in prot) else
                  "amber" if (prot or (months is not None and months < 3)) else "green" if bs["own"].get("Cash") else "none",
                  "value": bs["own"].get("Cash"),
                  "lines": [f"{months:.1f} months of essentials" if months is not None else
                            "Waiting for an exchange rate: press Refresh" if not cash_known else "Essentials not entered",
                            (f"{len(prot)} account{'s' if len(prot) != 1 else ''} near a protection limit" if prot
                             else "Every account within its protection limit")]
                  + ([f"Includes {narrative._money(bs['cash_abroad'])} held abroad"] if bs["cash_abroad"] else [])})
    if tb["budget"]:
        try:
            from ..budget import engine as budget_engine
            tiles.append(budget_engine.tile())
        except Exception as e:
            db.log("overall.budget", str(e))
    big = narrative.big_picture(market, pb, exp, alloc, tot, texp)
    big["you"] = _your_plan_words(bs, ret, tiles)
    main_sigs = [r for r in pb["signals"] if r["group"] == main]
    return {"balance": bs, "history": history(), "tiles": tiles, "this_year": this_year(ret, pb),
            "big_picture": big, "tabs": tb, "warnings": warns[:6], "setup": setup(bs),
            "market": {"regime": market["regime"], "label": market["label"], "gauge": market["gauge"],
                       "watch": w, "groups": market["groups"],
                       "lights": [{k: x.get(k) for k in ("key", "title", "level", "words", "group")}
                                  for x in market["lights"] if x["group"] == main]},
            "exposure": {"ai_pct": exp["ai_pct"], "ai_value": exp["ai_value"], "unknown": len(exp["unknown"])},
            "watch_exposure": {"pct": texp.get("ai_pct") if main == "ai" else texp.get("pct"),
                               "value": texp.get("ai_value") if main == "ai" else texp.get("value"),
                               "unknown": len(texp.get("unknown") or [])},
            "playbook": {"ai_firing": sum(1 for r in pb["signals"] if r["group"] == "ai" and r["firing"]),
                         "main_firing": sum(1 for r in main_sigs if r["firing"]), "main_of": len(main_sigs)}}



def setup(bs: dict | None = None) -> dict:
    """What has been set up so far, for the checklist on a new copy's Overall screen."""
    from . import builder
    tb = tabs()
    prog = builder.progress()
    parts = [p for p in prog["parts"] if p["key"] != "holdings"]
    s = retirement.settings()
    steps = [
        {"key": "review", "title": "Your plan review",
         "done": bool(prog.get("applied")) or all(p["done"] == p["of"] for p in parts),
         "detail": f"{sum(p['done'] for p in parts)} of {sum(p['of'] for p in parts)} questions answered"
                   + (", plan in use" if prog.get("applied") else ""), "go": "plan"},
        {"key": "platforms", "title": "Where you invest and save",
         "done": bool(db.scalar("SELECT COUNT(*) FROM platforms WHERE provider<>'sample' "
                                "AND IFNULL(institution,'')<>'sample'", (), 0)),
         "detail": f"{db.scalar('SELECT COUNT(*) FROM platforms', (), 0)} platforms and accounts", "go": "import"},
    ]
    if tb["mortgage"]:
        steps.append({"key": "mortgage", "title": "Your mortgage",
                      "done": bool(db.scalar("SELECT COUNT(*) FROM mortgages WHERE IFNULL(notes,'')<>'sample'", (), 0)),
                      "detail": "The balance, rate and when the fixed rate ends", "go": "mortgage"})
    if tb["retirement"]:
        steps.append({"key": "pensions", "title": "Your pensions",
                      "done": bool(db.scalar("SELECT COUNT(*) FROM pensions WHERE IFNULL(notes,'')<>'sample'", (), 0)),
                      "detail": f"{db.scalar('SELECT COUNT(*) FROM pensions', (), 0)} added", "go": "pensions"})
        steps.append({"key": "retirement", "title": "When you'd like to stop, and what you spend",
                      "done": not retirement.missing(s, {}), "detail": "The basics the year-by-year plan needs",
                      "go": "retirement"})
    steps.append({"key": "home", "title": "Your home",
                  "done": bool(db.scalar("SELECT COUNT(*) FROM assets WHERE IFNULL(notes,'')<>'sample'", (), 0))
                  or bool(db.scalar("SELECT COUNT(*) FROM mortgages WHERE property_value IS NOT NULL", (), 0)),
                  "detail": "What it's worth, for net worth and inheritance tax", "go": "settings"})
    return {"steps": steps, "done": sum(1 for x in steps if x["done"]), "of": len(steps)}


def _your_plan_words(bs: dict, ret: dict | None, tiles: list[dict]) -> str:
    """The third paragraph of the big picture: the person's own money and plan. Amounts
    are wrapped in [[ ]] so "Hide amounts" blurs them like every other figure."""
    m = narrative._money
    parts = []
    if bs["total_own"] or bs["total_owe"]:
        parts.append(f"You own {m(bs['total_own'])} and owe {m(bs['total_owe'])}, so your net worth is "
                     f"{m(bs['net'])}.")
    else:
        parts.append("Nothing has been added yet.")
    h = history()
    if len(h) >= 2:
        month_ago = (dt.date.today() - dt.timedelta(days=30)).isoformat()
        then = next((v for d, v in reversed(h) if d <= month_ago), None)
        if then:
            parts.append(f"That is {'up' if bs['net'] >= then else 'down'} {m(abs(bs['net'] - then))} on a month ago.")
    if bs["promised"]:
        parts.append(f"On top of that, pensions promise {m(sum(p['yearly'] for p in bs['promised']))} a year, "
                     "which isn't counted as money you own.")
    if ret and ret.get("ready"):
        pl = ret["plan"]
        parts.append("On your plan's assumptions the money lasts to the end of the plan." if pl["lasts"] else
                     f"On your plan's assumptions the money runs short at about {int(pl['runs_out_at'])}; "
                     "the Retirement tab shows what would change that.")
    red = [t for t in tiles if t["level"] == "red"]
    if red:
        parts.append("Worth a look first: " + ", ".join(t["title"].lower() for t in red) + ".")
    parts.append("Anything looking ahead is in today's money and is arithmetic on assumptions, not a forecast.")
    return " ".join(parts)
