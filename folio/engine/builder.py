"""The plan builder: a full financial and portfolio review, done through questions.

It follows the steps a financial planner takes (the CFP Board's seven-step process):
understand the person's circumstances, their goals, what they already have and where it
is heading, then put a plan to them that they can accept or change. Eight parts — you,
your goals, your safety net, income for life, tax and wrappers, risk, your beliefs and
worries, and what you hold — saved as they go, so it can be done over several sittings.

How much to hold in shares comes from three tests (Bogleheads, after Larry Swedroe): the
risk you are *willing* to take, the risk you are *able* to take, and the risk you *need*
to take to reach your goals. The plan uses the lower of willing and able (as the FCA
expects advisers to), and if the need is lower still it offers taking only what is
needed. It never raises risk to meet a need: it shows the other levers instead.

Everything here is a starting point built from published research and common practice,
not advice. It names kinds of investment, never particular funds, and nothing is changed
until the person chooses to use the plan.
"""

from __future__ import annotations

import datetime as dt
import json

from .. import db
from . import (allocation, classify, isa, mortgage as mort, planbuilder, playbook, portfolio,
               retirement, signals, statepension, stress, themes, ukrules as R, xray)

FORMAT = 2


def _opts(*pairs):
    return [[k, v] for k, v in pairs]


THEME_OPTIONS = [[k, t["label"]] for k, t in themes.LIBRARY.items() if k != "rand"]

PARTS = [
    {"key": "you", "title": "You", "intro": "The basics a plan rests on. Nothing here leaves this computer."},
    {"key": "goals", "title": "Your goals", "intro": "What the money is for, in today's prices."},
    {"key": "safety", "title": "Your safety net", "intro": "The things that matter before any investing does."},
    {"key": "income", "title": "Income for life", "intro": "What will pay you in retirement, whatever markets do."},
    {"key": "tax", "title": "Tax and wrappers", "intro": "Where money is held changes how much of it you keep."},
    {"key": "risk", "title": "Risk", "intro": "How you would feel and act when markets fall. There are no right answers."},
    {"key": "beliefs", "title": "Beliefs and worries", "intro": "What you'd like a stake in, and what keeps you up at night."},
    {"key": "holdings", "title": "What you hold", "intro": "The X-Ray: what your investments really contain."},
]

