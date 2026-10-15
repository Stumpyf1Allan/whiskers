"""The retirement plan: one row a year, in today's money, from now to the end of the plan.

Each year: what comes in (salary until stopping, each pension from its own age, the
State Pension from State Pension age), what goes out (spending, the mortgage until it
clears, one-off costs), the tax on it, and — when the money coming in falls short —
which pot pays the difference, in the order chosen. Every pot then grows at its own rate
above inflation. The first year nothing can pay is the age the money runs short.

Today's money throughout: £20,000 in 2040 means what £20,000 buys now. That keeps every
figure on the screen comparable with the person's own sense of prices. Things fixed in
cash terms are converted honestly: a mortgage payment that never rises costs less each
year in today's money; a frozen tax threshold catches a little more each year until the
freeze ends; a level annuity buys less every year.

What it is not: a forecast. Returns are steady assumptions the person can change, not
predictions, and the stress tests exist because real returns are not steady. It is a
way of seeing whether a plan hangs together, and what changes it most.
"""

from __future__ import annotations

import copy
import datetime as dt

from .. import db
from ..market import store
from . import classify, mortgage as mort, portfolio, statepension, uktax, ukrules as R

ASSUMPTIONS = {
    "inflation": 2.5,      # % a year: only used for things fixed in cash terms
    "shares": 4.0,         # real returns, % a year, before charges
    "bonds": 1.5,
    "cash": 0.5,
    "property": 2.5,
    "gold": 1.0,
    "dc_default": 3.0,     # a pension pot whose funds nobody has described
    "rand_drift": 0.0,     # % a year the rand moves against the pound (negative: weakens)
    "sp_real": 0.0,        # State Pension rises above prices (the triple lock): 0 is cautious
    "annuity_rate": 5.0,   # an inflation-linked annuity's starting income, % of the pot
}
#: Why each default is what it is, shown beside it on the Retirement screen.
ASSUMPTION_NOTES = {
    "inflation": "The Bank of England's target is 2%; 2.5% leaves a little room.",
    "shares": "Below the long-run 5% a year above inflation UK and world shares have "
              "returned, because starting valuations are high.",
    "bonds": "About what index-linked gilts pay above inflation today.",
    "cash": "Savings rates have mostly sat just above inflation; often less.",
    "property": "Property and infrastructure funds, between shares and bonds.",
    "gold": "Gold has no income; over long periods it has roughly kept pace with prices.",
    "dc_default": "A pension pot in a typical balanced fund.",
    "rand_drift": "0 assumes no change. The rand has tended to weaken against the pound "
                  "over long periods; −2 would assume it loses 2% a year.",
    "sp_real": "The triple lock has raised the State Pension faster than prices; 0 assumes "
               "it only keeps pace.",
    "annuity_rate": "Illustrative only. Get real quotes before deciding.",
}

DEFAULTS = {
    "dob": None, "nation": "england", "partner": False,
    "stop_age": None, "cut_back_age": None, "cut_back_pct": None,
    "horizon_age": 95, "retire_country": "uk",
    "salary": None, "salary_growth": 0.0, "contrib_pct": None, "contrib_method": "net_pay",
    "saving_monthly": None,
    "spend_essential": None, "spend_extra": None, "spend_less_from_75": 0,
    "one_offs": [], "other_income": [],
    "state_pension": {"weekly": None, "years": None, "gaps": None},
    "assumptions": {},
    "withdrawal_order": "isa_first",
    "tax_free_cash": "upfront",
    "clear_mortgage_at_stop": False,
    "emergency_months": 6,
    "home_to_children": True,
}
ORDERS = {
    "isa_first": "Savings and ISAs first, pensions last",
    "pension_first": "Pensions first, ISAs last",
    "fill_band": "Pensions up to the basic-rate band each year, then ISAs",
}
NATIONS = {"england": "England", "wales": "Wales", "scotland": "Scotland", "ni": "Northern Ireland"}


class RetirementError(ValueError):
    pass


# ---------------------------------------------------------------------------- settings

def settings() -> dict:
    s = copy.deepcopy(DEFAULTS)
    stored = db.get_meta("retirement", {}) or {}
    for k, v in stored.items():
        if k in DEFAULTS:
            s[k] = v
    s["assumptions"] = dict(ASSUMPTIONS, **(stored.get("assumptions") or {}))
    sp = dict(DEFAULTS["state_pension"])
    sp.update(stored.get("state_pension") or {})
    s["state_pension"] = sp
    return s


def _num(v, what, lo=None, hi=None):
    if v in (None, ""):
        return None
    try:
        f = float(str(v).replace(",", "").replace("£", "").replace("%", "").strip())
    except ValueError:
        raise RetirementError(f"{what} needs to be a number.") from None
    if (lo is not None and f < lo) or (hi is not None and f > hi):
        raise RetirementError(f"{what} needs to be between {lo:g} and {hi:g}.")
    return f


