"""Everything that deserves a look, in one list, worst first.

Rules the person has set — "trim Alphabet back to 8% when it passes 9.3%" — are checked
here, alongside the limits that come with the territory: each platform against the FSCS
protection limit, each sleeve against its band, and the gaps in the data that would make
any of those figures wrong.

A warning always says what was found, what it is being compared with, and where to go
about it. Where a rule implies a trade, the size is given as arithmetic on the person's
own rule — "selling about £1,900 brings it back to 8%" — never as advice to do it.
"""

from __future__ import annotations

from .. import db
from . import isa

ORDER = {"red": 0, "amber": 1, "info": 2, "green": 3}


def _month_ago_sleeves() -> dict:
    """Sleeve shares from the daily snapshot of about a month ago, when there is one."""
    import datetime as dt
    import json
    lo = (dt.date.today() - dt.timedelta(days=40)).isoformat()
    hi = (dt.date.today() - dt.timedelta(days=25)).isoformat()
    row = db.one("SELECT detail FROM snapshots WHERE d BETWEEN ? AND ? ORDER BY d LIMIT 1", (lo, hi))
    try:
        return (json.loads(row["detail"]) or {}).get("_sleeves", {}) if row else {}
    except (ValueError, TypeError):
        return {}


def _drift_trend(r: dict, then: float | None) -> str:
    """A drift is a trend or a jolt; last month's share says which."""
    if then is None:
        return ""
    before, now = abs(then - r["target"]), abs(r["actual"] - r["target"])
    if abs(now - before) < 0.2:
        return f" A month ago it was {then:.1f}%, so this has been the case for a while."
    return (f" A month ago it was {then:.1f}%, so it is moving "
            f"{'further from' if now > before else 'back towards'} its target.")


def _money(v: float) -> str:
    return f"£{v:,.0f}"


def company_exposure(pos: list[dict], total: float, company: str) -> dict:
    name = (company or "").strip().lower()
    direct = [x for x in pos if (x["company"] or "").strip().lower() == name and x["value"] is not None]
    direct_value = sum(x["value"] for x in direct)
    fund_values: dict[int, float] = {}
    for x in pos:
        if x["value"] is not None:
            fund_values[x["instrument_id"]] = fund_values.get(x["instrument_id"], 0.0) + x["value"]
    look = db.rows("SELECT l.fund_id, l.weight, l.as_of, i.name FROM lookthrough l "
                   "JOIN instruments i ON i.id=l.fund_id WHERE lower(l.company)=?", (name,))
    via = [{"fund_id": r["fund_id"], "name": r["name"], "weight": r["weight"], "as_of": r["as_of"],
            "value": fund_values.get(r["fund_id"], 0.0) * r["weight"] / 100} for r in look]
    lt_value = sum(v["value"] for v in via)
    return {"company": company, "direct_value": direct_value,
            "direct_pct": (direct_value / total * 100) if total else None,
            "true_value": direct_value + lt_value,
            "true_pct": ((direct_value + lt_value) / total * 100) if total else None,
            "holdings": [{"name": x["name"], "platform": x["platform"], "value": x["value"]}
                         for x in direct],
            "via_funds": via}


def _companies(pos: list[dict], total: float, basis: str, skip: set[str]) -> list[dict]:
    """Every single company held directly, with its share of everything (counting what
    funds hold when the basis is "true"), biggest first. A holding counts as its company
    when the company is set on it, or by its own name when it is plainly one company."""
    from . import classify
    groups: dict[str, dict] = {}
    for x in pos:
        if x["value"] is None:
            continue
        name = (x.get("company") or "").strip()
        if not name and classify.is_single_company(x):
            name = (x.get("name") or "").strip()
        if not name or name.lower() in skip:
            continue
        g = groups.setdefault(name.lower(), {"company": name, "direct": 0.0})
        g["direct"] += x["value"]
    out = []
    for g in groups.values():
        value = g["direct"]
        if basis == "true":
            value += sum(v["value"] for v in company_exposure(pos, total, g["company"])["via_funds"])
        if total:
            out.append({"company": g["company"], "pct": value / total * 100, "value": value})
    return sorted(out, key=lambda c: -c["pct"])


