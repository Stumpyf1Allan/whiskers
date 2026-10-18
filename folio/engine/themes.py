"""Watch themes: the market forces that can move most of a person's money.

Allan's portfolio is built around the AI trade, so his Market watch is too. Somebody
else's money may lean on gold, oil, interest rates or UK companies instead. A theme here
is one such force, with the price series that show it, a handful of warning lights
using standard definitions, signal templates with documented default thresholds, and the
plain-English words for when everything is calm.

Which themes a person watches is chosen from their own holdings (how much of their money
each force can move, looking through funds) and from what they say they believe in or
worry about. The app never forecasts which force matters next; it measures exposure and
describes what prices have already done. The person confirms the choice, and nothing
changes without them.

A copy that has never chosen keeps the original set-up exactly: the AI trade as its main
watch, with Allan's eight signals.
"""

from __future__ import annotations

import datetime as dt
import re

from .. import db
from . import classify

#: A theme becomes a candidate for watching above this share of the person's money.
THRESHOLD = 10.0


def _trend(key, title, ref, sub, explain, invert=False):
    return {"key": key, "title": title, "ref": ref, "kind": "trend", "sub": sub, "explain": explain,
            **({"invert": True} if invert else {})}


def _fall(key, title, ref, amber, red, sub, explain):
    return {"key": key, "title": title, "ref": ref, "kind": "drawdown", "amber": amber, "red": red,
            "sub": sub, "explain": explain}


def _level(key, title, ref, amber, red, sub, explain, smooth=None):
    d = {"key": key, "title": title, "ref": ref, "kind": "level", "amber": amber, "red": red,
         "sub": sub, "explain": explain}
    if smooth is not None:
        d["smooth"] = smooth
    return d


TREND_WHY = ("Price against its 200-day average, the usual definition of a long-term trend. "
             "Red only once the average itself has turned down.")

