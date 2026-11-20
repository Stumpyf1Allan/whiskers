"""Lenses: the Overview's dial and big picture, pointed at one thing at a time.

The card opens on the main watch (the AI trade unless the plan review chose something
else). Buttons switch it to the whole market, the person's own portfolio, or one of the
sectors they hold most of, looking through funds. Each lens uses the same scoring as the
watch: green 0, amber 1, red 2, and it reads Turning at half its worst.
"""
from __future__ import annotations

from . import narrative, signals, themes

#: Library themes that are not sectors, so never offered as one.
NOT_SECTORS = {"ai", "rates", "inflation", "rand"}
SECTORS_SHOWN = 4

PORTFOLIO_DEFS = [
    {"key": "pf_trend", "title": "Your holdings: trend", "kind": "trend", "group": "portfolio", "ref": "PORTFOLIO",
     "sub": "Today's holdings priced back over time, against their 200-day average",
     "explain": "Whether your own holdings, as they stand today, are above or below their long-term trend."},
]


def choices(pos: list[dict], tot: dict, market: dict) -> list[dict]:
    """The buttons, in order: the main watch, the whole market, your portfolio, then your
    biggest sectors."""
    w = market.get("watch") or {}
    main = w.get("main") or "ai"
    out = [{"key": main, "label": w.get("main_label") or themes.label(main)},
           {"key": "market", "label": "Whole market"},
           {"key": "portfolio", "label": "My portfolio"}]
    sized = []
    for key in themes.LIBRARY:
        if key in NOT_SECTORS or key == main:
            continue
        try:
            pct = themes.exposure(pos, tot, key).get("pct")
        except Exception:
            pct = None
        if pct:
            sized.append((pct, key))
    for pct, key in sorted(sized, reverse=True)[:SECTORS_SHOWN]:
        out.append({"key": key, "label": themes.label(key), "pct": pct})
    return out


def _portfolio_lights(back: dict, alloc: dict, pb: dict | None) -> list[dict]:
    pts = [(d, v) for d, v in (back or {}).get("points") or [] if v]
    out = [signals.reading(d, pts) for d in PORTFOLIO_DEFS]
    lad = (pb or {}).get("ladder") or {}
    drop = lad.get("drop")
    # The same fall your ladder uses, so the light and the ladder never disagree.
    out.append({"key": "pf_fall", "title": "Your holdings: fall from high", "group": "portfolio",
                "sub": "Amber from 10% down, red from 20%, the first rungs of your ladder",
                "level": "none" if drop is None else "red" if drop >= 20 else "amber" if drop >= 10 else "green",
                "words": "Not enough history yet." if drop is None else
                f"{drop:.1f}% below their high of {narrative._day(lad.get('high_on'))}, the figure your ladder uses.",
                "since": None, "direction": "steady"})
    reds = [r for r in alloc.get("sleeves", []) if r.get("status") == "red"]
    ambers = [r for r in alloc.get("sleeves", []) if r.get("status") == "amber"]
    far = max(reds or ambers, key=lambda r: abs(r["drift"])) if (reds or ambers) else None
    out.append({"key": "pf_bands", "title": "Sleeves within their bands", "group": "portfolio",
                "sub": "Each sleeve against its own target band", "level": "red" if reds else "amber" if ambers else "green",
                "words": (f"{len(reds or ambers)} sleeve{'s' if len(reds or ambers) != 1 else ''} "
                          f"{'outside' if reds else 'past halfway to the edge of'} {'their' if len(reds or ambers) != 1 else 'its'} band, "
                          f"furthest {far['name']} at {far['actual']:.1f}% against {far['target']:g}%.") if far
                else "Every sleeve is inside its band.", "since": None, "direction": "steady"})
    return out


def view(key: str, pos, tot, alloc, exp, market, pb, back) -> dict:
    """One lens: its word, dial position, lights, signals and the fixed-rule big picture."""
    w = market.get("watch") or {}
    main = w.get("main") or "ai"
    if key == "portfolio":
        title, short = "Your portfolio", "your portfolio"
        lights = _portfolio_lights(back, alloc, pb)
    elif key == "market":
        title, short = "The whole market", "the market"
        lights = [x for x in market.get("lights", []) if x["group"] == "market"]
    elif key in themes.LIBRARY:
        title, short = themes.title(key), themes.label(key)
        lights = [x for x in market.get("lights", []) if x["group"] == key] or \
            [signals.reading(d) for d in themes.lights_for(key)]
    else:
        raise ValueError("No such lens.")
    for x in lights:
        x.pop("history", None)
        x.pop("spark", None)
    g = signals.group_reading([x["level"] for x in lights], key, len(lights))
    sigs = [r for r in (pb or {}).get("signals", []) if r["group"] == key]
    if key == "portfolio":
        share = None
    elif key == "market":
        share = 1.0
    elif key == "ai":
        share = exp.get("ai_pct")
    else:
        share = themes.exposure(pos, tot, key).get("pct")

    # The fixed-rule big picture for this lens.
    if key == main:
        story = narrative.big_picture(market, pb, exp, alloc, tot,
                                      None if key == "ai" else themes.exposure(pos, tot, key))
    else:
        first = f"{title} reads {g['label'].lower()}. " + narrative.lights_story(lights, key, brief=True)
        if sigs:
            fired = sum(1 for r in sigs if r["firing"])
            first += f" Your {len(sigs)} signals for it: {fired} firing."
        texp = {} if key in ("portfolio", "market") else (
            {"ai_pct": exp.get("ai_pct"), "ai_value": exp.get("ai_value"), "top": exp.get("top", [])}
            if key == "ai" else themes.exposure(pos, tot, key))
        story = narrative._portfolio_paragraphs(first, market, pb, texp, alloc, tot, title,
                                                "AI" if key == "ai" else short)
    return {"key": key, "title": title, "label": g["label"], "level": g["level"], "score": g["score"],
            "lights": [{k: x.get(k) for k in ("key", "title", "level", "words", "since", "direction", "sub")}
                       for x in lights],
            "signals": [{k: r.get(k) for k in ("key", "title", "value", "threshold", "op", "unit", "firing",
                                               "updated", "stale", "kind")} for r in sigs],
            "share": share, "turn_at": 4 if key in ("market", "ai") else max(1, len(lights)),
            "big_picture": story}
