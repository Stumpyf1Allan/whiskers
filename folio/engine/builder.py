"""The plan builder: investing questions only, a view on each theme in the person's own
words, and a plan shaped by those answers rather than by a fixed recipe.

Five short steps: you and this money, risk, how hands-on, your views, what you hold.
Anything about retirement is asked in the Retirement section instead; when that section is
on, the builder reads from it (how long until the money is needed, how much of the
essentials guaranteed income covers) and asks none of it again.

How much to hold in shares comes from three tests (Bogleheads, after Larry Swedroe): the
risk a person is *willing* to take, the risk they are *able* to take, and the risk they
*need* to take. The plan uses the lower of willing and able, as the FCA expects advisers
to (FG11/05), and if the need is lower still it says so. It never raises risk to meet a
need.

The shape then follows the answers:

* How hands-on someone is sets the size of the core (funds only: a big core; enjoys
  picking: a smaller core, more sleeves and room for single companies).
* How strongly they believe in each theme sizes it, within limits set by the risk they
  can take and by how hands-on they are.
* What they worry about chooses the defences: a bubble, gold and cash; inflation,
  index-linked gilts; rising rates, short-dated gilts; a crash, cash for the ladder.
* "Ride it, with a parachute" keeps a real stake and agrees the protections in advance:
  a cap counting what funds hold, a trim on the biggest winners, a step to take when the
  theme's warning lights turn, and a defensive sleeve to step into.

With a plan already in Whiskers it *reviews* that plan against the answers, one suggestion
at a time, each with its reason, and changes nothing that the answers don't call for: a
personal plan's own numbers stand unless the person's own answers contradict them. A
fresh plan is built only when asked for. For a fully bespoke plan it writes a brief to
hand to Claude, and checks the plan file that comes back before anything is loaded.

A starting point built from published research and common practice, not advice. It names
kinds of investment, never particular funds.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import threading

from .. import config, db
from . import (allocation, classify, mortgage as mort, playbook, portfolio, retirement, sections,
               signals, themes, xray)

FORMAT = 2

# ---------------------------------------------------------------------------- the questions

STEPS = [
    {"key": "you", "title": "You and this money",
     "intro": "What this money is for and when it will be needed. Questions about retirement itself live in "
              "the Retirement section."},
    {"key": "risk", "title": "Risk",
     "intro": "How you would feel and act when markets fall. There are no right answers; the honest one is "
              "the useful one."},
    {"key": "hands", "title": "How hands-on",
     "intro": "How much of this you want to do yourself. It decides the size of the core and the room for "
              "themes and single companies."},
    {"key": "views", "title": "Your views",
     "intro": "What you believe in, what worries you, and what you want to do about each, in your own words. "
              "Your words become the reasons in your plan."},
    {"key": "holdings", "title": "What you hold",
     "intro": "The X-Ray: what your investments really contain, looking through funds. Then choose how to "
              "use your answers."},
]


def _opts(*pairs):
    return [[k, v] for k, v in pairs]


Q = [
    # ---- 1. you and this money
    {"id": "need_when", "step": "you", "kind": "one", "from": "retirement",
     "text": "When will you start spending from this money?",
     "options": _opts(("now", "I'm already spending from it"), ("under5", "Within 5 years"),
                      ("5to10", "In 5 to 10 years"), ("10to20", "In 10 to 20 years"),
                      ("over20", "More than 20 years away")),
     "why": "Money needed soon has little time to recover from a fall, so less of it belongs in shares."},
    {"id": "draw_rate", "step": "you", "kind": "one", "show_if": {"need_when": ["now", "under5"]}, "from": "retirement",
     "text": "Once you draw on it, roughly how much a year will you take out?",
     "options": _opts(("2", "About 2% of it"), ("3", "About 3%"), ("4", "About 4%"), ("5", "5% or more")),
     "why": "Sets how much is kept in cash, so a fall never forces a sale. Research puts the highest safe "
            "starting rate at about 3.9% a year over 30 years."},
    {"id": "soon", "step": "you", "kind": "money", "text": "Is any of it needed for something big within five years?",
     "hint": "A car, a new roof, help for family. Leave it blank if not.",
     "why": "Money needed within five years is kept out of shares."},
    {"id": "guaranteed", "step": "you", "kind": "one", "from": "retirement",
     "text": "In retirement, how much of your essential spending will guaranteed income cover?",
     "hint": "The State Pension, a final-salary or career-average pension such as the NHS scheme, an annuity.",
     "options": _opts(("most", "Most or all of it"), ("half", "About half"), ("little", "Little or none"),
                      ("unsure", "Not sure")),
     "why": "A secure pension behaves like a large holding of bonds, so the rest can carry more risk."},
    {"id": "emergency", "step": "you", "kind": "one",
     "text": "Outside this money, do you have savings for emergencies, at least three months of spending?",
     "options": _opts(("yes", "Yes"), ("no", "Not yet")),
     "why": "A cushion in easy-access savings comes before investing."},
    {"id": "income_pref", "step": "you", "kind": "one", "text": "Should this money pay you an income?",
     "options": _opts(("growth", "No: growth is fine"), ("some", "Some income would be nice"),
                      ("income", "Yes: I want a regular income from it"))},
    {"id": "age_band", "step": "you", "kind": "one", "from": "retirement", "text": "How old are you?",
     "options": _opts(("under40", "Under 40"), ("40to54", "40 to 54"), ("55to64", "55 to 64"),
                      ("65to74", "65 to 74"), ("75plus", "75 or over")),
     "why": "Used only to suggest which of Whiskers' sections would suit you."},
    {"id": "home", "step": "you", "kind": "one", "from": "mortgage", "text": "Do you have a mortgage?",
     "options": _opts(("yes", "Yes"), ("no", "No")),
     "why": "Used only to suggest which of Whiskers' sections would suit you."},

    # ---- 2. risk
    {"id": "fall", "step": "risk", "kind": "one",
     "text": "If your investments fell by a third within a year, what would you most likely do?",
     "options": _opts(("sell", "Sell to stop the losses"), ("worry", "Worry, but hold on"),
                      ("hold", "Hold on without much worry"), ("buy", "Buy more while prices are low"))},
    {"id": "did", "step": "risk", "kind": "one", "text": "What did you actually do when markets fell in 2020 or 2022?",
     "options": _opts(("sold", "I sold some or all"), ("held", "I held on"), ("bought", "I bought more"),
                      ("none", "I wasn't invested then")),
     "why": "What people did in a real fall predicts the next one better than what they say they'd do."},
    {"id": "experience", "step": "risk", "kind": "one", "text": "How long have you been invested through ups and downs?",
     "options": _opts(("new", "I'm new to it"), ("few", "A few years"), ("long", "Ten years or more, including a big fall"))},
    {"id": "prefer", "step": "risk", "kind": "one", "text": "Which would you rather have?",
     "options": _opts(("steady", "Small, steady growth"), ("balanced", "Better growth, with some ups and downs"),
                      ("growth", "The best long-run growth, accepting big swings"))},

    # ---- 3. how hands-on
    {"id": "hands", "step": "hands", "kind": "one", "text": "How hands-on do you want to be?",
     "options": _opts(("funds", "Funds only: a few index funds, checked now and then"),
                      ("few", "Funds, plus a few themes and companies I believe in"),
                      ("enjoy", "I enjoy picking: themes, sectors and single companies")),
     "why": "Sets the core: the more you want to choose, the smaller the core and the more room for your own "
            "choices."},
    {"id": "time", "step": "hands", "kind": "one", "text": "How much time a month do you want to give it?",
     "options": _opts(("little", "Under an hour"), ("some", "A few hours"), ("lots", "More: I enjoy it")),
     "why": "A plan with many sleeves needs looking after; under an hour a month suits a simpler one."},

    # ---- 4. your views (the theme cards are their own kind)
    {"id": "views", "step": "views", "kind": "views", "text": "The themes"},
    {"id": "worries", "step": "views", "kind": "many", "text": "Which of these worry you most about markets?",
     "options": _opts(("bubble", "A bubble bursting"), ("crash", "A crash in general"), ("recession", "A recession"),
                      ("inflation", "Inflation"), ("rates", "Interest rates rising"), ("uk", "The UK economy"),
                      ("rand", "The rand"), ("none", "Nothing in particular")),
     "why": "Each worry chooses a defence: a bubble, gold and cash; inflation, index-linked gilts; rising rates, "
            "short-dated gilts; a crash, cash to buy with."},
    {"id": "avoid", "step": "views", "kind": "many", "text": "Anything you'd rather not own?",
     "options": _opts(("tobacco", "Tobacco"), ("weapons", "Weapons"), ("fossil", "Fossil fuels"),
                      ("gambling", "Gambling"), ("none", "No preference"))},
]
BY_ID = {q["id"]: q for q in Q}

ACTIONS = {
    "avoid": "Avoid it",
    "little": "Hold a little",
    "ride": "Ride it",
    "parachute": "Ride it, with a parachute",
    "dip": "Wait for a fall to buy",
}
ACTION_ABOUT = {
    "avoid": "Left out of your own choices. A world index fund still holds a little of most things.",
    "little": "A small slice: enough to notice, too small to hurt.",
    "ride": "A real stake, sized by how strongly you believe in it.",
    "parachute": "A real stake, with protections agreed now: a cap counting what funds hold, a trim on the "
                 "biggest winners, a step to take when its warning lights turn, and a defensive sleeve to step into.",
    "dip": "A small starter now, and a rule to buy more after a big fall.",
}

#: The themes a person can take a view on, in the order the cards are shown.
CARD_THEMES = ["ai", "healthcare", "industrials", "consumer", "financials", "property", "oil", "gold",
               "metals", "defence", "uk", "em", "smallcaps", "speculative", "crypto"]
SLEEVE_NAME = {"ai": "Technology & AI", "healthcare": "Healthcare", "industrials": "Industrials",
               "consumer": "Consumer brands", "financials": "Financials", "property": "Property and infrastructure",
               "oil": "Energy", "gold": "Gold", "metals": "Metals and miners", "defence": "Defence",
               "uk": "UK companies", "em": "Emerging markets", "smallcaps": "Smaller companies",
               "speculative": "Speculative", "crypto": "Crypto"}
#: Themes an avoid answer rules out.
AVOID_THEMES = {"fossil": ["oil"], "weapons": ["defence"], "tobacco": [], "gambling": []}

#: How big a theme gets for each level of belief, as a share of the part in shares,
#: before how hands-on someone is scales it.
BELIEVE_SIZE = {1: 1.0, 2: 2.5, 3: 5.0, 4: 9.0, 5: 15.0}
HANDS = {
    # mult: scales BELIEVE_SIZE; core_min: least of the shares part kept in the core;
    # cap: most any one theme gets (% of everything); little: a small slice (% of everything);
    # single: (trigger, back to) for a trim on any one company, None with funds only.
    "funds": {"mult": 0.35, "core_min": 0.80, "cap": 6.0, "little": 1.0, "single": None},
    "few": {"mult": 0.8, "core_min": 0.50, "cap": 15.0, "little": 1.5, "single": (7.0, 5.0)},
    "enjoy": {"mult": 1.5, "core_min": 0.20, "cap": 30.0, "little": 2.0, "single": (10.0, 8.0)},
}
#: Whatever the conviction, these stay small (% of everything).
SPECIAL_CAP = {"crypto": 3.0, "speculative": 5.0}
#: Gold sits beside bonds and cash rather than in shares.
NOT_SHARES = {"gold"}

SOURCES = [
    ["Bogleheads: the ability, willingness and need to take risk", "https://www.bogleheads.org/wiki/Risk_tolerance"],
    ["FCA FG11/05: establishing the risk a customer is willing and able to take",
     "https://www.fca.org.uk/publication/finalised-guidance/fsa-fg11-05.pdf"],
    ["Vanguard: target-date glide path (about 90% shares 25 years out, 50% at retirement)",
     "https://institutional.vanguard.com/content/dam/inst/iig-transformation/insights/pdf/2025/231657-02_TDF_PTDF_OTH-TRIGT-Research.pdf"],
    ["Morningstar (Christine Benz): the bucket approach to retirement portfolios",
     "https://www.morningstar.com/retirement/take-this-simple-step-runup-retirement"],
    ["Morningstar: What's a safe retirement withdrawal rate for 2026? (3.9% over 30 years)",
     "https://www.morningstar.com/retirement/whats-safe-retirement-withdrawal-rate-2026"],
    ["Bogleheads: rebalancing and the 5/25 rule", "https://www.bogleheads.org/wiki/Rebalancing"],
    ["Bogleheads: investment policy statement", "https://www.bogleheads.org/wiki/Investment_policy_statement"],
    ["Erb & Harvey: The Golden Dilemma (gold as an inflation hedge)", "https://www.nber.org/papers/w18706"],
    ["Morningstar: Portfolio X-Ray", "https://www.morningstar.co.uk/uk/xray/overview"],
]


# ---------------------------------------------------------------------------- answers

def _state() -> dict:
    st = db.get_meta("builder", {}) or {}
    if st.get("v") != 2:
        # The Mega build's plan review kept different answers; none of them carry over.
        st = {"v": 2}
    st.setdefault("answers", {})
    st.setdefault("at", {})
    st.setdefault("mood", {})
    return st


def _band(years: float | None) -> str | None:
    if years is None:
        return None
    return ("now" if years <= 0.25 else "under5" if years < 5 else "5to10" if years < 10 else
            "10to20" if years < 20 else "over20")


def _age_band(age: float | None) -> str | None:
    if age is None:
        return None
    return ("under40" if age < 40 else "40to54" if age < 55 else "55to64" if age < 65 else
            "65to74" if age < 75 else "75plus")


def facts(deep: bool = True) -> dict:
    """What Whiskers already knows from the switched-on sections, so the builder never asks it
    twice: the Retirement section's age, stopping age and guaranteed income, and whether the
    Mortgage section holds a mortgage. `deep` adds the growth the retirement plan needs,
    which takes a few dozen runs of it: wanted for a plan, not for saving an answer."""
    sec = sections.on()
    out: dict = {"retirement_on": sec["retirement"], "mortgage_on": sec["mortgage"], "derived": {}, "ready": False}
    if sec["retirement"]:
        s = retirement.settings()
        dob = retirement.dob_of(s)
        today = dt.date.today()
        if dob:
            out["age"] = retirement.age_on(dob, today)
            out["derived"]["age_band"] = _age_band(out["age"])
            if s.get("stop_age"):
                out["years_to_stop"] = float(s["stop_age"]) - out["age"]
                out["derived"]["need_when"] = _band(out["years_to_stop"])
        try:
            data = retirement.gather(s)
            if not retirement.missing(s, data):
                base = retirement.project(s, data)
                fl = base.get("income_floor") or {}
                out["covers"] = fl.get("covers")
                if out["covers"] is not None:
                    out["derived"]["guaranteed"] = ("most" if out["covers"] >= 0.9 else
                                                    "half" if out["covers"] >= 0.4 else "little")
                out.update(ready=True, lasts=base["lasts"], runs_out_at=base.get("runs_out_at"),
                           horizon=base.get("horizon"))
                rows = base.get("rows") or []
                if out.get("years_to_stop") is not None and out["years_to_stop"] <= 0.25 and rows:
                    r0 = rows[0]
                    pot = (base.get("at_stop") or {}).get("liquid") or 0.0
                    drawn = r0["from_isa"] + r0["from_gia"] + r0["from_pension"] + r0["from_cash"]
                    if pot:
                        out["draw_rate"] = r = drawn / pot * 100
                        out["derived"]["draw_rate"] = "2" if r < 2.5 else "3" if r < 3.5 else "4" if r < 4.5 else "5"
                if deep:
                    n = retirement.need(s, data)
                    out.update(need_share=n.get("growth_share"), need_real=n.get("real"),
                               need_words=n.get("words"))
        except retirement.RetirementError:
            pass
    if sec["mortgage"]:
        out["derived"]["home"] = "yes" if mort.all_mortgages() else "no"
    return out


def answers(f: dict | None = None) -> dict:
    """Every answer, with the ones a switched-on section knows filled in from there."""
    st = _state()
    out = dict(st["answers"])
    out.setdefault("views", {})
    out.setdefault("custom", [])
    f = facts(deep=False) if f is None else f
    for k, v in (f.get("derived") or {}).items():
        if v is not None:
            out[k] = v
    return out


def _clean_view(v: dict) -> dict:
    out = {}
    for k in ("believe", "worry"):
        if v.get(k) not in (None, ""):
            try:
                out[k] = max(1, min(5, int(v[k])))
            except (TypeError, ValueError):
                pass
    if v.get("action") in ACTIONS:
        out["action"] = v["action"]
    for k in ("why", "change"):
        if isinstance(v.get(k), str):
            out[k] = v[k].strip()[:1200]
    return out


#: Answers arrive a click at a time, and the server answers requests side by side: without
#: this, two quick clicks on one card could each read the old answers and the second would
#: write back over the first.
_save_lock = threading.Lock()


def save_answers(incoming: dict) -> dict:
    with _save_lock:
        _save(incoming)
    return progress(facts(deep=False))


def _save(incoming: dict) -> None:
    """Store answers as they are given, dated, with the market's mood that day for the risk
    questions: people answer them more boldly in a rising market, and a later review should
    know."""
    st = _state()
    today = db.today()
    mood = None
    if any((BY_ID.get(k) or {}).get("step") == "risk" for k in (incoming or {})):
        try:
            mood = signals.evaluate()["label"]
        except Exception:
            mood = None
    a = st["answers"]
    for qid, value in (incoming or {}).items():
        if qid == "views" and isinstance(value, dict):
            views = a.setdefault("views", {})
            for theme, v in value.items():
                if theme not in themes.LIBRARY or not isinstance(v, dict):
                    continue
                merged = dict(views.get(theme) or {})
                merged.update(_clean_view(v))
                for k in ("believe", "worry", "action"):
                    if k in v and v[k] in (None, ""):
                        merged.pop(k, None)
                views[theme] = merged
            st["at"]["views"] = today
            continue
        if qid == "custom" and isinstance(value, list):
            items = []
            for c in value[:8]:
                if isinstance(c, dict) and str(c.get("label") or "").strip():
                    items.append({"label": str(c["label"]).strip()[:40]} | _clean_view(c))
            a["custom"] = items
            st["at"]["custom"] = today
            continue
        if qid == "watch_main":
            a["watch_main"] = value if (value in themes.LIBRARY or value in (None, "", "auto")) else "auto"
            continue
        q = BY_ID.get(qid)
        if not q or q["kind"] == "views":
            continue
        if q["kind"] == "money":
            try:
                value = None if value in (None, "") else max(0.0, float(value))
            except (TypeError, ValueError):
                value = None
        elif q["kind"] == "one":
            if value not in [o[0] for o in q["options"]] and value is not None:
                continue
        elif q["kind"] == "many":
            allowed = {o[0] for o in q["options"]}
            value = [x for x in (value or []) if x in allowed]
        a[qid] = value
        st["at"][qid] = today
        if q["step"] == "risk" and mood:
            st["mood"][qid] = mood
    st["updated"] = today
    db.set_meta("builder", st)


def _visible(q: dict, a: dict) -> bool:
    for k, allowed in (q.get("show_if") or {}).items():
        if a.get(k) not in allowed:
            return False
    return True


def progress(f: dict | None = None) -> dict:
    f = facts(deep=False) if f is None else f
    a = answers(f)
    steps = []
    for s in STEPS:
        if s["key"] == "holdings":
            continue
        qs = [q for q in Q if q["step"] == s["key"] and _visible(q, a) and q["kind"] != "views"]
        done = sum(1 for q in qs if a.get(q["id"]) not in (None, "", []))
        if s["key"] == "views":
            qs = qs + [{"id": "views"}]
            done += 1 if any((v or {}).get("action") for v in (a.get("views") or {}).values()) else 0
        steps.append({"key": s["key"], "title": s["title"], "done": done, "of": len(qs)})
    st = _state()
    return {"steps": steps, "updated": st.get("updated"), "applied": st.get("applied"),
            "complete": all(p["done"] == p["of"] for p in steps)}


def _theme_cards(pos: list[dict], tot: dict) -> list[dict]:
    """One card per theme: what it is, how much of the money rides on it today, and which of
    the person's sleeves hold it, so a view is taken knowing where things stand."""
    exps = {e["theme"]: e for e in themes.all_exposures(pos, tot)}
    sleeves = allocation.sleeves()
    out = []
    for key in CARD_THEMES:
        t = themes.LIBRARY[key]
        e = exps.get(key) or {}
        mine = [{"name": s["name"], "target": s["target"]} for s in sleeves if sleeve_theme(s) == key]
        out.append({"key": key, "label": t["label"], "title": t["title"], "about": t["about"],
                    "pct": e.get("pct"), "value": e.get("value"), "coverage": e.get("coverage"),
                    "sleeves": mine, "lights": len(themes.lights_for(key)),
                    "held": bool(mine) or (e.get("pct") or 0.0) >= 0.05})
    return out