def save(changes: dict) -> dict:
    stored = db.get_meta("retirement", {}) or {}
    c = changes or {}
    nums = {"stop_age": (40, 85), "cut_back_age": (30, 85), "cut_back_pct": (0, 100),
            "horizon_age": (70, 110), "salary": (0, 5_000_000), "salary_growth": (-5, 10),
            "contrib_pct": (0, 100), "saving_monthly": (0, 1_000_000),
            "spend_essential": (0, 1_000_000), "spend_extra": (0, 1_000_000),
            "spend_less_from_75": (0, 90), "emergency_months": (0, 60)}
    for k, (lo, hi) in nums.items():
        if k in c:
            stored[k] = _num(c[k], k.replace("_", " ").capitalize(), lo, hi)
    if "dob" in c:
        v = str(c["dob"] or "").strip()[:10]
        if v:
            try:
                d = dt.date.fromisoformat(v)
            except ValueError:
                raise RetirementError("The date of birth should look like 1962-05-14.") from None
            if not dt.date(1920, 1, 1) <= d <= dt.date.today():
                raise RetirementError("That date of birth doesn't look right.")
        stored["dob"] = v or None
    for k, allowed in (("nation", NATIONS), ("withdrawal_order", ORDERS),
                       ("tax_free_cash", {"upfront": 1, "ufpls": 1}),
                       ("contrib_method", {"net_pay": 1, "salary_sacrifice": 1, "relief_at_source": 1}),
                       ("retire_country", {"uk": 1, "za": 1, "both": 1})):
        if k in c:
            if c[k] not in allowed:
                raise RetirementError(f"Unknown choice for {k.replace('_', ' ')}.")
            stored[k] = c[k]
    for k in ("partner", "clear_mortgage_at_stop", "home_to_children"):
        if k in c:
            stored[k] = bool(c[k])
    if "state_pension" in c and isinstance(c["state_pension"], dict):
        sp = dict(stored.get("state_pension") or {})
        for k, (lo, hi) in {"weekly": (0, 1000), "years": (0, 60), "gaps": (0, 20)}.items():
            if k in c["state_pension"]:
                sp[k] = _num(c["state_pension"][k], f"State Pension {k}", lo, hi)
        stored["state_pension"] = sp
    if "assumptions" in c and isinstance(c["assumptions"], dict):
        a = dict(stored.get("assumptions") or {})
        for k, v in c["assumptions"].items():
            if k in ASSUMPTIONS:
                a[k] = _num(v, k, -10, 20) if v not in (None, "") else None
                if a[k] is None:
                    a.pop(k)
        stored["assumptions"] = a
    for k in ("one_offs", "other_income"):
        if k in c:
            items = []
            for it in (c[k] or [])[:30]:
                if not isinstance(it, dict):
                    continue
                label = str(it.get("label") or "").strip()[:80]
                if k == "one_offs":
                    amt, age = _num(it.get("amount"), "An amount", -10_000_000, 10_000_000), \
                        _num(it.get("age"), "An age", 18, 110)
                    if label and amt is not None and age is not None:
                        items.append({"label": label, "amount": amt, "age": age})
                else:
                    yearly = _num(it.get("yearly"), "A yearly amount", 0, 10_000_000)
                    if label and yearly is not None:
                        items.append({"label": label, "yearly": yearly,
                                      "from_age": _num(it.get("from_age"), "An age", 18, 110),
                                      "to_age": _num(it.get("to_age"), "An age", 18, 110),
                                      "taxable": bool(it.get("taxable", True))})
            stored[k] = items
    db.set_meta("retirement", stored)
    return settings()


def dob_of(s: dict) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(s.get("dob"))[:10]) if s.get("dob") else None
    except ValueError:
        return None


def age_on(dob: dt.date, d: dt.date) -> float:
    return (d - dob).days / 365.25


# ---------------------------------------------------------------------------- today

def blended(pos: list[dict], plats: list[dict], a: dict, wrappers: tuple[str, ...]) -> dict:
    """The real return and charges of the money in these wrappers, from what it holds."""
    rate = {"equity": a["shares"], "bond": a["bonds"], "linker": a["bonds"], "cash": a["cash"],
            "gold": a["gold"], "commodity": a["gold"], "property": a["property"],
            "crypto": a["shares"], "mixed": 0.6 * a["shares"] + 0.4 * a["bonds"]}
    growth_like = {"equity": 1.0, "crypto": 1.0, "property": 1.0, "mixed": 0.6}
    ids = {p["id"] for p in plats if p["kind"] == "platform" and p["wrapper"] in wrappers}
    total = weighted = equity = cost = 0.0
    for x in pos:
        if x["platform_id"] not in ids or x["value"] is None:
            continue
        cls, _ = classify.asset_class(x)
        v = x["value"]
        total += v
        weighted += v * rate.get(cls, a["shares"])
        equity += v * growth_like.get(cls, 0.0)
        oc, _ = classify.ocf(x)
        cost += v * ((oc if oc is not None else 0.2) / 100)
    for p in plats:
        if p["id"] in ids and p["cash"]:
            total += p["cash"]
            weighted += p["cash"] * a["cash"]
        if p["id"] in ids and p.get("fee_year"):
            cost += p["fee_year"]
    if not total:
        return {"real": a["shares"] * 0.8 + a["bonds"] * 0.2 - 0.2, "equity": 0.8, "charges": 0.2,
                "value": 0.0, "assumed": True}
    charges = cost / total * 100
    return {"real": weighted / total - charges, "equity": equity / total, "charges": charges,
            "value": total, "assumed": False}