LIBRARY: dict[str, dict] = {
    "ai": {
        "label": "AI and big tech", "title": "The AI trade", "short": "AI",
        "about": "The companies building and selling artificial intelligence, and the chips it runs on.",
        "lights": "signals.DEFS",            # the original four, kept exactly as they were
        "series": ["NDX", "SOX", "NVDA", "SMH", "SPY"],
        "scenario_ref": "NDX",
        "calm": "The AI trade's trend is intact, chip stocks and Nvidia are near their highs, and "
                "AI stocks are still keeping pace with the market.",
        "sleeve_words": ["tech", " ai", "ai ", "semi", "artificial"],
    },
    "gold": {
        "label": "Gold", "title": "Gold", "short": "gold",
        "about": "Physical gold and gold miners.",
        "lights": [
            _trend("gold_trend", "Gold", "GOLD", "Gold against its 200-day average", TREND_WHY),
            _fall("gold_fall", "Gold: fall from high", "GOLD", 0.10, 0.20,
                  "10% is a correction, 20% a bear market",
                  "How far gold is below its best level of the past year."),
            _level("real_yield", "Real interest rates", "REALYIELD", 2.0, 2.5,
                   "US 10-year real yield, %",
                   "Gold pays no income, so it has tended to struggle when real yields are high. "
                   "Amber from 2%, red from 2.5%: levels last seen before 2008."),
        ],
        "series": ["GOLD", "REALYIELD"], "scenario_ref": "GOLD",
        "calm": "Gold's trend is intact and it is near its high; real interest rates aren't "
                "unusually high.",
        "sleeve_words": ["gold", "precious"],
    },
    "oil": {
        "label": "Oil and energy", "title": "Oil and energy", "short": "oil",
        "about": "Oil and gas producers, and the oil price behind them.",
        "lights": [
            _trend("brent_trend", "Oil price", "BRENT", "Brent crude against its 200-day average", TREND_WHY),
            _fall("brent_fall", "Oil: fall from high", "BRENT", 0.20, 0.35,
                  "Oil swings more than shares, so the bands are wider",
                  "How far Brent crude is below its best level of the past year."),
            _trend("energy_trend", "Energy companies", "ENERGY", "US energy shares against their 200-day average",
                   TREND_WHY),
        ],
        "series": ["BRENT", "ENERGY"], "scenario_ref": "ENERGY",
        "calm": "The oil price and energy companies are holding their trends.",
        "sleeve_words": ["energy", "oil"],
    },
    # Before metals, so a sleeve called "Industrials & Materials" is read as industrials.
    "industrials": {
        "label": "Industrials", "title": "Industrial companies", "short": "industrials",
        "about": "Machinery, transport, freight, building and the robots in factories: the business cycle in "
                 "company form.",
        "lights": [
            _trend("ind_trend", "Industrial companies", "INDUSTRIALS", "US industrials against their 200-day average",
                   TREND_WHY),
            _fall("ind_fall", "Industrials: fall from high", "INDUSTRIALS", 0.10, 0.20,
                  "10% is a correction, 20% a bear market",
                  "Industrials fall early when orders dry up, so this is a read on the economy as well."),
        ],
        "series": ["INDUSTRIALS"], "scenario_ref": "INDUSTRIALS",
        "calm": "Industrial companies are holding their trend.",
        "sleeve_words": ["industr", "freight", "transport", "robot"],
    },
    "metals": {
        "label": "Industrial metals and miners", "title": "Metals and miners", "short": "metals",
        "about": "Copper, iron ore and the mining companies that dig them up.",
        "lights": [
            _trend("copper_trend", "Copper", "COPPER", "Copper against its 200-day average", TREND_WHY),
            _fall("copper_fall", "Copper: fall from high", "COPPER", 0.15, 0.30,
                  "Metals swing more than shares, so the bands are wider",
                  "Copper is a read on factory and building demand worldwide."),
        ],
        "series": ["COPPER"], "scenario_ref": "COPPER",
        "calm": "Copper is holding its trend and near its high.",
        "sleeve_words": ["metal", "mining", "material", "commod"],
    },
    "rates": {
        "label": "Interest rates and bonds", "title": "Interest rates and bonds", "short": "bonds",
        "about": "Gilts and other bonds, whose prices fall when interest rates rise.",
        "lights": [
            _level("uk10y_level", "UK 10-year gilt yield", "UK10Y", 5.0, 5.5, "Monthly average, %",
                   "Amber from 5%, red from 5.5%: above about 5.5% gilts have tended to fall with "
                   "shares rather than cushion them.", smooth=1),
            _level("us10y_level", "US 10-year yield", "US10Y", 4.75, 5.0, "%",
                   "Amber from 4.75%, red from 5%: the highest since 2007."),
            _fall("gilts_fall", "Gilt prices: fall from high", "GILTS", 0.05, 0.10,
                  "Gilt funds move less than shares, so the bands are narrower",
                  "How far a UK gilt fund is below its best level of the past year."),
        ],
        "series": ["UK10Y", "US10Y", "GILTS"], "scenario_ref": "GILTS",
        "calm": "Gilt yields are below the levels where bonds stop cushioning shares.",
        "sleeve_words": ["gilt", "bond", "fixed"],
    },
    "inflation": {
        "label": "Inflation", "title": "Inflation", "short": "inflation",
        "about": "Rising prices: what erodes cash and fixed incomes, and what index-linked gilts protect against.",
        "lights": [
            _level("breakeven", "Inflation the bond market expects", "BREAKEVEN", 2.75, 3.25,
                   "US 10-year breakeven, %",
                   "The inflation rate bond prices imply. Amber from 2.75%, red from 3.25%: well "
                   "above the 2% central banks aim for."),
            {"key": "uk_cpi", "title": "UK inflation", "ref": "UKCPI", "kind": "yoy", "amber": 3.0,
             "red": 4.0, "sub": "Consumer prices over twelve months, %",
             "explain": "Amber from 3%: more than a point above the 2% target, when the Bank of "
                        "England's Governor must write to the Chancellor. Red from 4%."},
        ],
        "series": ["BREAKEVEN", "UKCPI"], "scenario_ref": "GILTS",
        "calm": "Inflation, and what markets expect of it, are close to target.",
        "sleeve_words": ["inflation", "linked"],
    },
    "property": {
        "label": "Property and infrastructure", "title": "Property", "short": "property",
        "about": "Companies and funds that own buildings, warehouses, pipes and power lines.",
        "lights": [
            _trend("uk_prop_trend", "UK property shares", "UKPROP", "Against their 200-day average", TREND_WHY),
            _fall("prop_fall", "Global property: fall from high", "PROPERTY", 0.10, 0.20,
                  "10% is a correction, 20% a bear market",
                  "Property companies borrow heavily, so rising rates hit them hardest."),
        ],
        "series": ["UKPROP", "PROPERTY"], "scenario_ref": "PROPERTY",
        "calm": "Property shares are holding their trend.",
        "sleeve_words": ["propert", "real", "reit", "infra"],
    },
    "healthcare": {
        "label": "Healthcare", "title": "Healthcare", "short": "healthcare",
        "about": "Drug makers, medical devices and health insurers.",
        "lights": [
            _trend("hc_trend", "Healthcare shares", "HEALTH", "US healthcare against its 200-day average", TREND_WHY),
            {"key": "hc_lead", "title": "Healthcare against the market", "ref": ("HEALTH", "SPY"),
             "kind": "ratio_trend", "sub": "Healthcare relative to the whole US market",
             "explain": "Falling means healthcare is lagging the market as a whole."},
        ],
        "series": ["HEALTH", "SPY"], "scenario_ref": "HEALTH",
        "calm": "Healthcare shares are holding their trend.",
        "sleeve_words": ["health", "pharma", "medic"],
    },
    "defence": {
        "label": "Defence", "title": "Defence", "short": "defence",
        "about": "Companies that make military equipment, paid for by government budgets.",
        "lights": [
            _trend("def_trend", "Defence shares", "DEFENCE", "Against their 200-day average", TREND_WHY),
            _fall("def_fall", "Defence: fall from high", "DEFENCE", 0.10, 0.20,
                  "10% is a correction, 20% a bear market", "How far defence shares are below their best of the past year."),
        ],
        "series": ["DEFENCE"], "scenario_ref": "DEFENCE",
        "calm": "Defence shares are holding their trend.",
        "sleeve_words": ["defen", "aerospace"],
    },
    "uk": {
        "label": "UK companies", "title": "UK companies", "short": "UK",
        "about": "Companies listed in London, and the UK economy behind the smaller ones.",
        "lights": [
            _trend("ftse250_trend", "UK mid-sized companies", "FTSE250", "FTSE 250 against its 200-day average",
                   TREND_WHY),
            _fall("ftse250_fall", "FTSE 250: fall from high", "FTSE250", 0.10, 0.20,
                  "10% is a correction, 20% a bear market",
                  "The FTSE 250 is much more tied to the UK economy than the FTSE 100."),
        ],
        "series": ["FTSE250", "FTSE100"], "scenario_ref": "FTSE250",
        "calm": "UK shares are holding their trend.",
        "sleeve_words": ["uk", "britain", "ftse"],
    },
    "em": {
        "label": "Emerging markets", "title": "Emerging markets", "short": "emerging markets",
        "about": "China, India, Taiwan, Korea, Brazil and other faster-growing economies.",
        "lights": [
            _trend("em_trend", "Emerging markets", "EM", "Against their 200-day average, in pounds", TREND_WHY),
            _trend("dollar", "The dollar", "DXY", "US dollar index against its 200-day average",
                   "A rising dollar has usually been hard on emerging markets, which often borrow in "
                   "dollars. Amber while it is above its average; red once the average is rising too.",
                   invert=True),
        ],
        "series": ["EM", "DXY"], "scenario_ref": "EM",
        "calm": "Emerging markets are holding their trend and the dollar isn't surging.",
        "sleeve_words": ["emerging"],
    },
    "financials": {
        "label": "Banks and financials", "title": "Banks and financials", "short": "financials",
        "about": "Banks, insurers and payment companies.",
        "lights": [
            _trend("fin_trend", "Financial shares", "FINANCIALS", "Against their 200-day average", TREND_WHY),
            _fall("fin_fall", "Financials: fall from high", "FINANCIALS", 0.10, 0.20,
                  "10% is a correction, 20% a bear market", "Banks suffer when loans go bad."),
        ],
        "series": ["FINANCIALS"], "scenario_ref": "FINANCIALS",
        "calm": "Financial shares are holding their trend.",
        "sleeve_words": ["financ", "bank", "insur"],
    },
    "smallcaps": {
        "label": "Smaller companies", "title": "Smaller companies", "short": "smaller companies",
        "about": "Companies too small for the big indices, more tied to borrowing costs.",
        "lights": [
            _trend("rut_trend", "US smaller companies", "RUT", "Russell 2000 against its 200-day average", TREND_WHY),
            _fall("rut_fall", "Smaller companies: fall from high", "RUT", 0.10, 0.20,
                  "10% is a correction, 20% a bear market", "Smaller companies fall further in downturns."),
        ],
        "series": ["RUT"], "scenario_ref": "RUT",
        "calm": "Smaller companies are holding their trend.",
        "sleeve_words": ["small"],
    },
    "consumer": {
        "label": "Consumer brands", "title": "Consumer brands", "short": "consumer brands",
        "about": "Food, drink and household names that people keep buying whatever the economy does.",
        "lights": [
            _trend("staples_trend", "Consumer staples", "STAPLES", "US consumer staples against their 200-day average",
                   TREND_WHY),
            _fall("staples_fall", "Consumer staples: fall from high", "STAPLES", 0.10, 0.20,
                  "10% is a correction, 20% a bear market",
                  "Staples usually fall less than the market; a deep fall here means even the steady names are "
                  "being sold."),
        ],
        "series": ["STAPLES"], "scenario_ref": "STAPLES",
        "calm": "Consumer brands are holding their trend.",
        "sleeve_words": ["consumer", "staple", "brand"],
    },
    "speculative": {
        "label": "Speculative growth", "title": "Speculative growth", "short": "speculative shares",
        "about": "Young companies valued on what they might become, many not yet profitable: the first to "
                 "soar when money is easy and the first to fall when it isn't.",
        "lights": [
            _trend("spec_trend", "Speculative growth shares", "SPECGROWTH",
                   "ARK Innovation against its 200-day average", TREND_WHY),
            _fall("spec_fall", "Speculative growth: fall from high", "SPECGROWTH", 0.20, 0.40,
                  "These swing hard, so the bands are wide",
                  "ARK Innovation, the best-known basket of speculative growth companies, as a read on how much "
                  "appetite there is for them. It is not what you hold."),
        ],
        "series": ["SPECGROWTH"], "scenario_ref": "SPECGROWTH",
        "calm": "Appetite for speculative growth shares is holding up.",
        "sleeve_words": ["speculat", "moonshot", "small bet", "venture", "punt"],
    },
    "rand": {
        "label": "The rand", "title": "The rand", "short": "rand",
        "about": "Money held in South African rand.",
        "lights": [
            {"key": "zar_rise", "title": "Pound against the rand", "ref": "GBPZAR", "kind": "rise",
             "amber": 0.10, "red": 0.20, "sub": "Rise from its low of the past year",
             "explain": "When a pound buys more rand, your rand is worth fewer pounds. Amber once the "
                        "rand has lost 10% from its best of the year, red at 20%."},
        ],
        "series": ["GBPZAR"], "scenario_ref": None,
        "calm": "The rand is within 10% of its best against the pound this year.",
        "sleeve_words": ["rand", "south africa"],
    },
    "crypto": {
        "label": "Crypto", "title": "Crypto", "short": "crypto",
        "about": "Bitcoin and other cryptocurrencies.",
        "lights": [
            _trend("btc_trend", "Bitcoin", "BTC", "Against its 200-day average, in pounds", TREND_WHY),
            _fall("btc_fall", "Bitcoin: fall from high", "BTC", 0.30, 0.50,
                  "Bitcoin swings hugely, so the bands are much wider", "Falls of more than half have happened several times."),
        ],
        "series": ["BTC"], "scenario_ref": "BTC",
        "calm": "Bitcoin is holding its trend.",
        "sleeve_words": ["crypto", "bitcoin"],
    },
}