def questions() -> dict:
    f = facts(deep=False)
    a = answers(f)
    st = _state()
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    return {"steps": STEPS, "questions": [dict(q, visible=_visible(q, a)) for q in Q], "answers": a,
            "at": st["at"], "mood": st["mood"], "progress": progress(f), "facts": _public_facts(f),
            "actions": ACTIONS, "action_about": ACTION_ABOUT, "cards": _theme_cards(pos, tot),
            "has_plan": bool(allocation.sleeves()), "watch": themes.watch()}


def _public_facts(f: dict) -> dict:
    keep = ("retirement_on", "mortgage_on", "derived", "ready", "age", "years_to_stop", "covers", "lasts",
            "runs_out_at", "need_share", "need_words", "draw_rate")
    return {k: f.get(k) for k in keep if k in f}


# ---------------------------------------------------------------------------- risk

def willingness(fall: str | None, experience: str | None, prefer: str | None) -> float:
    """0 to 1, weighted towards how someone says they would react: that is what decides
    whether a plan survives its first bad year."""
    f = {"sell": 0.0, "worry": 0.33, "hold": 0.67, "buy": 1.0}.get(fall, 0.67)
    e = {"new": 0.0, "few": 0.5, "long": 1.0}.get(experience, 0.5)
    p = {"steady": 0.0, "balanced": 0.5, "growth": 1.0}.get(prefer, 0.5)
    return 0.5 * f + 0.2 * e + 0.3 * p


def _half(x: float) -> float:
    return round(x * 2) / 2


def risk_profile(a: dict, f: dict) -> dict:
    """Willing, able and need, each with its reasoning."""
    why = []
    fall = a.get("fall") or "hold"
    if a.get("did") == "sold" and fall in ("hold", "buy", "worry"):
        why.append("You sold in a real fall, so the plan goes by that rather than by a bolder answer now.")
        fall = "sell"
    w = willingness(fall, a.get("experience") or "few", a.get("prefer") or "balanced")
    willing = 30.0 + 70.0 * w
    if a.get("did") == "bought":
        willing = min(100.0, willing + 5)
    need_when = a.get("need_when")
    drawing = need_when == "now"
    able = {"over20": 90.0, "10to20": 80.0, "5to10": 60.0, "under5": 45.0, "now": 50.0}.get(need_when, 70.0)
    if drawing:
        why.append("You are spending from this money, so the plan follows the bucket approach: cash for the "
                   "next couple of years' withdrawals, bonds for several more, shares for the rest.")
    elif need_when == "under5":
        why.append("Money needed within five years has little time to recover from a fall, so less of it "
                   "is in shares.")
    elif need_when in ("over20", "10to20"):
        why.append("With ten years or more before you need it, the plan starts where target-date funds do "
                   f"at that distance, about {able:.0f}% in shares.")
    g = a.get("guaranteed")
    if g == "most":
        able += 10
        why.append("Guaranteed income covers most of your essentials, so this money can carry more risk: a "
                   "secure pension behaves like a large bond holding.")
    elif g == "little":
        able -= 5
        why.append("Guaranteed income covers little of your essentials, so the plan leans a little safer.")
    if a.get("emergency") == "no":
        able -= 5
        why.append("There are no emergency savings outside this money yet: building them comes first.")
    able = max(10.0, min(100.0, able))
    growth = _half(min(willing, able))
    if growth >= 95:
        growth = 97.0
    if willing < able:
        why.append(f"Your answers on how you'd feel in a fall put you at about {willing:.0f}% in shares at "
                   "most. The plan never asks you to take more risk than you're willing to.")
    else:
        why.append(f"Your situation can carry about {able:.0f}% in shares; you're willing to take at least "
                   "that, so the plan stops there.")
    need = f.get("need_share")
    alternative = short = None
    if f.get("ready"):
        if f.get("need_real") is None:
            short = ("Even high returns wouldn't make your retirement plan last: the levers in the Retirement "
                     "section matter more than risk.")
        elif need is not None and need < growth - 10:
            alternative = {"growth": max(float(need), 20.0),
                           "words": f"Your retirement plan needs only about {need:.0f}% in shares on its assumptions. "
                                    "Taking less risk than you can is a reasonable choice once there is enough: "
                                    "extra risk then buys little you need."}
        elif need is not None and need > growth + 5:
            short = (f"Your retirement plan needs about {need:.0f}% in shares on its assumptions, more than the "
                     f"{growth:.0f}% this plan will take. Rather than raise the risk, look at the levers in the "
                     "Retirement section.")
    return {"willing": round(willing), "able": round(able), "need": need, "growth": growth, "drawing": drawing,
            "need_status": ("unknown" if not f.get("ready") else "beyond" if f.get("need_real") is None else "known"),
            "need_words": f.get("need_words"), "why": why, "alternative": alternative, "shortfall": short,
            "willingness": round(w, 2)}


