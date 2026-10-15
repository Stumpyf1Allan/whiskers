"""The warning lights for the AI trade and for markets in general.

WHAT THESE ARE, AND WHAT THEY ARE NOT. Every light below describes something prices
have *already* done: a trend broken, a fall from a high, fear or credit stress already
rising. None of them can say a fall is coming, and each has gone red in sell-offs that
recovered within months. Their job is narrower and more useful than prediction: to make
sure a genuine turn in the AI trade does not go unnoticed, and to put the plan you wrote
while calm next to the evidence when it isn't.

The definitions are deliberately standard, so that "red" means the same here as in
the financial press:

* **Trend** — price against its 200-day average, the most widely used definition of a
  long-term trend. Above: green. Below: amber. Below *and* the average itself turning
  down: red.
* **Fall from high** — distance below the highest close of the past year. Ten per cent
  is the conventional "correction", twenty a "bear market". Single companies swing
  harder than indices, so Nvidia's bands are wider.
* **Fear (VIX)** — under 20 calm, 20–30 elevated, over 30 genuine fear: common rules of
  thumb.
* **Credit stress** — the US junk-bond spread. Its long-run average is around five per
  cent; above six has historically come only with real trouble.

A series nobody could fetch is grey, never green. The overall reading says how many of
the lights it is based on.
"""

from __future__ import annotations

import datetime as dt

from ..market import store
from . import mathx

LEVELS = ("green", "amber", "red")

DEFS = [
    {"key": "world_trend", "title": "World shares", "ref": "WORLD", "kind": "trend",
     "group": "market", "sub": "FTSE All-World, in pounds, against its 200-day average"},
    {"key": "world_fall", "title": "World shares: fall from high", "ref": "WORLD", "kind": "drawdown",
     "amber": 0.10, "red": 0.20, "group": "market", "sub": "10% is a correction, 20% a bear market"},
    {"key": "ndx_trend", "title": "Tech-heavy US market", "ref": "NDX", "kind": "trend",
     "group": "ai", "sub": "Nasdaq-100 against its 200-day average"},
    {"key": "sox_fall", "title": "Chip stocks", "ref": "SOX", "kind": "drawdown",
     "amber": 0.10, "red": 0.20, "group": "ai", "sub": "Semiconductor index, fall from its 1-year high"},
    {"key": "nvda_fall", "title": "Nvidia", "ref": "NVDA", "kind": "drawdown",
     "amber": 0.15, "red": 0.30, "group": "ai", "sub": "Fall from its 1-year high"},
    {"key": "ai_lead", "title": "Is AI still leading?", "ref": ("SMH", "SPY"), "kind": "ratio_trend",
     "group": "ai", "sub": "Chip stocks relative to the whole US market"},
    {"key": "vix", "title": "Fear gauge", "ref": "VIX", "kind": "level", "amber": 20, "red": 30,
     "group": "market", "sub": "VIX — expected swings in US shares"},
    {"key": "credit", "title": "Credit stress", "ref": "HYOAS", "kind": "level",
     "amber": 4.5, "red": 6.0, "group": "market", "sub": "US junk-bond spread, % a year"},
    # The economy and money: slower gauges of a downturn building, not of prices falling.
    {"key": "curve", "title": "Yield curve", "ref": "CURVE", "kind": "curve", "group": "economy",
     "sub": "US 10-year less 3-month yield, points"},
    {"key": "sahm", "title": "Recession indicator", "ref": "SAHM", "kind": "level", "amber": 0.3,
     "red": 0.5, "smooth": 1, "group": "economy", "sub": "Sahm rule: rise in US unemployment"},
    {"key": "fsi", "title": "Financial stress", "ref": "FSI", "kind": "level", "amber": 0.0,
     "red": 1.0, "smooth": 1, "group": "economy", "sub": "St. Louis Fed index, 0 is average"},
    {"key": "ig", "title": "Solid-company borrowing", "ref": "IGOAS", "kind": "level",
     "amber": 1.5, "red": 2.0, "group": "economy", "sub": "Investment-grade spread, % a year"},
]
#: Daily readings are judged on a 5-day average, so one bad day can't turn a light: a
#: light changes colour when a move has lasted about a week, not on the day it happens.
SMOOTH = 5