def gather(s: dict | None = None) -> dict:
    """Everything the plan starts from, as the rest of the app knows it today."""
    s = s or settings()
    a = s["assumptions"]
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    plats = tot["platforms"]
    pots = {"cash": 0.0, "isa": 0.0, "gia": 0.0, "abroad": 0.0, "owed": 0.0}
    sipps, missing_fx = [], []
    for p in plats:
        if p["fx_missing"]:
            missing_fx.append(p["name"])
            continue
        if p["kind"] == "card":
            pots["owed"] += -(p["cash"] or 0.0)
        elif p["kind"] == "bank":
            if p["currency"] != "GBP":
                pots["abroad"] += p["cash"] or 0.0
            else:
                pots["cash"] += p["cash"] or 0.0
        elif p["wrapper"] in ("isa", "lisa"):
            pots["isa"] += p["total"]
        elif p["wrapper"] == "gia":
            pots["gia"] += p["total"]
        elif p["wrapper"] == "sipp":
            sipps.append({"name": p["name"], "value": p["total"]})
        else:
            pots["cash"] += p["total"]
    mix = blended(pos, plats, a, ("isa", "lisa", "gia"))
    sipp_mix = blended(pos, plats, a, ("sipp",))
    rows = db.rows("SELECT * FROM pensions ORDER BY sort, id")
    dcs, dbs, annuities = [], [], []
    for r in rows:
        ccy = (r.get("currency") or "GBP").upper()
        conv = (lambda v: v) if ccy == "GBP" else (lambda v: store.to_gbp(v, ccy))
        if r["kind"] in ("dc", "sa_ra"):
            value = conv(r["pot"]) if r["pot"] is not None else None
            if r["pot"] is not None and value is None:
                missing_fx.append(r["name"])
            dcs.append({"id": r["id"], "name": r["name"], "kind": r["kind"], "value": value or 0.0,
                        "known": value is not None,
                        "growth": (r["growth"] if r["growth"] is not None else a["dc_default"])
                        - (r["charges"] or 0.0),
                        "contrib": (conv(r["contrib_monthly"]) or 0.0) * 12 if r["contrib_monthly"] else 0.0,
                        "start_age": r["start_age"], "take": r["take"] or "drawdown",
                        "nominee": r["nominee"]})
        elif r["kind"] == "db":
            dbs.append({"id": r["id"], "name": r["name"], "yearly": conv(r["yearly"]) or 0.0,
                        "known": r["yearly"] is not None,
                        "normal_age": r["normal_age"] or 67, "start_age": r["start_age"] or r["normal_age"] or 67,
                        "early_reduction": r["early_reduction"] if r["early_reduction"] is not None else 5.0,
                        "lump_sum": conv(r["lump_sum"]) or 0.0, "commute_pct": r["commute_pct"] or 0.0,
                        "commute_factor": r["commute_factor"] or 12.0,
                        "indexation": r["indexation"] or "cpi", "index_cap": r["index_cap"],
                        "accruing": bool(r["accruing"]), "accrual": conv(r["accrual_yearly"]) or 0.0})
        elif r["kind"] == "annuity":
            annuities.append({"id": r["id"], "name": r["name"], "yearly": conv(r["yearly"]) or 0.0,
                              "start_age": r["start_age"], "indexation": r["indexation"] or "none",
                              "index_cap": r["index_cap"]})
    for sp in sipps:
        dcs.append({"id": None, "name": sp["name"], "kind": "sipp", "value": sp["value"], "known": True,
                    "growth": sipp_mix["real"], "contrib": 0.0, "start_age": None, "take": "drawdown",
                    "nominee": None})
    mortgages = []
    for m in mort.all_mortgages():
        sm = mort.summarise(m)
        mortgages.append({"record": m, "summary": sm})
    assets = db.rows("SELECT * FROM assets")
    property_value = 0.0
    home_value = 0.0
    linked = {m["record"].get("property_asset_id") for m in mortgages if m["record"].get("property_asset_id")}
    for x in assets:
        v = x["value"] if (x["currency"] or "GBP") == "GBP" else store.to_gbp(x["value"], x["currency"])
        property_value += v or 0.0
        if x["is_home"]:
            home_value += v or 0.0
    for m in mortgages:
        if not m["record"].get("property_asset_id") and m["summary"].get("property_value"):
            property_value += m["summary"]["property_value"]
            home_value += m["summary"]["property_value"] if not home_value else 0.0
    del linked
    return {"pots": pots, "mix": mix, "dcs": dcs, "dbs": dbs, "annuities": annuities,
            "mortgages": mortgages, "property": property_value, "home": home_value,
            "missing_fx": missing_fx, "today": dt.date.today()}


# ---------------------------------------------------------------------------- the year loop

def _mortgage_years(mortgages: list[dict], years: int, infl_path: list[float],
                    revert_override: float | str | None, today: dt.date) -> tuple[list[float], list[float]]:
    """Each year's mortgage payments and the balance left at its end, in today's money.

    When a fixed rate ends, most people move to a new deal rather than stay on the lender's
    standard variable rate, so the plan assumes a new five-year fix at today's average.
    `revert_override` changes that: a rate, or "svr" for staying on the standard rate (each
    mortgage's own, or two points above today's average fix where nobody has entered it)."""
    pay = [0.0] * years
    bal = [0.0] * years
    for m in mortgages:
        rec, sm = m["record"], m["summary"]
        balance, payment = sm.get("balance"), sm.get("monthly_payment")
        if balance is None or not payment or balance <= 0:
            continue
        rate = rec.get("rate") or 0.0
        fixed_until = rec.get("fixed_until")
        if revert_override == "svr":
            revert = rec.get("revert_rate") or (R.MARKET["avg_fix_5y"] + 2.0)
        elif revert_override is not None:
            revert = float(revert_override)
        else:
            revert = R.MARKET["avg_fix_5y"]
        interest_only = rec.get("repayment_type") == "interest_only"
        term_left = sm.get("months_left") or (rec.get("term_months") or 300)
        left = float(balance)
        month = 0
        cur_rate, cur_pay = rate, float(payment)
        switched = False
        deflator = 1.0
        for y in range(years):
            if y:
                deflator *= 1 + infl_path[y - 1]
            paid = 0.0
            for _ in range(12):
                if left <= 0.005:
                    break
                on = mort._add_months(today.replace(day=1), month)
                if not switched and fixed_until and revert is not None and on.isoformat() >= fixed_until[:10]:
                    cur_rate = revert
                    remaining = max(1, (term_left or 1) - month)
                    cur_pay = left * mort.monthly_rate(cur_rate) if interest_only else \
                        (mort.payment_for(left, cur_rate, remaining) or cur_pay)
                    switched = True
                interest = left * mort.monthly_rate(cur_rate)
                due = interest if interest_only else cur_pay
                capital = min(left, max(0.0, due - interest))
                left -= capital
                paid += interest + capital
                month += 1
                if interest_only and term_left and month >= term_left:
                    paid += left
                    left = 0.0
            pay[y] += paid / deflator
            bal[y] += left / (deflator * (1 + infl_path[y]))
    return pay, bal