def theme_lights(theme: str, market: dict | None = None) -> dict:
    """How many of a theme's warning lights are red now, from the market reading when the
    theme is watched, or read on the spot when it isn't."""
    lights = [x for x in (market or {}).get("lights", []) if x.get("group") == theme]
    if not lights:
        from . import signals, themes
        lights = [signals.reading(d) for d in themes.lights_for(theme)]
    levels = [x["level"] for x in lights]
    return {"reds": sum(1 for x in levels if x == "red"), "ambers": sum(1 for x in levels if x == "amber"),
            "have": sum(1 for x in levels if x != "none"), "of": len(levels),
            "red_titles": [x["title"] for x in lights if x["level"] == "red"]}


def theme_fall(theme: str) -> dict | None:
    """How far a theme's own index is below its high of the past year, judged on a 5-day
    average like the lights, so one bad day can't trigger a purchase."""
    from . import mathx, signals, themes
    ref = (themes.LIBRARY.get(theme) or {}).get("scenario_ref")
    if not ref:
        return None
    pts = signals._series(ref)
    if len(pts) < 60:
        return None
    vals = [v for _, v in pts]
    sm = mathx.sma(vals, signals.SMOOTH)
    vals = [a if a is not None else v for a, v in zip(sm, vals)]
    dd = mathx.drawdowns(vals, 252)
    return {"fall": dd[-1] * 100, "as_of": pts[-1][0], "ref": ref}


def _sleeve_values(pos: list[dict], totals: dict) -> dict[str, float]:
    from . import allocation
    return {r["name"]: r["value"] for r in allocation.view(pos, totals)["sleeves"]}


def steps_done() -> dict:
    return db.get_meta("steps_done", {}) or {}


def mark_done(rule_id: int, on: str | None = None) -> None:
    done = steps_done()
    done[str(rule_id)] = on or db.today()
    db.set_meta("steps_done", done)


def rule_status(pos: list[dict], totals: dict, exp: dict | None = None,
                market: dict | None = None) -> list[dict]:
    total = totals.get("total") or 0.0
    out = []
    rules = db.rows("SELECT * FROM rules WHERE enabled=1 ORDER BY id")
    own = {(r["subject"] or "").strip().lower() for r in rules if r["kind"] == "company_cap"}
    values = None
    done = steps_done()
    cleared = False
    for r in rules:
        trig = float(r["trigger_pct"])
        tgt = float(r["target_pct"]) if r["target_pct"] is not None else None
        if r["kind"] in ("theme_step", "theme_dip"):
            # Steps agreed in calm weather: a level of their own, not a cap's.
            if values is None:
                values = _sleeve_values(pos, totals)
            from_value = values.get(r.get("sleeve") or "")
            item = {"rule": r, "detail": {"from_value": from_value, "into": r.get("into_sleeve"), "sleeve": r.get("sleeve")}}
            if r["kind"] == "theme_step":
                tl = theme_lights(r["subject"], market)
                item["now"] = tl["reds"] if tl["have"] else None
                item["detail"].update(tl)
                at = tl["reds"] >= trig
                if not tl["have"]:
                    item["level"] = "none"
                elif at:
                    item["level"] = "red"
                elif tl["reds"] == trig - 1 and (tl["reds"] or tl["ambers"]):
                    item["level"] = "amber"
                else:
                    item["level"] = "green"
                item["move"] = (from_value or 0.0) * (tgt if tgt is not None else 33.0) / 100
            else:
                tf = theme_fall(r["subject"])
                item["now"] = tf["fall"] if tf else None
                item["detail"].update(tf or {})
                at = bool(tf) and tf["fall"] >= trig
                item["level"] = ("none" if not tf else "amber" if at else
                                 "info" if tf["fall"] >= 0.75 * trig else "green")
                item["move"] = (tgt or 0.0) / 100 * total
            key = str(r["id"])
            if key in done:
                if at:
                    item["done"] = done[key]
                else:
                    # The lights have cleared since the step was taken: it applies again next time.
                    done.pop(key)
                    cleared = True
            out.append(item)
            continue
        if r["kind"] == "any_company_cap":
            cos = _companies(pos, total, r["basis"], own)
            top = cos[0] if cos else None
            item = {"rule": r, "now": top["pct"] if top else None,
                    "detail": {"company": top["company"] if top else None, "companies": cos[:6],
                               "over": [c for c in cos if c["pct"] > trig]}}
        elif r["kind"] == "company_cap":
            ce = company_exposure(pos, total, r["subject"])
            now = ce["true_pct"] if r["basis"] == "true" else ce["direct_pct"]
            item = {"rule": r, "now": now, "detail": ce}
        elif r["kind"] == "theme_cap":
            v = sum(x["value"] for x in pos if x["value"] is not None
                    and (x["theme"] or "").strip().lower() == (r["subject"] or "").strip().lower())
            item = {"rule": r, "now": (v / total * 100) if total else None, "detail": {"value": v}}
        elif r["kind"] == "ai_cap":
            item = {"rule": r, "now": (exp["ai_pct"] * 100) if exp and exp.get("ai_pct") is not None
                    else None, "detail": {}}
        elif r["kind"] == "exposure_cap":
            # 2.0: a cap on any watch theme — gold, oil, rand — counting what funds hold.
            from . import themes
            key = (r["subject"] or "").strip().lower()
            if key == "rand":
                e = next((x for x in themes.all_exposures(pos, totals) if x["theme"] == "rand"), None)
            else:
                e = themes.exposure(pos, totals, key)
            item = {"rule": r, "now": (e["pct"] * 100) if e and e.get("pct") is not None else None,
                    "detail": {"value": (e or {}).get("value")}}
        else:
            continue
        now = item["now"]
        if now is None:
            item["level"] = "none"
        else:
            back_to = tgt if tgt is not None else trig
            amber_from = back_to + (trig - back_to) / 2 if tgt is not None else trig * 0.9
            item["level"] = "red" if now > trig else "amber" if now > amber_from else "green"
            item["amber_from"] = amber_from
            item["trim"] = max(0.0, (now - back_to) / 100 * total) if now > back_to else 0.0
        out.append(item)
    if cleared:
        db.set_meta("steps_done", done)
    return out