EXPLAIN = {
    "curve": "Amber while inverted (short rates above long ones), which has come before most "
             "US recessions, often by a year or more. Red when it has turned back up after "
             "spending most of the past year inverted: historically the nearer warning.",
    "sahm": "Amber from 0.3, red from 0.5: the Sahm rule, which has marked the early months "
            "of every US recession since 1970. It confirms a downturn; it doesn't foresee one.",
    "fsi": "Amber once strain is above average (0), red above 1. Built from 18 weekly market "
           "measures, so a single noisy one can't move it much.",
    "ig": "Amber from 1.5%, red from 2%. When even safe companies' borrowing costs widen, the "
          "strain is broad rather than confined to riskier borrowers.",
    "world_trend": "The long-term trend of shares everywhere, which is what your core index "
                   "funds hold. A break below the 200-day average is the usual definition of a "
                   "trend ending; red only once the average itself is falling.",
    "world_fall": "How far world shares are below their best level of the past year. Your "
                  "ladder runs on your own holdings' fall; this is the market's.",
    "ndx_trend": "The long-term trend of the companies at the centre of the AI boom. A break "
                 "below the 200-day average is the most common definition of a trend ending; "
                 "it goes red only when the average itself has also started falling.",
    "sox_fall": "Chip makers are where AI spending actually lands. If buyers start to doubt "
                "that spending, this is usually the first place it shows.",
    "nvda_fall": "The single company most tied to the AI boom — and one of the largest weights "
                 "inside US and world index funds, so it reaches you through those too.",
    "ai_lead": "Rising means AI-linked companies are outrunning everything else. A sustained "
               "turn down means the market has stopped paying extra for them — what a "
               "bubble deflating looks like from the inside.",
    "vix": "The options market's own estimate of turbulence ahead. It spikes during a sell-off "
           "rather than before one.",
    "credit": "What riskier companies pay to borrow, over the US government. Share-price falls "
              "with calm credit markets tend to be shallower than ones where this widens too.",
}

REGIMES = {
    "calm": {"label": "Calm", "text": "Every light is green: trends intact, no big falls, "
             "no fear."},
    "watch": {"label": "Watch", "text": "Something has started to wobble. Worth a look, not "
              "worth acting on by itself — most wobbles come to nothing."},
    "turning": {"label": "Turning", "text": "Several lights are red together: trends broken and "
                "prices well off their highs, in the AI trade, markets in general, or both. "
                "Whether it lasts is unknowable. Check it against your playbook."},
    "stress": {"label": "Stress", "text": "Markets are falling broadly, with fear or credit "
               "stress high. The plan you wrote in calm weather matters most now."},
    "none": {"label": "No data", "text": "None of the market series could be fetched yet."},
}


def _series(ref) -> list[tuple[str, float]]:
    """A light's series: one reference series, a ratio of two, a holding's own price
    ("SEC", symbol), or an equal-weighted basket of holdings ("BASKET", symbol, ...)."""
    if isinstance(ref, tuple):
        if ref and ref[0] == "SEC":
            return store.gbp_points(store.sec_key(ref[1]))
        if ref and ref[0] == "BASKET":
            return basket([store.gbp_points(store.sec_key(s)) for s in ref[1:]])
        return mathx.ratio(store.points(store.ref_key(ref[0])), store.points(store.ref_key(ref[1])))
    return store.points(store.ref_key(ref))