# ---------------------------------------------------------------------------- sleeves and themes

def sleeve_theme(s: dict) -> str | None:
    """The theme a sleeve rides on: set on the sleeve, or read from its name."""
    if s.get("theme") and s["theme"] in themes.LIBRARY:
        return s["theme"]
    return themes._sleeve_theme(s.get("name"))


def sleeve_kind(s: dict) -> str:
    """core, cash, bonds, gold or a theme key (or 'other')."""
    if s.get("is_cash"):
        return "cash"
    name = (s.get("name") or "").lower()
    if re.search(r"\b(core|global|world|all[- ]world|tracker|index)\b", name) and not sleeve_theme(s):
        return "core"
    t = sleeve_theme(s)
    if t in ("rates", "inflation") or re.search(r"gilt|bond|fixed income|treasur", name):
        return "bonds"
    if t == "gold":
        return "gold"
    if re.search(r"defensive", name):
        return "defensive"
    if re.search(r"\bcash\b|money market", name):
        return "cash"
    return t or "other"


def _is_safe(kind: str) -> bool:
    return kind in ("cash", "bonds", "gold", "defensive")


def _views(a: dict) -> dict:
    return {k: v for k, v in (a.get("views") or {}).items() if k in themes.LIBRARY and isinstance(v, dict)}


def _avoided(a: dict) -> set:
    out = set()
    for k in a.get("avoid") or []:
        out.update(AVOID_THEMES.get(k, []))
    for k, v in _views(a).items():
        if v.get("action") == "avoid":
            out.add(k)
    return out


def _hands(a: dict) -> str:
    h = a.get("hands") if a.get("hands") in HANDS else "few"
    if a.get("time") == "little" and h == "enjoy":
        h = "few"
    return h


def theme_size(key: str, v: dict, a: dict, growth: float) -> float:
    """What a theme gets on its own, before everything is fitted together (% of everything)."""
    h = HANDS[_hands(a)]
    action = v.get("action")
    if action in (None, "avoid"):
        return 0.0
    if action in ("little", "dip"):
        size = h["little"]
    else:
        b = v.get("believe") or 3
        size = BELIEVE_SIZE[b] * h["mult"] * growth / 100
        if action == "ride" and (v.get("worry") or 0) >= 4:
            size *= 0.7
    size = min(size, h["cap"], SPECIAL_CAP.get(key, 100.0))
    return max(0.5, _half(size)) if size > 0 else 0.0


def _defences(a: dict) -> dict:
    w = set(a.get("worries") or []) - {"none"}
    views = _views(a)
    parachutes = [k for k, v in views.items() if v.get("action") == "parachute"]
    return {"gold": bool(w & {"bubble", "crash"}) or bool(parachutes) or
            any(v.get("action") in ("ride", "parachute") and k == "gold" for k, v in views.items()),
            "linkers": "inflation" in w, "short_gilts": "rates" in w, "cash_ladder": "crash" in w,
            "parachutes": parachutes, "worries": sorted(w)}


def fresh_plan(a: dict, risk: dict, f: dict, invested: float) -> dict:
    """A whole plan from the answers: for somebody with no plan yet, or who asks to start again."""
    why = []
    growth = risk["growth"]
    views = _views(a)
    avoided = _avoided(a)
    h = HANDS[_hands(a)]
    d = _defences(a)
    # ---- the safe part: cash, gold, bonds
    safe = 100.0 - growth
    rate = {"2": 2.0, "3": 3.0, "4": 4.0, "5": 5.0}.get(a.get("draw_rate") or "", 4.0)
    if risk["drawing"] or a.get("need_when") == "under5":
        cash = min(safe, max(4.0, min(10.0, 2 * rate)))
        why.append(f"About two years of withdrawals ({cash:g}% of everything) in cash, so a fall never forces a sale"
                   + ("." if risk["drawing"] else ", ready for when you start drawing on it."))
        if rate >= 5:
            why.append("Taking 5% or more a year is above what research finds sustainable: Morningstar's 2025 "
                       "study puts the highest safe starting rate at 3.9% for a 30-year retirement.")
    else:
        cash = min(safe, max(3.0, min(8.0, _half(0.2 * safe))))
    if d["cash_ladder"] and not risk["drawing"] and cash < 5.0 <= safe:
        cash = 5.0
        why.append("A crash worries you, so 5% is kept in cash: money your ladder can put to work after a fall, "
                   "a third at a time.")
    soon = float(a.get("soon") or 0.0)
    if soon and invested:
        extra = min(30.0, _half(soon / invested * 100))
        if extra:
            cash += extra
            growth = max(0.0, growth - extra)
            why.append(f"{extra:g}% more is kept as cash for the £{soon:,.0f} needed within five years.")
    gold = 0.0
    gold_view = views.get("gold") or {}
    if "gold" not in avoided and (d["gold"] or gold_view.get("action") in ("little", "ride", "parachute", "dip")):
        want = theme_size("gold", gold_view, a, 100.0) if gold_view.get("action") in ("ride", "parachute") else 0.0
        floor = 3.0 if d["gold"] else h["little"]
        gold = min(max(want, floor), max(0.0, _half(0.5 * max(0.0, safe - cash))))
        if gold:
            reason = []
            if set(d["worries"]) & {"bubble", "crash"}:
                reason.append("a bubble or a crash worries you")
            if d["parachutes"]:
                reason.append("a parachute needs somewhere to land")
            if gold_view.get("action") in ("ride", "parachute", "little", "dip"):
                reason.append("you believe in it")
            why.append(f"{gold:g}% in gold, because " + " and ".join(reason or ["it steadies a plan in a fall"]) +
                       ": over long periods it has tended to hold up when shares fall hard, though it is "
                       "an unreliable guard against inflation.")
    bonds = max(0.0, 100.0 - growth - cash - gold)
    linked = 0.0
    if bonds >= 4 and (d["linkers"] or risk["drawing"] or a.get("need_when") in ("under5", "5to10")):
        linked = _half(bonds * (0.5 if d["linkers"] else 0.35))
        why.append("Part of the bond money is index-linked gilts, which rise with inflation directly"
                   + (": inflation is one of your worries." if d["linkers"] else "."))
    gilts = _half(bonds - linked)
    gilt_name = "Short-dated gilts" if d["short_gilts"] else "Gilts"
    if d["short_gilts"] and gilts:
        why.append("Rising rates worry you, so the gilts are short-dated: they fall far less when rates rise, "
                   "and mature soon enough to be reinvested at the higher rate.")
    # ---- the shares part: themes by conviction, the core takes the rest
    sized = []
    for key in CARD_THEMES:
        if key in NOT_SHARES or key in avoided:
            continue
        v = views.get(key) or {}
        size = theme_size(key, v, a, growth)
        if size:
            sized.append([key, size, v.get("action")])
    for c in a.get("custom") or []:
        size = theme_size("custom", c, a, growth)
        if size:
            sized.append(["custom:" + c["label"], size, c.get("action")])
    room = growth * (1 - h["core_min"])
    total = sum(s[1] for s in sized)
    if total > room and total:
        fixed = sum(s[1] for s in sized if s[2] in ("little", "dip"))
        scale = max(0.0, room - fixed) / max(0.01, total - fixed)
        for s in sized:
            if s[2] not in ("little", "dip"):
                s[1] = max(0.5, _half(s[1] * scale))
        why.append(f"Your themes together would have taken more than {room:.0f}%; each was scaled back so the "
                   f"core keeps at least {h['core_min'] * 100:.0f}% of the part in shares.")
    income = 0.0
    if a.get("income_pref") == "income":
        income = _half(growth * 0.2)
        why.append(f"{income:g}% in a dividend income fund, for the regular income you asked for.")
    core = _half(growth - sum(s[1] for s in sized) - income)
    why.append({"funds": "You want funds only, so most of the shares part is a global index fund: one fund "
                         "holding thousands of companies across many countries.",
                "few": "A global index fund is the core, with room beside it for the themes you believe in.",
                "enjoy": "You enjoy picking, so the core is smaller and your themes get real room; the core still "
                         "holds the whole market underneath them."}[_hands(a)])
    sleeves = [{"name": "Global core index", "target": core, "kind": "core",
                "why": "The whole world's stock market in one fund: the part of the plan that needs no view."}]
    for key, size, action in sized:
        if key.startswith("custom:"):
            label = key.split(":", 1)[1]
            c = next((x for x in a.get("custom") or [] if x["label"] == label), {})
            sleeves.append({"name": label, "target": size, "kind": key, "why": c.get("why") or None,
                            "change": c.get("change") or None})
        else:
            v = views.get(key) or {}
            sleeves.append({"name": SLEEVE_NAME[key], "target": size, "theme": key, "kind": key,
                            "why": v.get("why") or None, "change": v.get("change") or None,
                            "ai_share": 100 if key == "ai" else 0})
    if income:
        sleeves.append({"name": "Dividend income", "target": income, "kind": "other"})
    if gold:
        sleeves.append({"name": "Gold", "target": gold, "theme": "gold", "kind": "gold", "ai_share": 0,
                        "why": gold_view.get("why") or "The defensive sleeve: steadier when shares fall hard.",
                        "change": gold_view.get("change") or None})
    if gilts > 0:
        sleeves.append({"name": gilt_name, "target": gilts, "kind": "bonds", "ai_share": 0})
    if linked > 0:
        sleeves.append({"name": "Index-linked gilts", "target": linked, "kind": "bonds", "ai_share": 0})
    sleeves.append({"name": "Cash", "target": _half(cash), "kind": "cash", "is_cash": True, "ai_share": 0})
    sleeves = [s for s in sleeves if s["target"] > 0 or s.get("is_cash")]
    diff = round(100.0 - sum(s["target"] for s in sleeves), 2)
    sleeves[0]["target"] = round(sleeves[0]["target"] + diff, 2)
    return {"sleeves": sleeves, "why": why}


def _typical_inside_core(theme: str) -> float:
    """How much of a world index fund rides on a theme, from the fund make-ups classify knows."""
    return float(classify.GLOBAL.get(theme, 0.0)) / 100


def _round_up5(x: float) -> float:
    return float(math.ceil(x / 5.0) * 5)


def _defensive_name(sleeves: list[dict], a: dict | None = None) -> str | None:
    """Where a parachute lands: a defensive sleeve, then gold; then cash before gilts for
    somebody worried about rising rates (which hit gilts too), gilts before cash otherwise."""
    by_kind = {}
    for s in sleeves:
        by_kind.setdefault(s.get("kind") or sleeve_kind(s), s["name"])
    rates = "rates" in ((a or {}).get("worries") or [])
    for k in ("defensive", "gold") + (("cash", "bonds") if rates else ("bonds", "cash")):
        if k in by_kind:
            return by_kind[k]
    return None


def _landing_for(sleeve: str, sleeves: list[dict], a: dict) -> str | None:
    """The defensive sleeve a theme's parachute lands in, never the theme's own sleeve (gold
    ridden with a parachute lands in cash, not in gold)."""
    others = [s for s in sleeves if s["name"] != sleeve]
    return _defensive_name(others, a)


