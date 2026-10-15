"""How much of the portfolio rides on AI, and what a fall would cost in pounds.

Exposure is **look-through**: a single company counts in full if it is AI-linked, and a
fund counts for the share of it that is — an S&P 500 fund is partly AI because Nvidia,
Microsoft, Alphabet and friends are some of its biggest holdings. Allan's own review
found true AI and tech exposure of 36% when direct positions alone suggested far less;
that gap is the reason this module exists.

The share for each holding comes from the person, not from here: fund make-ups change
monthly and this app has no trustworthy free source for them. A holding whose share
nobody has set is counted separately and named, never assumed to be zero.
"""

from __future__ import annotations

#: Context for the stress screen. Well-documented history, kept deliberately short.
DOTCOM = ("From March 2000 to October 2002 the Nasdaq-100 fell more than 80% and the "
          "S&P 500 nearly half. The Nasdaq Composite didn't get back to its 2000 peak "
          "until 2015.")


def exposure(pos: list[dict], totals: dict) -> dict:
    """The AI share of everything, from the share set on each holding or its sleeve. A
    well-known fund nobody has rated starts from its index's own weights (see classify),
    marked as typical; anything else unrated is named and left out, never counted as 0."""
    from . import classify
    total = totals.get("total") or 0.0
    pos = [dict(x) for x in pos]
    for x in pos:
        if x["value"] is not None and x["ai_share"] is None:
            d = classify.default_themes(x).get("ai")
            if d is not None:
                x["ai_share"], x["ai_typical"] = d, True
    priced = [x for x in pos if x["value"] is not None]
    unknown = [x for x in priced if x["ai_share"] is None]
    rows = []
    ai_value = 0.0
    for x in priced:
        if x["ai_share"] is None:
            continue
        v = x["value"] * x["ai_share"] / 100
        ai_value += v
        if v > 0:
            rows.append({"name": x["name"], "platform": x["platform"], "value": x["value"],
                         "share": x["ai_share"], "ai_value": v, "instrument_id": x["instrument_id"],
                         "typical": bool(x.get("ai_typical"))})
    # The same shares held on two platforms are one exposure.
    merged: dict[int, dict] = {}
    for r in rows:
        m = merged.setdefault(r["instrument_id"], dict(r, value=0.0, ai_value=0.0, platforms=[]))
        m["value"] += r["value"]
        m["ai_value"] += r["ai_value"]
        m["platforms"].append(r["platform"])
    top = sorted(merged.values(), key=lambda r: r["ai_value"], reverse=True)
    return {
        "total": total, "ai_value": ai_value,
        "ai_pct": (ai_value / total) if total else None,
        "unknown": [{"name": x["name"], "value": x["value"], "instrument_id": x["instrument_id"]}
                    for x in unknown],
        "unknown_value": sum(x["value"] for x in unknown),
        "top": top[:14],
    }


def scenario(exp: dict, totals: dict, ai_fall: float, other_fall: float) -> dict:
    """What the portfolio would be worth if AI-linked holdings fell by `ai_fall` and
    everything else invested fell by `other_fall` (fractions). Cash stays put."""
    total = totals.get("total") or 0.0
    cash = totals.get("cash") or 0.0
    invested = total - cash
    ai = exp["ai_value"]
    other = max(0.0, invested - ai)
    loss_ai = ai * ai_fall
    loss_other = other * other_fall
    after = total - loss_ai - loss_other
    return {"before": total, "after": after, "loss": loss_ai + loss_other,
            "loss_pct": ((loss_ai + loss_other) / total) if total else None,
            "loss_ai": loss_ai, "loss_other": loss_other, "ai": ai, "other": other,
            "cash": cash, "unknown_value": exp["unknown_value"]}


# ---------------------------------------------------------------------------- 2.0: any theme

def replay(theme_key: str, theme_value: float, invested: float, ref: str | None,
           days: int = 5 * 365) -> dict | None:
    """The worst fall the theme's own series has had in the history the app holds, and what
    the same episode would do to today's money: the theme's part falls as the series did,
    everything else invested moves as world shares did over the same dates."""
    import datetime as dt
    from ..market import store
    from . import mathx
    if not ref:
        return None
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    pts = store.points(store.ref_key(ref), since)
    worst = mathx.max_drawdown(pts) if len(pts) > 60 else None
    if not worst or worst["depth"] <= 0.02:
        return None
    world = store.gbp_points(store.ref_key("WORLD"), since)
    w0 = mathx.value_on(world, worst["peak"]) if world else None
    w1 = mathx.value_on(world, worst["trough"]) if world else None
    world_move = (w1 / w0 - 1) if (w0 and w1) else None
    other = max(0.0, invested - theme_value)
    loss = theme_value * worst["depth"] + (other * max(0.0, -world_move) if world_move is not None else 0.0)
    return {"theme": theme_key, "ref": ref, "depth": worst["depth"], "peak": worst["peak"],
            "trough": worst["trough"], "world_move": world_move, "loss": loss,
            "theme_value": theme_value, "other": other}


def standard(pos: list[dict], totals: dict) -> list[dict]:
    """Three what-ifs everybody gets: world shares down a third, interest rates up a
    point, and the rand down a fifth for anyone holding rand."""
    from . import classify
    out = []
    shares = sum(x["value"] for x in pos if x["value"] is not None
                 and classify.asset_class(x)[0] in ("equity", "property", "crypto"))
    mixed = sum(x["value"] for x in pos if x["value"] is not None and classify.asset_class(x)[0] == "mixed")
    out.append({"key": "world_third", "label": "Shares everywhere fall by a third",
                "loss": (shares + 0.6 * mixed) / 3,
                "why": "About what world shares lost in 2008-09 and in 2020's first weeks."})
    bond_loss, unknown_duration = 0.0, []
    for x in pos:
        if x["value"] is None:
            continue
        cls, _ = classify.asset_class(x)
        if cls in ("bond", "linker"):
            dur, _ = classify.duration(x)
            if dur is None:
                unknown_duration.append(x["name"])
                dur = 7.0
            bond_loss += x["value"] * dur / 100
        elif cls == "mixed":
            bond_loss += x["value"] * 0.4 * 7.0 / 100
    if bond_loss:
        out.append({"key": "rates_up", "label": "Interest rates rise by one point",
                    "loss": bond_loss,
                    "why": "A bond fund loses roughly its duration in per cent for each point "
                           "rates rise." + (f" Duration not known for {', '.join(unknown_duration[:3])}: "
                                            f"7 years assumed." if unknown_duration else "")})
    rand = sum(p["cash"] or 0.0 for p in totals.get("platforms", []) if p.get("currency") == "ZAR")
    if rand:
        out.append({"key": "rand_down", "label": "The rand falls by a fifth against the pound",
                    "loss": rand * 0.2, "why": "It has done so within a year more than once."})
    return out
