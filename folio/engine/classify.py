"""What a holding is: shares, bonds, gold, property, cash — and roughly what it costs and
which market forces move it.

Three sources, in order: what the person has set on the holding; a short table of
well-known funds and companies; and, failing both, the words in its name. The table's
figures are typical ones, dated, and every screen that uses them says they are
approximate — a fund's own factsheet is always the better source, and typing it in
replaces the default.

The index weights are MSCI ACWI's own, from its factsheet of 30 September 2026: the
nearest thing to "the whole world's stock market" for a global index fund.
"""

from __future__ import annotations

import re

from ..brokers import tbills

AS_OF = "2026-09-30"
ACWI_SOURCE = "MSCI ACWI factsheet, 30 September 2026"

#: MSCI ACWI, 30 Sep 2026. AI-linked: Nvidia 5.11, Microsoft 3.52, Amazon 2.35, Alphabet
#: (both classes) 3.52, TSMC 1.87, Meta 1.55, Broadcom 1.55, Micron 1.17 = 20.6%.
GLOBAL = {"ai": 20.6, "healthcare": 8.4, "financials": 16.2, "oil": 4.0, "metals": 3.5,
          "property": 3.7, "uk": 3.0}
#: An S&P 500 fund: the same companies' weights rescaled to the US's 64.2% of ACWI.
US500 = {"ai": 29.2}

# symbol: (asset class, typical yearly charge %, duration in years, theme shares, label)
KNOWN: dict[str, tuple] = {
    # global and developed-world index funds
    "VWRL": ("equity", 0.19, None, GLOBAL, "Global index"),
    "VWRP": ("equity", 0.19, None, GLOBAL, "Global index"),
    "SSAC": ("equity", 0.20, None, GLOBAL, "Global index"),
    "VHVG": ("equity", 0.12, None, GLOBAL, "Developed-world index"),
    "SWDA": ("equity", 0.20, None, GLOBAL, "Developed-world index"),
    "XDWD": ("equity", 0.19, None, GLOBAL, "Developed-world index"),
    # US
    "VUSA": ("equity", 0.07, None, US500, "S&P 500 index"),
    "VUAG": ("equity", 0.07, None, US500, "S&P 500 index"),
    "CSP1": ("equity", 0.07, None, US500, "S&P 500 index"),
    "SPXP": ("equity", 0.05, None, US500, "S&P 500 index"),
    # emerging markets
    "EMIM": ("equity", 0.18, None, {"em": 100, "ai": 15}, "Emerging markets index"),
    "VFEM": ("equity", 0.22, None, {"em": 100, "ai": 15}, "Emerging markets index"),
    # UK
    "ISF": ("equity", 0.07, None, {"uk": 100, "oil": 12, "financials": 23, "healthcare": 11, "metals": 7}, "FTSE 100 index"),
    "VUKE": ("equity", 0.09, None, {"uk": 100, "oil": 12, "financials": 23, "healthcare": 11, "metals": 7}, "FTSE 100 index"),
    "VMID": ("equity", 0.10, None, {"uk": 100, "smallcaps": 100}, "FTSE 250 index"),
    # smaller companies
    "WLDS": ("equity", 0.35, None, {"smallcaps": 100}, "World smaller companies"),
    # bonds
    "VGOV": ("bond", 0.07, 9.0, {"rates": 100}, "UK gilts"),
    "IGLT": ("bond", 0.07, 9.0, {"rates": 100}, "UK gilts"),
    "GLTS": ("bond", 0.06, 2.5, {"rates": 100}, "Short-dated UK gilts"),
    "INXG": ("linker", 0.10, 16.0, {"rates": 100, "inflation": 100}, "Index-linked gilts"),
    "VAGP": ("bond", 0.10, 6.5, {"rates": 100}, "Global bonds (£ hedged)"),
    # gold and commodities
    "SGLN": ("gold", 0.12, None, {"gold": 100}, "Physical gold"),
    "PHAU": ("gold", 0.19, None, {"gold": 100}, "Physical gold"),
    "IGLN": ("gold", 0.12, None, {"gold": 100}, "Physical gold"),
    # property and infrastructure
    "IUKP": ("property", 0.40, None, {"property": 100, "uk": 100}, "UK property shares"),
    "HPRO": ("property", 0.24, None, {"property": 100}, "Global property shares"),
    "INFR": ("property", 0.65, None, {"property": 100}, "Global infrastructure"),
    # themes
    "NATP": ("equity", 0.49, None, {"defence": 100}, "Defence companies"),
    "INRG": ("equity", 0.65, None, {}, "Clean energy companies"),
}