def parachute(theme: str, sleeve: str, target: float, core: float, landing: str | None, a: dict,
              now_pct: float | None = None) -> list[dict]:
    """The protections "ride it, with a parachute" agrees in advance. The cap sits five points
    above what the plan means to hold, counting what a world index fund holds of the theme
    (or above what is held today, if that is more), rounded up to a five."""
    lights = len(themes.lights_for(theme))
    reds = max(1, math.ceil(lights / 2))
    planned = target + core * _typical_inside_core(theme)
    cap = _round_up5(max(planned, now_pct or 0.0) + 5)
    out = []
    if theme == "ai":
        out.append({"kind": "ai_cap", "trigger": cap,
                    "note": f"Parachute: keep money riding on AI, counting what funds hold, under {cap:g}%."})
    else:
        out.append({"kind": "exposure_cap", "subject": theme, "trigger": cap,
                    "note": f"Parachute: keep money riding on {themes.in_sentence(theme)}, counting what funds hold, "
                            f"under {cap:g}%."})
    if landing:
        out.append({"kind": "theme_step", "subject": theme, "trigger": reds, "target": 33, "sleeve": sleeve,
                    "into": landing,
                    "note": f"Parachute: when {reds} of {themes.in_sentence(theme)}'s {lights} warning lights are red, "
                            f"move a third of {sleeve} into {landing}."})
    single = HANDS[_hands(a)]["single"]
    if single:
        out.append({"kind": "any_company_cap", "trigger": single[0], "target": single[1], "basis": "true",
                    "note": f"Trim any one company back to {single[1]:g}% once it passes {single[0]:g}% of everything, "
                            "counting what funds hold: the biggest winners are trimmed, not sold."})
    return out


def dip_rule(theme: str, into: str, cash_sleeve: str, size: float, starter: float) -> dict | None:
    defs = themes.lights_for(theme)
    red = next((d["red"] for d in defs if d.get("kind") == "drawdown"), 0.20)
    fall = round(red * 100)
    add = max(1.0, _half(size - starter))
    return {"kind": "theme_dip", "subject": theme, "trigger": fall, "target": add, "sleeve": cash_sleeve,
            "into": into,
            "note": f"Waiting for a fall: when {themes.in_sentence(theme)} is {fall}% below its high, move {add:g} "
                    f"points from {cash_sleeve} into {into}."}


def watch_from_views(a: dict, pos: list[dict], tot: dict) -> dict:
    views = _views(a)
    care = []
    for k, v in sorted(views.items(), key=lambda kv: (kv[1].get("action") != "parachute",
                                                     -(kv[1].get("worry") or 0), -(kv[1].get("believe") or 0))):
        if v.get("action") == "avoid":
            continue
        if v.get("action") in ("parachute", "dip") or (v.get("worry") or 0) >= 4 or (
                v.get("action") in ("ride",) and (v.get("believe") or 0) >= 4):
            care.append(k)
    pinned = a.get("watch_main") if a.get("watch_main") in themes.LIBRARY else None
    if not pinned:
        para = [k for k in care if views[k].get("action") == "parachute"]
        if para:
            exps = {e["theme"]: e.get("pct") or 0.0 for e in themes.all_exposures(pos, tot)}
            pinned = max(para, key=lambda k: exps.get(k, 0.0))
    sug = themes.suggest(pos, tot, care, pinned)
    why = dict(sug["why"])
    for k in care:
        v = views[k]
        bits = []
        if v.get("action") == "parachute":
            bits.append("you ride it with a parachute, and its lights decide when the step applies")
        elif v.get("action") == "dip":
            bits.append("you're waiting for a fall to buy")
        if (v.get("worry") or 0) >= 4:
            bits.append(f"it worries you ({v['worry']} of 5)")
        if bits:
            why[k] = "Because " + " and ".join(bits) + "."
    return {"main": sug["main"], "themes": sug["themes"], "why": why,
            "titles": {t: themes.title(t) for t in sug["themes"]}, "note": sug["note"]}


def plans_text(a: dict, risk: dict, steps: list[dict], watch: dict) -> dict:
    main = watch.get("main")
    title = themes.in_sentence(main) if main else "markets"
    crash = ("Spend from the Cash sleeve. After good years, top it up from shares; after bad years, top it up "
             "from gilts and leave shares to recover. Don't sell shares in a fall."
             if risk["drawing"] else
             "Keep contributing as normal. Rebalance only when a sleeve leaves its band, using new money first. "
             "Put cash to work by the ladder, a third at a time, only if my holdings have actually fallen. "
             "Don't sell the core in a fall.")
    mine = [s for s in steps if s.get("kind") == "theme_step" and s.get("subject") == main]
    if mine:
        s = mine[0]
        theme_plan = (f"If {title} turns, take the step I agreed: when {s['trigger']:g} of its lights are red, move "
                      f"a third of {s['sleeve']} into {s['into']}. Re-read why I hold it and what would change my "
                      "mind. Keep the global core, and keep contributing.")
    else:
        theme_plan = (f"If {title} turns: check that sleeve against its band, rebalance with new money first, and "
                      "only sell if it is outside its band. Re-read why I own each company in it. Don't sell the "
                      "global core.")
    return {"crash": crash, "ai": theme_plan}


def _current_rules() -> list[dict]:
    return db.rows("SELECT * FROM rules WHERE enabled=1 ORDER BY id")


def _has_rule(rules: list[dict], kind: str, subject: str | None = None) -> bool:
    return any(r["kind"] == kind and (subject is None or (r["subject"] or "").lower() == subject.lower())
               for r in rules)


def _company_caps(xr: dict, rules: list[dict], a: dict) -> list[dict]:
    """A trim rule for each company held directly that is already past the limit for one
    company, unless a rule covers it: the Alphabet ratchet, for whoever holds a company like
    that. The trigger sits a little above where it is now and trims back two points, so the
    rule takes profits from a winner rather than forcing a sale today."""
    out = []
    if _has_rule(rules, "any_company_cap"):
        return out
    single = HANDS[_hands(a)]["single"] or (7.0, 5.0)
    for d in xr.get("biggest_companies", [])[:5]:
        if not xr.get("total") or not d["direct"] or len(out) >= 3:
            continue
        pct = d["true"] / xr["total"] * 100
        if pct >= single[0] and not _has_rule(rules, "company_cap", d["company"]):
            trig = _half(pct + 1.5)
            back = trig - 2
            out.append({"kind": "company_cap", "subject": d["company"], "trigger": trig, "target": back,
                        "basis": "true",
                        "note": f"Trim {d['company']} back to {back:g}% once it passes {trig:g}%, counting what "
                                "funds hold."})
    return out


# ---------------------------------------------------------------------------- the review

def _suggest(sid, kind, title, reason, change=None, ticked=False, group="plan"):
    return {"id": sid, "kind": kind, "title": title, "reason": reason, "change": change or {},
            "ticked": ticked, "group": group}