#: Signal templates for each theme: what to watch beyond prices, with a documented
#: default threshold the person can change, and room for their own action.
SIGNALS: dict[str, list[dict]] = {
    "gold": [
        {"key": "real_yield_hi", "title": "US real yield", "group": "gold", "kind": "auto", "ref": "REALYIELD",
         "op": ">", "threshold": 2.5, "unit": "%",
         "means": "Gold has tended to struggle when real yields are this high."},
        {"key": "gold_fall_20", "title": "Gold below its high", "group": "gold", "kind": "auto", "ref": "GOLD",
         "measure": "drawdown", "op": ">", "threshold": 20.0, "unit": "%",
         "means": "A bear market in gold."},
    ],
    "oil": [
        {"key": "brent_high", "title": "Brent crude above", "group": "oil", "kind": "auto", "ref": "BRENT",
         "op": ">", "threshold": 100.0, "unit": "$",
         "means": "An oil shock: good for producers, bad for inflation and everything else."},
        {"key": "brent_low", "title": "Brent crude below", "group": "oil", "kind": "auto", "ref": "BRENT",
         "op": "<", "threshold": 60.0, "unit": "$",
         "means": "Producers' profits and dividends come under pressure."},
    ],
    "industrials": [
        {"key": "ind_fall_20", "title": "Industrials below their high", "group": "industrials", "kind": "auto",
         "ref": "INDUSTRIALS", "measure": "drawdown", "op": ">", "threshold": 20.0, "unit": "%",
         "means": "A bear market in industrial companies: orders are drying up."},
        {"key": "ism_below_50", "title": "US factory survey (ISM PMI) below 50", "group": "industrials",
         "kind": "manual", "op": ">=", "threshold": 1, "unit": "", "choices": ["Yes"],
         "means": "Below 50, factories are shrinking. Tick after each monthly release."},
    ],
    "consumer": [
        {"key": "staples_fall_20", "title": "Consumer staples below their high", "group": "consumer", "kind": "auto",
         "ref": "STAPLES", "measure": "drawdown", "op": ">", "threshold": 20.0, "unit": "%",
         "means": "Even the steady names are in a bear market."},
    ],
    "speculative": [
        {"key": "spec_fall_40", "title": "Speculative growth below its high", "group": "speculative", "kind": "auto",
         "ref": "SPECGROWTH", "measure": "drawdown", "op": ">", "threshold": 40.0, "unit": "%",
         "means": "Appetite for speculative companies has gone: they can fall much further from here."},
        {"key": "spec_hy", "title": "Junk-bond spread above", "group": "speculative", "kind": "auto",
         "ref": "HYOAS", "op": ">", "threshold": 5.0, "unit": "%",
         "means": "Lenders are getting nervous, and companies that aren't yet profitable need lenders most."},
    ],
    "metals": [
        {"key": "copper_fall_20", "title": "Copper below its high", "group": "metals", "kind": "auto",
         "ref": "COPPER", "measure": "drawdown", "op": ">", "threshold": 20.0, "unit": "%",
         "means": "A global growth scare usually shows here first."},
        {"key": "china_pmi", "title": "China's factory survey (PMI) below 50", "group": "metals",
         "kind": "manual", "op": ">=", "threshold": 1, "unit": "", "choices": ["Yes"],
         "means": "China buys about half the world's copper. Tick after each monthly release."},
    ],
    "rates": [
        {"key": "gilts_fall_10", "title": "Gilt fund below its high", "group": "rates", "kind": "auto",
         "ref": "GILTS", "measure": "drawdown", "op": ">", "threshold": 10.0, "unit": "%",
         "means": "A large fall for bonds: rates have jumped."},
    ],
    "inflation": [
        {"key": "breakeven_hi", "title": "US inflation expectation", "group": "inflation", "kind": "auto",
         "ref": "BREAKEVEN", "op": ">", "threshold": 3.0, "unit": "%",
         "means": "Markets doubt inflation will come back to target."},
        {"key": "uk_cpi_hi", "title": "UK inflation", "group": "inflation", "kind": "auto", "ref": "UKCPI",
         "measure": "yoy", "op": ">", "threshold": 4.0, "unit": "%",
         "means": "Cash and fixed incomes losing ground quickly."},
    ],
    "property": [
        {"key": "uk10y_prop", "title": "UK 10-year gilt yield", "group": "property", "kind": "auto",
         "ref": "UK10Y", "op": ">", "threshold": 5.0, "unit": "%",
         "means": "Property yields have to compete with what gilts pay."},
        {"key": "uk_prop_fall", "title": "UK property shares below their high", "group": "property",
         "kind": "auto", "ref": "UKPROP", "measure": "drawdown", "op": ">", "threshold": 20.0, "unit": "%",
         "means": "A bear market in UK property shares."},
    ],
    "healthcare": [
        {"key": "hc_lag", "title": "Healthcare against the market since your baseline", "group": "healthcare",
         "kind": "auto", "ref": ("HEALTH", "SPY"), "op": "<", "threshold": -10.0, "unit": "%",
         "means": "Healthcare falling well behind the market as a whole."},
        {"key": "drug_pricing", "title": "US drug-pricing rules tightened this quarter", "group": "healthcare",
         "kind": "manual", "op": ">=", "threshold": 1, "unit": "", "choices": ["Yes"],
         "means": "The biggest single risk to drug makers' profits. Tick after each quarter's news."},
    ],
    "defence": [
        {"key": "def_fall_20", "title": "Defence shares below their high", "group": "defence", "kind": "auto",
         "ref": "DEFENCE", "measure": "drawdown", "op": ">", "threshold": 20.0, "unit": "%",
         "means": "A bear market in defence companies."},
        {"key": "nato_cut", "title": "Defence budgets cut or pledges dropped", "group": "defence",
         "kind": "manual", "op": ">=", "threshold": 1, "unit": "", "choices": ["Yes"],
         "means": "Defence companies live on government budgets."},
    ],
    "uk": [
        {"key": "ftse250_fall_20", "title": "FTSE 250 below its high", "group": "uk", "kind": "auto",
         "ref": "FTSE250", "measure": "drawdown", "op": ">", "threshold": 20.0, "unit": "%",
         "means": "A bear market in UK mid-sized companies."},
        {"key": "gbp_low", "title": "Pound in dollars below", "group": "uk", "kind": "auto", "ref": "GBPUSD",
         "op": "<", "threshold": 1.20, "unit": "$", "means": "A weak pound: confidence in the UK falling."},
    ],
    "em": [
        {"key": "dxy_high", "title": "US dollar index above", "group": "em", "kind": "auto", "ref": "DXY",
         "op": ">", "threshold": 105.0, "unit": "", "means": "A strong dollar squeezes emerging markets."},
        {"key": "em_fall_20", "title": "Emerging markets below their high", "group": "em", "kind": "auto",
         "ref": "EM", "measure": "drawdown", "op": ">", "threshold": 20.0, "unit": "%",
         "means": "A bear market in emerging markets."},
    ],
    "financials": [
        {"key": "curve_inverted", "title": "US yield curve inverted", "group": "financials", "kind": "auto",
         "ref": "CURVE", "op": "<", "threshold": 0.0, "unit": "pts",
         "means": "Banks borrow short and lend long; an inverted curve squeezes them."},
        {"key": "fin_fall_20", "title": "Financials below their high", "group": "financials", "kind": "auto",
         "ref": "FINANCIALS", "measure": "drawdown", "op": ">", "threshold": 20.0, "unit": "%",
         "means": "A bear market in banks and insurers."},
    ],
    "smallcaps": [
        {"key": "rut_fall_20", "title": "Smaller companies below their high", "group": "smallcaps",
         "kind": "auto", "ref": "RUT", "measure": "drawdown", "op": ">", "threshold": 20.0, "unit": "%",
         "means": "A bear market in smaller companies."},
        {"key": "hy_wide", "title": "Junk-bond spread above", "group": "smallcaps", "kind": "auto",
         "ref": "HYOAS", "op": ">", "threshold": 5.0, "unit": "%",
         "means": "Smaller companies borrow more, and pay more when lenders get nervous."},
    ],
    "rand": [
        {"key": "zar_weak", "title": "Pound buys more than", "group": "rand", "kind": "auto", "ref": "GBPZAR",
         "op": ">", "threshold": 25.0, "unit": "R", "means": "The rand at its weakest in years."},
    ],
    "crypto": [
        {"key": "btc_fall_50", "title": "Bitcoin below its high", "group": "crypto", "kind": "auto",
         "ref": "BTC", "measure": "drawdown", "op": ">", "threshold": 50.0, "unit": "%",
         "means": "A crypto winter."},
    ],
}