def _index_real(kind: str, cap: float | None, infl: float) -> float:
    """How a pension in payment moves in today's money over one year."""
    if kind == "cpi":
        return 0.0
    if kind == "capped":
        c = (cap if cap is not None else 5.0) / 100
        return (1 + min(infl, c)) / (1 + infl) - 1
    if kind == "fixed":
        return (1 + (cap or 0.0) / 100) / (1 + infl) - 1
    return 1 / (1 + infl) - 1


def project(s: dict, data: dict, opts: dict | None = None) -> dict:
    """Run the plan once. `opts` changes one thing for a what-if or a stress test."""
    o = opts or {}
    a = dict(s["assumptions"])
    dob = dob_of(s)
    today = data["today"]
    if dob is None:
        raise RetirementError("Add a date of birth first.")
    age0 = age_on(dob, today)
    stop_age = float(o.get("stop_age") or s.get("stop_age") or max(age0, 67))
    horizon = float(o.get("horizon") or s.get("horizon_age") or 95)
    years = max(1, int(horizon - int(age0)) + 1)
    base_infl = (a["inflation"] or 0.0) / 100
    extra = o.get("extra_inflation") or {}
    infl_path = [base_infl + ((extra.get("add", 0) / 100) if y < extra.get("years", 0) else 0.0)
                 for y in range(years)]
    spa_months, _ = statepension.age_months(dob)
    spa = spa_months / 12
    sp = statepension.estimate(s, dob, today)
    sp_yearly = sp["yearly"] or 0.0
    access_age = 57 if dob >= dt.date(1973, 4, 6) else 55
    nation = R.nation_key(s.get("nation"))
    mix = data["mix"]
    r_inv = (o["uniform"] if o.get("uniform") is not None else mix["real"]) / 100
    r_cash = (a["cash"] or 0.0) / 100
    equity_share = mix["equity"]
    mort_pay, mort_bal = _mortgage_years(data["mortgages"], years, infl_path,
                                         o.get("revert_rate"), today)

    pots = dict(data["pots"])
    cash = pots["cash"] - pots["owed"]                 # cards cleared from cash at the start
    floor = min(max(cash, 0.0), (s.get("emergency_months") or 0) * (s.get("spend_essential") or 0.0))
    cash -= floor
    cash += float(o.get("extra_now") or 0.0)            # the "have more saved today" lever
    isa, gia, abroad = pots["isa"], pots["gia"], pots["abroad"]
    dcs = [dict(d) for d in data["dcs"]]
    for d in dcs:
        d["open"] = False
        d["income"] = 0.0
    dbs = [dict(d) for d in data["dbs"]]
    for d in dbs:
        d["paying"] = 0.0
        d["started"] = False
    annuities = [dict(x) for x in data["annuities"]]
    for x in annuities:
        x["now"] = x["yearly"]
    lsa_left = float(R.PENSIONS["lump_sum_allowance"])
    salary = float(s.get("salary") or 0.0)
    saving_monthly = float(s.get("saving_monthly") or 0.0)
    essential = float(s.get("spend_essential") or 0.0) * 12
    extra_spend = float(s.get("spend_extra") or 0.0) * 12 * float(o.get("spend_factor", 1.0))
    less_75 = float(s.get("spend_less_from_75") or 0.0) / 100
    sp_real = (a.get("sp_real") or 0.0) / 100
    rand_drift = (a.get("rand_drift") or 0.0) / 100
    order = o.get("order") or s.get("withdrawal_order") or "isa_first"
    shock = o.get("shock")                              # fraction shares fall in the first year retired
    theme_hit = o.get("theme_hit") or 0.0                # pounds lost today in a theme scenario
    if theme_hit:
        total_inv = isa + gia + sum(d["value"] for d in dcs if d["kind"] == "sipp")
        if total_inv:
            cut = min(theme_hit, total_inv) / total_inv
            isa *= 1 - cut
            gia *= 1 - cut
            for d in dcs:
                if d["kind"] == "sipp":
                    d["value"] *= 1 - cut
    cleared_mortgage = False
    rows, shortfall_ages, total_tax = [], [], 0.0
    sp_level = sp_yearly
    tfc_total = 0.0
    deflate = 1.0
    for y in range(years):
        age = int(age0) + y + (age0 - int(age0))
        tax_year = R.tax_year_of(today) + y
        if y:
            deflate *= 1 + infl_path[y - 1]
        infl = infl_path[y]
        factor = 1.0
        for k in range(y):
            if R.tax_year_of(today) + k < R.FROZEN_UNTIL_TAX_YEAR:
                factor /= 1 + infl_path[k]
        worked = max(0.0, min(1.0, stop_age - age))
        cut = 1.0
        if s.get("cut_back_age") and s.get("cut_back_pct") is not None and age >= float(s["cut_back_age"]):
            cut = float(s["cut_back_pct"]) / 100
        gross = salary * ((1 + (s.get("salary_growth") or 0.0) / 100) ** y) * worked * cut
        contrib_pct = float(s.get("contrib_pct") or 0.0)
        method = s.get("contrib_method") or "net_pay"
        emp_contrib = gross * contrib_pct / 100
        over_spa = age >= spa
        if method == "salary_sacrifice":
            taxable_salary, ni_base, cash_cost = gross - emp_contrib, gross - emp_contrib, 0.0
        elif method == "relief_at_source":
            taxable_salary, ni_base, cash_cost = gross, gross, emp_contrib * 0.8
        else:
            taxable_salary, ni_base, cash_cost = gross - emp_contrib, gross, 0.0
        if method != "relief_at_source":
            cash_cost = 0.0
        ni = uktax.national_insurance(ni_base, factor, over_spa)
        # Pensions building up while working.
        for d in dcs:
            if worked > 0 and d["kind"] != "sipp":
                d["value"] += d["contrib"] * worked
        for d in dbs:
            if d["accruing"] and worked > 0:
                d["yearly"] += d["accrual"] * worked
        # Guaranteed income: defined benefit, annuities, the State Pension.
        lump = 0.0
        db_income = 0.0
        for d in dbs:
            if age >= d["start_age"] and not d["started"]:
                early = max(0.0, d["normal_age"] - d["start_age"])
                full = d["yearly"] * max(0.0, 1 - early * d["early_reduction"] / 100)
                given_up = full * d["commute_pct"] / 100
                d["paying"] = full - given_up
                cash_lump = d["lump_sum"] + given_up * d["commute_factor"]
                take = min(cash_lump, lsa_left)
                lsa_left -= take
                lump += cash_lump
                d["started"] = True
            elif d["started"]:
                d["paying"] *= 1 + _index_real(d["indexation"], d["index_cap"], infl)
            db_income += d["paying"]
        ann_income = 0.0
        for x in annuities:
            if x["start_age"] is None or age >= x["start_age"]:
                ann_income += x["now"]
                x["now"] *= 1 + _index_real(x["indexation"], x["index_cap"], infl)
        sp_income = 0.0
        if age + 1 > spa and sp_yearly:
            sp_income = sp_level * max(0.0, min(1.0, age + 1 - spa))
            frozen = s.get("retire_country") == "za"
            sp_level *= (1 / (1 + infl)) if frozen else (1 + sp_real)
        other_tax, other_free = 0.0, 0.0
        for it in s.get("other_income") or []:
            if (it.get("from_age") is None or age >= it["from_age"]) and \
                    (it.get("to_age") is None or age < it["to_age"]):
                if it.get("taxable", True):
                    other_tax += it["yearly"]
                else:
                    other_free += it["yearly"]
        # Pension pots opening: tax-free cash, an annuity, or the lot.
        for d in dcs:
            starts = d["start_age"] or stop_age
            if not d["open"] and age >= max(access_age, starts) and (age >= stop_age or d["start_age"]):
                d["open"] = True
                if d["kind"] == "sa_ra":
                    lump += d["value"]              # South African tax on it is not modelled
                    d["value"] = 0.0
                    continue
                if d["take"] == "lump":
                    tfc = min(d["value"] * R.PENSIONS["tax_free_share"], lsa_left)
                    lsa_left -= tfc
                    lump += tfc
                    d["lump_taxable"] = d["value"] - tfc
                    d["value"] = 0.0
                    continue
                if s.get("tax_free_cash") != "ufpls":
                    tfc = min(d["value"] * R.PENSIONS["tax_free_share"], lsa_left)
                    lsa_left -= tfc
                    lump += tfc
                    d["value"] -= tfc
                if d["take"] == "annuity":
                    d["income"] = d["value"] * (a["annuity_rate"] or 5.0) / 100
                    d["value"] = 0.0
        dc_annuity = sum(d["income"] for d in dcs)
        lump_taxable = sum(d.pop("lump_taxable", 0.0) for d in dcs)
        tfc_total += lump
        base_taxable = taxable_salary + db_income + ann_income + sp_income + other_tax + dc_annuity + lump_taxable
        base_tax = uktax.income_tax(base_taxable, nation, factor)["tax"]
        net_in = (gross - (emp_contrib if method != "relief_at_source" else cash_cost) - ni - base_tax
                  + db_income + ann_income + sp_income + other_tax + other_free + dc_annuity + lump_taxable)
        cash += lump
        # Going out.
        spend = essential + extra_spend * ((1 - less_75) if age >= 75 else 1.0)
        one = sum(it["amount"] for it in s.get("one_offs") or [] if int(it["age"]) == int(age))
        mpay = 0.0 if cleared_mortgage else mort_pay[y]
        clear = 0.0
        if s.get("clear_mortgage_at_stop") and not cleared_mortgage and age >= stop_age and y > 0 \
                and mort_bal[y - 1] > 0:
            clear = mort_bal[y - 1]
            mpay = 0.0
            cleared_mortgage = True
        # The "save more" lever: spend that much less while working and invest it.
        moved = min(spend, float(o.get("extra_saving") or 0.0) * 12 * worked)
        spend -= moved
        out = spend + one + mpay + clear
        gap = out - net_in
        draws = {"cash": 0.0, "isa": 0.0, "gia": 0.0, "abroad": 0.0, "pension": 0.0, "floor": 0.0}
        extra_tax = 0.0
        isa_room = R.ISA["allowance"] * factor
        to_isa = min(moved, isa_room)
        isa += to_isa
        gia += moved - to_isa
        isa_room -= to_isa
        save_isa = moved

        def take_from(amount: float, pot: str) -> float:
            nonlocal cash, isa, gia, abroad, floor
            have = {"cash": cash, "isa": isa, "gia": gia, "abroad": abroad, "floor": floor}[pot]
            got = min(max(have, 0.0), amount)
            if pot == "cash":
                cash -= got
            elif pot == "isa":
                isa -= got
            elif pot == "gia":
                gia -= got
            elif pot == "abroad":
                abroad -= got
            else:
                floor -= got
            draws[pot if pot != "floor" else "floor"] += got
            return amount - got

        def from_pensions(net_needed: float, cap_gross: float | None = None) -> float:
            """Draw net_needed after tax from open pots; returns what is still needed."""
            nonlocal extra_tax, lsa_left
            pots_open = [d for d in dcs if d["open"] and d["value"] > 0.005 and d["take"] == "drawdown"]
            if not pots_open or net_needed <= 0:
                return net_needed
            avail = sum(d["value"] for d in pots_open)
            ufpls = s.get("tax_free_cash") == "ufpls"
            taxed_so_far = base_taxable + draws["pension_taxable"]

            def net_of(g: float) -> float:
                free = min(g * 0.25, lsa_left) if ufpls else 0.0
                t = uktax.income_tax(taxed_so_far + g - free, nation, factor)["tax"] - \
                    uktax.income_tax(taxed_so_far, nation, factor)["tax"]
                return g - t
            hi_g = min(avail, cap_gross) if cap_gross is not None else avail
            if net_of(hi_g) <= net_needed:
                g = hi_g
            else:
                lo, hi = 0.0, hi_g
                for _ in range(40):
                    mid = (lo + hi) / 2
                    if net_of(mid) < net_needed:
                        lo = mid
                    else:
                        hi = mid
                g = hi
            got_net = net_of(g)
            free = min(g * 0.25, lsa_left) if ufpls else 0.0
            lsa_left -= free
            extra_tax += g - got_net
            draws["pension"] += g
            draws["pension_taxable"] += g - free
            left = g
            for d in pots_open:
                share = min(d["value"], left * d["value"] / avail) if avail else 0.0
                d["value"] -= share
            return max(0.0, net_needed - got_net)

        draws["pension_taxable"] = 0.0
        if gap < 0:
            # Money left over. With a monthly saving set, that much is invested and the
            # rest builds up as cash; without one, all of it is assumed invested (in the
            # ISA while there is allowance left, as cash after that).
            surplus = -gap
            planned = surplus if s.get("saving_monthly") is None else min(surplus, saving_monthly * 12 * worked)
            to_isa = min(planned, max(0.0, isa_room))
            isa += to_isa
            save_isa += to_isa
            cash += surplus - to_isa
        else:
            need = gap
            if order == "fill_band":
                band_top = (R.INCOME_TAX[nation]["personal_allowance"] + R.INCOME_TAX[nation]["bands"][0][0]
                            if nation == "ruk" else
                            R.INCOME_TAX[nation]["personal_allowance"] + R.INCOME_TAX[nation]["bands"][2][0]) * factor
                headroom = max(0.0, band_top - base_taxable)
                if headroom > 0:
                    before = draws["pension"]
                    rest = from_pensions(need, cap_gross=headroom)
                    got = draws["pension"] - before
                    need = rest
                    del got
            seq = {"isa_first": ["cash", "gia", "isa", "abroad", "pension", "floor"],
                   "pension_first": ["cash", "pension", "gia", "isa", "abroad", "floor"],
                   "fill_band": ["cash", "gia", "isa", "abroad", "pension", "floor"]}[order]
            for pot in seq:
                if need <= 0.005:
                    break
                need = from_pensions(need) if pot == "pension" else take_from(need, pot)
            if need > 0.5:
                shortfall_ages.append(age)
            gap_left = need
        total_tax += base_tax + extra_tax + ni
        # Growth over the year, after the year's money has moved.
        year_r = r_inv - (extra.get("add", 0) / 100 * (1 - equity_share) if y < extra.get("years", 0) else 0.0)
        year_cash = r_cash - (extra.get("add", 0) / 100 if y < extra.get("years", 0) else 0.0)
        first_retired = shock is not None and int(age) == int(max(stop_age, age0))
        if first_retired:
            hit = -shock * equity_share + year_r * (1 - equity_share)
            isa *= 1 + hit
            gia *= 1 + hit
        else:
            isa *= 1 + year_r
            gia *= 1 + year_r
        cash *= 1 + year_cash
        floor *= 1 + year_cash
        abroad *= 1 + year_cash + rand_drift
        for d in dcs:
            g = (o["uniform"] / 100) if o.get("uniform") is not None else d["growth"] / 100
            if first_retired:
                g = -shock * 0.7 + g * 0.3
            d["value"] *= 1 + g
        dc_total = sum(d["value"] for d in dcs)
        liquid = cash + floor + isa + gia + abroad
        rows.append({
            "age": round(age, 2), "year": today.year + y, "tax_year": tax_year,
            "salary": round(gross - (emp_contrib if method != "relief_at_source" else cash_cost) - ni, 2),
            "salary_gross": round(gross, 2), "db": round(db_income, 2), "annuity": round(ann_income + dc_annuity, 2),
            "state": round(sp_income, 2), "other": round(other_tax + other_free, 2),
            "lump": round(lump, 2), "tax": round(base_tax + extra_tax, 2), "ni": round(ni, 2),
            "spend": round(spend, 2), "one_off": round(one, 2), "mortgage": round(mpay + clear, 2),
            "saving": round(save_isa, 2),
            "from_cash": round(draws["cash"] + draws["floor"], 2), "from_isa": round(draws["isa"], 2),
            "from_gia": round(draws["gia"], 2), "from_abroad": round(draws["abroad"], 2),
            "from_pension": round(draws["pension"], 2),
            "short": round(gap_left, 2) if gap > 0 and gap_left > 0.5 else 0.0,
            "cash": round(cash + floor, 2), "isa": round(isa, 2), "gia": round(gia, 2),
            "abroad": round(abroad, 2), "pensions": round(dc_total, 2), "liquid": round(liquid + dc_total, 2),
            "mortgage_left": round(0.0 if cleared_mortgage else mort_bal[y], 2),
            "guaranteed": round(db_income + ann_income + sp_income + dc_annuity, 2),
            "factor": round(factor, 4),
        })
        if gap <= 0:
            gap_left = 0.0
    first_short = shortfall_ages[0] if shortfall_ages else None
    last = rows[-1]
    estate = last["liquid"] + data["property"] - last["mortgage_left"]
    iht = _iht(estate, data["home"], last["pensions"], s, rows[-1]["factor"])
    stop_row = next((r for r in rows if r["age"] + 1 > stop_age), rows[0])
    mortgage_free = next((r["age"] for r in rows if r["mortgage_left"] <= 0.5), None) if data["mortgages"] else None
    floor_row = next((r for r in rows if r["age"] >= max(stop_age, spa)), rows[-1])
    return {
        "rows": rows, "first_short": first_short, "lasts": first_short is None,
        "runs_out_at": first_short, "horizon": horizon, "stop_age": stop_age, "spa": spa,
        "age_now": age0, "total_tax": round(total_tax, 2), "estate": round(estate, 2), "iht": iht,
        "at_stop": {"liquid": stop_row["liquid"], "isa": stop_row["isa"], "pensions": stop_row["pensions"],
                    "cash": stop_row["cash"]},
        "mortgage_free_age": mortgage_free,
        "income_floor": {"age": floor_row["age"], "guaranteed": floor_row["guaranteed"],
                         "essential": essential,
                         "covers": (floor_row["guaranteed"] / essential) if essential else None},
        "tax_free_cash": round(tfc_total, 2),
    }