#: Single companies, by the symbol brokers write.
COMPANIES = {
    "ai": ["NVDA", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "AVGO", "TSM", "ASML", "AMD", "MU",
           "ORCL", "ARM", "SMCI", "PLTR", "CRWV"],
    "healthcare": ["AZN", "GSK", "NVO", "NOVO-B", "JNJ", "PFE", "LLY", "MRK", "ABBV", "SN.", "SN",
                   "BMY", "UNH", "HLN", "TMO", "A"],
    "oil": ["SHEL", "BP.", "BP", "XOM", "CVX", "TTE", "COP", "HBR"],
    "metals": ["RIO", "GLEN", "AAL", "BHP", "FCX", "ANTO", "SCCO", "VALE"],
    "gold": ["NEM", "GOLD", "FRES", "AEM"],
    "defence": ["BA.", "BAE", "RR.", "LMT", "RTX", "NOC", "GD", "RHM", "QQ.", "CHG"],
    "financials": ["HSBA", "LLOY", "BARC", "NWG", "JPM", "BAC", "V", "MA", "BRK-B", "BRK.B",
                   "GS", "MS", "LSEG", "STAN"],
    "property": ["LAND", "BLND", "SGRO", "O", "PLD", "AMT"],
}
_COMPANY_THEME = {sym: theme for theme, syms in COMPANIES.items() for sym in syms}

_WORDS = [
    (r"index[- ]linked|inflation[- ]linked|\blinker", "linker"),
    (r"\bgilt|treasury(?! bill)|\bbond|govt|government|corporate|aggregate|fixed income", "bond"),
    (r"money market|\bcash\b|liquidity|t-?bill|treasury bill", "cash"),
    (r"\bgold\b", "gold"),
    (r"silver|platinum|commodit|copper|\boil\b|brent|crude", "commodity"),
    (r"propert|\breit|real estate|infrastructure", "property"),
    (r"bitcoin|ethereum|crypto", "crypto"),
    (r"multi[- ]asset|lifestrategy|balanced|managed|lifestyle|target date|cautious|moderate",
     "mixed"),
]

ASSET_CLASSES = {
    "equity": "Shares", "bond": "Bonds and gilts", "linker": "Index-linked gilts",
    "cash": "Cash", "gold": "Gold", "commodity": "Other commodities",
    "property": "Property and infrastructure", "crypto": "Crypto", "mixed": "Mixed funds",
}


def _base(symbol: str | None) -> str:
    s = (symbol or "").upper().strip()
    return re.sub(r"\.L$", "", s) if not s.endswith(".") else s


def known(row: dict) -> tuple | None:
    for cand in (row.get("symbol"), row.get("market_symbol")):
        hit = KNOWN.get(_base(cand))
        if hit:
            return hit
    return None


def asset_class(row: dict) -> tuple[str, str]:
    """(class, how it was decided: 'you' | 'known' | 'name' | 'guess')."""
    if row.get("asset_class"):
        return row["asset_class"], "you"
    if tbills.is_tbill(row.get("name"), row.get("symbol"), row.get("isin")):
        return "cash", "known"
    k = known(row)
    if k:
        return k[0], "known"
    name = (row.get("name") or "").lower()
    for rx, cls in _WORDS:
        if re.search(rx, name):
            return cls, "name"
    sleeve = (row.get("sleeve") or "").lower()
    if sleeve:
        for rx, cls in _WORDS:
            if re.search(rx, sleeve):
                return cls, "name"
    return "equity", "guess"


def ocf(row: dict) -> tuple[float | None, str]:
    if row.get("ocf") is not None:
        return float(row["ocf"]), "you"
    k = known(row)
    if k:
        return k[1], "typical"
    return None, "unknown"


def duration(row: dict) -> tuple[float | None, str]:
    if row.get("duration") is not None:
        return float(row["duration"]), "you"
    k = known(row)
    if k and k[2]:
        return k[2], "typical"
    return None, "unknown"


def is_single_company(row: dict) -> bool:
    if known(row):
        return False
    name = (row.get("name") or "").lower()
    if re.search(r"\betf\b|ucits|\bfund\b|index|tracker|trust\b|\bacc\b|\bdist\b|\binc\b\)|ishares|vanguard|"
                 r"invesco|xtrackers|spdr|hanetf|wisdomtree|amundi|l&g|legal & general|hsbc ftse|"
                 r"fidelity index|\bett?c\b", name):
        return False
    cls, _ = asset_class(row)
    return cls == "equity" and not tbills.is_tbill(row.get("name"), row.get("symbol"), row.get("isin"))


def default_themes(row: dict) -> dict[str, float]:
    """Theme shares a holding starts with before anybody sets them. Empty means unknown."""
    k = known(row)
    if k:
        return dict(k[3])
    sym = _base(row.get("symbol"))
    out: dict[str, float] = {}
    theme = _COMPANY_THEME.get(sym)
    if theme and is_single_company(row):
        out[theme] = 100.0
    cls, how = asset_class(row)
    if how != "guess":
        if cls == "gold":
            out["gold"] = 100.0
        elif cls in ("bond", "linker"):
            out["rates"] = 100.0
            if cls == "linker":
                out["inflation"] = 100.0
        elif cls == "property":
            out["property"] = 100.0
        elif cls == "crypto":
            out["crypto"] = 100.0
    if is_single_company(row) and (row.get("isin") or "").upper().startswith("GB"):
        out["uk"] = 100.0
    return out