def _step_warning(s: dict) -> dict | None:
    """A parachute step or a buying point, in the words agreed when it was set."""
    from . import themes
    r, d = s["rule"], s["detail"]
    if s["level"] in ("green", "none") or s.get("done"):
        return None
    title_t = themes.title(r["subject"] or "")
    note = (r["note"] or "").replace("Parachute: ", "").replace("Waiting for a fall: ", "")
    if r["kind"] == "theme_step":
        if s["level"] == "red":
            title = (f"{title_t}: {d['reds']} of its {d['of']} warning lights are red — the step you agreed "
                     f"applies")
            detail = (f"{note[:1].upper() + note[1:] if note else ''} That is about {_money(s['move'])}: from "
                      f"{r['sleeve']} into {r['into_sleeve']}. Red: {', '.join(d['red_titles'])}.").strip()
        else:
            title = f"{title_t}: {d['reds']} of {d['of']} warning lights red — one more and your agreed step applies"
            detail = note[:1].upper() + note[1:] if note else ""
        return {"id": f"rule:{r['id']}", "level": s["level"], "kind": "step", "title": title,
                "detail": detail, "go": "ai"}
    fall = s["now"] or 0.0
    if s["level"] == "amber":
        title = f"{title_t} is {fall:.0f}% below its high — the fall you were waiting for"
        detail = (f"Your plan: move about {r['target_pct']:g} points ({_money(s['move'])}) from {r['sleeve']} "
                  f"into {r['into_sleeve']}, and raise {r['into_sleeve']}'s target to match.")
    else:
        title = f"{title_t} is {fall:.0f}% below its high; your plan buys at {r['trigger_pct']:g}%"
        detail = note[:1].upper() + note[1:] if note else ""
    return {"id": f"rule:{r['id']}", "level": s["level"], "kind": "step", "title": title, "detail": detail,
            "go": "ai"}