def review(a: dict, risk: dict, f: dict, xr: dict, pos: list[dict], tot: dict) -> dict:
    """The person's own plan against their own answers. Targets they chose stand unless an
    answer contradicts them; protections they asked for (a parachute, a dip to buy) are
    offered ready to tick."""
    cur = allocation.sleeves()
    for s in cur:
        s["kind"] = sleeve_kind(s)
    alloc = allocation.view(pos, tot)
    actual = {r["name"]: r["actual"] for r in alloc["sleeves"]}
    views = _views(a)
    avoided = _avoided(a)
    h = HANDS[_hands(a)]
    rules = _current_rules()
    out = []
    core = next((s for s in cur if s["kind"] == "core"), None)
    balancer = core or next((s for s in cur if s["kind"] == "cash"), None) or (max(cur, key=lambda s: s["target"]) if cur else None)
    bal = balancer["name"] if balancer else None
    by_theme: dict[str, list[dict]] = {}
    for s in cur:
        t = sleeve_theme(s)
        if t:
            by_theme.setdefault(t, []).append(s)
    growth_now = sum(s["target"] for s in cur if not _is_safe(s["kind"]))
    # ---- 1. your own words, always kept
    for k, v in views.items():
        for s in by_theme.get(k, [])[:1]:
            if (v.get("why") and v["why"] != (s.get("why") or "")) or (v.get("change") and v["change"] != (s.get("breakers") or "")):
                out.append(_suggest(f"words:{s['id']}", "words", f"Keep your reasons with {s['name']}",
                                    "In your own words, shown beside the sleeve and in your written plan, and next to "
                                    "the evidence when its lights turn.",
                                    {"sleeve": s["name"], "why": v.get("why") or None, "change": v.get("change") or None,
                                     "theme": k}, ticked=True, group="words"))
    # ---- 2. what the answers contradict
    for k in sorted(avoided):
        for s in by_theme.get(k, []):
            if s["target"] > 0 and bal and s["name"] != bal:
                out.append(_suggest(f"avoid:{s['id']}", "target", f"Wind down {s['name']}",
                                    f"You said you'd rather avoid {themes.in_sentence(k)}. Its {s['target']:g}% would go to "
                                    f"{bal}.", {"sleeve": s["name"], "to": 0.0, "from": s["target"], "balance": bal}))
    for k, v in views.items():
        if k in avoided or k in NOT_SHARES:
            continue
        action = v.get("action")
        mine = by_theme.get(k, [])
        size = theme_size(k, v, a, risk["growth"])
        held_target = sum(s["target"] for s in mine)
        if action in ("ride", "parachute") and (v.get("believe") or 0) >= 4 and not mine:
            pct = next((e.get("pct") or 0.0 for e in xr.get("themes", []) if e["theme"] == k), 0.0) * 100
            out.append(_suggest(f"add:{k}", "add", f"Add a {SLEEVE_NAME[k]} sleeve at {size:g}%",
                                f"You believe in {themes.in_sentence(k)} ({v['believe']} of 5) and want to ride it, but no "
                                f"sleeve holds it: today {pct:.0f}% of your money rides on it, through your funds."
                                + (f" The {size:g}% would come from {bal}." if bal else ""),
                                {"sleeve": SLEEVE_NAME[k], "to": size, "from": 0.0, "theme": k, "balance": bal,
                                 "why": v.get("why") or None, "change": v.get("change") or None}))
        for s in mine:
            if s["target"] > h["cap"] + 0.01 and bal and s["name"] != bal:
                out.append(_suggest(f"cap:{s['id']}", "target", f"Bring {s['name']} down to {h['cap']:g}%",
                                    f"At {s['target']:g}% it is more than the {h['cap']:g}% a single theme gets for "
                                    f"someone who wants {dict(HANDS_WORDS)[_hands(a)]}. The rest would go to {bal}.",
                                    {"sleeve": s["name"], "to": h["cap"], "from": s["target"], "balance": bal}))
            elif action == "little" and s["target"] > max(4.0, 2 * h["little"]) and bal and s["name"] != bal:
                out.append(_suggest(f"little:{s['id']}", "target", f"Trim {s['name']} to a small slice",
                                    f"You said you'd hold a little of {themes.in_sentence(k)}, but {s['target']:g}% is more "
                                    f"than a little. About {max(h['little'], 2.0):g}% would match your answer; the rest "
                                    f"would go to {bal}.",
                                    {"sleeve": s["name"], "to": max(h["little"], 2.0), "from": s["target"], "balance": bal}))
        if action == "ride" and (v.get("worry") or 0) >= 4 and held_target >= 8:
            out.append(_suggest(f"worry:{k}", "info", f"You're worried about {themes.in_sentence(k)}, and ride it "
                                f"without a parachute",
                                f"{held_target:g}% of your plan rides on it and it worries you ({v['worry']} of 5). Choosing "
                                "\"ride it, with a parachute\" keeps the stake and agrees the protections in advance.",
                                group="info"))
    # ---- 3. risk: never more than the answers allow; less is the person's choice
    if cur and growth_now > risk["growth"] + 10:
        excess = _half(growth_now - risk["growth"])
        safe_target = next((s for s in cur if s["kind"] == "bonds"), None) or next((s for s in cur if s["kind"] == "cash"), None)
        if safe_target and core:
            out.append(_suggest("risk:down", "move", f"Move {excess:g} points from {core['name']} to {safe_target['name']}",
                                f"Your plan holds about {growth_now:.0f}% in shares and other growth investments; your "
                                f"answers on risk point to about {risk['growth']:g}%. Moving the difference keeps the plan "
                                "within the risk you said you'd take.",
                                {"from_sleeve": core["name"], "to_sleeve": safe_target["name"], "points": excess}))
    elif cur and growth_now < risk["growth"] - 15:
        out.append(_suggest("risk:low", "info", "Your plan takes less risk than your answers allow",
                            f"About {growth_now:.0f}% in growth investments against the {risk['growth']:g}% your answers "
                            "would allow. That's a fine choice if it is enough; the builder never raises risk by itself.",
                            group="info"))
    # ---- 4. protections: parachutes and dips
    core_t = core["target"] if core else 0.0
    cash_name = next((s["name"] for s in cur if s["kind"] == "cash"), None)
    for k, v in views.items():
        if k in avoided:
            continue
        mine = by_theme.get(k, [])
        if v.get("action") == "parachute":
            sleeve = mine[0]["name"] if mine else SLEEVE_NAME.get(k, themes.title(k))
            target = sum(s["target"] for s in mine) or theme_size(k, v, a, risk["growth"])
            landing = _landing_for(sleeve, cur, a)
            if not landing and not any(x["id"] == "defensive" for x in out):
                out.append(_suggest("defensive", "add", "Add a Gold sleeve at 3%, to land in",
                                    "A parachute needs somewhere to land: a defensive sleeve that holds up when shares "
                                    f"fall hard. The 3% would come from {bal}." if bal else
                                    "A parachute needs somewhere to land: a defensive sleeve.",
                                    {"sleeve": "Gold", "to": 3.0, "from": 0.0, "theme": "gold", "balance": bal},
                                    ticked=True, group="protect"))
                landing_here = "Gold"
            else:
                landing_here = landing or "Gold"
            needs_landing = "defensive" if any(x["id"] == "defensive" for x in out) else None
            for r in parachute(k, sleeve, target, core_t, landing_here, a, _exposure_pct(xr, k)):
                if r["kind"] == "ai_cap" and _has_rule(rules, "ai_cap"):
                    continue
                if r["kind"] == "exposure_cap" and _has_rule(rules, "exposure_cap", k):
                    continue
                if r["kind"] == "theme_step" and _has_rule(rules, "theme_step", k):
                    continue
                if r["kind"] == "any_company_cap" and (_has_rule(rules, "any_company_cap") or
                                                       any(x["change"].get("rule", {}).get("kind") == "any_company_cap" for x in out)):
                    continue
                title = {"ai_cap": f"Cap AI at {r['trigger']:g}%, counting what funds hold",
                         "exposure_cap": f"Cap {themes.in_sentence(k)} at {r['trigger']:g}%, counting what funds hold",
                         "theme_step": f"Agree the step: {r['trigger']:g} red lights, a third of {sleeve} into {landing_here}",
                         "any_company_cap": f"Trim any one company back to {r.get('target', 0):g}% once it passes "
                                            f"{r['trigger']:g}%"}[r["kind"]]
                reason = {"ai_cap": "Part of your parachute: today about "
                                    f"{_exposure_pct(xr, 'ai'):.0f}% of your money rides on AI once funds are counted. "
                                    "The cap warns you before it grows past what you planned.",
                          "exposure_cap": "Part of your parachute: a ceiling on the whole theme, funds included, so it "
                                          "can't grow past what you planned without you noticing.",
                          "theme_step": f"Part of your parachute, decided now while things are calm: {themes.title(k)} has "
                                        f"{len(themes.lights_for(k))} warning lights on Market watch. When "
                                        f"{r['trigger']:g} are red, Whiskers shows this step on the Overview and the "
                                        "Market watch.",
                          "any_company_cap": "Part of your parachute: the biggest winners are trimmed, not sold, as your "
                                             "own company rules do."}[r["kind"]]
                sug = _suggest(f"rule:{r['kind']}:{k}", "rule", title, reason, {"rule": r}, ticked=True,
                               group="protect")
                if r["kind"] == "theme_step":
                    sug["needs"] = [x for x in (needs_landing, None if mine else f"add:{k}") if x]
                out.append(sug)
        elif v.get("action") == "dip" and not _has_rule(rules, "theme_dip", k):
            into = mine[0]["name"] if mine else SLEEVE_NAME.get(k, themes.title(k))
            size = BELIEVE_SIZE.get(v.get("believe") or 3, 5.0) * HANDS[_hands(a)]["mult"] * risk["growth"] / 100
            size = min(size, h["cap"], SPECIAL_CAP.get(k, 100.0))
            starter = sum(s["target"] for s in mine) or h["little"]
            if not mine and bal:
                out.append(_suggest(f"add:{k}", "add", f"Add a {into} sleeve at {starter:g}%, as a starter",
                                    f"You're waiting for a fall to buy {themes.in_sentence(k)}: a small starter now, and "
                                    "the rule below for the rest.",
                                    {"sleeve": into, "to": starter, "from": 0.0, "theme": k, "balance": bal}))
            if cash_name:
                r = dip_rule(k, into, cash_name, size, starter)
                sug = _suggest(f"rule:theme_dip:{k}", "rule",
                               f"Buy {themes.in_sentence(k)} after a {r['trigger']:g}% fall",
                               f"You said you'd wait for a fall to buy. When it is {r['trigger']:g}% below its high, "
                               f"Whiskers says so and suggests moving {r['target']:g} points from {cash_name} into "
                               f"{into}.", {"rule": r}, ticked=True, group="protect")
                if not mine:
                    sug["needs"] = [f"add:{k}"]
                out.append(sug)
    for r in _company_caps(xr, rules, a):
        if any(x["change"].get("rule", {}).get("kind") == "any_company_cap" for x in out):
            break
        out.append(_suggest(f"rule:company_cap:{r['subject']}", "rule", f"Trim {r['subject']} back to {r['target']:g}% "
                            f"once it passes {r['trigger']:g}%",
                            f"{r['subject']} is already a large part of your money, counting what funds hold. A trim rule "
                            "takes the biggest winner back without selling it.", {"rule": r}, ticked=True, group="protect"))
    # ---- 5. the watch and the written plan for a fall
    w = watch_from_views(a, pos, tot)
    now = themes.watch()
    # The original AI watch and a chosen watch of the AI trade alone look the same on screen:
    # only a real difference is worth suggesting.
    if w["themes"] and (set(now["themes"]) != set(w["themes"]) or now["main"] != w["main"]):
        from . import playbook as pb_
        n_now, n_new = len(pb_.signals_for(now)), len(pb_.signals_for({"main": w["main"], "themes": w["themes"]}))
        same_dial = (now.get("main") or "ai") == w["main"]
        extra = [t for t in w["themes"] if t not in now["themes"]]
        reason = ("From your views. " + " ".join(f"{themes.title(t)}: {w['why'].get(t, '')}" for t in w["themes"][:4])).strip()
        if same_dial and extra:
            reason += (f" The dial stays on {themes.in_sentence(w['main'])}; this adds lights for "
                       f"{', '.join(themes.in_sentence(t) for t in extra)}, and your signals go from {n_now} to {n_new}.")
        out.append(_suggest("watch", "watch", f"Watch {', '.join(themes.title(t) for t in w['themes'])}"
                            + (f", with {themes.in_sentence(w['main'])} on the dial" if w["main"] else ""), reason,
                            {"watch": {"main": w["main"], "themes": w["themes"], "why": w["why"]}},
                            # Ticked only when the dial itself should move: adding lights to a dial
                            # that stays put changes somebody's signals, so it is theirs to choose.
                            ticked=not same_dial and (bool(now.get("legacy")) or not now.get("chosen_at")),
                            group="watch"))
    steps = [x["change"]["rule"] for x in out if x["kind"] == "rule"] + [
        dict(r) | {"trigger": r["trigger_pct"], "into": r.get("into_sleeve")} for r in rules if r["kind"] == "theme_step"]
    pt = plans_text(a, risk, steps, w)
    have = {r["topic"]: (r["body"] or "").strip() for r in db.rows("SELECT topic, body FROM plans")}
    for topic, words, label in (("ai", pt["ai"], f"If {themes.in_sentence(w['main']) if w['main'] else 'your main watch'} turns"),
                                ("crash", pt["crash"], "In any big fall")):
        if have.get(topic) != words:
            out.append(_suggest(f"plans:{topic}", "plans", f"{label}: write the plan down",
                                ("You haven't written this yet. " if not have.get(topic) else
                                 "This would replace what you wrote before. ") + words,
                                {"topic": topic, "body": words}, ticked=not have.get(topic), group="watch"))
    return {"suggestions": out, "balancer": bal, "sleeves": [{"name": s["name"], "target": s["target"],
                                                             "actual": actual.get(s["name"]), "kind": s["kind"],
                                                             "theme": sleeve_theme(s), "why": s.get("why")}
                                                            for s in cur],
            "growth_now": growth_now, "watch": w}


HANDS_WORDS = [("funds", "funds only"), ("few", "funds plus a few themes"), ("enjoy", "to pick their own")]


def _exposure_pct(xr: dict, theme: str) -> float:
    return next(((e.get("pct") or 0.0) * 100 for e in xr.get("themes", []) if e["theme"] == theme), 0.0)


# ---------------------------------------------------------------------------- the draft

def draft(mode: str | None = None) -> dict:
    """Everything the last step shows. Nothing is saved by this."""
    f = facts()
    a = answers(f)
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    xr = xray.run(pos, tot, retirement.settings())
    risk = risk_profile(a, f)
    has_plan = bool(allocation.sleeves())
    mode = mode if mode in ("review", "fresh") else ("review" if has_plan else "fresh")
    out = {"answers": a, "facts": _public_facts(f), "risk": risk, "mode": mode, "has_plan": has_plan,
           "progress": progress(f), "sources": SOURCES, "xray": xr, "hands": _hands(a),
           "views": _views(a), "custom": a.get("custom") or [], "actions": ACTIONS}
    if mode == "review":
        out["review"] = review(a, risk, f, xr, pos, tot)
        out["watch"] = out["review"]["watch"]
    else:
        fp = fresh_plan(a, risk, f, tot.get("invested") or 0.0)
        sleeves = fp["sleeves"]
        core = next((s["target"] for s in sleeves if s.get("kind") == "core"), 0.0)
        cash_name = next((s["name"] for s in sleeves if s.get("is_cash")), "Cash")
        rules = []
        views = _views(a)
        for k, v in views.items():
            s = next((x for x in sleeves if x.get("theme") == k), None)
            if v.get("action") == "parachute" and s:
                for r in parachute(k, s["name"], s["target"], core, _landing_for(s["name"], sleeves, a), a):
                    if r["kind"] == "any_company_cap" and any(x["kind"] == "any_company_cap" for x in rules):
                        continue
                    rules.append(r)
            elif v.get("action") == "dip" and s:
                size = min(BELIEVE_SIZE.get(v.get("believe") or 3, 5.0) * HANDS[_hands(a)]["mult"] * risk["growth"] / 100,
                           HANDS[_hands(a)]["cap"], SPECIAL_CAP.get(k, 100.0))
                r = dip_rule(k, s["name"], cash_name, size, s["target"])
                if r:
                    rules.append(r)
        cur_rules = _current_rules()
        for r in _company_caps(xr, cur_rules + [{"kind": x["kind"], "subject": x.get("subject")} for x in rules], a):
            rules.append(r)
        if "rand" in (a.get("worries") or []) and _exposure_pct(xr, "rand") > 0:
            rules.append({"kind": "exposure_cap", "subject": "rand", "trigger": 10,
                          "note": "Keep rand under 10% of everything, as I'll spend my retirement in pounds."})
        w = watch_from_views(a, pos, tot)
        plans = plans_text(a, risk, rules, w)
        plan = {"whiskers_plan": FORMAT, "about": "Built from your answers to the plan builder.",
                "replace_sleeves": True,
                "sleeves": [{k: s[k] for k in ("name", "target", "is_cash", "ai_share", "theme", "why", "change") if k in s}
                            for s in sleeves],
                "rules": rules, "plans": plans,
                "watch": {"main": w["main"], "themes": w["themes"], "why": w["why"]}}
        if risk["drawing"]:
            plan["playbook"] = {"ladder": {"0": "Spend from cash as normal",
                                           "10": "Spend from cash; refill it from gilts, not shares",
                                           "20": "Keep spending from cash and gilts; leave shares alone",
                                           "30": "Trim extras for a year if cash runs low; still don't sell shares",
                                           "40": "Lean on the cash and gilt buckets for up to two years"}}
        out.update(plan=plan, why=risk["why"] + fp["why"], watch=w,
                   sleeves_now=[{"name": s["name"], "target": s["target"]} for s in allocation.sleeves()])
    age = f.get("age")
    if age is None:
        age = {"under40": 35, "40to54": 47, "55to64": 60, "65to74": 70, "75plus": 78}.get(a.get("age_band"))
    years = {"now": 0, "under5": 3, "5to10": 7.5, "10to20": 15, "over20": 25}.get(a.get("need_when"))
    has_mortgage = (a.get("home") == "yes") if a.get("home") else None
    adv = sections.advice(age, has_mortgage, years, risk["drawing"])
    on = sections.on()
    out["sections"] = [{"key": k, "why": v, "on": on[k]} for k, v in adv.items()]
    return out