def _iht(estate: float, home: float, pensions_left: float, s: dict, factor: float) -> dict:
    """A rough inheritance tax figure at the end of the plan, in today's money. Pensions
    count from April 2027; a spouse or civil partner inherits free of it."""
    if s.get("partner"):
        return {"tax": 0.0, "note": "Left to a spouse or civil partner, an estate is free of "
                "inheritance tax, and their own allowances usually double up later.",
                "estate": round(estate, 2), "pensions_included": round(pensions_left, 2)}
    nrb = R.IHT["nil_rate_band"] * factor
    rnrb = R.IHT["residence_band"] * factor if (home > 0 and s.get("home_to_children", True)) else 0.0
    taper = R.IHT["taper_from"] * factor
    if estate > taper:
        rnrb = max(0.0, rnrb - (estate - taper) / 2)
    tax = max(0.0, estate - nrb - rnrb) * R.IHT["rate"]
    return {"tax": round(tax, 2), "allowances": round(nrb + rnrb, 2), "estate": round(estate, 2),
            "pensions_included": round(pensions_left, 2),
            "note": "Pensions count from 6 April 2027. Gifts, trusts and reliefs aren't modelled."}


# ---------------------------------------------------------------------------- analysis

def missing(s: dict, data: dict) -> list[str]:
    out = []
    if not dob_of(s):
        out.append("your date of birth")
    if not s.get("stop_age"):
        out.append("when you'd like to stop working")
    if s.get("spend_essential") is None:
        out.append("what you spend a month on essentials")
    return out