Q = [
    # ---- 1. you
    {"id": "dob", "part": "you", "kind": "date", "text": "Your date of birth", "maps": "dob",
     "why": "Sets your State Pension age and how long the plan runs."},
    {"id": "nation", "part": "you", "kind": "one", "text": "Where do you live?", "maps": "nation",
     "options": _opts(("england", "England"), ("wales", "Wales"), ("scotland", "Scotland"),
                      ("ni", "Northern Ireland")),
     "why": "Scotland sets its own income tax bands."},
    {"id": "household", "part": "you", "kind": "one", "text": "Who shares your finances?",
     "options": _opts(("single", "Just me"), ("married", "Me and my husband, wife or civil partner"),
                      ("cohabit", "Me and a partner we're not married to")),
     "why": "A husband, wife or civil partner inherits free of inheritance tax; an unmarried partner doesn't."},
    {"id": "plan_to", "part": "you", "kind": "one", "text": "How long should the plan last?", "maps": "horizon_age",
     "options": _opts((90, "To 90"), (95, "To 95 (the usual choice)"), (100, "To 100")),
     "why": "Running out of money is the risk a plan most needs to avoid; long family lives argue for 100."},
    {"id": "work", "part": "you", "kind": "one", "text": "How secure is your income from work?",
     "options": _opts(("very", "Very secure: for example the NHS, teaching or the civil service"),
                      ("secure", "Fairly secure"), ("unsure", "It could change"),
                      ("variable", "Self-employed or it varies"), ("none", "I'm not working now")),
     "why": "Secure earnings behave like a bond, so the rest of your money can carry a little more risk."},
    {"id": "stop_age", "part": "you", "kind": "number", "unit": "years old", "maps": "stop_age",
     "text": "At what age would you like to stop working?",
     "why": "The single biggest lever in most plans."},
    {"id": "cut_back", "part": "you", "kind": "one", "text": "Would you like to cut your hours before you stop?",
     "options": _opts(("no", "No"), ("yes", "Yes")),
     "why": "A few part-time years often do more for a plan than a few years' growth."},
    {"id": "cut_back_age", "part": "you", "kind": "number", "unit": "years old", "maps": "cut_back_age",
     "text": "From what age?", "show_if": {"cut_back": ["yes"]}},
    {"id": "cut_back_pct", "part": "you", "kind": "number", "unit": "% of your pay", "maps": "cut_back_pct",
     "text": "Earning about what share of your pay now?", "show_if": {"cut_back": ["yes"]}},
    {"id": "retire_where", "part": "you", "kind": "one", "text": "Where do you expect to live in retirement?",
     "maps": "retire_country",
     "options": _opts(("uk", "The UK"), ("za", "South Africa"), ("both", "Some of each")),
     "why": "The currency you'll spend in, and a UK State Pension paid in South Africa doesn't rise each year."},

    # ---- 2. goals
    {"id": "spend_essential", "part": "goals", "kind": "money", "unit": "a month", "maps": "spend_essential",
     "text": "Roughly what do you spend a month on essentials?",
     "hint": "Bills, food, transport, insurance, council tax. Leave the mortgage out: it has its own tab.",
     "why": "Guaranteed income should ideally cover this; the plan checks."},
    {"id": "spend_extra", "part": "goals", "kind": "money", "unit": "a month", "maps": "spend_extra",
     "text": "And on extras: holidays, hobbies, eating out, gifts?",
     "hint": "Pensions UK's Retirement Living Standards for one person: about £13,900 a year for the "
             "minimum, £32,700 moderate, £45,400 comfortable (everything included).",
     "why": "The flexible part: the first thing to trim if a plan falls short."},
    {"id": "spend_later", "part": "goals", "kind": "one", "maps": "spend_less_from_75",
     "text": "From 75, do you expect to spend less on extras?",
     "options": _opts((0, "About the same"), (20, "A little less"), (40, "Quite a bit less")),
     "why": "Spending on extras tends to fall in later retirement; assuming it doesn't is the cautious choice."},
    {"id": "mortgage_goal", "part": "goals", "kind": "one", "maps": "clear_mortgage_at_stop", "needs": "mortgage",
     "text": "Would you like the mortgage gone by the time you stop working?",
     "options": _opts((True, "Yes: clear it then, from savings or tax-free cash if need be"),
                      (False, "No: let it run to its end")),
     "why": "Clearing it lowers the income retirement needs; keeping it keeps money invested."},
    {"id": "one_offs", "part": "goals", "kind": "list_oneoffs", "maps": "one_offs",
     "text": "Any big costs ahead?", "hint": "A car, a new roof, a wedding, help for family.",
     "why": "Each comes out of the plan in the year you give."},
    {"id": "soon", "part": "goals", "kind": "money", "unit": "",
     "text": "Is any of your invested money needed within five years? How much?",
     "hint": "Leave blank if none.", "why": "Money needed within five years is kept out of shares."},
    {"id": "legacy", "part": "goals", "kind": "one", "text": "Leaving money to family is…",
     "options": _opts(("no", "Not a priority"), ("nice", "Nice if there's some left"), ("important", "Important to me")),
     "why": "Shapes which pots to spend first, now that pensions count for inheritance tax from April 2027."},
    {"id": "home_to_children", "part": "goals", "kind": "one", "maps": "home_to_children",
     "text": "Would your home go to your children or grandchildren?",
     "options": _opts((True, "Yes"), (False, "No")),
     "why": "Adds up to £175,000 to the amount that's free of inheritance tax."},

    # ---- 3. safety net
    {"id": "emergency_months", "part": "safety", "kind": "number", "unit": "months", "maps": "emergency_months",
     "text": "How many months of essential spending do you keep in easy-access savings?",
     "why": "Three to six months is the usual cushion, kept out of investments."},
    {"id": "debts", "part": "safety", "kind": "one", "text": "Any debts other than the mortgage?",
     "options": _opts(("none", "None"), ("cleared", "Credit cards I clear every month"),
                      ("some", "Loans or card balances I'm paying off"))},
    {"id": "debt_rate", "part": "safety", "kind": "number", "unit": "% a year",
     "text": "Roughly what interest do they charge?", "show_if": {"debts": ["some"]},
     "why": "Paying off a debt at 20% beats almost any investment."},
    {"id": "life_cover", "part": "safety", "kind": "one", "text": "Do you have life insurance?",
     "options": _opts(("yes", "Yes"), ("no", "No"), ("unsure", "Not sure"))},
    {"id": "income_protection", "part": "safety", "kind": "one",
     "text": "Income protection, if you couldn't work for a long time?",
     "options": _opts(("yes", "Yes"), ("no", "No"), ("unsure", "Not sure"))},
    {"id": "will", "part": "safety", "kind": "one", "text": "Do you have a will?",
     "options": _opts(("yes", "Yes, up to date"), ("old", "Yes, but it's more than five years old"), ("no", "No"))},
    {"id": "will_sa", "part": "safety", "kind": "one", "needs": "rand",
     "text": "Does a will cover what's left in South Africa?",
     "options": _opts(("yes", "Yes"), ("no", "No"), ("unsure", "Not sure")),
     "why": "Assets in South Africa usually need a South African will, or a UK one that clearly covers them."},
    {"id": "lpa", "part": "safety", "kind": "one", "text": "Lasting powers of attorney, for money and for health?",
     "options": _opts(("yes", "Yes, both"), ("one", "One of them"), ("no", "No"))},
    {"id": "nominations", "part": "safety", "kind": "one",
     "text": "Are your pension nominations up to date?",
     "options": _opts(("yes", "Yes"), ("no", "No"), ("unsure", "Not sure")),
     "why": "A nomination tells each scheme who should receive it. Wills don't always reach pensions."},

    # ---- 4. income for life
    {"id": "pensions", "part": "income", "kind": "pensions",
     "text": "Your pensions", "hint": "Add each one on the Retirement tab: final salary, pots and annuities.",
     "why": "Each is shown as income from its own age."},
    {"id": "sp_weekly", "part": "income", "kind": "money", "unit": "a week", "maps": "state_pension.weekly",
     "text": "Your State Pension forecast",
     "hint": "From gov.uk: search “Check your State Pension forecast”. The full new State Pension "
             "is £241.30 a week in 2026–27.",
     "why": "Usually the biggest guaranteed income anyone has."},
    {"id": "sp_years", "part": "income", "kind": "number", "unit": "years", "maps": "state_pension.years",
     "text": "Qualifying years on your National Insurance record so far",
     "why": "35 for the full amount. Years worked in South Africa don't count."},
    {"id": "sp_gaps", "part": "income", "kind": "number", "unit": "years", "maps": "state_pension.gaps",
     "text": "Gaps your record says you could still fill",
     "why": "Each year bought costs about £957 and adds about £359 a year for life."},
    {"id": "salary", "part": "income", "kind": "money", "unit": "a year", "maps": "salary",
     "text": "Your salary before tax"},
    {"id": "contrib_pct", "part": "income", "kind": "number", "unit": "% of salary", "maps": "contrib_pct",
     "text": "What you pay into your workplace pension"},
    {"id": "contrib_method", "part": "income", "kind": "one", "maps": "contrib_method",
     "text": "How it comes out of your pay",
     "options": _opts(("net_pay", "Before tax (most public-sector schemes)"),
                      ("salary_sacrifice", "Salary sacrifice"),
                      ("relief_at_source", "From take-home pay, with tax relief added by the provider"))},
    {"id": "saving_monthly", "part": "income", "kind": "money", "unit": "a month", "maps": "saving_monthly",
     "text": "What you put into ISAs and other investments each month",
     "hint": "Leave blank to let the plan assume whatever is left over each month is invested."},
    {"id": "other_income", "part": "income", "kind": "list_income", "maps": "other_income",
     "text": "Any other income, now or later?", "hint": "Rent from a property, part-time work, a trust."},

    # ---- 5. tax and wrappers
    {"id": "employer_match", "part": "tax", "kind": "one",
     "text": "Would your employer pay in more if you paid in more?",
     "options": _opts(("yes", "Yes"), ("no", "No"), ("unsure", "Not sure")),
     "why": "Extra employer money is the best return there is."},
    {"id": "self_assessment", "part": "tax", "kind": "one",
     "text": "Do you fill in a Self Assessment tax return?",
     "options": _opts(("yes", "Yes"), ("no", "No")),
     "why": "Interest earned abroad, and dividends above £500 outside an ISA, usually need one."},
    {"id": "isa_info", "part": "tax", "kind": "isa", "text": "Your ISA allowance this tax year"},

    # ---- 6. risk
    {"id": "fall", "part": "risk", "kind": "one",
     "text": "If your investments fell by a third within a year, what would you most likely do?",
     "options": _opts(("sell", "Sell to stop the losses"), ("worry", "Worry, but hold on"),
                      ("hold", "Hold on without much worry"), ("buy", "Buy more while prices are low"))},
    {"id": "did", "part": "risk", "kind": "one",
     "text": "What did you actually do when markets fell in 2020 or 2022?",
     "options": _opts(("sold", "I sold some or all"), ("held", "I held on"), ("bought", "I bought more"),
                      ("none", "I wasn't invested then")),
     "why": "What people did in a real fall predicts the next one better than what they say they'd do."},
    {"id": "experience", "part": "risk", "kind": "one", "text": "How long have you been invested through ups and downs?",
     "options": _opts(("new", "I'm new to it"), ("few", "A few years"), ("long", "Ten years or more, including a big fall"))},
    {"id": "prefer", "part": "risk", "kind": "one", "text": "Which would you rather have?",
     "options": _opts(("steady", "Small, steady growth"), ("balanced", "Better growth, with some ups and downs"),
                      ("growth", "The best long-run growth, accepting big swings"))},

    # ---- 7. beliefs and worries
    {"id": "believe", "part": "beliefs", "kind": "many",
     "text": "Which of these would you like a stake in? (Pick any, or none.)", "options": THEME_OPTIONS},
    {"id": "worry", "part": "beliefs", "kind": "many", "text": "What worries you most about markets?",
     "options": _opts(("ai", "An AI bubble"), ("rates", "Interest rates rising"), ("inflation", "Inflation"),
                      ("oil", "An oil shock"), ("em", "China or emerging markets"), ("uk", "The UK economy"),
                      ("rand", "The rand"), ("crash", "A crash in general"), ("none", "Nothing in particular"))},
    {"id": "main_theme", "part": "beliefs", "kind": "one",
     "text": "Is there one market force you most want to keep an eye on?",
     "options": [["auto", "Choose it from what I hold"]] + THEME_OPTIONS,
     "why": "Becomes the dial on your Overall screen. Choosing from your holdings picks whatever "
            "carries most of your money."},
    {"id": "singles", "part": "beliefs", "kind": "one", "text": "Single companies, or funds only?",
     "options": _opts(("funds", "Funds only"), ("few", "A few companies I believe in"),
                      ("many", "I enjoy picking companies"))},
    {"id": "time", "part": "beliefs", "kind": "one", "text": "How much time a month do you want to spend on this?",
     "options": _opts(("little", "Under an hour"), ("some", "A few hours"), ("lots", "More: I enjoy it"))},
    {"id": "avoid", "part": "beliefs", "kind": "many", "text": "Anything you'd rather not own?",
     "options": _opts(("tobacco", "Tobacco"), ("weapons", "Weapons"), ("fossil", "Fossil fuels"),
                      ("gambling", "Gambling"), ("none", "No preference"))},
    {"id": "uk_bias", "part": "beliefs", "kind": "one", "text": "How much would you like in UK companies?",
     "options": _opts(("global", "What a global fund holds (about 3%)"), ("some", "A bit more than that"),
                      ("lots", "A lot: I'd rather own what I know"))},
    {"id": "income_pref", "part": "beliefs", "kind": "one", "text": "Should your investments pay you an income?",
     "options": _opts(("growth", "No: growth is fine"), ("some", "Some income would be nice"),
                      ("income", "Yes: I want regular income"))},

    # ---- 8. holdings: the X-Ray, no questions
    {"id": "xray", "part": "holdings", "kind": "xray", "text": "Your X-Ray"},
]
BY_ID = {q["id"]: q for q in Q}