# ---------------------------------------------------------------------------- using it

def _n(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _apply_targets(changes: list[dict]) -> list[str]:
    """Target changes and new sleeves, each balanced against the sleeve its suggestion names,
    so the targets still add up to 100 afterwards."""
    done = []
    with db.tx() as c:
        for ch in changes:
            name, to = ch["sleeve"], float(ch["to"])
            row = c.execute("SELECT * FROM sleeves WHERE name=?", (name,)).fetchone()
            before = float(row["target"]) if row else 0.0
            delta = to - before
            if row:
                c.execute("UPDATE sleeves SET target=? WHERE id=?", (to, row["id"]))
            else:
                c.execute("INSERT INTO sleeves(name,target,ai_share,theme,why,breakers,sort) VALUES(?,?,?,?,?,?,"
                          "(SELECT COALESCE(MAX(sort),0)+1 FROM sleeves))",
                          (name, to, 100 if ch.get("theme") == "ai" else 0 if ch.get("theme") else None,
                           ch.get("theme"), ch.get("why"), ch.get("change")))
            bal = ch.get("balance")
            if bal and bal != name and delta:
                c.execute("UPDATE sleeves SET target=MAX(0, target-?) WHERE name=?", (delta, bal))
            done.append(f"{name} {before:g}% to {to:g}%")
    return done


def _move_points(fr: str, to: str, points: float) -> None:
    with db.tx() as c:
        c.execute("UPDATE sleeves SET target=MAX(0, target-?) WHERE name=?", (points, fr))
        c.execute("UPDATE sleeves SET target=target+? WHERE name=?", (points, to))


def _save_rules(rules: list[dict]) -> int:
    if not rules:
        return 0
    from . import plan as planfile
    rep = planfile.import_plan({"whiskers_plan": FORMAT, "rules": rules})
    for r in rules:
        if r["kind"] != "company_cap":
            continue
        for x in portfolio.positions():
            if (x.get("company") or "") == "" and xray._company_of(x) == r["subject"]:
                db.execute("UPDATE instruments SET company=? WHERE id=? AND (company IS NULL OR company='')",
                           (r["subject"], x["instrument_id"]))
    return rep["rules"]


def apply(choice: dict) -> dict:
    """Use what the person ticked: suggestions in a review, or the whole fresh plan. Asked
    for, never automatic; nothing on any platform changes."""
    mode = choice.get("mode") if choice.get("mode") in ("review", "fresh") else None
    d = draft(mode)
    done = []
    sorted_into: list[dict] = []
    from . import plan as planfile
    if d["mode"] == "review":
        ticked = set(choice.get("ticked") or [])
        sug = [s for s in d["review"]["suggestions"] if s["id"] in ticked and s["kind"] != "info"]
        targets = [s["change"] for s in sug if s["kind"] in ("target", "add")]
        if targets:
            done += _apply_targets(targets)
        for s in sug:
            ch = s["change"]
            if s["kind"] == "move":
                _move_points(ch["from_sleeve"], ch["to_sleeve"], float(ch["points"]))
                done.append(f"{ch['points']:g} points from {ch['from_sleeve']} to {ch['to_sleeve']}")
            elif s["kind"] == "words":
                db.execute("UPDATE sleeves SET why=COALESCE(?, why), breakers=COALESCE(?, breakers), "
                           "theme=COALESCE(theme, ?) WHERE name=?",
                           (ch.get("why"), ch.get("change"), ch.get("theme"), ch["sleeve"]))
        n = sum(1 for s in sug if s["kind"] == "words")
        if n:
            done.append(f"your reasons for {_n(n, 'sleeve')}")
        rules = [s["change"]["rule"] for s in sug if s["kind"] == "rule"]
        if rules:
            done.append(_n(_save_rules(rules), "rule"))
        for s in sug:
            if s["kind"] == "watch":
                w = s["change"]["watch"]
                themes.set_watch(w.get("main"), w.get("themes") or [], w.get("why"))
                done.append("your watch")
            elif s["kind"] == "plans":
                planfile.import_plan({"whiskers_plan": 1, "plans": {s["change"]["topic"]: s["change"]["body"]}})
                done.append("your plan for a fall" if s["change"]["topic"] == "crash" else "your plan if your watch turns")
        if targets:
            sorted_into = sort_into_sleeves()
    else:
        plan = d["plan"]
        parts = choice.get("parts") or {}
        if parts.get("sleeves", True):
            rep = planfile.import_plan({k: plan[k] for k in ("whiskers_plan", "about", "replace_sleeves", "sleeves")})
            done.append(_n(rep["sleeves"], "sleeve"))
            sorted_into = sort_into_sleeves()
            if sorted_into:
                done.append(f"{_n(len(sorted_into), 'holding')} sorted into them")
        if parts.get("rules", True) and plan["rules"]:
            done.append(_n(_save_rules(plan["rules"]), "rule"))
        if parts.get("watch", True) and plan["watch"].get("themes"):
            w = plan["watch"]
            themes.set_watch(w.get("main"), w.get("themes") or [], w.get("why"))
            done.append("your watch")
        if parts.get("plans", True):
            planfile.import_plan({"whiskers_plan": 1, "plans": plan["plans"]})
            done.append("your plan for a fall")
        if parts.get("playbook", True) and plan.get("playbook"):
            ov = playbook.overrides()
            ov.update(plan["playbook"])
            db.set_meta("playbook", ov)
    turned_on = []
    for key, want in (choice.get("sections") or {}).items():
        if key in ("mortgage", "retirement") and want and not sections.on()[key]:
            config.settings.update({f"show_{key}": True})
            turned_on.append({"mortgage": "the Mortgage section", "retirement": "the Retirement section"}[key])
    if turned_on:
        done.append(" and ".join(turned_on) + " switched on")
    st = _state()
    st["applied"] = db.today()
    st["applied_mode"] = d["mode"]
    db.set_meta("builder", st)
    db.set_meta("plan_loaded", {"at": db.now(), "about": "Set from the plan builder."})
    return {"ok": True, "done": done, "sorted": sorted_into}


#: Where each kind of investment goes when its name doesn't say, by words in a sleeve's name.
CLASS_SLEEVE = {"bond": ("gilt", "bond"), "linker": ("index-linked", "gilt", "bond"), "cash": ("cash",),
                "gold": ("gold", "commod", "defensive"), "commodity": ("commod", "metal"),
                "property": ("propert", "infrastruct", "real"), "crypto": ("crypto",)}


def sort_into_sleeves() -> list[dict]:
    """Holdings in no sleeve go to the one their name or kind points to: a world fund to the
    global core, a gilt fund to gilts. Only where the answer is clear; anything else is left
    for the Allocation screen, which lists it with a suggestion."""
    sleeves = db.rows("SELECT * FROM sleeves ORDER BY sort, id")
    if not sleeves:
        return []
    out = []
    seen = set()
    for x in portfolio.positions():
        if x["sleeve_id"] or x["instrument_id"] in seen:
            continue
        seen.add(x["instrument_id"])
        cls, _ = classify.asset_class(x)
        sid = None
        words = CLASS_SLEEVE.get(cls)
        if words:
            sid = next((s_["id"] for w in words for s_ in sleeves if w in s_["name"].lower()), None)
        if sid is None and cls == "cash":
            sid = next((s_["id"] for s_ in sleeves if s_["is_cash"]), None)
        if sid is None:
            th = classify.default_themes(x)
            if classify.is_single_company(x) and th:
                key = max(th, key=th.get)
                sid = next((s_["id"] for s_ in sleeves if sleeve_theme(s_) == key), None)
        if sid is None:
            sid = allocation.suggest(x["name"], sleeves)
        if sid is None and cls == "equity" and xray._index_kind(x):
            sid = next((s_["id"] for s_ in sleeves if sleeve_kind(s_) == "core"), None)
        if sid is None:
            continue
        db.execute("UPDATE instruments SET sleeve_id=? WHERE id=? AND sleeve_id IS NULL", (sid, x["instrument_id"]))
        out.append({"holding": x["name"], "sleeve": next(s_["name"] for s_ in sleeves if s_["id"] == sid)})
    return out


# ---------------------------------------------------------------------------- the written plan

OP_WORDS = {">": "above", ">=": "at or above", "<": "below", "<=": "at or below"}


def _day(iso: str | None) -> str:
    try:
        d = dt.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso or "")
    return f"{d.day} {d:%B %Y}"


def rule_words(r: dict) -> str:
    """One rule as a sentence, whatever its kind."""
    if r.get("note"):
        return str(r["note"]).replace("Parachute: ", "")
    k, trig, tgt = r["kind"], r.get("trigger_pct", r.get("trigger")), r.get("target_pct", r.get("target"))
    subj = r.get("subject") or ""
    if k == "company_cap":
        return f"Trim {subj} back to {tgt:g}% once it passes {trig:g}%." if tgt is not None else f"Warn me if {subj} passes {trig:g}%."
    if k == "any_company_cap":
        return f"Trim any one company back to {tgt:g}% once it passes {trig:g}%."
    if k == "ai_cap":
        return f"Keep money riding on AI under {trig:g}%."
    if k == "exposure_cap":
        return f"Keep money riding on {themes.in_sentence(subj)} under {trig:g}%."
    if k == "theme_cap":
        return f"Keep {subj} under {trig:g}%."
    into = r.get("into") or r.get("into_sleeve")
    if k == "theme_step":
        return f"When {trig:g} of {themes.in_sentence(subj)}'s lights are red, move a third of {r.get('sleeve')} into {into}."
    if k == "theme_dip":
        return f"When {themes.in_sentence(subj)} is {trig:g}% below its high, move {tgt:g} points from {r.get('sleeve')} into {into}."
    return f"{k} {subj} {trig}"


