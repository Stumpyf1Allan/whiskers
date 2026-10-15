"""The figures the government sets, in one place, each with the date it applies from,
where it came from, and when it was last checked.

Nothing else in the app writes a tax band or an allowance down. When a Budget changes
one, it changes here, once — and every screen that uses it follows. Figures are kept as
the law states them (nominal pounds). The retirement plan works in today's money, so it
asks `real()` for a threshold in a future year: frozen thresholds shrink in real terms
until the freeze ends, which is the fiscal drag the freeze was announced to produce.

Checked against the sources below on 15 October 2026. The UK Budget on 28 October 2026
may change some of them.
"""

from __future__ import annotations

import datetime as dt

CHECKED = "2026-10-15"

#: Tax year the latest known figures belong to ("2026" = 6 April 2026 to 5 April 2027).
LATEST_TAX_YEAR = 2026

#: Income tax thresholds and the National Insurance limits are frozen in cash terms up to
#: and including this tax year (the Autumn Budget 2025 extended the freeze to April 2031).
#: After it, the plan assumes they rise with prices again.
FROZEN_UNTIL_TAX_YEAR = 2030

SOURCES = {
    "income_tax": "https://www.gov.uk/income-tax-rates",
    "scottish_tax": "https://www.gov.scot/publications/scottish-income-tax-rates-and-bands/pages/2026-to-2027/",
    "dividends_savings": "https://www.gov.uk/government/publications/income-tax-changes-to-tax-rates-for-property-savings-and-dividend-income/income-tax-changes-to-tax-rates-for-property-savings-and-dividend-income",
    "state_pension": "https://www.gov.uk/new-state-pension/what-youll-get",
    "state_pension_age": "https://www.which.co.uk/news/article/state-pension-age-rising-when-will-you-qualify-acvYJ8U38PLJ",
    "ni_top_up": "https://www.which.co.uk/money/pensions-and-retirement/state-pension/guides/can-i-top-up-my-state-pension",
    "pension_iht": "https://pensionsage.com/pa/Pensions-to-come-into-scope-of-IHT-from-April-2027-as-Finance-Bill-reaches-Royal-Assent.php",
    "isa": "https://www.crowe.com/uk/crowefinancialplanning/insights/isa-changes",
    "fscs": "https://www.fscs.org.uk/",
    "codi": "https://resbank.co.za/en/home/what-we-do/Deposit-insurance/CODI-Frequently-Asked-Questions",
    "sa_tfsa": "https://www.sars.gov.za/types-of-tax/personal-income-tax/tax-free-investments/",
    "mortgage_rates": "https://www.itv.com/news/2026-10-05/mortgage-misery-as-average-five-year-deal-hits-6-for-first-time-in-three-years",
}

# ---------------------------------------------------------------------------- income tax

#: Bands on *taxable* income (after the personal allowance), as (upper limit, rate). The
#: last band has no upper limit. England, Wales and Northern Ireland share one set.
INCOME_TAX = {
    "ruk": {
        "personal_allowance": 12570,
        "taper_from": 100000,            # £1 of allowance lost for every £2 above this
        "bands": [(37700, 0.20), (125140, 0.40), (None, 0.45)],
        "names": ["basic", "higher", "additional"],
    },
    # Scotland sets its own bands on earnings and pensions (not on savings or dividends,
    # which use the UK's). 2026-27, from the Scottish Rate Resolution.
    "scotland": {
        "personal_allowance": 12570,
        "taper_from": 100000,
        "bands": [(3967, 0.19), (16956, 0.20), (31092, 0.21), (62430, 0.42),
                  (125140, 0.45), (None, 0.48)],
        "names": ["starter", "basic", "intermediate", "higher", "advanced", "top"],
    },
}

#: Employee Class 1 National Insurance, 2026-27. Not paid from State Pension age.
NI = {"primary_threshold": 12570, "upper_limit": 50270, "main": 0.08, "upper": 0.02}

#: Dividends (UK-wide). The ordinary and upper rates rose by 2 points from 6 April 2026.
DIVIDENDS = {"allowance": 500, "basic": 0.1075, "higher": 0.3575, "additional": 0.3935}

#: Savings interest (UK-wide). Rates rise by 2 points from 6 April 2027.
SAVINGS = {
    "allowance": {"basic": 1000, "higher": 500, "additional": 0},
    "starting_band": 5000,
    "rates": [("2026-04-06", {"basic": 0.20, "higher": 0.40, "additional": 0.45}),
              ("2027-04-06", {"basic": 0.22, "higher": 0.42, "additional": 0.47})],
}

# ---------------------------------------------------------------------------- pensions

STATE_PENSION = {
    "full_weekly": 241.30,             # 2026-27, the full new State Pension
    "years_for_full": 35,
    "min_years": 10,
    "class3_weekly": 18.40,            # voluntary NI, 2026-27
    # Gaps can usually be filled for the past six tax years; each 5 April closes one.
    "top_up_years_back": 6,
}