def _rule_warnings(s: dict) -> list[dict]:
    r = s["rule"]
    if r["kind"] in ("theme_step", "theme_dip"):
        w = _step_warning(s)
        return [w] if w else []
    if r["kind"] == "any_company_cap":
        out = []
        trig = float(r["trigger_pct"])
        tgt = float(r["target_pct"]) if r["target_pct"] is not None else None
        basis = " counting what your funds hold" if r["basis"] == "true" else ""
        for c in s["detail"]["companies"]:
            back_to = tgt if tgt is not None else trig
            amber_from = back_to + (trig - back_to) / 2 if tgt is not None else trig * 0.9
            if c["pct"] > trig:
                trim = (c["pct"] - back_to) / 100 * (c["value"] / c["pct"] * 100 if c["pct"] else 0.0)
                out.append({"id": f"rule:{r['id']}:{c['company']}", "level": "red", "kind": r["kind"],
                            "title": f"{c['company']} is {c['pct']:.1f}% of the portfolio{basis} — over your "
                                     f"{trig:g}% limit for any one company",
                            "detail": (f"Your rule brings it back to {tgt:g}%: that is selling about {_money(trim)} "
                                       "of it." if tgt is not None else (r["note"] or "")), "go": "allocation"})
            elif c["pct"] > amber_from:
                out.append({"id": f"rule:{r['id']}:{c['company']}", "level": "amber", "kind": r["kind"],
                            "title": f"{c['company']} is {c['pct']:.1f}%{basis} — past halfway to your {trig:g}% "
                                     "limit for any one company",
                            "detail": r["note"] or "", "go": "allocation"})
        return out
    w = _rule_warning(s)
    return [w] if w else []


def _rule_warning(s: dict) -> dict | None:
    r, now = s["rule"], s["now"]
    if s["level"] not in ("red", "amber"):
        return None
    who = r["subject"] or "AI-linked holdings"
    if r["kind"] == "exposure_cap":
        from . import themes
        who = themes.label(r["subject"] or "")
    basis = " counting what your funds hold too" if r["basis"] == "true" else ""
    if s["level"] == "red":
        title = f"{who} is {now:.1f}% of the portfolio — over your {r['trigger_pct']:g}% trigger"
    else:
        title = f"{who} is {now:.1f}%{basis} — past halfway to your {r['trigger_pct']:g}% trigger"
    detail = r["note"] or ""
    if r["target_pct"] is not None and s.get("trim"):
        detail = (detail + " " if detail else "") + (
            f"Your rule brings it back to {r['target_pct']:g}%: that is selling about "
            f"{_money(s['trim'])} of it.")
    return {"id": f"rule:{r['id']}", "level": s["level"], "kind": r["kind"], "title": title,
            "detail": detail.strip(), "go": "allocation"}


def _regime_since(market: dict) -> str:
    strip = market.get("strip") or []
    if not strip:
        return ""
    i = len(strip) - 1
    while i > 0 and strip[i - 1][1] == strip[-1][1]:
        i -= 1
    from .narrative import _day
    return f" The lights have read like this since {_day(strip[i][0])}."


def _watch_moved(pos: list[dict], totals: dict) -> dict | None:
    """When the money has moved on from the main watch, ask; never switch by itself. Only
    for a watch the plan review chose from what was held: a theme somebody picked by name,
    and the original AI watch, are theirs to keep."""
    from . import themes
    try:
        w = themes.watch()
        answers = (db.get_meta("builder", {}) or {}).get("answers") or {}
        cur = w.get("main")
        if w.get("legacy") or not cur or answers.get("watch_main") not in (None, "", "auto"):
            return None
        # A theme ridden with a parachute is watched because of the parachute, not because of
        # how much money it carries.
        if ((answers.get("views") or {}).get(cur) or {}).get("action") == "parachute":
            return None
        sug = themes.suggest(pos, totals)
    except Exception as e:                    # a suggestion is never worth a broken screen
        db.log("rules.watch", str(e))
        return None
    by = {e["theme"]: e.get("pct") or 0.0 for e in sug.get("exposures") or []}
    new = sug.get("main")
    if not new or new == cur or new not in themes.LIBRARY or by.get(new, 0.0) - by.get(cur, 0.0) < 0.05:
        return None
    return {"id": f"watch:{new}", "level": "info", "kind": "market",
            "title": f"{themes.title(new)} is now {by[new] * 100:.0f}% of your money; "
                     f"{themes.lower_first(themes.title(cur))}, your main watch, {by.get(cur, 0.0) * 100:.0f}%",
            "detail": f"Make {themes.lower_first(themes.title(new))} your main watch? Nothing changes unless "
                      "you choose to: Market watch, then Change what you watch.", "go": "ai"}