SOURCES = planbuilder.SOURCES + [
    ["CFP Board: the seven-step financial planning process",
     "https://www.cfp.net/-/media/files/cfp-board/standards-and-ethics/compliance-resources/guide-to-financial-planning-process.pdf"],
    ["Bogleheads: the ability, willingness and need to take risk", "https://www.bogleheads.org/wiki/Risk_tolerance"],
    ["Morningstar: Portfolio X-Ray", "https://www.morningstar.co.uk/uk/xray/overview"],
    ["Pensions UK: Retirement Living Standards", "https://www.retirementlivingstandards.org.uk/"],
    ["MSCI ACWI factsheet (30 September 2026)", "https://www.msci.com/documents/10199/a71b65b5-d0ea-4b5c-a709-24b1213bc3c5"],
]


# ---------------------------------------------------------------------------- answers

def _state() -> dict:
    st = db.get_meta("builder", {}) or {}
    st.setdefault("answers", {})
    st.setdefault("at", {})
    st.setdefault("mood", {})
    return st


def _get_path(d: dict, path: str):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def answers() -> dict:
    """Every answer, with the ones that live in the retirement settings read from there,
    so the builder and the Retirement tab can never disagree."""
    st = _state()
    s = retirement.settings()
    out = dict(st["answers"])
    for q in Q:
        if q.get("maps"):
            v = _get_path(s, q["maps"])
            # A setting still at the app's own default was never anybody's answer: shown as
            # chosen, it would count as done in a review that hasn't asked yet.
            dflt = _get_path(retirement.DEFAULTS, q["maps"])
            if v is not None and v != [] and (q["id"] in st["answers"] or v != dflt):
                out[q["id"]] = v
    if "household" not in out and s.get("partner"):
        out["household"] = "married"
    if out.get("cut_back") is None and s.get("cut_back_age"):
        out["cut_back"] = "yes"
    return out


def save_answers(incoming: dict) -> dict:
    """Store answers as they are given, dated, with the market's mood that day: people answer
    risk questions more boldly in a rising market, and a later review should know."""
    st = _state()
    today = db.today()
    try:
        mood = signals.evaluate()["label"]
    except Exception:
        mood = None
    ret_changes: dict = {}
    for qid, value in (incoming or {}).items():
        q = BY_ID.get(qid)
        if not q or q["kind"] in ("pensions", "isa", "xray"):
            continue
        if q.get("maps"):
            path = q["maps"]
            if "." in path:
                top, sub = path.split(".", 1)
                ret_changes.setdefault(top, {})[sub] = value
            else:
                ret_changes[path] = value
        st["answers"][qid] = value
        st["at"][qid] = today
        if q["part"] == "risk" and mood:
            st["mood"][qid] = mood
    if "household" in (incoming or {}):
        ret_changes["partner"] = incoming["household"] == "married"
    if (incoming or {}).get("cut_back") == "no":
        ret_changes["cut_back_age"] = None
        ret_changes["cut_back_pct"] = None
    if ret_changes:
        retirement.save(ret_changes)
    st["updated"] = today
    db.set_meta("builder", st)
    return progress()


def _visible(q: dict, a: dict, ctx: dict) -> bool:
    for k, allowed in (q.get("show_if") or {}).items():
        if a.get(k) not in allowed:
            return False
    need = q.get("needs")
    if need == "mortgage" and not ctx.get("mortgage"):
        return False
    if need == "rand" and not ctx.get("rand") and a.get("retire_where") not in ("za", "both"):
        return False
    return True


def _context() -> dict:
    tot = portfolio.totals()
    return {"mortgage": bool(mort.all_mortgages()),
            "rand": any(p.get("currency") == "ZAR" for p in tot["platforms"]) or
            bool(db.scalar("SELECT COUNT(*) FROM pensions WHERE currency='ZAR'", (), 0))}