def written_plan() -> dict:
    """The investment policy statement, Bogleheads-style: everything decided, in one place,
    to print and keep, with the person's own reasons for each theme."""
    f = facts()
    a = answers(f)
    risk = risk_profile(a, f)
    w = themes.watch()
    sections_ = []

    def sec(title, lines, kind="list"):
        lines = [x for x in lines if x]
        if lines:
            sections_.append({"title": title, "lines": lines, "kind": kind})

    name = config.settings.get("user_name") or None
    st = _state()
    sec("About this plan", [
        f"Built from my answers to the plan builder{', last changed ' + _day(st['updated']) if st.get('updated') else ''}.",
        {"now": "I'm already spending from this money.", "under5": "I'll start spending from it within five years.",
         "5to10": "I'll start spending from it in five to ten years.", "10to20": "I'll start spending from it in ten to "
         "twenty years.", "over20": "I won't need it for more than twenty years."}.get(a.get("need_when") or ""),
        {"funds": "I keep it simple: index funds, checked now and then.",
         "few": "Index funds at the core, with a few themes and companies I believe in.",
         "enjoy": "I enjoy picking: a smaller core, with themes, sectors and single companies."}.get(a.get("hands") or ""),
    ])
    sec("Risk", [
        f"Willing to hold about {risk['willing']}% in shares; able to hold about {risk['able']}%.",
        f"My retirement plan needs about {risk['need']:.0f}% in shares." if risk.get("need") is not None else None,
        f"The plan holds about {risk['growth']:g}% in shares; the rest in bonds, gold and cash.",
    ])
    sl = allocation.sleeves()
    sec("Target mix", [f"{x['name']}: {x['target']:g}%" + (f" (band ±{x['band']:g})" if x["band"] is not None else "")
                       for x in sl] or ["Not set yet."])
    views = _views(a)
    cards = []
    for k in CARD_THEMES:
        v = views.get(k)
        if not v or not v.get("action"):
            continue
        s = next((x for x in sl if sleeve_theme(x) == k), None)
        cards.append({"title": themes.title(k), "action": ACTIONS[v["action"]], "believe": v.get("believe"),
                      "worry": v.get("worry"), "why": v.get("why") or (s or {}).get("why"),
                      "change": v.get("change") or (s or {}).get("breakers"),
                      "sleeve": s["name"] if s else None, "target": s["target"] if s else None})
    for c in a.get("custom") or []:
        if c.get("action"):
            cards.append({"title": c["label"], "action": ACTIONS[c["action"]], "believe": c.get("believe"),
                          "worry": c.get("worry"), "why": c.get("why"), "change": c.get("change")})
    if cards:
        sections_.append({"title": "Why I hold each theme", "kind": "cards", "lines": cards})
    rules = _current_rules()
    para = [rule_words(r) for r in rules if r["kind"] in ("theme_step", "theme_dip")]
    sec("My parachutes and buying points", para)
    sec("My limits", [rule_words(r) for r in rules if r["kind"] not in ("theme_step", "theme_dip")] or ["None set."])
    pb = playbook.evaluate(None, None)
    sec("What I watch", [
        f"Main watch: {themes.title(w['main'])}." if w.get("main") and not w.get("legacy") else
        ("The AI trade, the original watch." if w.get("legacy") else "Markets in general."),
        f"Also: {', '.join(themes.in_sentence(t) for t in w['themes'] if t != w['main'])}." if len(w["themes"]) > 1 else None,
        *[f"{r['title']}: a signal {OP_WORDS.get(r['op'], r['op'])} {r['threshold']:g}{r['unit'] if r['unit'] != 'of 4' else ' of 4'}"
          + (f". {r['action']}" if r.get("action") else "") for r in pb["signals"]],
    ])
    plans = {r["topic"]: r["body"] for r in db.rows("SELECT topic, body FROM plans")}
    sec("In a fall", [plans.get("crash"), plans.get("ai")])
    avoid = [dict(BY_ID["avoid"]["options"]).get(x) for x in a.get("avoid") or [] if x != "none"]
    sec("What I avoid", [", ".join(x for x in avoid if x) + "." if avoid else None,
                         *[f"{themes.title(k)}: I'd rather not hold it." for k, v in views.items() if v.get("action") == "avoid"]])
    sec("Keeping to it", [
        "Each sleeve has a band of 5 points either side of its target, or a quarter of the target when that is "
        "smaller (the 5/25 rule).",
        "New money goes to whatever is furthest below its target first; I sell only to bring a sleeve back inside "
        "its band, or when a step I agreed above applies.",
        "I review the plan once a year, and after any big change in life.",
    ])
    return {"title": f"{name}'s written plan" if name else "My written plan", "made": db.today(),
            "sections": sections_,
            "footer": "Written with Whiskers' plan builder from published research and common practice. It is a record "
                      "of my own decisions, not financial advice."}


# ---------------------------------------------------------------------------- the brief for Claude

def _md_row(cells) -> str:
    return "| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in cells) + " |"


def brief(amounts: bool = False) -> str:
    """Everything Claude needs to write a bespoke plan file, and exactly what to send back."""
    f = facts()
    a = answers(f)
    risk = risk_profile(a, f)
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    xr = xray.run(pos, tot, retirement.settings())
    total = tot.get("total") or 0.0
    name = config.settings.get("user_name") or "the person"
    L = [f"# Plan brief for Claude, {_day(db.today())}", "",
         f"Made by Whiskers' plan builder for {name}. Please write a bespoke investment plan as a Whiskers plan "
         "file. Everything you need is below: their answers, their views in their own words, what they hold, "
         "their current plan and what the X-Ray found.", "",
         "## What to send back", "",
         "1. One JSON plan file, in a single ```json code block, in the format below. They will load it into "
         "Whiskers' plan builder, which checks it before anything changes.",
         "2. After it, a short explanation in plain English: what you changed from their current plan and why, "
         "theme by theme, quoting their own reasons where they gave them.", "",
         "Keep to these:", "",
         f"- About {risk['growth']:g}% in shares and other growth investments (willing about {risk['willing']}%, "
         f"able about {risk['able']}%" + (f", their retirement plan needs about {risk['need']:.0f}%" if risk.get("need") is not None else "")
         + "). Go above this only with a clear reason, and say so.",
         "- Their views decide the shape: size each theme by how strongly they believe in it and what they want to do "
         "about it. \"Ride it, with a parachute\" means a real stake plus protections agreed now (a cap counting what "
         "funds hold, a trim rule for the biggest winners, a step for when the theme's lights turn, and a defensive "
         "sleeve to step into).",
         "- Start from their current plan where it already fits their answers: a personal plan is the point, not a "
         "textbook one. Change what their answers call for, and say why.",
         "- Name kinds of investment for sleeves (\"Global core index\", \"Healthcare\"), not particular funds, unless "
         "their holdings already name them.",
         "- Respect anything they said they'd avoid.",
         "- It is a planning aid, not regulated advice; write it that way.", "",
         "### The plan file", "",
         "```json",
         json.dumps({
             "whiskers_plan": 2, "about": "One line: what this plan is and who made it.", "replace_sleeves": True,
             "sleeves": [
                 {"name": "Global core index", "target": 40, "is_cash": False, "why": "Their reason, in their words where possible."},
                 {"name": "Technology & AI", "target": 20, "theme": "ai", "ai_share": 100, "band": 5,
                  "why": "...", "change": "What would change their mind."},
                 {"name": "Gold", "target": 4, "theme": "gold"},
                 {"name": "Cash", "target": 4, "is_cash": True}],
             "rules": [
                 {"kind": "ai_cap", "trigger": 35, "note": "Keep money riding on AI, counting what funds hold, under 35%."},
                 {"kind": "theme_step", "subject": "ai", "trigger": 2, "target": 33, "sleeve": "Technology & AI",
                  "into": "Gold", "note": "When 2 of the AI trade's 4 lights are red, move a third of Technology & AI into Gold."},
                 {"kind": "any_company_cap", "trigger": 10, "target": 8, "basis": "true",
                  "note": "Trim any one company back to 8% once it passes 10%, counting funds."}],
             "watch": {"main": "ai", "themes": ["ai", "healthcare"], "why": {"ai": "..."}},
             "plans": {"ai": "If my main watch turns, I will...", "crash": "In any big fall, I will..."}}, indent=1),
         "```", "",
         "Rules for the file:", "",
         "- `sleeves`: every sleeve's `target` is a percentage of everything, and all of them must add up to exactly "
         "100. One sleeve has `is_cash: true`. `band` is optional, in percentage points either side; left out, "
         "Whiskers uses the 5/25 rule (5 points, or a quarter of the target if smaller). `theme` is optional, one of "
         "the theme keys listed at the end. `why` and `change` are optional; use their own words where they gave them.",
         "- `replace_sleeves: true` makes the file the whole list of sleeves; any sleeve not named is removed.",
         "- `rules`, by `kind`:",
         "  - `company_cap`: `subject` (company), `trigger` %, optional `target` % to trim back to, `basis` "
         "`\"true\"` to count what funds hold.",
         "  - `any_company_cap`: the same for every single company: `trigger`, `target`, `basis`.",
         "  - `ai_cap`: `trigger` %, counting what funds hold.",
         "  - `exposure_cap`: `subject` (theme key), `trigger` %.",
         "  - `theme_step`: `subject` (theme key), `trigger` (number of the theme's warning lights that must be red), "
         "`target` (% of the sleeve to move), `sleeve` (the sleeve it comes from), `into` (the sleeve it goes to).",
         "  - `theme_dip`: `subject` (theme key), `trigger` (% fall from its high), `target` (points of everything to "
         "move), `sleeve` (where the money comes from, usually Cash), `into` (the theme's sleeve).",
         "  - every rule may have a `note`: one sentence, in plain words, that Whiskers shows when it applies.",
         "- `watch`: up to five theme keys; `main` is the one on the dial.",
         "- `plans`: `ai` is what they will do if their main watch turns, `crash` what they will do in any big fall.", ""]
    # ---- the person
    L += ["## Their answers", ""]
    for q in Q:
        if q["kind"] == "views" or not _visible(q, a):
            continue
        v = a.get(q["id"])
        if v in (None, "", []):
            continue
        opts = dict(q.get("options") or [])
        if isinstance(v, list):
            words = ", ".join(opts.get(x, x) for x in v)
        elif q["kind"] == "money":
            words = f"£{float(v):,.0f}"
        else:
            words = opts.get(v, v)
        src = " (from their Retirement section)" if q.get("from") == "retirement" and q["id"] in (f.get("derived") or {}) else ""
        L.append(f"- {q['text']} **{words}**{src}")
    if f.get("ready"):
        L += ["", "Their retirement plan, on its own assumptions: "
              + (f"the money lasts to {int(f['horizon'])}." if f.get("lasts") else f"the money runs short at about {int(f.get('runs_out_at') or 0)}.")
              + (f" Guaranteed income covers {min(f['covers'], 9.99) * 100:.0f}% of essential spending." if f.get("covers") is not None else "")]
    L += ["", f"Risk, as Whiskers worked it out: willing about {risk['willing']}% in shares, able about {risk['able']}%, "
          f"so about {risk['growth']:g}%." + (f" {risk['shortfall']}" if risk.get("shortfall") else "")
          + (f" {risk['alternative']['words']}" if risk.get("alternative") else ""), ""]
    L += ["## Their views, in their own words", "",
          _md_row(["Theme", "Believe (1-5)", "Worried (1-5)", "What they want", "Why they hold it", "What would change their mind"]),
          _md_row(["---"] * 6)]
    views = _views(a)
    for k in CARD_THEMES:
        v = views.get(k)
        if v and (v.get("action") or v.get("believe") or v.get("why")):
            L.append(_md_row([f"{themes.title(k)} (`{k}`)", v.get("believe") or "", v.get("worry") or "",
                              ACTIONS.get(v.get("action"), ""), v.get("why") or "", v.get("change") or ""]))
    for c in a.get("custom") or []:
        L.append(_md_row([f"{c['label']} (their own theme)", c.get("believe") or "", c.get("worry") or "",
                          ACTIONS.get(c.get("action"), ""), c.get("why") or "", c.get("change") or ""]))
    L.append("")
    # ---- what they hold
    L += ["## What they hold", "",
          f"{_n(len({x['instrument_id'] for x in pos}), 'holding')}" + (f", £{total:,.0f} in all including £{(tot.get('cash') or 0):,.0f} cash." if amounts else "."),
          "", _md_row(["Holding", "Symbol", "Platform", "Sleeve", "Share of everything"] + (["Value"] if amounts else [])),
          _md_row(["---"] * (6 if amounts else 5))]
    for x in sorted(pos, key=lambda r: -(r["value"] or 0)):
        share = f"{x['value'] / total * 100:.1f}%" if (x["value"] is not None and total) else "no price"
        L.append(_md_row([x["name"], x["symbol"], x["platform"], x["sleeve"] or "not in a sleeve", share]
                         + ([f"£{x['value']:,.0f}" if x["value"] is not None else ""] if amounts else [])))
    L.append("")
    th = db.rows("SELECT t.*, i.name FROM theses t JOIN instruments i ON i.id=t.instrument_id ORDER BY i.name")
    th = [t for t in th if (t["why"] or "").strip() or (t["breakers"] or "").strip()]
    if th:
        L += ["### Their reasons for single companies", ""]
        verdicts = {"intact": "reason intact", "watch": "watching", "impaired": "weakened", "broken": "broken: time to sell"}
        for t in th:
            bits = [f"- **{t['name']}**: {(t['why'] or '').strip()}"]
            if (t["breakers"] or "").strip():
                bits.append(f"What would change their mind: {t['breakers'].strip()}")
            if t.get("verdict"):
                bits.append(f"({verdicts.get(t['verdict'], t['verdict'])})")
            try:
                fg = json.loads(t["factors"]) if t.get("factors") else {}
            except ValueError:
                fg = {}
            grades = ", ".join(f"{k} {v}" for k, v in fg.items() if k != "on")
            if grades:
                bits.append(f"Factor grades{' (' + fg['on'] + ')' if fg.get('on') else ''}: {grades}.")
            L.append(" ".join(bits))
        L.append("")
    # ---- the current plan
    alloc = allocation.view(pos, tot)
    L += ["## Their current plan", ""]
    if alloc["sleeves"]:
        L += [_md_row(["Sleeve", "Target", "Now", "Band ±", "Their reason"]), _md_row(["---"] * 5)]
        why = {s["name"]: s.get("why") or "" for s in allocation.sleeves()}
        for r in alloc["sleeves"]:
            L.append(_md_row([r["name"], f"{r['target']:g}%", f"{r['actual']:.1f}%", f"{r['band']:.2g}", why.get(r["name"], "")]))
    else:
        L.append("No plan yet.")
    rules = _current_rules()
    if rules:
        L += ["", "Rules:"] + [f"- {rule_words(r)}" for r in rules]
    w = themes.watch()
    L += ["", f"Watching: {', '.join(themes.title(t) for t in w['themes'])}" + (f"; main watch {themes.title(w['main'])}." if w.get("main") else ".")]
    plans = {r["topic"]: (r["body"] or "").strip() for r in db.rows("SELECT topic, body FROM plans")}
    if plans.get("ai"):
        L.append(f"If their main watch turns, they wrote: \"{plans['ai']}\"")
    if plans.get("crash"):
        L.append(f"In any big fall, they wrote: \"{plans['crash']}\"")
    L.append("")
    # ---- the X-Ray
    L += ["## The X-Ray", ""]
    if xr.get("empty"):
        L.append("Nothing priced yet.")
    else:
        L += ["What it's made of: " + ", ".join(f"{m['label']} {(m['pct'] or 0) * 100:.0f}%" for m in xr.get("asset_mix", [])) + ".",
              f"Where, roughly: US {xr['regions']['us_pct'] * 100:.0f}%, UK {xr['regions']['uk_pct'] * 100:.0f}%, "
              f"emerging markets {xr['regions']['em_pct'] * 100:.0f}% (of what is invested).",
              "What moves it, counting what funds hold: " + ", ".join(
                  f"{t['label']} {t['pct'] * 100:.0f}%" for t in xr.get("themes", []) if (t.get("pct") or 0) >= 0.02) + ".",
              "Biggest companies, counting funds: " + ", ".join(
                  f"{b['company']} {b['pct'] * 100:.1f}%" for b in xr.get("biggest_companies", [])[:6] if b.get("pct")) + ".",
              f"Charges: about {(xr['costs'].get('pct') or 0) * 100:.2f}% a year." if xr.get("costs") else "", ""]
        for fd in xr.get("findings", []):
            L.append(f"- **{fd['title']}.** {fd['detail']}")
    L.append("")
    # ---- the market today
    try:
        m = signals.evaluate()
        L += ["## Warning lights today", "", f"Overall reading: {m['label']}.", ""]
        for x in m["lights"]:
            L.append(f"- {x['title']} ({m['groups'].get(x['group'], {}).get('title', x['group'])}): {x['level']}. {x['words']}")
    except Exception as e:
        L += ["## Warning lights today", "", f"Not available when this was made ({e}).", ""]
    L += ["", "## Theme keys", ""] + [f"- `{k}`: {t['label']}. {t['about']}" for k, t in themes.LIBRARY.items()]
    L += ["", "Not financial advice: a brief for a planning conversation."]
    return "\n".join(L)