def evaluate(pos: list[dict], totals: dict, alloc: dict, exp: dict | None = None,
             market: dict | None = None, playbook: dict | None = None,
             holding_targets: list[dict] | None = None) -> list[dict]:
    out: list[dict] = []

    for s in rule_status(pos, totals, exp, market):
        out.extend(_rule_warnings(s))

    for p in totals.get("platforms", []):
        if not p["total"]:
            continue
        if p.get("kind") == "card":
            continue                                   # a debt, not something to protect
        share = p["total"] / p["limit"] if p["limit"] else 0
        if p.get("kind") == "bank":
            if share >= 0.9:
                out.append({"id": f"fscs:{p['id']}", "level": "red" if share > 1 else "amber",
                            "kind": "fscs",
                            "title": f"{p['name']} holds {_money(p['total'])}, against "
                                     f"{_money(p['limit'])} of deposit protection",
                            "detail": "FSCS protects bank deposits up to £120,000 per person per "
                                      "banking licence. Brands that share a licence share one limit.",
                            "go": "settings"})
            continue
        if share > 1:
            out.append({"id": f"fscs:{p['id']}", "level": "red", "kind": "fscs",
                        "title": f"{p['name']} is {_money(p['total'] - p['limit'])} over the "
                                 f"{_money(p['limit'])} protection limit",
                        "detail": "FSCS protects up to £85,000 per person per firm if a platform "
                                  "fails and assets turn out to be missing. Your investments are "
                                  "held separately from the platform's own money, so this is a "
                                  "back-stop — but it is the limit your plan is built around.",
                        "go": "overview"})
        elif share >= 0.9:
            out.append({"id": f"fscs:{p['id']}", "level": "amber", "kind": "fscs",
                        "title": f"{p['name']} is within {_money(p['limit'] - p['total'])} of the "
                                 f"{_money(p['limit'])} protection limit",
                        "detail": "Growth alone can take it over. New money may be better "
                                  "paid into another platform.", "go": "overview"})

    month_ago = _month_ago_sleeves()
    for r in alloc["sleeves"]:
        trend = _drift_trend(r, month_ago.get(r["name"]))
        if r["status"] == "red":
            direction = "over" if r["drift"] > 0 else "under"
            out.append({"id": f"sleeve:{r['id']}", "level": "red", "kind": "drift",
                        "title": f"{r['name']} is {r['actual']:.1f}% against a {r['target']:g}% target",
                        "detail": f"{abs(r['drift']):.1f} points {direction}, outside its "
                                  f"±{r['band']:.2g}-point band.{trend}", "go": "allocation"})
        elif r["status"] == "amber":
            out.append({"id": f"sleeve:{r['id']}", "level": "amber", "kind": "drift",
                        "title": f"{r['name']} is drifting: {r['actual']:.1f}% against {r['target']:g}%",
                        "detail": f"Past half of its ±{r['band']:.2g}-point band.{trend}",
                        "go": "allocation"})
    if alloc["sleeves"] and not alloc["targets_add_up"]:
        out.append({"id": "targets", "level": "amber", "kind": "data",
                    "title": f"Your sleeve targets add up to {alloc['target_sum']:g}%, not 100%",
                    "detail": "Every drift figure is measured against these, so they need to "
                              "add up.", "go": "settings"})

    if playbook:
        t = playbook["tier"]
        if t["level"] in ("amber", "red"):
            out.append({"id": "signals", "level": t["level"], "kind": "market",
                        "title": f"Your signals: {playbook['firing']} of {playbook['of']} firing, {t['label'].lower()}",
                        "detail": t["text"], "go": "ai"})
        if playbook["manual_due"]:
            out.append({"id": "signals-due", "level": "info", "kind": "market",
                        "title": "The quarterly signals need filling in",
                        "detail": "Capex guidance, Nvidia data-centre growth and the Magnificent Seven's "
                                  "share, after each earnings season.", "go": "ai"})
        lad = playbook["ladder"]
        if lad.get("drop") is not None and lad["drop"] >= 10:
            rung = next(r for r in lad["rungs"] if r.get("active"))
            out.append({"id": "ladder", "level": "red" if lad["drop"] >= 20 else "amber", "kind": "market",
                        "title": f"Your holdings are {lad['drop']:.0f}% below their high: {rung['text'].lower()}",
                        "detail": "From your ladder. Never: " + lad["never"][0].lower() + lad["never"][1:],
                        "go": "ai"})
    out_of_band = [h for h in (holding_targets or []) if h["status"] == "out"]
    if out_of_band:
        out.append({"id": "holding-bands", "level": "info", "kind": "drift",
                    "title": f"{len(out_of_band)} holding{'s' if len(out_of_band) != 1 else ''} outside "
                             f"their own target band",
                    "detail": ", ".join(h["key"] for h in out_of_band[:8]) +
                              (" and more" if len(out_of_band) > 8 else "") + ".",
                    "go": "allocation"})
    if market and market.get("regime") in ("turning", "stress"):
        reds = sum(1 for x in market["lights"] if x["level"] == "red")
        level = "red"
        out.append({"id": "market", "level": level, "kind": "market",
                    "title": f"Market lights: {market['label']}, {reds} of {market['have']} red",
                    "detail": market["text"] + _regime_since(market), "go": "ai"})
    econ = [x for x in (market or {}).get("lights", []) if x.get("group") == "economy"
            and x["level"] in ("amber", "red")]
    if econ and any(x["level"] == "red" for x in econ):
        from .narrative import _day
        out.append({"id": "economy", "level": "amber", "kind": "market",
                    "title": "The economy: " + ", ".join(
                        f"{x['title'].lower()} {x['level']} since {_day(x['since'])}" for x in econ),
                    "detail": "Slow gauges of a downturn building. They describe the economy, not "
                              "prices, and have given false alarms as well as true ones.", "go": "ai"})

    w = _watch_moved(pos, totals)
    if w:
        out.append(w)

    # Gaps in the data: each of these makes some figure above less true.
    unassigned = [x for x in pos if x["sleeve_id"] is None]
    if unassigned:
        out.append({"id": "unassigned", "level": "info", "kind": "data",
                    "title": f"{len(unassigned)} holding{'s' if len(unassigned) != 1 else ''} "
                             f"not in a sleeve yet",
                    "detail": "They are left out of every sleeve's percentage until they are.",
                    "go": "allocation"})
    unpriced = [x for x in pos if x["value"] is None]
    if unpriced:
        out.append({"id": "unpriced", "level": "amber", "kind": "data",
                    "title": f"No price for {len(unpriced)} holding{'s' if len(unpriced) != 1 else ''}",
                    "detail": ", ".join(x["name"] for x in unpriced[:5]) +
                              " — left out of the totals rather than counted as £0. Check the "
                              "price symbol on the Holdings screen.", "go": "holdings"})
    if exp and exp["unknown"]:
        out.append({"id": "ai_unset", "level": "info", "kind": "data",
                    "title": f"AI share not set for {len(exp['unknown'])} holding"
                             f"{'s' if len(exp['unknown']) != 1 else ''}",
                    "detail": f"{_money(exp['unknown_value'])} is left out of the AI figure until "
                              f"it is.", "go": "ai"})
    for p in totals.get("platforms", []):
        if p["last_error"]:
            out.append({"id": f"sync:{p['id']}", "level": "amber", "kind": "data",
                        "title": f"{p['name']} didn't update", "detail": p["last_error"],
                        "go": "settings"})
    from ..market import store
    wanted = set(store.wanted_keys())
    stale = [r for r in db.rows("SELECT key, last_error, last_ok FROM series_meta WHERE key LIKE "
                                "'SEC:%' AND last_error IS NOT NULL") if r["key"] in wanted]
    if stale:
        out.append({"id": "prices", "level": "amber", "kind": "data",
                    "title": f"Prices for {len(stale)} holding{'s' if len(stale) != 1 else ''} "
                             f"couldn't be refreshed",
                    "detail": stale[0]["last_error"], "go": "settings"})

    a = isa.allowance()
    if a["has_data"]:
        if a["over"]:
            out.append({"id": "isa", "level": "red", "kind": "isa",
                        "title": f"Paid in {_money(a['used'])} this tax year — over the "
                                 f"{_money(a['limit'])} ISA allowance",
                        "detail": "Worth checking with the platforms: over-subscribing an ISA has "
                                  "to be corrected with HMRC.", "go": "activity"})
        elif a["days_left"] is not None:
            out.append({"id": "isa", "level": "info", "kind": "isa",
                        "title": f"{_money(a['remaining'])} of this year's ISA allowance left",
                        "detail": f"{a['days_left']} days until the tax year ends on 5 April.",
                        "go": "activity"})

    out.sort(key=lambda w: ORDER.get(w["level"], 9))
    return out