def progress() -> dict:
    a = answers()
    ctx = _context()
    parts = []
    for p in PARTS:
        qs = [q for q in Q if q["part"] == p["key"] and _visible(q, a, ctx)
              and q["kind"] not in ("pensions", "isa", "xray")]
        done = sum(1 for q in qs if a.get(q["id"]) not in (None, "", []))
        parts.append({"key": p["key"], "title": p["title"], "done": done, "of": len(qs)})
    st = _state()
    return {"parts": parts, "updated": st.get("updated"), "applied": st.get("applied"),
            "complete": all(p["done"] == p["of"] for p in parts if p["key"] not in ("holdings",))}


def questions() -> dict:
    a = answers()
    ctx = _context()
    st = _state()
    return {"parts": PARTS, "questions": [dict(q, visible=_visible(q, a, ctx)) for q in Q],
            "answers": a, "at": st["at"], "mood": st["mood"], "progress": progress(), "context": ctx}


# ---------------------------------------------------------------------------- risk

def risk_profile(a: dict, s: dict, ret: dict | None) -> dict:
    """Willing, able and need, each with its reasoning."""
    why = []
    fall = a.get("fall") or "hold"
    if a.get("did") == "sold" and fall in ("hold", "buy", "worry"):
        why.append("You sold in a real fall, so the plan goes by that rather than by a bolder answer now.")
        fall = "sell"
    w = planbuilder.willingness({"fall": fall, "experience": a.get("experience") or "few",
                                 "prefer": a.get("prefer") or "balanced"})
    willing = 30.0 + 70.0 * w
    if a.get("did") == "bought":
        willing = min(100.0, willing + 5)
    dob = retirement.dob_of(s)
    age = retirement.age_on(dob, dt.date.today()) if dob else None
    stop = s.get("stop_age")
    drawing = bool(age is not None and stop and age >= float(stop)) or a.get("work") == "none"
    years = (float(stop) - age) if (age is not None and stop) else None
    if drawing:
        able = 50.0
        why.append("You are drawing on your money (or will be within the year), so the plan "
                   "follows the bucket approach rather than a growth glide path.")
    elif years is None:
        able = 70.0
    elif years > 20:
        able = 90.0
    elif years > 10:
        able = 80.0
    elif years > 5:
        able = 60.0
    else:
        able = 45.0
    floor = (ret or {}).get("plan", {}).get("income_floor") if ret else None
    covers = floor.get("covers") if floor else None
    if covers is not None and covers >= 0.9:
        able += 10
        why.append(f"Guaranteed income covers {min(covers, 9.99) * 100:.0f}% of your essential spending "
                   "from State Pension age, so your investments can carry more risk: a secure "
                   "pension behaves like a large bond holding.")
    elif covers is not None and covers < 0.5:
        able -= 5
        why.append("Guaranteed income covers less than half of your essentials, so the plan leans "
                   "a little safer.")
    if (s.get("emergency_months") or 0) < 3:
        able -= 5
        why.append("Fewer than three months of essentials set aside: building that up comes first.")
    if a.get("debts") == "some" and (a.get("debt_rate") or 0) >= 6:
        able -= 5
    if a.get("work") in ("unsure", "variable"):
        able -= 5
    elif a.get("work") == "very" and not drawing:
        able += 5
        why.append("Very secure earnings act like a bond in your favour.")
    able = max(10.0, min(100.0, able))
    need = (ret or {}).get("need") or {}
    need_share = need.get("growth_share")
    growth = round(min(willing, able) * 2) / 2
    if willing < able:
        why.append(f"Your answers on how you'd feel in a fall put you at about {willing:.0f}% in shares at "
                   "most. The plan never asks you to take more risk than you're willing to.")
    else:
        why.append(f"Your situation can carry about {able:.0f}% in shares; you're willing to take at "
                   f"least that, so the plan stops there.")
    alternative = None
    if need_share is not None and need_share < growth - 10:
        alternative = {"growth": max(need_share, 20.0),
                       "words": f"Your goals need only about {need_share:.0f}% in shares on these "
                                f"assumptions. Taking less risk than you can is a reasonable choice once "
                                f"there is enough: extra risk then buys little you need."}
    short = None
    if need.get("real") is None and ret and ret.get("ready"):
        short = "Even high returns wouldn't make this plan last: the levers below matter more than risk."
    elif need_share is not None and need_share > growth + 5:
        short = (f"Your goals need about {need_share:.0f}% in shares on these assumptions, more than the "
                 f"{growth:.0f}% the plan will take. Rather than raise the risk, look at the levers below.")
    need_status = ("unknown" if not (ret and ret.get("ready")) else
                   "beyond" if need.get("real") is None else "known")
    return {"willing": round(willing), "able": round(able), "need": need_share, "need_real": need.get("real"),
            "need_status": need_status,
            "need_words": need.get("words"), "growth": growth, "drawing": drawing,
            "years_to_stop": years, "why": why, "alternative": alternative, "shortfall": short,
            "willingness": round(w, 2)}


# ---------------------------------------------------------------------------- the plan

V1_THEME = {"ai": "tech", "healthcare": "health", "oil": "energy", "defence": "defence", "gold": "commod",
            "metals": "commod", "property": "real", "em": "em", "uk": "uk"}
EXTRA_SLEEVES = {"financials": "Financials", "smallcaps": "Smaller companies", "crypto": "Crypto"}