PENSIONS = {
    "lump_sum_allowance": 268275,      # most tax-free cash anyone can take, in total
    "tax_free_share": 0.25,
    "annual_allowance": 60000,
    "money_purchase_annual_allowance": 10000,
    "minimum_access_age_from_2028": 57,  # the normal minimum pension age rises on 6 April 2028
    "minimum_access_age": 55,
    "iht_from": "2027-04-06",          # unused pensions count in the estate from this day
}

IHT = {"nil_rate_band": 325000, "residence_band": 175000, "taper_from": 2000000, "rate": 0.40,
       "frozen_until_tax_year": 2030}

# ---------------------------------------------------------------------------- savings

ISA = {"allowance": 20000, "cash_cap_under_65_from": "2027-04-06", "cash_cap": 12000,
       "lisa": 4000}

PROTECTION = {
    "fscs_deposits": 120000,           # per person, per banking licence (from 1 Dec 2025)
    "fscs_investments": 85000,         # per person, per firm
    "codi_zar": 100000,                # South Africa: per depositor, per bank, interest included
}

SOUTH_AFRICA = {"tfsa_year": 46000, "tfsa_lifetime": 500000, "tfsa_penalty": 0.40,
                "sda_year": 2000000, "ra_nonresident_years": 3}

#: The market backdrop a stress test can borrow: today's average new fixed rate.
MARKET = {"avg_fix_2y": 5.98, "avg_fix_5y": 6.00, "as_of": "2026-10-05"}


# ---------------------------------------------------------------------------- helpers

def tax_year_of(d: dt.date | None = None) -> int:
    d = d or dt.date.today()
    return d.year if (d.month, d.day) >= (4, 6) else d.year - 1


def nation_key(nation: str | None) -> str:
    return "scotland" if (nation or "").lower().startswith("scot") else "ruk"


def real_factor(tax_year: int, inflation: float, base_year: int | None = None) -> float:
    """How much a figure frozen in cash terms is worth in today's money in `tax_year`.

    1.0 this year; shrinking by inflation each year while the freeze lasts; level after
    it, when thresholds are assumed to rise with prices again."""
    base = tax_year_of() if base_year is None else base_year
    frozen_years = max(0, min(tax_year, FROZEN_UNTIL_TAX_YEAR) - base)
    return 1.0 / ((1.0 + inflation) ** frozen_years)


def savings_rates(on: dt.date) -> dict:
    out = SAVINGS["rates"][0][1]
    for start, rates in SAVINGS["rates"]:
        if on.isoformat() >= start:
            out = rates
    return out


def summary() -> list[dict]:
    """The figures as a person would want to see them listed, with where each came from."""
    ruk, sco = INCOME_TAX["ruk"], INCOME_TAX["scotland"]
    return [
        {"what": "Personal allowance", "value": f"£{ruk['personal_allowance']:,}",
         "note": "Lost at £1 for every £2 of income over £100,000. Frozen until April 2031.",
         "source": SOURCES["income_tax"]},
        {"what": "Income tax (England, Wales, Northern Ireland)",
         "value": "20% to £50,270, 40% to £125,140, 45% above", "note": "",
         "source": SOURCES["income_tax"]},
        {"what": "Income tax (Scotland)",
         "value": "19%, 20%, 21%, 42%, 45%, 48%",
         "note": f"Bands from £{12571:,} to £{125140:,}: Scotland's own, for earnings and pensions.",
         "source": SOURCES["scottish_tax"]},
        {"what": "Full new State Pension", "value": f"£{STATE_PENSION['full_weekly']:.2f} a week",
         "note": "35 qualifying years for the full amount, 10 for any.", "source": SOURCES["state_pension"]},
        {"what": "Voluntary NI (Class 3)", "value": f"£{STATE_PENSION['class3_weekly']:.2f} a week",
         "note": "One full year adds about 1/35 of the full State Pension.", "source": SOURCES["ni_top_up"]},
        {"what": "Pension tax-free cash", "value": "25%, up to £268,275 in total", "note": "",
         "source": SOURCES["pension_iht"]},
        {"what": "Pensions and inheritance tax", "value": "From 6 April 2027",
         "note": "Unused pensions count in the estate.", "source": SOURCES["pension_iht"]},
        {"what": "Inheritance tax bands", "value": "£325,000 plus £175,000 for a home left to children",
         "note": "40% above. Frozen until April 2031.", "source": SOURCES["pension_iht"]},
        {"what": "ISA allowance", "value": "£20,000 a year",
         "note": "From 6 April 2027, no more than £12,000 of it in cash ISAs for under-65s.",
         "source": SOURCES["isa"]},
        {"what": "FSCS protection", "value": "£120,000 per bank, £85,000 per investment firm",
         "note": "", "source": SOURCES["fscs"]},
        {"what": "South Africa: CoDI deposit insurance", "value": "R100,000 per depositor per bank",
         "note": "Interest included. Unit trusts and shares aren't covered.", "source": SOURCES["codi"]},
        {"what": "South Africa: tax-free savings", "value": "R46,000 a year, R500,000 for life",
         "note": "A 40% penalty on anything over.", "source": SOURCES["sa_tfsa"]},
    ]
