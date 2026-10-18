"""The X-Ray: what a portfolio really holds, the way a careful adviser would check it.

Built on Morningstar's Portfolio X-Ray (asset mix, regions, sectors, the same company
inside several funds) and on the checks in Allan's own reviews: concentration, the
holdings too small to matter, what it all costs a year in pounds, money in the wrong
wrapper, protection limits, how much a rise in interest rates would cost, and whether each
single company has beaten simply owning the world.

Every figure says how sure it is. A fund's make-up typed from its factsheet is exact; a
typical figure for a well-known fund is labelled as typical; anything unknown is listed
as unknown and never counted as nothing.
"""

from __future__ import annotations

import datetime as dt

from .. import db
from ..market import store
from . import allocation, classify, isa, mathx, portfolio, rules, themes

#: The largest companies inside a global or S&P 500 index fund, with their weights in
#: it — MSCI ACWI, 30 September 2026 (the S&P 500 weights rescaled to the US's 64.21%).
#: Enough to see when a single company owned directly is also a big part of the funds.
TOP_INSIDE = {
    "global": {"NVIDIA": 5.11, "Apple": 4.76, "Microsoft": 3.52, "Amazon": 2.35, "Alphabet": 3.52,
               "TSMC": 1.87, "Meta": 1.55, "Broadcom": 1.55, "Micron": 1.17},
    "us500": {"NVIDIA": 7.96, "Apple": 7.41, "Microsoft": 5.48, "Amazon": 3.66, "Alphabet": 5.48,
              "Meta": 2.41, "Broadcom": 2.41, "Micron": 1.82},
}
_NAME_KEYS = {"NVIDIA": ["nvidia", "nvda"], "Apple": ["apple", "aapl"], "Microsoft": ["microsoft", "msft"],
              "Amazon": ["amazon", "amzn"], "Alphabet": ["alphabet", "googl", "goog"],
              "TSMC": ["taiwan semiconductor", "tsm"], "Meta": ["meta platforms", "meta"],
              "Broadcom": ["broadcom", "avgo"], "Micron": ["micron", "mu"]}
US_SHARE = {"global": 64.21, "us500": 100.0}


def _index_kind(x: dict) -> str | None:
    k = classify.known(x)
    if not k:
        return None
    if k[3] is classify.GLOBAL:
        return "global"
    if k[3] is classify.US500:
        return "us500"
    return None


def _company_of(x: dict) -> str | None:
    if not classify.is_single_company(x):
        return None
    hay = f"{(x.get('company') or '').lower()} {(x.get('name') or '').lower()} {(x.get('symbol') or '').lower()}"
    for name, keys in _NAME_KEYS.items():
        if any(k == (x.get("symbol") or "").lower() or (len(k) > 4 and k in hay) for k in keys):
            return name
    return x.get("company") or x.get("name")