def sleeves_for(a: dict, risk: dict, ret: dict | None, invested: float) -> tuple[list[dict], list[str]]:
    growth = risk["growth"]
    why = []
    drawing = risk["drawing"]
    rate = None
    plan = (ret or {}).get("plan") or {}
    if drawing and plan.get("rows"):
        r0 = plan["rows"][0]
        pot = (plan.get("at_stop") or {}).get("liquid") or 0
        drawn = r0["from_isa"] + r0["from_gia"] + r0["from_pension"] + r0["from_cash"]
        rate = (drawn / pot * 100) if pot else None
    safe = 100.0 - growth
    if drawing:
        r = rate or 4.0
        cash = min(safe, max(4.0, 2 * r))
        why.append(f"About two years of withdrawals ({cash:g}%) in cash, so a fall never forces a sale.")
        if r >= 5:
            why.append("Taking 5% or more a year is above what research finds sustainable: Morningstar's "
                       "2025 study puts the highest safe starting rate at 3.9% for a 30-year retirement.")
    else:
        cash = max(3.0, round(0.25 * safe * 2) / 2)
    cash = min(cash, safe)
    soon = float(a.get("soon") or 0.0)
    if soon and invested:
        extra = min(30.0, round(soon / invested * 100 * 2) / 2)
        if extra:
            cash += extra
            growth = max(0.0, growth - extra)
            why.append(f"{extra:g}% kept as cash for the £{soon:,.0f} needed within five years.")
    rest = max(0.0, 100.0 - growth - cash)
    older = risk["years_to_stop"] is not None and risk["years_to_stop"] < 10
    linked = round(rest * 0.35 * 2) / 2 if (drawing or older) and rest >= 4 else 0.0
    gilts = round((rest - linked) * 2) / 2
    if linked:
        why.append("Part of the safe money is index-linked gilts, which rise with inflation directly.")
    style = {"funds": "simple", "few": "mixed", "many": "hands"}.get(a.get("singles"), "mixed")
    if a.get("time") == "little":
        style = "simple"
    share_of_eq, cap = planbuilder.SATELLITES[style]
    if drawing:
        share_of_eq, cap = min(share_of_eq, 0.15), min(cap, 5.0)
    believe = [t for t in (a.get("believe") or []) if t in themes.LIBRARY]
    names = []
    for t in believe:
        n = planbuilder.THEMES[V1_THEME[t]][0] if t in V1_THEME else EXTRA_SLEEVES.get(t)
        if n and n not in names:
            names.append(n)
    if a.get("uk_bias") in ("some", "lots") and "UK companies" not in names:
        names.append("UK companies")
    if a.get("income_pref") in ("some", "income") and "Dividend income" not in names:
        names.append("Dividend income")
    each = round(min(cap, growth * share_of_eq / len(names)) * 2) / 2 if names else 0.0
    if "Crypto" in names:
        each_crypto = min(each, 2.0)
    else:
        each_crypto = each
    sats = [{"name": n, "target": each_crypto if n == "Crypto" else each} for n in names]
    uk_extra = 0.0
    if a.get("uk_bias") == "lots":
        uk_extra = min(10.0, growth * 0.15)
        for s_ in sats:
            if s_["name"] == "UK companies":
                s_["target"] = round((s_["target"] + uk_extra) * 2) / 2
    core = growth - sum(s_["target"] for s_ in sats)
    why.append(f"{core:g}% goes to a global index fund: one fund holding thousands of companies across "
               "many countries, the usual core.")
    if sats:
        why.append("Each theme you picked gets a small slice beside the core, small enough that one "
                   "going wrong doesn't sink the plan.")
    ai_share = {"Technology & AI": 100}
    sleeves = [{"name": "Global core index", "target": core, "ai_share": None}]
    for s_ in sats:
        sleeves.append({"name": s_["name"], "target": s_["target"], "ai_share": ai_share.get(s_["name"], 0)
                        if s_["name"] in ("Technology & AI", "Healthcare", "Energy", "Defence",
                                          "Commodities & gold", "Property & infrastructure") else None})
    if gilts > 0:
        sleeves.append({"name": "Gilts and bonds", "target": gilts, "ai_share": 0})
    if linked > 0:
        sleeves.append({"name": "Index-linked gilts", "target": linked, "ai_share": 0})
    sleeves.append({"name": "Cash", "target": cash, "ai_share": 0, "is_cash": True})
    sleeves = [x for x in sleeves if x["target"] > 0 or x.get("is_cash")]
    sleeves[0]["target"] = round(sleeves[0]["target"] + 100.0 - sum(x["target"] for x in sleeves), 2)
    return sleeves, why


def _rules(a: dict, watch: dict, xr: dict, s: dict) -> list[dict]:
    out = []
    worry = set(a.get("worry") or [])
    if "ai" in worry or "ai" in watch.get("themes", []):
        cap = 25 if "ai" in worry else 35
        out.append({"kind": "ai_cap", "trigger": cap,
                    "note": f"Keep money riding on AI, counting what funds hold, under {cap}%."})
    # A cap only makes sense where more exposure means more risk. Worrying about inflation or
    # rising rates is a reason to watch them (and hold the things that protect against them),
    # not to cap index-linked gilts.
    for t in worry - {"ai", "crash", "none", "rand", "inflation", "rates"}:
        if t in themes.LIBRARY:
            out.append({"kind": "exposure_cap", "subject": t, "trigger": 20,
                        "note": f"Warn me if more than 20% of my money rides on {themes.LIBRARY[t]['label'].lower()}."})
    if s.get("retire_country", "uk") == "uk" and any(t["theme"] == "rand" and (t["pct"] or 0) > 0 for t in xr.get("themes", [])):
        out.append({"kind": "exposure_cap", "subject": "rand", "trigger": 10,
                    "note": "Keep rand under 10% of everything, as I'll spend my retirement in pounds."})
    for d in xr.get("biggest_companies", [])[:5]:
        if xr.get("total") and d["direct"] and d["true"] / xr["total"] > 0.07:
            out.append({"kind": "company_cap", "subject": d["company"], "trigger": 10, "target": 8,
                        "basis": "true",
                        "note": f"Trim {d['company']} back to 8% once it passes 10%, counting what funds hold."})
    return out


def _plans(a: dict, risk: dict, watch: dict) -> dict:
    main = watch.get("main")
    title = themes.title(main) if main else "markets"
    crash = ("Spend from the Cash sleeve. After good years, top it up from shares; after bad years, top it "
             "up from gilts and leave shares to recover. Don't sell shares in a fall."
             if risk["drawing"] else
             "Keep contributing as normal. Rebalance only when a sleeve leaves its band, using new money "
             "first. Don't sell the core in a fall.")
    theme_plan = (f"If {themes.lower_first(title) if title else 'my main theme'} turns: check that sleeve against its band, "
                  "rebalance with new money first, and only sell if it is outside its band. Re-read why I own "
                  "each single company in it. Don't sell the global core.")
    return {"crash": crash, "ai": theme_plan}


def _day(iso: str | None) -> str:
    try:
        d = dt.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso or "")
    return f"{d.day} {d:%B %Y}"


def _ladder(risk: dict) -> dict | None:
    if not risk["drawing"]:
        return None
    return {"0": "Spend from cash as normal",
            "10": "Spend from cash; refill it from gilts, not shares",
            "20": "Keep spending from cash and gilts; leave shares alone",
            "30": "Trim extras for a year if cash runs low; still don't sell shares",
            "40": "Lean on the cash and gilt buckets for up to two years"}