def _solve(fn, lo: float, hi: float, steps: int = 32) -> float | None:
    """The smallest x in [lo, hi] for which fn(x) is True, assuming it stays True above."""
    if not fn(hi):
        return None
    if fn(lo):
        return lo
    for _ in range(steps):
        mid = (lo + hi) / 2
        if fn(mid):
            hi = mid
        else:
            lo = mid
    return hi


def need(s: dict, data: dict) -> dict:
    """The return above inflation the plan needs on everything invested to last."""
    ok = lambda r: project(s, data, {"uniform": r})["lasts"]  # noqa: E731
    r = _solve(ok, -3.0, 12.0, 26)
    a = s["assumptions"]
    out = {"real": r, "shares": a["shares"], "bonds": a["bonds"]}
    if r is None:
        out["words"] = ("Even 12% a year above inflation wouldn't be enough: this plan needs "
                        "changing, not more risk.")
        out["growth_share"] = None
    elif r <= -3.0:
        out["words"] = ("Your income and savings already cover the plan without any growth at "
                        "all. Taking investment risk is a choice here, not a need.")
        out["growth_share"] = 0.0
    else:
        span = (a["shares"] - a["bonds"]) or 1.0
        share = max(0.0, min(1.0, (r - a["bonds"]) / span))
        out["growth_share"] = round(share * 100)
        out["words"] = (f"The plan needs about {r:.1f}% a year above inflation on what is invested. "
                        f"On the return assumptions here, that is roughly {round(share * 100)}% in shares "
                        f"and the rest in bonds and cash.")
    return out