def run(pos: list[dict] | None = None, tot: dict | None = None, settings: dict | None = None) -> dict:
    pos = portfolio.positions() if pos is None else pos
    tot = portfolio.totals(pos) if tot is None else tot
    total = tot.get("total") or 0.0
    priced = [x for x in pos if x["value"] is not None]
    invested = sum(x["value"] for x in priced)
    out: dict = {"total": total, "invested": invested, "cash": tot.get("cash"), "as_of": db.today(),
                 "holdings": len(pos), "unpriced": tot.get("unpriced", 0)}
    if not priced:
        out["empty"] = True
        out["findings"] = []
        return out

    # ---- asset mix
    mix: dict[str, dict] = {}
    for x in priced:
        cls, how = classify.asset_class(x)
        m = mix.setdefault(cls, {"cls": cls, "label": classify.ASSET_CLASSES.get(cls, cls), "value": 0.0,
                                 "guessed": 0.0})
        m["value"] += x["value"]
        if how == "guess":
            m["guessed"] += x["value"]
    if tot.get("cash"):
        m = mix.setdefault("cash", {"cls": "cash", "label": "Cash", "value": 0.0, "guessed": 0.0})
        m["value"] += tot["cash"]
    out["asset_mix"] = sorted(({**m, "pct": m["value"] / total if total else None} for m in mix.values()),
                              key=lambda m: -m["value"])

    # ---- regions (approximate) and currencies
    us = uk = em = 0.0
    region_known = 0.0
    for x in priced:
        kind = _index_kind(x)
        isin = (x.get("isin") or "").upper()
        if kind:
            us += x["value"] * US_SHARE[kind] / 100
            uk += x["value"] * (3.0 if kind == "global" else 0.0) / 100
            region_known += x["value"]
        elif classify.is_single_company(x) and (isin[:2] in ("US", "GB") or
                                                (x.get("currency") or "").upper() in ("USD", "GBP", "GBX")):
            # Where a company is listed is a fair stand-in for where it is based.
            if isin.startswith("US") or (not isin and (x.get("currency") or "").upper() == "USD"):
                us += x["value"]
            else:
                uk += x["value"]
            region_known += x["value"]
        else:
            th = classify.default_themes(x)
            if "em" in th:
                em += x["value"] * th["em"] / 100
                region_known += x["value"]
            elif "uk" in th:
                uk += x["value"] * th["uk"] / 100
                region_known += x["value"]
    out["regions"] = {"us": us, "uk": uk, "em": em, "known": region_known,
                      "us_pct": us / invested, "uk_pct": uk / invested, "em_pct": em / invested,
                      "coverage": region_known / invested, "note": "Approximate: index funds from their "
                      f"index's country weights ({classify.ACWI_SOURCE}); single companies by where they are listed."}
    ccy: dict[str, float] = {}
    for x in priced:
        c = (x.get("currency") or "GBP").upper()
        c = {"GBX": "GBP", "GBP": "GBP"}.get(c, c)
        ccy[c] = ccy.get(c, 0.0) + x["value"]
    for p in tot.get("platforms", []):
        if p["kind"] != "card" and p.get("cash"):
            ccy[p.get("currency") or "GBP"] = ccy.get(p.get("currency") or "GBP", 0.0) + p["cash"]
    out["currencies"] = sorted(({"ccy": k, "value": v, "pct": v / sum(ccy.values())} for k, v in ccy.items()),
                               key=lambda r: -r["value"])

    # ---- themes
    out["themes"] = [{k: e[k] for k in ("theme", "label", "value", "pct", "coverage", "unknown_value",
                                         "typical_share")} | {"top": e["top"][:5], "unknown": e["unknown"][:8]}
                     for e in themes.all_exposures(pos, tot)]
    out["clusters"] = [{k: c[k] for k in ("theme", "label", "value", "pct")} for c in themes.clusters(pos, tot)]

    # ---- overlap: one company owned directly and inside funds
    inside: dict[str, dict] = {}
    for x in priced:
        kind = _index_kind(x)
        if kind:
            for co, w in TOP_INSIDE[kind].items():
                d = inside.setdefault(co, {"company": co, "direct": 0.0, "via": 0.0, "funds": []})
                d["via"] += x["value"] * w / 100
                d["funds"].append(x["name"])
    for r in db.rows("SELECT l.fund_id, l.company, l.weight FROM lookthrough l"):
        fund_value = sum(x["value"] for x in priced if x["instrument_id"] == r["fund_id"])
        d = inside.setdefault(r["company"], {"company": r["company"], "direct": 0.0, "via": 0.0, "funds": []})
        d["via"] += fund_value * r["weight"] / 100
    for x in priced:
        co = _company_of(x)
        if co:
            d = inside.setdefault(co, {"company": co, "direct": 0.0, "via": 0.0, "funds": []})
            d["direct"] += x["value"]
    overlap = []
    for d in inside.values():
        d["true"] = d["direct"] + d["via"]
        d["pct"] = d["true"] / total if total else None
        d["funds"] = sorted(set(d["funds"]))
        if d["direct"] and d["via"]:
            overlap.append(d)
    out["overlap"] = sorted(overlap, key=lambda d: -d["true"])
    biggest = sorted(inside.values(), key=lambda d: -d["true"])[:10]
    out["biggest_companies"] = biggest

    # ---- concentration, small holdings
    merged: dict[int, float] = {}
    names: dict[int, str] = {}
    for x in priced:
        merged[x["instrument_id"]] = merged.get(x["instrument_id"], 0.0) + x["value"]
        names[x["instrument_id"]] = x["name"]
    ranked = sorted(merged.items(), key=lambda kv: -kv[1])
    out["top10_pct"] = sum(v for _, v in ranked[:10]) / total if total else None
    out["largest"] = [{"name": names[i], "value": v, "pct": v / total, "instrument_id": i} for i, v in ranked[:10]]
    out["small"] = [{"name": names[i], "value": v, "pct": v / total, "instrument_id": i}
                    for i, v in ranked if total and v / total < 0.01]

    # ---- costs
    fund_cost, unknown_cost, dear = 0.0, [], []
    for x in priced:
        oc, how = classify.ocf(x)
        single = classify.is_single_company(x)
        if single:
            continue
        if oc is None:
            unknown_cost.append({"name": x["name"], "value": x["value"], "instrument_id": x["instrument_id"]})
            continue
        fund_cost += x["value"] * oc / 100
        if oc > 0.5:
            dear.append({"name": x["name"], "ocf": oc, "how": how, "cost": x["value"] * oc / 100,
                         "instrument_id": x["instrument_id"]})
    fees = sum(p.get("fee_year") or 0.0 for p in tot.get("platforms", []) if p["kind"] == "platform")
    out["costs"] = {"funds": fund_cost, "platforms": fees, "total": fund_cost + fees,
                    "pct": (fund_cost + fees) / invested if invested else None,
                    "unknown": unknown_cost, "dear": sorted(dear, key=lambda d: -d["cost"]),
                    "trades_12m": db.scalar("SELECT SUM(fees_gbp) FROM trades WHERE traded_on>=?",
                                            ((dt.date.today() - dt.timedelta(days=365)).isoformat(),), 0.0)}

    # ---- wrappers
    by_wrapper: dict[str, float] = {}
    for p in tot.get("platforms", []):
        if p["kind"] == "platform":
            by_wrapper[p["wrapper"]] = by_wrapper.get(p["wrapper"], 0.0) + p["total"]
    allowance = isa.allowance()
    out["wrappers"] = {"by": by_wrapper, "gia": by_wrapper.get("gia", 0.0), "isa_left": allowance["remaining"],
                       "isa_used": allowance["used"], "isa_year": allowance["label"],
                       "isa_days_left": allowance["days_left"]}

    # ---- protection
    prot = []
    for p in tot.get("platforms", []):
        if p.get("limit") and p["kind"] != "card":
            share = p["total"] / p["limit"] if p["limit"] else 0.0
            if share >= 0.9:
                prot.append({"name": p["name"], "total": p["total"], "limit": p["limit"], "share": share,
                             "scheme": p.get("scheme") or "FSCS", "currency": p.get("currency"),
                             "native": p.get("cash_native"), "limit_native": p.get("limit_native")})
    out["protection"] = prot

    # ---- interest rates and inflation
    bonds, linked, real = [], 0.0, 0.0
    per_point = 0.0
    for x in priced:
        cls, _ = classify.asset_class(x)
        if cls in ("bond", "linker"):
            dur, how = classify.duration(x)
            loss = x["value"] * (dur if dur is not None else 7.0) / 100
            per_point += loss
            bonds.append({"name": x["name"], "value": x["value"], "duration": dur, "how": how, "loss": loss})
            if cls == "linker":
                linked += x["value"]
        if cls in ("equity", "property", "gold", "commodity", "linker"):
            real += x["value"]
    out["rates"] = {"bonds": bonds, "per_point": per_point, "bond_value": sum(b["value"] for b in bonds)}
    out["inflation"] = {"linked": linked, "real_assets": real, "real_pct": real / total if total else None}

    # ---- income
    since = (dt.date.today() - dt.timedelta(days=365)).isoformat()
    divs = db.scalar("SELECT SUM(amount_gbp) FROM dividends WHERE paid_on>=?", (since,), 0.0) or 0.0
    out["income"] = {"dividends_12m": divs, "yield": divs / invested if invested else None}

    # ---- single companies: against simply owning the world, and whether a reason is written down
    theses = {r["instrument_id"]: r for r in db.rows("SELECT * FROM theses")}
    world = store.gbp_points(store.ref_key("WORLD"))
    singles = []
    for i, v in ranked:
        x = next(p for p in priced if p["instrument_id"] == i)
        if not classify.is_single_company(x):
            continue
        cost = sum(p["cost"] for p in priced if p["instrument_id"] == i and p["cost"] is not None)
        first = db.scalar("SELECT MIN(traded_on) FROM trades WHERE instrument_id=? AND side IN ('BUY','TRANSFER_IN')",
                          (i,))
        mine = (v / cost - 1) if cost else None
        idx = None
        if first and world:
            w0 = mathx.value_on(world, first)
            if w0 and world[-1][1]:
                idx = world[-1][1] / w0 - 1
        t = theses.get(i)
        singles.append({"name": x["name"], "instrument_id": i, "value": v, "pct": v / total,
                        "since": first, "return": mine, "world": idx,
                        "ahead": (mine - idx) if (mine is not None and idx is not None) else None,
                        "thesis": bool(t and (t["why"] or "").strip()),
                        "next_check": t["next_check"] if t else None, "verdict": t["verdict"] if t else None})
    out["singles"] = singles
    out["findings"] = findings(out, pos, tot, settings)
    return out