def todos(a: dict, s: dict, ret: dict | None, xr: dict, tot: dict) -> list[dict]:
    """Things worth doing, with dates where there is one. None of them needs the app."""
    out = []
    today = dt.date.today()

    def add(level, title, detail, when=None, link=None):
        out.append({"level": level, "title": title, "detail": detail, "when": when, "link": link})

    sp = (ret or {}).get("state_pension") or {}
    if sp.get("top_up"):
        t = sp["top_up"]
        add("amber", f"Check whether to fill {t['years']} gap{'s' if t['years'] != 1 else ''} in your National Insurance record",
            f"Each year costs about £{t['cost_each']:,.0f} and adds about £{t['adds_each']:,.0f} a year of State "
            f"Pension for life, paying for itself in about {t['pays_back_years']:g} years. Check your record on "
            f"gov.uk first: years you'll earn anyway, and credits, may cover it. The {t['oldest_year']} year can "
            f"only be filled until {t['oldest_deadline']}.", t["oldest_deadline"], t.get("source"))
    if (s.get("emergency_months") or 0) < 3:
        add("amber", "Build an emergency fund of three to six months' essentials",
            "In easy-access savings, before investing more.")
    if a.get("debts") == "some" and (a.get("debt_rate") or 0) >= 6:
        add("amber", "Pay off the expensive debt before investing more",
            f"At {a.get('debt_rate')}% a year, clearing it is a guaranteed return no investment matches.")
    if a.get("will") in ("no", "old", None):
        add("amber" if a.get("will") == "no" else "info",
            "Make or update your will" if a.get("will") != "no" else "Make a will",
            "Without one, the law decides who inherits. Pensions follow their nominations, not the will.")
    if a.get("will_sa") in ("no", "unsure"):
        add("info", "Check a will covers what's left in South Africa",
            "Usually a separate South African will, or a UK one that names those assets.")
    if a.get("lpa") in ("no", "one", None):
        add("info", "Lasting powers of attorney",
            "One for money and property, one for health and care: easier to arrange long before they're needed.")
    if a.get("nominations") in ("no", "unsure", None) and db.scalar("SELECT COUNT(*) FROM pensions", (), 0):
        add("amber", "Check every pension nomination before April 2027",
            "From 6 April 2027 unused pensions count towards inheritance tax; who you've nominated matters more.",
            "6 April 2027", R.SOURCES["pension_iht"])
    if a.get("income_protection") in ("no", "unsure") and a.get("work") not in ("none",):
        add("info", "Consider income protection",
            "Pays a share of your income if illness stops you working for a long time, after sick pay ends.")
    if a.get("life_cover") in ("no", "unsure") and mort.all_mortgages():
        add("info", "Check life cover for the mortgage",
            "Usually wanted when someone else would be left with the house or the debt.")
    if a.get("employer_match") == "yes":
        add("amber", "Take the employer's extra contribution",
            "If paying in a little more means your employer pays more too, that's free money.")
    allowance = isa.allowance()
    if allowance["remaining"] > 0:
        add("info", f"£{allowance['remaining']:,.0f} of ISA allowance left this tax year",
            f"Unused allowance doesn't carry over. {allowance['label']} ends on 5 April.",
            f"5 April {int(allowance['end'][:4])}")
    dob = retirement.dob_of(s)
    if dob and retirement.age_on(dob, today) < 65:
        add("info", "Cash ISAs are capped at £12,000 a year from 6 April 2027",
            "For anyone under 65. The full £20,000 can still go into stocks and shares ISAs.", "6 April 2027",
            R.SOURCES["isa"])
    gia = (xr.get("wrappers") or {}).get("gia") or 0.0
    if gia > 100 and allowance["remaining"] > 0:
        add("info", "Move money from your general account into your ISA",
            f"Up to £{min(gia, allowance['remaining']):,.0f} this tax year ('bed and ISA').")
    for m in mort.all_mortgages():
        sm = mort.summarise(m)
        d = sm.get("days_to_rate_change")
        if d is not None and 0 <= d <= 200:
            add("amber", f"Your fixed rate ends in {d} days",
                "Most lenders let you book a new deal three to six months ahead. New five-year fixes averaged "
                f"about {R.MARKET['avg_fix_5y']:.2f}% on 5 October 2026.", m.get("fixed_until"))
    if dob and retirement.age_on(dob, today) >= 50 and db.scalar(
            "SELECT COUNT(*) FROM pensions WHERE kind='dc'", (), 0):
        add("info", "Book a free Pension Wise appointment",
            "Free, impartial, government-backed guidance on your pension pot options, for anyone 50 or over.",
            None, "https://www.moneyhelper.org.uk/en/pensions-and-retirement/pension-wise")
    for p in xr.get("protection", []):
        if p["scheme"] == "CoDI":
            add("amber" if p["share"] > 1 else "info", f"{p['name']} is near or over CoDI's R100,000",
                "South Africa's deposit insurance covers R100,000 per bank. Spreading it keeps all of it covered.")
    rand_cash = sum(p.get("cash_native") or 0.0 for p in tot.get("platforms", []) if p.get("currency") == "ZAR")
    if rand_cash and a.get("self_assessment") == "no":
        add("info", "Interest earned in South Africa belongs on a UK tax return",
            "As a UK resident, South African interest is taxable here (under the UK–South Africa treaty). "
            "Small amounts may fall within your Personal Savings Allowance; check it does.")
    singles = [x for x in xr.get("singles", []) if not x["thesis"] and x["pct"] >= 0.01]
    if singles:
        add("info", "Write down why you own each single company",
            "On each holding's page. A reason written in calm weather is the best guide in a fall.")
    add("info", "Review the plan once a year", "Or sooner after a big change in life. The answers come back filled in.",
        (today.replace(year=today.year + 1)).isoformat())
    order = {"red": 0, "amber": 1, "info": 2}
    return sorted(out, key=lambda t: order.get(t["level"], 3))