def levers(s: dict, data: dict) -> list[dict]:
    """When the plan falls short: how big each change would need to be on its own."""
    out = []
    save = _solve(lambda x: project(s, data, {"extra_saving": x})["lasts"], 0.0, 10000.0, 22)
    if save is not None and save > 0:
        out.append({"key": "save", "label": "Spend less now and invest it, until you stop",
                    "value": round(save, -1), "words": f"About £{round(save, -1):,.0f} more a month"})
    base_stop = float(s.get("stop_age") or 67)
    later = _solve(lambda x: project(s, data, {"stop_age": base_stop + x})["lasts"], 0.0, 12.0, 14)
    if later is not None and later > 0:
        out.append({"key": "later", "label": "Stop working later",
                    "value": round(later, 1), "words": f"About {later:.1f} years later, at {base_stop + later:.1f}"})
    if s.get("spend_extra"):
        cut = _solve(lambda x: project(s, data, {"spend_factor": 1 - x})["lasts"], 0.0, 1.0, 16)
        if cut is not None and cut > 0:
            out.append({"key": "spend", "label": "Spend less on extras",
                        "value": round(cut * 100), "words":
                        f"About {cut * 100:.0f}% less on extras: £{(s['spend_extra'] or 0) * cut:,.0f} a month"})
    # Whoever has already stopped working has fewer levers; this one always has an answer.
    more = _solve(lambda x: project(s, data, {"extra_now": x})["lasts"], 0.0, 5_000_000.0, 24)
    if more is not None and more > 0:
        out.append({"key": "more", "label": "Have more saved today",
                    "value": round(more, -2), "words": f"About £{round(more, -2):,.0f} more in savings or investments now"})
    return out


