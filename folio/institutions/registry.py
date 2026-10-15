"""The catalogue of UK and South African banks, brokers, platforms and pensions, and the
honest answer to "what can this app do with it?".

Brought from Mittens & Pence with its rule intact: only offer a route that works, for
free, for a household, with code behind it. Here that means Trading 212 and Monzo connect
automatically; Freetrade, Hargreaves Lansdown, AJ Bell, interactive investor and Vanguard
come in from the files they let you download; everything else is typed in. (EasyEquities'
files are in rand and its layout hasn't been checked against a real one, so it is typed in
until it has.)
A route the catalogue knows about but this app cannot drive is named and explained,
never offered.
"""

from __future__ import annotations

import functools
import json
import pathlib
import re
import unicodedata

from .. import config

DATA = pathlib.Path(__file__).resolve().parent / "data"

#: Providers with a working client in this app.
BUILT = {"trading212", "monzo"}
#: Statement layouts this app can read for investments (see importers.investments).
INVESTMENT_PROFILES = {"freetrade", "trading212", "hargreaves_lansdown", "aj_bell",
                       "interactive_investor", "vanguard"}

KIND_BECOMES = {"broker": "platform", "platform": "platform", "crypto": "platform",
                "bank": "bank", "building_society": "bank", "ewallet": "bank",
                "card": "card", "pension": "pension", "asset": "property", "other": "platform"}


def _data_dir() -> pathlib.Path:
    frozen = config.resource_dir() / "institutions" / "data"
    return frozen if frozen.exists() else DATA


@functools.lru_cache(maxsize=1)
def _load() -> dict:
    d = _data_dir()
    out = {"countries": {}, "by_id": {}, "providers": {}}
    for code, fname in (("GB", "institutions_gb.json"), ("ZA", "institutions_za.json")):
        payload = json.loads((d / fname).read_text(encoding="utf-8"))
        out["countries"][code] = payload
        for inst in payload["institutions"]:
            out["by_id"][inst["id"]] = inst
    out["providers"] = json.loads((d / "providers.json").read_text(encoding="utf-8"))
    return out


def get(institution_id: str) -> dict | None:
    return _load()["by_id"].get(institution_id)


def provider(pid: str) -> dict | None:
    return _load()["providers"].get(pid)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def all_institutions(country: str | None = None) -> list[dict]:
    data = _load()
    if country:
        return list(data["countries"][country.upper()]["institutions"])
    return data["countries"]["GB"]["institutions"] + data["countries"]["ZA"]["institutions"]


def search(query: str, country: str | None = None, kinds: list[str] | None = None,
           limit: int = 30) -> list[dict]:
    """Exact name beats an abbreviation beats a prefix beats a word inside the name."""
    q = _norm(query)
    pool = all_institutions(country)
    if kinds:
        pool = [i for i in pool if i["kind"] in kinds]
    if not q:
        return [brief(i) for i in pool[:limit]]
    scored = []
    for inst in pool:
        hay = _norm(inst["search"])
        name = _norm(inst["name"])
        aliases = {_norm(a) for a in inst.get("aka", [])}
        score = None
        if name == q:
            score = 0
        elif q in aliases:
            score = 0.5
        elif name.startswith(q):
            score = 1
        elif any(w.startswith(q) for w in hay.split()):
            score = 2
        elif q in hay:
            score = 3
        else:
            initials = "".join(w[0] for w in name.split() if w)
            if initials.startswith(q):
                score = 2
        if score is not None:
            kind_rank = 0 if inst["kind"] in ("broker", "platform", "bank", "building_society") else 1
            scored.append((score, kind_rank, len(inst["name"]), inst))
    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    return [brief(s[3]) for s in scored[:limit]]


def brief(inst: dict) -> dict:
    step = next_step(inst["id"])
    return {"id": inst["id"], "name": inst["name"], "country": inst["country"], "kind": inst["kind"],
            "kind_label": inst["kind_label"], "currency": inst["currency"],
            "route": step["route"], "route_label": step["route_label"], "becomes": step["becomes"]}