def draft() -> dict:
    """The whole review: nothing is saved by this."""
    a = answers()
    s = retirement.settings()
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    xr = xray.run(pos, tot, s)
    care = [t for t in (a.get("believe") or []) + (a.get("worry") or []) if t in themes.LIBRARY]
    pinned = a.get("main_theme") if a.get("main_theme") not in (None, "", "auto") else None
    sug = themes.suggest(pos, tot, care, pinned)
    scen = []
    for t in sug["themes"]:
        if t in themes.LIBRARY:
            e = next((x for x in sug["exposures"] if x["theme"] == t), None)
            rp = stress.replay(t, (e or {}).get("value") or 0.0, (tot.get("invested") or 0.0),
                               themes.LIBRARY[t].get("scenario_ref"))
            if rp and rp["loss"] > 0:
                scen.append({"key": t, "label": f"The worst fall of the last five years in {themes.in_sentence(t)}, again",
                             "loss": rp["loss"],
                             "why": f"{themes.LIBRARY[t]['title']} fell {rp['depth'] * 100:.0f}% from "
                                    f"{_day(rp['peak'])} to {_day(rp['trough'])}; world shares moved "
                                    + (f"{rp['world_move'] * 100:+.0f}%" if rp['world_move'] is not None else "an unknown amount")
                                    + " over the same dates.", "replay": rp})
    try:
        ret = retirement.analyse(full=True, theme_scenarios=scen)
    except retirement.RetirementError:
        ret = None
    risk = risk_profile(a, s, ret if ret and ret.get("ready") else None)
    sleeves, sleeve_why = sleeves_for(a, risk, ret if ret and ret.get("ready") else None, tot.get("invested") or 0.0)
    watch = {"main": sug["main"], "themes": sug["themes"], "why": sug["why"],
             "titles": {t: themes.title(t) for t in sug["themes"]}, "note": sug["note"]}
    w = {"main": sug["main"] or "ai", "themes": sug["themes"] or [], "legacy": False}
    sigs = playbook.signals_for(w) if sug["themes"] else [d for d in playbook.SIGNALS if d["group"] == "market"]
    rules = _rules(a, watch, xr, s)
    plans = _plans(a, risk, watch)
    why = list(risk["why"]) + sleeve_why
    if watch["main"]:
        why.append(f"Your main watch is {themes.title(watch['main']).lower()}: "
                   f"{watch['why'].get(watch['main'], 'chosen from your holdings')}")
    else:
        why.append("No single market force carries much of your money, so your watch follows markets in general.")
    plan = {"whiskers_plan": FORMAT, "about": "Built from your answers to the plan review.",
            "replace_sleeves": True, "sleeves": sleeves, "rules": rules, "plans": plans,
            "watch": {"main": watch["main"], "themes": watch["themes"], "why": watch["why"]}}
    lad = _ladder(risk)
    if lad:
        plan["playbook"] = {"ladder": lad}
    standard = stress.standard(pos, tot)
    return {"answers": a, "risk": risk, "xray": xr, "watch": watch, "signals": sigs, "plan": plan,
            "why": why, "sources": SOURCES, "retirement": ret, "standard_stress": standard,
            "theme_scenarios": scen, "todos": todos(a, s, ret, xr, tot), "progress": progress(),
            "sleeves_now": allocation.sleeves(), "watch_now": themes.watch()}


def apply(choice: dict) -> dict:
    """Use the plan, or the parts of it the person ticked. Asked for, never automatic."""
    d = draft()
    plan = d["plan"]
    done = []
    from . import plan as planfile
    sorted_into: list[dict] = []
    if choice.get("sleeves", True):
        rep = planfile.import_plan({k: plan[k] for k in ("whiskers_plan", "about", "replace_sleeves", "sleeves")}
                                   | {"whiskers_plan": 1})
        done.append(_n(rep["sleeves"], "sleeve"))
        sorted_into = sort_into_sleeves()
        if sorted_into:
            done.append(f"{_n(len(sorted_into), 'holding')} sorted into them")
    if choice.get("rules", True) and plan["rules"]:
        rep = planfile.import_plan({"whiskers_plan": 2, "rules": plan["rules"]})
        done.append(_n(rep["rules"], "rule"))
        # A company rule counts the holdings that say which company they are; make sure the
        # ones the X-Ray recognised do.
        for r in plan["rules"]:
            if r["kind"] != "company_cap":
                continue
            for x in portfolio.positions():
                if (x.get("company") or "") == "" and xray._company_of(x) == r["subject"]:
                    db.execute("UPDATE instruments SET company=? WHERE id=? AND (company IS NULL OR company='')",
                               (r["subject"], x["instrument_id"]))
    if choice.get("watch", True):
        w = plan["watch"]
        themes.set_watch(w.get("main"), w.get("themes") or [], w.get("why"))
        done.append("your watch")
    if choice.get("plans", True):
        planfile.import_plan({"whiskers_plan": 1, "plans": plan["plans"]})
        done.append("your plan for a fall")
    if choice.get("playbook", True) and plan.get("playbook"):
        ov = playbook.overrides()
        ov.update(plan["playbook"])
        db.set_meta("playbook", ov)
    sig = choice.get("signals")
    if isinstance(sig, dict):
        ov = playbook.overrides()
        sov = ov.get("signals") or {}
        for k, v in sig.items():
            if isinstance(v, dict):
                cur = dict(sov.get(k) or {})
                if v.get("threshold") not in (None, ""):
                    cur["threshold"] = float(v["threshold"])
                if "action" in v:
                    cur["action"] = str(v["action"] or "")[:400]
                sov[k] = cur
        ov["signals"] = sov
        db.set_meta("playbook", ov)
    st = _state()
    st["applied"] = db.today()
    st["applied_plan"] = plan
    db.set_meta("builder", st)
    return {"ok": True, "done": done, "sorted": sorted_into}