# ---------------------------------------------------------------------------- the choice

def legacy() -> dict:
    return {"main": "ai", "themes": ["ai"], "legacy": True}


def watch() -> dict:
    """What this copy watches. A copy that has never chosen keeps the original AI watch."""
    w = db.get_meta("watch")
    if not isinstance(w, dict) or not w.get("themes"):
        return legacy()
    themes = [t for t in w.get("themes") if t in LIBRARY or str(t).startswith(("company:", "cluster:"))]
    if not themes:
        return legacy()
    main = w.get("main") if w.get("main") in themes else themes[0]
    return {"main": main, "themes": themes, "legacy": False, "chosen_at": w.get("chosen_at"),
            "why": w.get("why") or {}}


def set_watch(main: str | None, themes: list[str], why: dict | None = None) -> dict:
    themes = [t for t in dict.fromkeys(themes) if t in LIBRARY or str(t).startswith(("company:", "cluster:"))]
    if not themes:
        db.set_meta("watch", {})
        return legacy()
    if main not in themes:
        main = themes[0]
    db.set_meta("watch", {"main": main, "themes": themes, "chosen_at": db.today(), "why": why or {}})
    return watch()


def label(key: str) -> str:
    if key in LIBRARY:
        return LIBRARY[key]["label"]
    kind, _, name = key.partition(":")
    return name or key


