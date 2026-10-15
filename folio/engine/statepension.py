"""The State Pension: when it starts, roughly how much, and whether filling a gap pays.

The age follows the timetable in law today (Pensions Acts 2007 and 2014): 66, rising to
67 for anyone born from 6 April 1960 (in monthly steps for the first eleven months of
births), and to 68 for anyone born from 6 April 1977 under the 2007 Act — a rise the
government is reviewing and could bring forward, which the screen says.

The amount is the person's own forecast from gov.uk whenever they have one. Without it,
a rough figure from qualifying years: 35 for the full new State Pension, at least 10 for
any. A forecast already assumes contributions continue to State Pension age; the rough
figure adds the working years still to come, and says it is rough.
"""

from __future__ import annotations

import datetime as dt

from . import ukrules as R


def _add_months(d: dt.date, months: int) -> dt.date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.date(y, m, min(d.day, last))


def age_months(dob: dt.date) -> tuple[int, str]:
    """State Pension age in months, and a note when the law may yet change it."""
    if dob < dt.date(1960, 4, 6):
        return 66 * 12, ""
    if dob < dt.date(1961, 3, 6):
        # 6 April–5 May 1960 is 66 and 1 month; each later month of births adds one more.
        k = (dob.year - 1960) * 12 + dob.month - 4 + (0 if dob.day >= 6 else -1)
        return 66 * 12 + min(11, max(1, k + 1)), ""
    if dob < dt.date(1977, 4, 6):
        return 67 * 12, ""
    note = ("Under current law it rises to 68 between 2044 and 2046. The government is "
            "reviewing this and could bring it forward, with at least 10 years' notice.")
    if dob < dt.date(1978, 4, 6):
        k = (dob.year - 1977) * 12 + dob.month - 4 + (0 if dob.day >= 6 else -1)
        return 67 * 12 + min(12, max(1, k + 1)), note
    return 68 * 12, note


def pension_date(dob: dt.date) -> dt.date:
    months, _ = age_months(dob)
    return _add_months(dob, months)


def describe_age(dob: dt.date) -> dict:
    months, note = age_months(dob)
    y, m = divmod(months, 12)
    when = pension_date(dob)
    words = f"{y}" + (f" and {m} month{'s' if m != 1 else ''}" if m else "")
    return {"months": months, "age": months / 12, "words": words, "date": when.isoformat(),
            "note": note, "source": R.SOURCES["state_pension_age"]}


def estimate(settings: dict, dob: dt.date | None, today: dt.date | None = None) -> dict:
    """{weekly, yearly, basis, years_at_pension_age, short_by, top_up} in today's money."""
    today = today or dt.date.today()
    sp = settings.get("state_pension") or {}
    full = R.STATE_PENSION["full_weekly"]
    weekly = sp.get("weekly")
    years = sp.get("years")
    out = {"full_weekly": full, "basis": "none", "weekly": None, "yearly": None,
           "years": years, "years_at_pension_age": None, "short_by": None, "top_up": None}
    if dob is None:
        out["basis"] = "no date of birth"
        return out
    when = pension_date(dob)
    stop_age = settings.get("stop_age")
    working_years_left = 0
    if stop_age:
        stop = _add_months(dob, int(round(float(stop_age) * 12)))
        last = min(stop, when)
        working_years_left = max(0, (last - today).days // 365)
    if years is not None:
        out["years_at_pension_age"] = min(50, int(years) + working_years_left)
    if weekly not in (None, ""):
        out.update(weekly=float(weekly), basis="your forecast")
    elif years is not None:
        y = out["years_at_pension_age"]
        out.update(weekly=0.0 if y < R.STATE_PENSION["min_years"] else round(full * min(y, 35) / 35, 2),
                   basis="rough, from qualifying years")
    if out["weekly"] is not None:
        out["yearly"] = round(out["weekly"] * 52, 2)
    # Filling gaps: what one year costs and what it adds, when it could add anything.
    gaps = sp.get("gaps")
    y_at = out["years_at_pension_age"]
    if y_at is not None and y_at < 35:
        out["short_by"] = 35 - y_at
    if gaps and (out["short_by"] or (out["weekly"] is not None and out["weekly"] < full - 0.5)):
        cost = R.STATE_PENSION["class3_weekly"] * 52
        adds = full / 35 * 52
        n = int(gaps) if out["short_by"] is None else min(int(gaps), out["short_by"])
        deadline_year = R.tax_year_of(today) - R.STATE_PENSION["top_up_years_back"] + 1
        out["top_up"] = {"years": n, "cost_each": round(cost, 2), "adds_each": round(adds, 2),
                         "pays_back_years": round(cost / adds, 1),
                         "oldest_deadline": f"5 April {R.tax_year_of(today) + 1}",
                         "oldest_year": f"{deadline_year - 1}/{str(deadline_year)[-2:]}",
                         "source": R.SOURCES["ni_top_up"]}
    return out
