"""UK income tax and employee National Insurance, for one person and one year.

Enough to plan with, not to file a return with: earnings and pensions (Scottish bands
for a Scottish taxpayer), savings interest and dividends stacked on top in the usual
order, the personal allowance tapering away above £100,000, and Class 1 National
Insurance on earnings below State Pension age. Every threshold comes from `ukrules`.

`factor` scales every threshold. The retirement plan passes the real value of a frozen
threshold in a future year (see `ukrules.real_factor`) so that its sums stay in today's
money while the freeze quietly drags more income into tax.
"""

from __future__ import annotations

import datetime as dt

from . import ukrules as R


def _personal_allowance(adjusted_net: float, nation: str, factor: float) -> float:
    pa = R.INCOME_TAX[nation]["personal_allowance"] * factor
    over = adjusted_net - R.INCOME_TAX[nation]["taper_from"] * factor
    if over > 0:
        pa = max(0.0, pa - over / 2)
    return pa


def _bands(nation: str, factor: float) -> list[tuple[float | None, float, str]]:
    conf = R.INCOME_TAX[nation]
    out = []
    for (limit, rate), name in zip(conf["bands"], conf["names"]):
        out.append((None if limit is None else limit * factor, rate, name))
    return out


def _slice_tax(start: float, amount: float, bands: list[tuple[float | None, float, str]],
               rates: dict | None = None) -> tuple[float, list[tuple[str, float]]]:
    """Tax on `amount` of taxable income sitting above `start` in the bands. `rates`
    swaps each band's rate by name (savings and dividends use their own)."""
    tax, used, pos, end = 0.0, [], start, start + max(0.0, amount)
    lower = 0.0
    for limit, rate, name in bands:
        top = float("inf") if limit is None else limit
        lo, hi = max(pos, lower), min(end, top)
        if hi > lo:
            r = (rates or {}).get(name, rate)
            tax += (hi - lo) * r
            used.append((name, hi - lo))
        lower = top
        if end <= top:
            break
    return tax, used


def _uk_band_name(position: float, factor: float) -> str:
    b = _bands("ruk", factor)
    for limit, _r, name in b:
        if limit is None or position <= limit:
            return name
    return "additional"


def income_tax(non_savings: float, nation: str = "ruk", factor: float = 1.0,
               savings: float = 0.0, dividends: float = 0.0,
               on: dt.date | None = None) -> dict:
    """Tax on a year's income. `non_savings` is earnings, pensions and the like, after
    any pension contributions taken before tax."""
    nation = R.nation_key(nation)
    on = on or dt.date.today()
    non_savings, savings, dividends = max(0.0, non_savings), max(0.0, savings), max(0.0, dividends)
    total = non_savings + savings + dividends
    pa = _personal_allowance(total, nation, factor)
    # The allowance is used against earnings and pensions first, then savings, then dividends.
    pa_ns = min(pa, non_savings)
    pa_sav = min(pa - pa_ns, savings)
    pa_div = min(pa - pa_ns - pa_sav, dividends)
    taxable_ns = non_savings - pa_ns
    taxable_sav = savings - pa_sav
    taxable_div = dividends - pa_div

    ns_tax, ns_used = _slice_tax(0.0, taxable_ns, _bands(nation, factor))

    # Savings and dividends use the UK's bands even for a Scottish taxpayer, stacked on top
    # of earnings and pensions.
    uk = _bands("ruk", factor)
    pos = taxable_ns
    sav_tax = 0.0
    if taxable_sav:
        start_band = max(0.0, R.SAVINGS["starting_band"] * factor - taxable_ns)
        at_zero = min(start_band, taxable_sav)
        band = _uk_band_name(taxable_ns + taxable_sav + taxable_div, factor)
        psa = R.SAVINGS["allowance"][band] * factor
        free = min(taxable_sav - at_zero, psa)
        rates = R.savings_rates(on)
        sav_tax, _ = _slice_tax(pos + at_zero + free, taxable_sav - at_zero - free, uk, rates)
    pos += taxable_sav
    div_tax = 0.0
    if taxable_div:
        free = min(taxable_div, R.DIVIDENDS["allowance"] * factor)
        div_tax, _ = _slice_tax(pos + free, taxable_div - free, uk,
                                {"basic": R.DIVIDENDS["basic"], "higher": R.DIVIDENDS["higher"],
                                 "additional": R.DIVIDENDS["additional"]})
    tax = ns_tax + sav_tax + div_tax
    top = ns_used[-1][0] if ns_used else None
    marginal = 0.0
    if taxable_ns > 0:
        marginal = next(r for (limit, r, name) in _bands(nation, factor) if name == top)
        # Inside the taper, each £1 more also loses 50p of allowance.
        if R.INCOME_TAX[nation]["taper_from"] * factor < total and pa > 0:
            marginal *= 1.5
    return {"tax": round(tax, 2), "personal_allowance": round(pa, 2),
            "non_savings_tax": round(ns_tax, 2), "savings_tax": round(sav_tax, 2),
            "dividend_tax": round(div_tax, 2), "top_band": top or "none",
            "marginal": marginal, "taxable": round(taxable_ns + taxable_sav + taxable_div, 2)}


def national_insurance(earnings: float, factor: float = 1.0, over_pension_age: bool = False) -> float:
    if over_pension_age or earnings <= 0:
        return 0.0
    pt, uel = R.NI["primary_threshold"] * factor, R.NI["upper_limit"] * factor
    main = max(0.0, min(earnings, uel) - pt) * R.NI["main"]
    upper = max(0.0, earnings - uel) * R.NI["upper"]
    return round(main + upper, 2)


def take_home(gross: float, nation: str = "ruk", pension_pct: float = 0.0,
              method: str = "net_pay", factor: float = 1.0, over_pension_age: bool = False,
              other_taxable: float = 0.0) -> dict:
    """A salary after pension contributions, income tax and NI.

    `method`: 'net_pay' (taken before tax, as public-sector schemes do), 'salary_sacrifice'
    (before tax and NI), or 'relief_at_source' (paid from take-home pay; the provider adds
    basic-rate relief, and higher-rate relief is claimed back — modelled here as the
    pension receiving the gross amount and take-home falling by 80% of it)."""
    gross = max(0.0, gross)
    contrib = gross * max(0.0, pension_pct) / 100.0
    if method == "salary_sacrifice":
        taxable, ni_base = gross - contrib, gross - contrib
    elif method == "relief_at_source":
        taxable, ni_base = gross, gross
    else:
        taxable, ni_base = gross - contrib, gross
    it = income_tax(taxable + other_taxable, nation, factor)
    tax_other = income_tax(other_taxable, nation, factor)["tax"] if other_taxable else 0.0
    tax = it["tax"] - tax_other
    ni = national_insurance(ni_base, factor, over_pension_age)
    net = gross - tax - ni - (contrib * 0.8 if method == "relief_at_source" else contrib)
    if method == "relief_at_source" and it["marginal"] > 0.2:
        # Higher-rate relief claimed back through the tax return.
        net += contrib * (min(it["marginal"], 0.45) - 0.2)
    return {"gross": round(gross, 2), "pension_in": round(contrib, 2), "tax": round(tax, 2),
            "ni": round(ni, 2), "net": round(net, 2), "marginal": it["marginal"],
            "top_band": it["top_band"]}