def title(key: str) -> str:
    if key in LIBRARY:
        return LIBRARY[key]["title"]
    return label(key)


def lower_first(text: str) -> str:
    """For a title inside a sentence: "The AI trade" becomes "the AI trade", but "UK
    companies" stays as it is, because a word in capitals is a name, not a capital letter."""
    if not text:
        return text
    first = text.split()[0]
    if len(first) > 1 and first.isupper():
        return text
    return text[0].lower() + text[1:]


def in_sentence(key: str) -> str:
    return lower_first(title(key))


def series_needed() -> list[str]:
    """Reference series the watched themes need beyond those every copy fetches."""
    out = []
    for t in watch()["themes"]:
        out += (LIBRARY.get(t) or {}).get("series") or []
    from ..market import catalogue
    return [k for k in dict.fromkeys(out) if k in catalogue.REFERENCE]


# ---------------------------------------------------------------------------- exposure

def _sleeve_theme(sleeve: str | None) -> str | None:
    s = " " + (sleeve or "").lower() + " "
    for key, t in LIBRARY.items():
        if any(w in s for w in t.get("sleeve_words") or []):
            return key
    return None


def _stored() -> dict[int, dict[str, tuple[float, str, str | None]]]:
    out: dict[int, dict] = {}
    for r in db.rows("SELECT instrument_id, theme, share, source, as_of FROM exposures"):
        out.setdefault(r["instrument_id"], {})[r["theme"]] = (r["share"], r["source"] or "you", r["as_of"])
    return out