# ---------------------------------------------------------------------------- checking a plan file

def _extract_json(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    text = raw.decode("utf-8-sig", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw or "")
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except ValueError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except ValueError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except ValueError:
            pass
    raise ValueError("That isn't a plan file: no JSON plan could be found in it.")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def check_plan(raw) -> dict:
    """Check a plan file before it goes anywhere near Whiskers: that it is well formed and adds
    up, and how it sits against the person's own answers. Then show what would change."""
    from . import plan as planfile
    errors, warnings = [], []
    try:
        data = _extract_json(raw)
    except ValueError as e:
        return {"ok": False, "errors": [str(e)], "warnings": [], "diff": None}
    if data.get("whiskers_plan") is None:
        return {"ok": False, "errors": ["That isn't a Whiskers plan: it has no \"whiskers_plan\" line."], "warnings": [],
                "diff": None}
    if (_num(data.get("whiskers_plan")) or 0) > planfile.FORMAT:
        errors.append("It was written for a newer version of Whiskers.")
    cur = allocation.sleeves()
    cur_by = {s["name"]: s for s in cur}
    new = data.get("sleeves") or []
    names = []
    for s in new:
        n = str((s or {}).get("name") or "").strip()
        if not n:
            errors.append("A sleeve has no name.")
            continue
        if n in names:
            errors.append(f"There are two sleeves called {n}.")
        names.append(n)
        t = _num(s.get("target"))
        if t is None or not 0 <= t <= 100:
            errors.append(f"{n}'s target should be a number between 0 and 100.")
        b = s.get("band")
        if b is not None and (_num(b) is None or not allocation.BAND_MIN <= _num(b) <= allocation.BAND_MAX):
            errors.append(f"{n}'s band should be between {allocation.BAND_MIN:g} and {allocation.BAND_MAX:g} points.")
        if s.get("theme") and s["theme"] not in themes.LIBRARY:
            warnings.append(f"{n} names a theme Whiskers doesn't know ({s['theme']}); it will be read from the name instead.")
    replace = bool(data.get("replace_sleeves"))
    if new:
        result = {} if replace else {k: v["target"] for k, v in cur_by.items()}
        for s in new:
            if str(s.get("name") or "").strip() and _num(s.get("target")) is not None:
                result[str(s["name"]).strip()] = _num(s["target"])
        total = sum(result.values())
        if abs(total - 100) > 0.05:
            if replace:
                errors.append(f"The targets add up to {total:g}%, not 100%.")
            else:
                errors.append(f"Together with the sleeves you already have (the file doesn't replace them), the targets "
                              f"would add up to {total:g}%, not 100%.")
        cash = [s for s in new if s.get("is_cash")]
        if replace and not cash:
            warnings.append("No sleeve is marked as cash, so cash on your platforms won't count towards any target.")
        if len(cash) > 1:
            errors.append("More than one sleeve is marked as cash.")
    else:
        result = {k: v["target"] for k, v in cur_by.items()}
    sleeve_names = set(result)
    for r in data.get("rules") or []:
        kind = (r or {}).get("kind")
        if kind not in planfile.KINDS:
            errors.append(f"Unknown kind of rule: {kind!r}.")
            continue
        if kind in ("theme_step", "theme_dip"):
            subj = r.get("subject")
            if subj not in themes.LIBRARY:
                errors.append(f"A {kind.replace('_', ' ')} names a theme Whiskers doesn't know: {subj!r}.")
            for fld in ("sleeve", "into"):
                if r.get(fld) not in sleeve_names:
                    errors.append(f"A {kind.replace('_', ' ')} for {subj} moves money {'from' if fld == 'sleeve' else 'into'} "
                                  f"{r.get(fld)!r}, but there is no sleeve called that.")
            if kind == "theme_step" and subj in themes.LIBRARY:
                n = len(themes.lights_for(subj))
                if not 1 <= (_num(r.get("trigger")) or 0) <= n:
                    errors.append(f"The step for {themes.in_sentence(subj)} waits for {r.get('trigger')} red lights, but it "
                                  f"has {n}.")
        else:
            trig = _num(r.get("trigger"))
            if trig is None or not 0 < trig <= 100:
                errors.append(f"A {kind.replace('_', ' ')} rule needs a trigger between 0 and 100.")
            if kind not in ("ai_cap", "any_company_cap") and not r.get("subject"):
                errors.append(f"A {kind.replace('_', ' ')} rule needs a subject.")
    w = data.get("watch") or {}
    if w:
        unknown = [t for t in w.get("themes") or [] if t not in themes.LIBRARY]
        if unknown:
            warnings.append(f"The watch names themes Whiskers doesn't know, which will be left out: {', '.join(map(str, unknown))}.")
        if len(w.get("themes") or []) > 5:
            warnings.append("The watch has more than five themes; more lights than that stop meaning anything.")
    # ---- against the answers
    f = facts()
    a = answers(f)
    risk = risk_profile(a, f)
    kinds = {}
    for n in result:
        s = next((x for x in new if str(x.get("name") or "").strip() == n), None) or cur_by.get(n) or {"name": n}
        kinds[n] = sleeve_kind({"name": n, "theme": s.get("theme"), "is_cash": s.get("is_cash")})
    growth = sum(t for n, t in result.items() if not _is_safe(kinds[n]))
    if new and growth > risk["growth"] + 10:
        warnings.append(f"It puts about {growth:.0f}% in shares and other growth investments; your answers point to "
                        f"about {risk['growth']:g}%. That is more risk than you said you'd take.")
    elif new and growth < risk["growth"] - 20:
        warnings.append(f"It puts only about {growth:.0f}% in growth investments against the {risk['growth']:g}% your "
                        "answers allow. Fine if it is deliberate.")
    avoided = _avoided(a)
    for n in result:
        if kinds[n] in avoided and result[n] > 0:
            warnings.append(f"{n} holds {themes.in_sentence(kinds[n])}, which you said you'd rather avoid.")
    rules_after = list(data.get("rules") or []) + [dict(r, trigger=r["trigger_pct"]) for r in _current_rules()]
    for k, v in _views(a).items():
        if v.get("action") == "parachute":
            if not any(r.get("kind") == "theme_step" and r.get("subject") == k for r in rules_after):
                warnings.append(f"You ride {themes.in_sentence(k)} with a parachute, but there is no step for when its "
                                "lights turn.")
            if not any((r.get("kind") == "ai_cap" and k == "ai") or (r.get("kind") == "exposure_cap" and r.get("subject") == k)
                       for r in rules_after):
                warnings.append(f"You ride {themes.in_sentence(k)} with a parachute, but nothing caps it.")
    h = HANDS[_hands(a)]
    for n, t in result.items():
        if kinds[n] in themes.LIBRARY and kinds[n] not in ("rates", "inflation", "gold") and t > h["cap"] + 0.01:
            warnings.append(f"{n} at {t:g}% is more than the {h['cap']:g}% one theme gets for how hands-on you said you "
                            "want to be.")
    # ---- what would change
    diff = {"sleeves": [], "rules": [], "watch": None, "plans": []}
    for n in sorted(set(result) | set(cur_by), key=lambda x: (x not in cur_by, x)):
        before = cur_by[n]["target"] if n in cur_by else None
        after = result.get(n)
        if before is None:
            diff["sleeves"].append({"name": n, "before": None, "after": after, "change": "new"})
        elif after is None:
            diff["sleeves"].append({"name": n, "before": before, "after": None, "change": "removed"})
        elif abs(before - after) > 0.001:
            diff["sleeves"].append({"name": n, "before": before, "after": after, "change": "changed"})
        else:
            diff["sleeves"].append({"name": n, "before": before, "after": after, "change": "same"})
    have = _current_rules()
    for r in data.get("rules") or []:
        same = next((x for x in have if x["kind"] == r.get("kind") and
                     (x["subject"] or "").lower() == str(r.get("subject") or "").lower()), None)
        diff["rules"].append({"words": rule_words({**r, "note": r.get("note")}), "change": "replaces" if same else "new",
                              "before": rule_words(same) if same else None})
    if w.get("themes"):
        now = themes.watch()
        if set(now["themes"]) != set(w["themes"]) or now.get("main") != w.get("main") or now.get("legacy"):
            diff["watch"] = {"before": [themes.title(t) for t in now["themes"]], "after": [themes.title(t) for t in w["themes"] if t in themes.LIBRARY],
                             "main": themes.title(w["main"]) if w.get("main") in themes.LIBRARY else None}
    plans = {r["topic"]: (r["body"] or "").strip() for r in db.rows("SELECT topic, body FROM plans")}
    for topic, body in (data.get("plans") or {}).items():
        if topic in ("ai", "crash") and isinstance(body, str) and body.strip() != plans.get(topic, ""):
            diff["plans"].append({"topic": topic, "before": plans.get(topic) or None, "after": body.strip()})
    token = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:16]
    if not errors:
        db.set_meta("checked_plan", {"token": token, "data": data, "at": db.now()})
    return {"ok": not errors, "errors": errors, "warnings": warnings, "diff": diff, "token": token if not errors else None,
            "about": str(data.get("about") or "")[:300], "growth": growth, "risk_growth": risk["growth"]}


def use_checked(token: str) -> dict:
    from . import plan as planfile
    held = db.get_meta("checked_plan") or {}
    if not token or held.get("token") != token:
        raise ValueError("Check the file again first: Whiskers only loads the plan it has just checked.")
    rep = planfile.import_plan(held["data"])
    sorted_into = sort_into_sleeves() if held["data"].get("sleeves") else []
    db.set_meta("checked_plan", None)
    st = _state()
    st["applied"] = db.today()
    st["applied_mode"] = "file"
    db.set_meta("builder", st)
    return {"ok": True, "report": rep, "sorted": sorted_into}