ROUTE_LABELS = {"connect": "Connects automatically", "file": "Download a file and drop it in",
                "type": "Type it in yourself"}


def next_step(institution_id: str) -> dict:
    """What happens after somebody picks this institution, in plain words."""
    inst = get(institution_id)
    if not inst:
        return {"route": "type", "route_label": ROUTE_LABELS["type"], "becomes": "platform",
                "summary": "Not in the list: add it by hand."}
    becomes = KIND_BECOMES.get(inst["kind"], "platform")
    methods = inst["sync"]["methods"]
    api = next((m for m in methods if m["method"] == "direct_api"
                and any(p in BUILT for p in m.get("providers", []))), None)
    csv = next((m for m in methods if m["method"] == "csv"), None)
    profile = (csv or {}).get("profile")
    readable = becomes == "platform" and profile in INVESTMENT_PROFILES
    if becomes == "bank" and profile and config.settings.get("budget_on"):
        readable = True
    name = inst["name"]
    if api:
        route = "connect"
        pid = next(p for p in api["providers"] if p in BUILT)
        p = provider(pid) or {}
        summary = (f"{name} has its own API for your own account: free, read-only, and nothing in "
                   f"between. Make a read-only key at {p.get('signup', 'their developer site')}, paste it in "
                   f"once, and Refresh keeps it up to date.")
        if pid == "monzo":
            summary = (f"{name} lets you connect your own account: you create a private client at "
                       "developers.monzo.com, approve the request in the Monzo app, and every Refresh "
                       "reads the balance.")
    elif readable:
        route = "file"
        where = csv.get("where") or "the statements or reports section of your account"
        summary = (f"{name} has no API anyone can use, so it comes in from the file it lets you download: "
                   f"{where}. Drop it on the Import screen or into your statements folder; the app works out "
                   f"the layout and remembers it. Importing an overlapping file is safe.")
    else:
        route = "type"
        summary = {"bank": f"Type in the balance whenever it changes. (Turning on the Budget tab adds "
                           f"statement imports for {name}.)",
                   "card": "Type in what you owe whenever it changes.",
                   "pension": "Type in the value from its yearly statement (or the pension a year it promises).",
                   "property": "Type in what it's worth; update it when you have a valuation.",
                   }.get(becomes, f"Type in its value, or its holdings, whenever they change.")
    withheld = []
    for m in methods:
        if m["method"] in ("openbanking", "aggregator") or (m["method"] == "direct_api" and m is not api):
            withheld.append(m["label"])
    from . import websites
    return {"institution": {k: inst[k] for k in ("id", "name", "country", "kind", "kind_label", "group",
                                                   "currency", "account_types")},
            "route": route, "route_label": ROUTE_LABELS[route], "becomes": becomes,
            "profile": profile, "where": (csv or {}).get("where"), "summary": summary,
            "withheld": withheld, "website": websites.website(inst["id"]),
            "wrappers": _wrappers(inst), "provider": "trading212" if (api and "trading212" in api["providers"])
            else "monzo" if (api and "monzo" in api["providers"]) else
            "freetrade" if profile == "freetrade" else None}


def _wrappers(inst: dict) -> list[str]:
    types = inst.get("account_types") or []
    if inst["country"] == "ZA":
        return ["gia"]
    out = [t for t in ("isa", "gia", "sipp", "lisa") if t in types]
    return out or ["isa", "gia", "sipp"]


def stats() -> dict:
    out = {}
    for c in ("GB", "ZA"):
        items = all_institutions(c)
        routes: dict[str, int] = {}
        for i in items:
            r = next_step(i["id"])["route"]
            routes[r] = routes.get(r, 0) + 1
        out[c] = {"total": len(items), "routes": routes}
    return out