def share_of(x: dict, theme: str, stored: dict | None = None) -> tuple[float | None, str]:
    """(share 0-100 or None if unknown, where it came from) for one holding and theme."""
    if theme == "ai":
        if x.get("ai_share") is not None:
            return float(x["ai_share"]), ("you" if x.get("ai_share_set") else "sleeve")
        d = classify.default_themes(x).get("ai")
        return (d, "typical") if d is not None else (None, "unknown")
    st = (stored if stored is not None else _stored()).get(x["instrument_id"], {})
    if theme in st:
        return float(st[theme][0]), st[theme][1]
    d = classify.default_themes(x)
    if theme in d:
        return float(d[theme]), "typical"
    if _sleeve_theme(x.get("sleeve")) == theme:
        return 100.0, "sleeve"
    if classify.is_single_company(x) or d:
        return 0.0, "typical"
    return None, "unknown"


def exposure(pos: list[dict], totals: dict, theme: str, stored: dict | None = None) -> dict:
    """Pounds and share of everything that rides on one theme, looking through funds."""
    if theme.startswith("company:"):
        from . import rules
        ce = rules.company_exposure(pos, totals.get("total") or 0.0, theme.split(":", 1)[1])
        return {"theme": theme, "value": ce["true_value"],
                "pct": (ce["true_value"] / totals["total"]) if totals.get("total") else None,
                "unknown": [], "unknown_value": 0.0, "top": ce["holdings"], "coverage": 1.0}
    if theme.startswith("cluster:"):
        name = theme.split(":", 1)[1].lower()
        mine = [x for x in pos if x["value"] is not None and (x.get("theme") or "").lower() == name]
        v = sum(x["value"] for x in mine)
        return {"theme": theme, "value": v, "pct": (v / totals["total"]) if totals.get("total") else None,
                "unknown": [], "unknown_value": 0.0,
                "top": [{"name": x["name"], "value": x["value"], "share": 100.0} for x in mine], "coverage": 1.0}
    stored = _stored() if stored is None else stored
    total = totals.get("total") or 0.0
    value, rated, unknown, rows = 0.0, 0.0, [], []
    sources: dict[str, float] = {}
    for x in pos:
        if x["value"] is None:
            continue
        share, src = share_of(x, theme, stored)
        if share is None:
            unknown.append({"name": x["name"], "value": x["value"], "instrument_id": x["instrument_id"]})
            continue
        rated += x["value"]
        v = x["value"] * share / 100
        value += v
        sources[src] = sources.get(src, 0.0) + v
        if v > 0:
            rows.append({"name": x["name"], "instrument_id": x["instrument_id"], "platform": x["platform"],
                         "value": x["value"], "share": share, "theme_value": v, "source": src})
    merged: dict[int, dict] = {}
    for r in rows:
        m = merged.setdefault(r["instrument_id"], dict(r, value=0.0, theme_value=0.0, platforms=[]))
        m["value"] += r["value"]
        m["theme_value"] += r["theme_value"]
        m["platforms"].append(r["platform"])
    invested = sum(x["value"] for x in pos if x["value"] is not None)
    return {"theme": theme, "value": value, "pct": (value / total) if total else None,
            "unknown": unknown, "unknown_value": sum(u["value"] for u in unknown),
            "top": sorted(merged.values(), key=lambda r: r["theme_value"], reverse=True)[:12],
            "coverage": (rated / invested) if invested else None,
            "typical_share": (sources.get("typical", 0.0) / value) if value else 0.0}