def basket(series: list[list[tuple[str, float]]]) -> list[tuple[str, float]]:
    """Several holdings as one: each rebased to 100 where they all have prices, averaged."""
    series = [s for s in series if len(s) > 20]
    if not series:
        return []
    start = max(s[0][0] for s in series)
    maps, bases = [], []
    for s in series:
        m = {d: v for d, v in s if d >= start}
        b = next((v for d, v in s if d >= start), None)
        if not b:
            continue
        maps.append(m)
        bases.append(b)
    if not maps:
        return []
    days = sorted(set().union(*[set(m) for m in maps]))
    last = [None] * len(maps)
    out = []
    for d in days:
        for i, m in enumerate(maps):
            if d in m:
                last[i] = m[d] / bases[i] * 100
        if all(v is not None for v in last):
            out.append((d, sum(last) / len(last)))
    return out


def _yoy(pts: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Twelve-month % change of a monthly index (consumer prices into an inflation rate)."""
    out = []
    for d, v in pts:
        then = mathx.value_on(pts, (dt.date.fromisoformat(d) - dt.timedelta(days=366)).isoformat())
        if then:
            out.append((d, (v / then - 1) * 100))
    return out


def levels_for(defn: dict, pts: list[tuple[str, float]]) -> list[tuple[str, str, float | None]]:
    """(date, level, measure) for every day there is enough history to judge."""
    if defn["kind"] == "yoy":
        pts = _yoy(pts)
    raw = [v for _, v in pts]
    n = int(defn.get("smooth", SMOOTH if defn["kind"] != "yoy" else 1))
    vals = [s if s is not None else r for s, r in zip(mathx.sma(raw, n), raw)] if n > 1 else raw
    pts = [(d, v) for (d, _), v in zip(pts, vals)]
    out = []
    kind = defn["kind"]
    if kind in ("trend", "ratio_trend"):
        avg = mathx.sma(vals, 200)
        for i, (d, v) in enumerate(pts):
            a = avg[i]
            if a is None:
                continue
            gap = v / a - 1
            prev = avg[i - 20] if i >= 20 else None
            falling = prev is not None and a < prev
            if defn.get("invert"):          # a rising dollar is the warning, not a falling one
                rising = prev is not None and a > prev
                lvl = "green" if gap <= 0 else ("red" if rising else "amber")
            else:
                lvl = "green" if gap >= 0 else ("red" if falling else "amber")
            out.append((d, lvl, gap))
    elif kind == "drawdown":
        dd = mathx.drawdowns(vals, 252)
        for i, (d, _) in enumerate(pts):
            if i < 60:
                continue                            # too little history for a "high"
            x = dd[i]
            out.append((d, "red" if x >= defn["red"] else "amber" if x >= defn["amber"] else "green", x))
    elif kind in ("level", "yoy"):
        for d, v in pts:
            out.append((d, "red" if v >= defn["red"] else "amber" if v >= defn["amber"] else "green", v))
    elif kind == "rise":
        for i, (d, v) in enumerate(pts):
            if i < 60:
                continue
            low = min(vals[max(0, i - 251):i + 1])
            x = (v / low - 1) if low else 0.0
            out.append((d, "red" if x >= defn["red"] else "amber" if x >= defn["amber"] else "green", x))
    elif kind == "curve":
        for i, (d, v) in enumerate(pts):
            year = vals[max(0, i - 250):i + 1]
            inverted = sum(1 for x in year if x < 0) / len(year)
            out.append((d, "amber" if v < 0 else "red" if inverted >= 0.5 else "green", v))
    return out


#: Which way is worse, for the direction arrow: a higher reading for levels and falls,
#: a lower one for trends and the yield curve.
_WORSE_IF_HIGHER = {"level", "drawdown", "rise", "yoy"}


def _trend(defn: dict, lv: list) -> dict:
    """How long the light has been this colour, and which way it is heading over the
    past month: the difference between a spike and a slide."""
    d0, lvl, now = lv[-1]
    start = len(lv) - 1
    while start > 0 and lv[start - 1][1] == lvl:
        start -= 1
    month_ago = (dt.date.fromisoformat(d0) - dt.timedelta(days=30)).isoformat()
    then = next((m for d, _, m in reversed(lv) if d <= month_ago), None)
    direction = "steady"
    if then is not None and now is not None:
        move = now - then
        scale = abs(then) if defn["kind"] in ("level", "yoy") and then else 1.0
        tolerance = 0.05 * scale if defn["kind"] in ("level", "yoy") else (0.1 if defn["kind"] == "curve" else 0.01)
        if abs(move) > tolerance:
            worse = move > 0 if (defn["kind"] in _WORSE_IF_HIGHER or defn.get("invert")) else move < 0
            direction = "worsening" if worse else "improving"
    return {"since": lv[start][0], "days": (dt.date.fromisoformat(d0) -
                                            dt.date.fromisoformat(lv[start][0])).days,
            "direction": direction}


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _day(iso: str) -> str:
    """'2026-07-22' -> '22 Jul 2026', by hand: strftime's no-padding flag differs
    between Windows and everything else."""
    y, m, d = (int(x) for x in iso[:10].split("-"))
    return f"{d} {MONTHS[m - 1]} {y}"


def _words(defn: dict, lvl: str, measure: float, pts: list, extra: dict) -> str:
    k = defn["kind"]
    if k in ("trend", "ratio_trend"):
        side = "above" if measure >= 0 else "below"
        s = f"{abs(measure) * 100:.1f}% {side} its 200-day average"
        if lvl == "red":
            s += ", and the average itself is now falling"
        return s
    if k == "drawdown":
        if measure < 0.005:
            return "At or near its high of the past year"
        return f"{measure * 100:.1f}% below its high of the past year ({_day(extra['high_on'])})"
    if k == "rise":
        if measure < 0.005:
            return "At or near its low of the past year"
        return f"{measure * 100:.1f}% above its low of the past year"
    if k == "yoy":
        return f"{measure:.1f}% over twelve months: amber from {defn['amber']}%, red from {defn['red']}%"
    if k == "curve":
        return (f"{measure:+.2f} points: inverted" if measure < 0 else
                f"{measure:+.2f} points, back up after a long inversion" if lvl == "red" else
                f"{measure:+.2f} points, not inverted")
    unit = "%" if defn["key"] in ("credit", "ig", "real_yield", "breakeven", "uk10y_level", "us10y_level") else ""
    avg = " (5-day average)" if int(defn.get("smooth", SMOOTH)) > 1 else ""
    return f"{measure:.2f}{unit}{avg}: amber from {defn['amber']}{unit}, red from {defn['red']}{unit}"


def _keys_of(ref) -> list[str]:
    if isinstance(ref, tuple):
        if ref and ref[0] in ("SEC", "BASKET"):
            return [store.sec_key(r) for r in ref[1:]]
        return [store.ref_key(r) for r in ref]
    return [store.ref_key(ref)]


def stopped_updating(ref, pts: list[tuple[str, float]]) -> bool:
    """True when a fetch succeeded recently but the series' last figure is far older than
    its usual gap allows: the source has stopped publishing it (FRED's copy of UK CPI
    stopped in March 2025, for one). Judged only when the last good fetch is known, so a
    computer that was simply switched off for a month isn't accused of it."""
    if len(pts) < 3:
        return False
    fetched = [m.get("last_ok") for m in (store.meta(k) or {} for k in _keys_of(ref)) if m.get("last_ok")]
    if not fetched:
        return False
    try:
        last_ok = max(dt.datetime.fromisoformat(f[:19]).date() for f in fetched)
        last = dt.date.fromisoformat(pts[-1][0][:10])
        recent = [dt.date.fromisoformat(d[:10]) for d, _ in pts[-7:]]
    except ValueError:
        return False
    gaps = sorted((b - a).days for a, b in zip(recent, recent[1:]))
    gap = gaps[len(gaps) // 2] if gaps else 1
    allowed = 30 if gap <= 7 else 110 if gap <= 40 else 200      # daily, monthly, quarterly
    return (last_ok - last).days > allowed


def reading(defn: dict) -> dict:
    pts = _series(defn["ref"])
    base = {"key": defn["key"], "title": defn["title"], "sub": defn["sub"], "group": defn["group"],
            "explain": defn.get("explain") or EXPLAIN.get(defn["key"], ""), "level": "none", "words": "",
            "as_of": None, "spark": [], "history": []}
    if not pts:
        refs = defn["ref"] if isinstance(defn["ref"], tuple) else (defn["ref"],)
        if refs and refs[0] in ("SEC", "BASKET"):
            keys = [store.sec_key(r) for r in refs[1:]]
        else:
            keys = [store.ref_key(r) for r in refs]
        errs = [(store.meta(k) or {}).get("last_error") for k in keys]
        base["words"] = next((e for e in errs if e), "Not fetched yet.")
        return base
    if stopped_updating(defn["ref"], pts):
        base["as_of"] = pts[-1][0]
        base["words"] = (f"Its source hasn't published a new figure since {_day(pts[-1][0])}, so this "
                         "light is left out rather than shown as though it were current.")
        return base
    lv = levels_for(defn, pts)
    if not lv:
        base["words"] = "Not enough history yet to judge."
        return base
    d, lvl, measure = lv[-1]
    extra = {}
    if defn["kind"] == "drawdown":
        window = pts[-252:]
        high = max(window, key=lambda p: p[1])
        extra["high_on"] = high[0]
    base.update(_trend(defn, lv))
    base.update(level=lvl, as_of=d, measure=measure, value=pts[-1][1],
                words=_words(defn, lvl, measure, pts, extra),
                spark=[[p[0], round(p[1], 6)] for p in mathx.thin(mathx.since(pts, 365), 120)],
                history=lv[-520:])
    if defn["kind"] in ("trend", "ratio_trend"):
        avg = mathx.sma([v for _, v in pts], 200)
        base["avg"] = [[pts[i][0], round(a, 6)] for i, a in enumerate(avg)
                       if a is not None and pts[i][0] >= base["spark"][0][0]]
        base["avg"] = mathx.thin([tuple(x) for x in base["avg"]], 120)
    return base


def regime_of(ai_levels: list[str], mkt_levels: list[str], theme_n: int = 4) -> tuple[str, float]:
    """One reading from the main watch theme's lights and the market's. `ai_levels` is the
    main theme's (named for the AI trade, the original and still the default). A theme
    turns when its lights add up to half their worst — two reds of the AI trade's four, or
    one red of a two-light theme — so a theme with fewer lights is judged as fairly."""
    score = {"green": 0, "amber": 1, "red": 2}
    ai = [score[x] for x in ai_levels if x in score]
    mk = [score[x] for x in mkt_levels if x in score]
    if not ai and not mk:
        return "none", 0.0
    a, m = sum(ai), sum(mk)
    gauge = (a + m) / (2 * (len(ai) + len(mk)))
    turn = max(1, int(theme_n))
    if (a >= turn and m >= 4) or m >= 6:
        return "stress", gauge
    if a >= turn or m >= 4:
        return "turning", gauge
    if a >= 1 or m >= 1:
        return "watch", gauge
    return "calm", gauge


def defs_for(w: dict | None = None) -> list[dict]:
    """The lights for a watch: markets and the economy always, then each watched theme's.
    The original AI watch comes out exactly as it always has, in the same order."""
    from . import themes
    w = w or themes.watch()
    out = [d for d in DEFS if d["group"] in ("market", "economy") or (d["group"] == "ai" and "ai" in w["themes"])]
    for t in w["themes"]:
        if t != "ai":
            out += themes.lights_for(t)
    return out


def evaluate(w: dict | None = None) -> dict:
    from . import themes
    w = w or themes.watch()
    defs = defs_for(w)
    main = w["main"]
    main_n = sum(1 for d in defs if d["group"] == main) or 4
    lights = [reading(d) for d in defs]
    ai = [x["level"] for x in lights if x["group"] == main]
    mk = [x["level"] for x in lights if x["group"] == "market"]
    regime, gauge = regime_of(ai, mk, main_n)
    have = sum(1 for x in lights if x["level"] != "none")

    # The same judgement for every day of the last two years, so the strip shows how
    # often each colour has come and gone — a red that cleared within weeks is useful
    # context for a red today.
    per_light = {x["key"]: {d: lvl for d, lvl, _ in x["history"]} for x in lights}
    days = sorted(set().union(*[set(v) for v in per_light.values()])) if per_light else []
    days = days[-520:]
    strip, last = [], {k: None for k in per_light}
    for d in days:
        for k in per_light:
            if d in per_light[k]:
                last[k] = per_light[k][d]
        r, _ = regime_of([last[x["key"]] for x in lights if x["group"] == main and last[x["key"]]],
                         [last[x["key"]] for x in lights if x["group"] == "market" and last[x["key"]]],
                         main_n)
        strip.append([d, r])
    for x in lights:
        x.pop("history", None)
    group_keys = ["market", "economy"] + list(w["themes"])
    groups = {g: dict(group_reading([x["level"] for x in lights if x["group"] == g], g, sum(1 for d in defs if d["group"] == g)),
                      title=themes.title(g) if g not in ("market", "economy") else
                      {"market": "Markets in general", "economy": "The economy and money"}[g])
              for g in group_keys}
    if "ai" not in groups:
        groups["ai"] = {"label": "Not watched", "level": "none", "score": 0.0, "have": 0, "title": "The AI trade"}
    return {"regime": regime, "label": REGIMES[regime]["label"], "text": REGIMES[regime]["text"],
            "gauge": gauge, "lights": lights, "have": have, "of": len(lights), "strip": strip,
            "groups": groups, "watch": {"main": main, "themes": list(w["themes"]), "legacy": w.get("legacy", False),
                                        "main_title": themes.title(main), "main_label": themes.label(main),
                                        "chosen_at": w.get("chosen_at")}}


def group_reading(levels: list[str], group: str, n: int = 4) -> dict:
    """One word for one group of lights. A theme uses the same words as the overall
    reading, turning at half its worst; the economy's gauges move slowly, so any red there
    is already a warning."""
    score = {"green": 0, "amber": 1, "red": 2}
    got = [score[x] for x in levels if x in score]
    if not got:
        return {"label": "No data", "level": "none", "score": 0.0, "have": 0}
    total, reds = sum(got), sum(1 for x in levels if x == "red")
    turn = 4 if group in ("market", "ai") else max(1, n)
    if group == "economy":
        label, level = (("Warning", "red") if reds else ("Watch", "amber") if total else ("Calm", "green"))
    else:
        label, level = (("Turning", "red") if total >= turn else ("Watch", "amber") if total else ("Calm", "green"))
    return {"label": label, "level": level, "score": total / (2 * len(got)), "have": len(got)}


def context() -> list[dict]:
    """Charts that inform without passing judgement: concentration, rates, the pound."""
    out = []
    breadth = mathx.ratio(store.points(store.ref_key("RSP")), store.points(store.ref_key("SPY")))
    if breadth:
        out.append({"key": "breadth", "title": "Equal-weight vs size-weight US market",
                    "explain": "Falls when the largest companies pull away from the rest — the "
                               "market getting more concentrated in a few giants. A sharp turn "
                               "up while the market falls is the giants being sold.",
                    "change_1y": mathx.change_over(breadth, 365),
                    "spark": [[d, round(v, 6)] for d, v in mathx.thin(mathx.since(breadth, 730), 160)]})
    for ref, title in (("US10Y", "US 10-year interest rate"), ("GBPUSD", "Pound in dollars")):
        pts = store.points(store.ref_key(ref))
        if pts:
            is_rate = ref == "US10Y"
            out.append({"key": ref, "title": title,
                        "explain": "", "value": pts[-1][1], "as_of": pts[-1][0],
                        "change_1y": None if is_rate else mathx.change_over(pts, 365),
                        "change_1y_pts": mathx.points_change(pts, 365) if is_rate else None,
                        "spark": [[d, round(v, 6)] for d, v in mathx.thin(mathx.since(pts, 730), 160)]})
    return out