STRESSES = [
    {"key": "fall", "label": "Shares fall by a third the year you stop",
     "why": "The order returns arrive in matters most around the time withdrawals start."},
    {"key": "inflation", "label": "Inflation 2 points higher for five years",
     "why": "Cash and bonds lose most; a mortgage fixed in pounds gets lighter."},
    {"key": "rate", "label": "Staying on the lender's standard rate when the deal ends",
     "why": "The plan assumes a new fix at today's average (about 6% for five years on 5 October "
            "2026, Moneyfacts). Not taking one usually costs a good deal more."},
    {"key": "long", "label": "Living to 100", "why": "A plan should survive a long life."},
    {"key": "early", "label": "Stopping two years earlier", "why": "Health and work don't always cooperate."},
    {"key": "late", "label": "Stopping two years later", "why": "For comparison."},
]


def stresses(s: dict, data: dict, extra: list[dict] | None = None) -> list[dict]:
    base_stop = float(s.get("stop_age") or 67)
    opts = {"fall": {"shock": 1 / 3}, "inflation": {"extra_inflation": {"years": 5, "add": 2.0}},
            "rate": {"revert_rate": "svr"}, "long": {"horizon": 100},
            "early": {"stop_age": base_stop - 2}, "late": {"stop_age": base_stop + 2}}
    out = []
    for st in STRESSES:
        if st["key"] == "rate" and not data["mortgages"]:
            continue
        r = project(s, data, opts[st["key"]])
        out.append(dict(st, lasts=r["lasts"], runs_out_at=r["runs_out_at"],
                        liquid_at_end=r["rows"][-1]["liquid"], horizon=r["horizon"]))
    for sc in extra or []:
        r = project(s, data, {"theme_hit": sc["loss"]})
        out.append({"key": "theme:" + sc["key"], "label": sc["label"], "why": sc["why"],
                    "lasts": r["lasts"], "runs_out_at": r["runs_out_at"],
                    "liquid_at_end": r["rows"][-1]["liquid"], "horizon": r["horizon"]})
    return out


def orders(s: dict, data: dict) -> list[dict]:
    out = []
    for key, label in ORDERS.items():
        r = project(s, data, {"order": key})
        out.append({"key": key, "label": label, "lasts": r["lasts"], "runs_out_at": r["runs_out_at"],
                    "total_tax": r["total_tax"], "estate": r["estate"], "iht": r["iht"]["tax"],
                    "chosen": key == (s.get("withdrawal_order") or "isa_first")})
    return out


def analyse(full: bool = True, theme_scenarios: list[dict] | None = None) -> dict:
    s = settings()
    data = gather(s)
    dob = dob_of(s)
    gaps = missing(s, data)
    sp = statepension.estimate(s, dob) if dob else None
    out = {"settings": s, "missing": gaps, "orders_available": ORDERS, "nations": NATIONS,
           "assumption_notes": ASSUMPTION_NOTES, "state_pension": sp,
           "spa": statepension.describe_age(dob) if dob else None,
           "start": {"pots": data["pots"], "mix": data["mix"], "dcs": data["dcs"], "dbs": data["dbs"],
                     "annuities": data["annuities"], "property": data["property"],
                     "mortgages": [m["summary"] for m in data["mortgages"]],
                     "missing_fx": data["missing_fx"]},
           "rules": R.summary(), "checked": R.CHECKED, "market": R.MARKET}
    if gaps:
        out["ready"] = False
        return out
    base = project(s, data)
    out.update(ready=True, plan=base)
    if full:
        out["need"] = need(s, data)
        out["levers"] = [] if base["lasts"] else levers(s, data)
        out["stresses"] = stresses(s, data, theme_scenarios)
        out["orders"] = orders(s, data)
    return out