def all_exposures(pos: list[dict], totals: dict) -> list[dict]:
    stored = _stored()
    out = []
    for key in LIBRARY:
        if key == "rand":
            continue
        e = exposure(pos, totals, key, stored)
        e.update(label=LIBRARY[key]["label"], short=LIBRARY[key]["short"])
        out.append(e)
    # Rand: cash held in rand, from the cash accounts rather than holdings.
    rand = sum(p["cash"] or 0.0 for p in totals.get("platforms", []) if p.get("currency") == "ZAR")
    everything = (totals.get("everything") or totals.get("total") or 0.0)
    out.append({"theme": "rand", "label": LIBRARY["rand"]["label"], "short": "rand", "value": rand,
                "pct": (rand / everything) if everything else None, "unknown": [], "unknown_value": 0.0,
                "top": [], "coverage": 1.0, "typical_share": 0.0})
    return sorted(out, key=lambda e: -(e["pct"] or 0.0))


def clusters(pos: list[dict], totals: dict) -> list[dict]:
    names = sorted({(x.get("theme") or "").strip() for x in pos if (x.get("theme") or "").strip()})
    out = []
    for n in names:
        e = exposure(pos, totals, f"cluster:{n}")
        e.update(label=n, short=n)
        out.append(e)
    return out


def suggest(pos: list[dict], totals: dict, care: list[str] | None = None,
            pinned: str | None = None, threshold: float = THRESHOLD) -> dict:
    """Which themes to watch, and why, from exposure and what the person cares about."""
    care = [c for c in (care or []) if c in LIBRARY]
    exps = all_exposures(pos, totals)
    by = {e["theme"]: e for e in exps}
    picked, why = [], {}
    for e in exps:
        pct = (e["pct"] or 0.0) * 100
        if pct >= threshold:
            picked.append(e["theme"])
            why[e["theme"]] = f"{pct:.0f}% of your money rides on it" + \
                (" (some of that from typical fund make-ups)" if e.get("typical_share", 0) > 0.3 else "") + "."
    for c in care:
        if c not in picked:
            picked.append(c)
            pct = (by.get(c, {}).get("pct") or 0.0) * 100
            why[c] = f"You said it matters to you ({pct:.0f}% of your money)."
    for cl in clusters(pos, totals):
        pct = (cl["pct"] or 0.0) * 100
        if pct >= 5:
            key = cl["theme"]
            picked.append(key)
            why[key] = f"Your own group of holdings, {pct:.0f}% of your money."
    if pinned and (pinned in LIBRARY or pinned.startswith(("company:", "cluster:"))):
        main = pinned
        if main not in picked:
            picked.insert(0, main)
            why.setdefault(main, "You chose it.")
    else:
        ranked = sorted([t for t in picked if t in by], key=lambda t: -(by[t]["pct"] or 0.0))
        main = ranked[0] if ranked else (picked[0] if picked else None)
    picked = sorted(picked, key=lambda t: (t != main, -((by.get(t) or {}).get("pct") or 0.0)))[:5]
    return {"main": main, "themes": picked, "why": why, "exposures": exps,
            "note": None if picked else "No single market force carries 10% or more of your money, "
                                         "so your watch follows markets in general."}