def _n(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


#: Where each kind of investment goes when its name doesn't say, by words in a sleeve's name.
CLASS_SLEEVE = {"bond": ("gilt", "bond"), "linker": ("index-linked", "gilt", "bond"), "cash": ("cash",),
                "gold": ("commod", "gold"), "commodity": ("commod",), "property": ("propert", "infrastruct", "real"),
                "crypto": ("crypto",)}


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
            sid = allocation.suggest(x["name"], sleeves)
        if sid is None and cls == "equity" and xray._index_kind(x):
            sid = next((s_["id"] for s_ in sleeves if "core" in s_["name"].lower() or "global" in s_["name"].lower()), None)
        if sid is None:
            continue
        db.execute("UPDATE instruments SET sleeve_id=? WHERE id=? AND sleeve_id IS NULL", (sid, x["instrument_id"]))
        out.append({"holding": x["name"], "sleeve": next(s_["name"] for s_ in sleeves if s_["id"] == sid)})
    return out


# ---------------------------------------------------------------------------- the written plan

OP_WORDS = {">": "above", ">=": "at or above", "<": "below", "<=": "at or below"}


def written_plan() -> dict:
    """The investment policy statement, Bogleheads-style: everything decided, in one place,
    to print and keep."""
    d = draft()
    a, s = d["answers"], retirement.settings()
    ret = d["retirement"] or {}
    p = ret.get("plan") or {}
    risk = d["risk"]
    w = themes.watch()
    pb = playbook.evaluate(None, None)
    sections = []

    def sec(title, lines):
        sections.append({"title": title, "lines": [x for x in lines if x]})

    dob = retirement.dob_of(s)
    spa = statepension.describe_age(dob) if dob else None
    name = None
    try:
        from .. import config
        name = config.settings.get("user_name") or None
    except Exception:
        pass
    sec("About me", [
        f"Born {dob.strftime('%d %B %Y').lstrip('0')}." if dob else None,
        f"Living in {retirement.NATIONS.get(s.get('nation'), 'England')}." if s.get("nation") else None,
        f"Planning to stop work at {s['stop_age']:g}." if s.get("stop_age") else None,
        f"State Pension from {spa['words']} ({_day(spa['date'])})." if spa else None,
        f"The plan runs to age {s.get('horizon_age') or 95:g}.",
    ])
    sec("My goals", [
        f"Essentials: £{s['spend_essential']:,.0f} a month; extras £{(s.get('spend_extra') or 0):,.0f} a month, in today's money."
        if s.get("spend_essential") is not None else None,
        f"Mortgage: {'cleared when I stop work' if s.get('clear_mortgage_at_stop') else 'runs to its end'}."
        if mort.all_mortgages() else None,
        *[f"{o['label']}: £{o['amount']:,.0f} at {o['age']:g}." for o in s.get("one_offs") or []],
    ])
    if p:
        sec("Where the plan stands", [
            ("On these assumptions the money lasts to the end of the plan." if p.get("lasts") else
             f"On these assumptions the money runs short at about {int(p['runs_out_at'])}."),
            f"Guaranteed income from {int(p['income_floor']['age'])}: £{p['income_floor']['guaranteed']:,.0f} a year "
            f"against essentials of £{p['income_floor']['essential']:,.0f}." if p.get("income_floor") else None,
            f"Mortgage-free at about {int(p['mortgage_free_age'])}." if p.get("mortgage_free_age") else None,
        ])
    sp = (ret or {}).get("state_pension") or {}
    income = [f"State Pension: £{sp['weekly']:,.2f} a week (£{sp['yearly']:,.0f} a year) from {spa['words']}, "
              f"{sp.get('basis', '')}." if sp.get("weekly") is not None and spa else None]
    from . import pensions as pens
    for r in pens.all_rows():
        income.append(f"{r['name']}: {pens.describe(r)}" + (f"; nominated: {r['nominee']}" if r.get("nominee") else "; no nomination recorded") + ".")
    if [x for x in income if x]:
        sec("Income for life", income)
    sec("Risk", [
        f"Willing to hold about {risk['willing']}% in shares; able to hold about {risk['able']}%.",
        f"My goals need about {risk['need']:.0f}% in shares." if risk.get("need") is not None else None,
        f"The plan holds {risk['growth']:g}% in shares and the rest in bonds and cash.",
    ])
    sleeves = allocation.sleeves()
    sec("Target mix", [f"{x['name']}: {x['target']:g}%" for x in sleeves] or ["Not set yet."])
    sec("Keeping to it", [
        "Each sleeve has a band of 5 points either side of its target, or a quarter of the target when "
        "that is smaller (the 5/25 rule).",
        "New money goes to whatever is furthest below its target first; I sell only to bring a sleeve "
        "back inside its band.",
        f"Withdrawals: {retirement.ORDERS.get(s.get('withdrawal_order') or 'isa_first')}.",
    ])
    rules = db.rows("SELECT * FROM rules WHERE enabled=1 ORDER BY id")
    sec("My rules", [r["note"] or f"{r['kind']} {r['subject'] or ''} {r['trigger_pct']}%" for r in rules]
        or ["None set."])
    sec("What I watch", [
        f"Main watch: {themes.title(w['main'])}." if w.get("main") else "Markets in general.",
        f"Also: {', '.join(themes.in_sentence(t) for t in w['themes'] if t != w['main'])}." if len(w["themes"]) > 1 else None,
        *[f"{r['title']}: a signal {OP_WORDS.get(r['op'], r['op'])} {r['threshold']:g}"
          f"{r['unit'] if r['unit'] != 'of 4' else ' of 4'}" + (f". {r['action']}" if r.get("action") else "")
          for r in pb["signals"]],
    ])
    plans = {r["topic"]: r["body"] for r in db.rows("SELECT topic, body FROM plans")}
    sec("In a fall", [plans.get("crash"), plans.get("ai")])
    sec("To do", [f"{t['title']}" + (f" (by {_day(t['when']) if len(str(t['when'])) == 10 and str(t['when'])[4] == '-' else t['when']})"
                                     if t.get("when") else "") for t in d["todos"]])
    sec("Reviews", ["Once a year, and after any big change in life."])
    return {"title": f"{name}'s written plan" if name else "My written plan", "made": db.today(),
            "sections": sections,
            "footer": "Built with the app's plan review from published research and common practice. "
                      "It is a record of my own decisions, not financial advice."}


def review_pack() -> str:
    """Everything a reviewer needs, in one readable file: hand it to Claude or an adviser."""
    d = draft()
    wp = written_plan()
    pos = portfolio.positions()
    lines = [f"# Review pack, {db.today()}", "",
             "Made by the app for a portfolio review. Figures in pounds unless marked.", ""]
    for s in wp["sections"]:
        lines += [f"## {s['title']}", ""] + [f"- {x}" for x in s["lines"]] + [""]
    lines += ["## Holdings", "", "| Holding | Platform | Sleeve | Value | Cost | Gain | Class |",
              "|---|---|---|---:|---:|---:|---|"]
    for x in sorted(pos, key=lambda r: -(r["value"] or 0)):
        cls, _ = classify.asset_class(x)
        g = f"{x['gain_pct'] * 100:+.1f}%" if x.get("gain_pct") is not None else ""
        lines.append(f"| {x['name']} | {x['platform']} | {x['sleeve'] or ''} | "
                     f"{(x['value'] or 0):,.0f} | {(x['cost'] or 0):,.0f} | {g} | {cls} |")
    xr = d["xray"]
    lines += ["", "## X-Ray", ""]
    for f in xr.get("findings", []):
        lines.append(f"- **{f['title']}.** {f['detail']}")
    lines += ["", "### Themes (share of everything)", ""]
    for t in xr.get("themes", []):
        if t["pct"]:
            lines.append(f"- {t['label']}: {t['pct'] * 100:.1f}%")
    lines += ["", "### Single companies", ""]
    for sgl in xr.get("singles", []):
        lines.append(f"- {sgl['name']}: {sgl['pct'] * 100:.1f}% of everything"
                     + (f", {sgl['ahead'] * 100:+.0f} points against the world index since bought" if sgl.get("ahead") is not None else "")
                     + ("" if sgl["thesis"] else ", no thesis written"))
    th = db.rows("SELECT t.*, i.name FROM theses t JOIN instruments i ON i.id=t.instrument_id")
    if th:
        lines += ["", "### Theses", ""]
        for t in th:
            lines += [f"**{t['name']}** ({t['verdict'] or 'no verdict'}; next check {t['next_check'] or 'not set'})",
                      f"- Why: {t['why'] or ''}", f"- What would change my mind: {t['breakers'] or ''}", ""]
    try:
        m = signals.evaluate()
        lines += ["", "## Warning lights", "", f"Reading: {m['label']}.", ""]
        for x in m["lights"]:
            lines.append(f"- {x['title']}: {x['level']} ({x['words']})")
    except Exception:
        pass
    lines += ["", "## Answers", "", "```json", json.dumps(d["answers"], indent=1, default=str), "```", "",
              "Not financial advice."]
    return "\n".join(lines)
