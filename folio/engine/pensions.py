"""Pensions: the records, checked on the way in.

Four kinds, because they behave differently enough that one form would mislead:

* **db** — a promise of so much a year (final salary or career average, like the NHS or
  teachers' schemes). Not a pot: it is shown as income, never added to net worth as
  though it could be spent tomorrow.
* **dc** — a pot (a workplace pension, a personal pension). Grows, can be drawn, 25% of
  it can usually come out tax-free.
* **annuity** — an income already bought.
* **sa_ra** — a South African retirement annuity, held in rand.

A SIPP run on an investment platform is tracked under Investments; adding it here as
well would count it twice, and the form says so.
"""

from __future__ import annotations

from .. import db

KINDS = {
    "db": "Final salary or career average",
    "dc": "Pension pot",
    "annuity": "Annuity (income already bought)",
    "sa_ra": "South African retirement annuity",
}
INDEXATION = {"cpi": "Rises with prices (CPI)", "capped": "Rises with prices, up to a cap",
              "fixed": "Rises by a fixed amount", "none": "Doesn't rise (level)"}
TAKE = {"drawdown": "Drawdown: take what you need", "annuity": "Buy an annuity",
        "lump": "Take it all as cash"}

FIELDS = {
    "name": str, "kind": str, "provider": str, "currency": str,
    "pot": float, "pot_as_of": str, "yearly": float, "yearly_as_of": str,
    "start_age": float, "normal_age": float, "early_reduction": float, "lump_sum": float,
    "commute_pct": float, "commute_factor": float, "indexation": str, "index_cap": float,
    "accruing": bool, "accrual_yearly": float, "contrib_monthly": float, "growth": float,
    "charges": float, "take": str, "spouse_pct": float, "nominee": str, "in_plan": bool,
    "notes": str,
}
LIMITS = {"pot": (0, 50_000_000), "yearly": (0, 2_000_000), "start_age": (40, 90),
          "normal_age": (50, 75), "early_reduction": (0, 20), "lump_sum": (0, 5_000_000),
          "commute_pct": (0, 100), "commute_factor": (1, 40), "index_cap": (0, 10),
          "accrual_yearly": (0, 200_000), "contrib_monthly": (0, 100_000), "growth": (-5, 15),
          "charges": (0, 5), "spouse_pct": (0, 100)}


class PensionError(ValueError):
    pass


def clean(body: dict, partial: bool = False) -> dict:
    out = {}
    for k, kind in FIELDS.items():
        if k not in body:
            continue
        v = body[k]
        if v in ("", None):
            out[k] = None
            continue
        if kind is float:
            try:
                f = float(str(v).replace(",", "").replace("£", "").replace("%", "").strip())
            except ValueError:
                raise PensionError(f"“{v}” isn't a number ({k.replace('_', ' ')}).") from None
            lo, hi = LIMITS.get(k, (None, None))
            if lo is not None and not lo <= f <= hi:
                raise PensionError(f"{k.replace('_', ' ').capitalize()} should be between {lo:g} and {hi:g}.")
            out[k] = f
        elif kind is bool:
            out[k] = 1 if v in (True, 1, "1", "true", "on", "yes") else 0
        else:
            out[k] = str(v).strip()[:400] or None
    if not partial and not out.get("name"):
        raise PensionError("Give the pension a name, for example “NHS Pension” or “Aviva workplace pension”.")
    if "kind" in out and out["kind"] not in KINDS:
        raise PensionError("Unknown kind of pension.")
    if "indexation" in out and out["indexation"] and out["indexation"] not in INDEXATION:
        raise PensionError("Unknown way of rising.")
    if "take" in out and out["take"] and out["take"] not in TAKE:
        raise PensionError("Unknown way of taking it.")
    if out.get("currency"):
        out["currency"] = out["currency"].upper()[:3]
    return out


def add(body: dict) -> int:
    vals = clean(body)
    vals.setdefault("kind", "dc")
    if vals["kind"] == "sa_ra":
        vals.setdefault("currency", "ZAR")
    vals["created_at"] = db.now()
    cols = list(vals)
    with db.tx() as c:
        cur = c.execute(f"INSERT INTO pensions({','.join(cols)}, sort) VALUES({','.join('?' * len(cols))},"  # nosec B608  # fixed column names
                        " (SELECT COALESCE(MAX(sort),0)+1 FROM pensions))", tuple(vals.values()))
        return cur.lastrowid


def update(pid: int, body: dict) -> None:
    vals = clean(body, partial=True)
    if "name" in vals and not vals["name"]:
        raise PensionError("A pension needs a name.")
    if not vals:
        return
    db.execute(f"UPDATE pensions SET {', '.join(f'{k}=?' for k in vals)} WHERE id=?",  # nosec B608  # fixed column names
               (*vals.values(), int(pid)))


def remove(pid: int) -> None:
    db.execute("DELETE FROM pensions WHERE id=?", (int(pid),))


def all_rows() -> list[dict]:
    return db.rows("SELECT * FROM pensions ORDER BY sort, id")


def describe(p: dict) -> str:
    """One line a person can check against their paperwork."""
    ccy = "R" if (p.get("currency") or "GBP") == "ZAR" else "£"
    if p["kind"] in ("db", "annuity"):
        amt = f"{ccy}{p['yearly']:,.0f} a year" if p.get("yearly") is not None else "amount not entered"
        age = p.get("start_age") or p.get("normal_age")
        return f"{amt}{f' from {age:g}' if age else ''}"
    amt = f"{ccy}{p['pot']:,.0f} pot" if p.get("pot") is not None else "value not entered"
    return amt + (f", {ccy}{p['contrib_monthly']:,.0f} a month going in" if p.get("contrib_monthly") else "")