def lights_for(key: str) -> list[dict]:
    """The light definitions for one theme, each tagged with its group."""
    if key == "ai":
        from . import signals
        return [d for d in signals.DEFS if d["group"] == "ai"]
    if key in LIBRARY:
        return [dict(d, group=key) for d in LIBRARY[key]["lights"]]
    kind, _, name = key.partition(":")
    if kind == "company":
        x = db.one("SELECT market_symbol FROM instruments WHERE lower(COALESCE(company, name, symbol))=? "
                   "AND market_symbol IS NOT NULL ORDER BY id LIMIT 1", (name.lower(),))
        if not x:
            return []
        ref = ("SEC", x["market_symbol"])
        return [{"key": f"co_trend_{_slug(name)}", "title": name, "ref": ref, "kind": "trend", "group": key,
                 "sub": "Share price against its 200-day average", "explain": TREND_WHY},
                {"key": f"co_fall_{_slug(name)}", "title": f"{name}: fall from high", "ref": ref,
                 "kind": "drawdown", "amber": 0.15, "red": 0.30, "group": key,
                 "sub": "One company swings more than an index, so the bands are wider",
                 "explain": "How far the share price is below its best level of the past year."}]
    if kind == "cluster":
        syms = [r["market_symbol"] for r in db.rows(
            "SELECT DISTINCT market_symbol FROM instruments WHERE lower(theme)=? AND market_symbol IS NOT NULL",
            (name.lower(),))]
        if not syms:
            return []
        ref = ("BASKET",) + tuple(syms)
        return [{"key": f"cl_fall_{_slug(name)}", "title": f"{name}: fall from high", "ref": ref,
                 "kind": "drawdown", "amber": 0.15, "red": 0.25, "group": key,
                 "sub": "Equal-weighted, from the holdings in it",
                 "explain": "How far this group of holdings, taken together, is below its best of the past year."}]
    return []


def signals_for(key: str) -> list[dict]:
    if key in SIGNALS:
        return [dict(s) for s in SIGNALS[key]]
    kind, _, name = key.partition(":")
    if kind == "company":
        x = db.one("SELECT market_symbol FROM instruments WHERE lower(COALESCE(company, name, symbol))=? "
                   "AND market_symbol IS NOT NULL ORDER BY id LIMIT 1", (name.lower(),))
        if x:
            return [{"key": f"co_sig_{_slug(name)}", "title": f"{name} below its high", "group": key,
                     "kind": "auto", "ref": ("SEC", x["market_symbol"]), "measure": "drawdown", "op": ">",
                     "threshold": 30.0, "unit": "%", "means": "A large fall in one company: time to "
                     "re-read why you own it, not necessarily to sell."}]
    return []


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:30]


def today() -> str:
    return dt.date.today().isoformat()