def findings(x: dict, pos: list[dict], tot: dict, settings: dict | None = None) -> list[dict]:
    """The X-Ray in sentences, worst first. Each says what was found and what is usual."""
    f = []
    total = x["total"] or 0.0

    def add(level, title, detail, go=None):
        f.append({"level": level, "title": title, "detail": detail, "go": go})

    for p in x.get("protection", []):
        if p["share"] > 1:
            add("red", f"{p['name']} is over its {p['scheme']} protection limit",
                f"If the firm failed with money missing, only up to the limit would be protected. "
                f"Spreading across firms keeps every pound covered.", "settings")
        else:
            add("amber", f"{p['name']} is near its {p['scheme']} protection limit",
                "Within 10% of the limit; a good year in markets could take it over.", "settings")
    for d in x.get("biggest_companies", [])[:3]:
        if total and d["true"] / total > 0.10:
            via = f", {d['via'] / total * 100:.1f} points of it through your funds" if d["via"] else ""
            add("amber", f"{d['company']} is {d['true'] / total * 100:.0f}% of your money{via}",
                "Common guidance keeps any one company under 5 to 10%. A rule on the Allocation "
                "screen can warn you when it passes your own limit.", "allocation")
    for t in x.get("themes", []):
        if (t["pct"] or 0) > 0.35 and t["theme"] not in ("rates",):
            add("amber", f"{t['pct'] * 100:.0f}% of your money rides on {t['label'].lower()}",
                "One market force can move a large part of everything you own. Worth watching "
                "on the Market watch screen, and perhaps capping.", "ai")
    if (x.get("top10_pct") or 0) > 0.7 and len(x.get("largest", [])) >= 10:
        add("info", f"Your ten largest holdings are {x['top10_pct'] * 100:.0f}% of everything",
            "Not a problem in itself when they are broad funds; worth knowing when they are single companies.")
    small = x.get("small") or []
    if len(small) >= 6:
        add("info", f"{len(small)} holdings are each under 1% of your money",
            "Too small to change the result much either way. Consolidating, or writing down why "
            "each is there, makes the portfolio easier to follow.", "holdings")
    c = x.get("costs") or {}
    if c.get("pct") is not None and c["pct"] > 0.005:
        add("amber", f"Charges cost about £{c['total']:,.0f} a year ({c['pct'] * 100:.2f}%)",
            "Every 0.1% a year compounds. Global index funds cost under 0.25% a year.", "holdings")
    if c.get("dear"):
        add("info", f"{len(c['dear'])} fund{'s' if len(c['dear']) != 1 else ''} charge more than 0.5% a year",
            ", ".join(f"{d['name']} ({d['ocf']:.2f}%)" for d in c["dear"][:4]) + ".", "holdings")
    if c.get("unknown"):
        add("info", f"Charges not known for {len(c['unknown'])} fund{'s' if len(c['unknown']) != 1 else ''}",
            "Type the yearly charge (OCF) from each fund's factsheet on its holding page.", "holdings")
    w = x.get("wrappers") or {}
    if w.get("gia", 0) > 100 and (w.get("isa_left") or 0) > 0:
        move = min(w["gia"], w["isa_left"])
        add("info", f"£{move:,.0f} could move from your general account into an ISA this tax year",
            f"Selling in the general account and buying the same thing in the ISA ('bed and ISA') "
            f"shelters future growth and dividends from tax. {w.get('isa_year')} has "
            f"£{w['isa_left']:,.0f} of allowance left.", "activity")
    rand = next((t for t in x.get("themes", []) if t["theme"] == "rand"), None)
    retire_uk = (settings or {}).get("retire_country", "uk") == "uk"
    if rand and (rand["pct"] or 0) > 0.10 and retire_uk:
        add("amber", f"{rand['pct'] * 100:.0f}% of your money is in rand",
            "If you'll spend your retirement in pounds, rand is a currency bet as well as savings: "
            "the rand has weakened against the pound over long periods.", "settings")
    uk = (x.get("regions") or {}).get("uk_pct") or 0.0
    if uk > 0.25:
        add("info", f"About {uk * 100:.0f}% of your shares are in UK companies",
            "The UK is about 3% of the world's stock markets. Owning more is a common, deliberate "
            "choice (home bias); it just means one economy matters more to you.", "allocation")
    no_thesis = [s for s in x.get("singles", []) if not s["thesis"] and s["pct"] >= 0.01]
    if no_thesis:
        add("info", f"No reason written down for {len(no_thesis)} single compan{'ies' if len(no_thesis) != 1 else 'y'}",
            "Writing down why you own a company, and what would change your mind, makes the next "
            "fall far easier to judge. Open the holding and add a thesis.", "holdings")
    behind = [s for s in x.get("singles", []) if s["ahead"] is not None and s["ahead"] < -0.2]
    if behind:
        add("info", f"{len(behind)} single compan{'ies' if len(behind) != 1 else 'y'} trail the world index by 20 points or more",
            "Since you bought, simply owning the world would have done better: "
            + ", ".join(f"{s['name']} ({s['ahead'] * 100:+.0f} points)" for s in behind[:4]) + ".", "holdings")
    t_cov = [t for t in x.get("themes", []) if t["theme"] == "ai"]
    if t_cov and t_cov[0].get("coverage") is not None and t_cov[0]["coverage"] < 0.7:
        add("info", "Some funds' make-up isn't known yet",
            "Themes count only what is known. Open each fund and type its main weights from the factsheet.",
            "holdings")
    order = {"red": 0, "amber": 1, "info": 2}
    return sorted(f, key=lambda r: order.get(r["level"], 3))


def sleeves_now() -> list[dict]:
    return allocation.sleeves()


def company_rules(pos: list[dict], tot: dict) -> list[dict]:
    return rules.rule_status(pos, tot)
