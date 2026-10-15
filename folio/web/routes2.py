"""The 2.0 routes: Overall, Mortgage, Retirement, the plan review, watch themes, the
institution catalogue, importing files, the statements folder and the reminder.

Same rules as the rest of the server: every route answers JSON; a top-level "error"
only ever means the request failed (raise ApiError for that); anything that downloads
returns {"_file": bytes, "_name": ..., "_type": ...}.
"""

from __future__ import annotations

import datetime as dt
import json

from .. import config, db, inbox, reminders
from ..engine import (builder, classify, mortgage as mort, overall, pensions as pens, phonecopy, portfolio,
                      retirement, statepension, stress, themes, ukrules, valuations, xray)
from ..importers import investments as inv
from ..institutions import registry
from .server import ApiError, _float, _int, route


# ============================================================================ overall

@route("GET", "/api/overall")
def api_overall(req, m, q, body):
    return overall.summary()


@route("GET", "/api/export/phone")
def api_export_phone(req, m, q, body):
    """One HTML file of the figures, for a phone without the app (an iPhone, say)."""
    return {"_file": phonecopy.build(), "_name": phonecopy.filename(), "_type": "text/html; charset=utf-8"}


# ============================================================================ assets

ASSET_KINDS = {"property": "Property", "vehicle": "Vehicle", "other": "Something else"}


def _asset_values(b: dict, partial: bool) -> dict:
    out = {}
    if "name" in b or not partial:
        name = str(b.get("name") or "").strip()
        if not name:
            raise ApiError("Give it a name, for example “Home”.")
        out["name"] = name[:80]
    if "kind" in b:
        if b["kind"] not in ASSET_KINDS:
            raise ApiError("Unknown kind of asset.")
        out["kind"] = b["kind"]
    if "value" in b:
        out["value"] = _float(b["value"], "The value", 0, 100_000_000, allow_none=True)
        out["valued_on"] = str(b.get("valued_on") or db.today())[:10]
    if "currency" in b:
        out["currency"] = str(b["currency"] or "GBP").upper()[:3]
    if "is_home" in b:
        out["is_home"] = 1 if b["is_home"] else 0
    if "notes" in b:
        out["notes"] = str(b["notes"] or "")[:400] or None
    return out


@route("GET", "/api/assets")
def api_assets(req, m, q, body):
    return {"items": db.rows("SELECT * FROM assets ORDER BY sort, id"), "kinds": ASSET_KINDS}


@route("POST", "/api/assets")
def api_add_asset(req, m, q, body):
    vals = _asset_values(body or {}, partial=False)
    cols = list(vals)
    with db.tx() as c:
        cur = c.execute(f"INSERT INTO assets({','.join(cols)}) VALUES({','.join('?' * len(cols))})",  # nosec B608  # fixed columns
                        tuple(vals.values()))
    return {"ok": True, "id": cur.lastrowid}


@route("PATCH", "/api/assets/{aid}")
def api_patch_asset(req, m, q, body):
    vals = _asset_values(body or {}, partial=True)
    if not vals:
        raise ApiError("Nothing to change.")
    db.execute(f"UPDATE assets SET {', '.join(f'{k}=?' for k in vals)} WHERE id=?",  # nosec B608  # fixed columns
               (*vals.values(), _int(m["aid"])))
    return {"ok": True}


@route("DELETE", "/api/assets/{aid}")
def api_delete_asset(req, m, q, body):
    db.execute("DELETE FROM assets WHERE id=?", (_int(m["aid"]),))
    return {"ok": True}


# ============================================================================ mortgage

_M_NUMERIC = {"original_amount", "rate", "revert_rate", "monthly_payment", "statement_balance",
              "property_value", "overpay_allowance"}
_M_INTEGER = {"term_months", "payment_day", "property_asset_id"}
_M_TEXT = {"name", "lender", "currency", "started_on", "rate_type", "fixed_until", "repayment_type",
           "statement_on", "property_valued_on", "erc_note", "notes"}
_M_FLAGS = {"split_payments"}


def _mortgage_values(b: dict) -> dict:
    out = {}
    for f, v in b.items():
        if f not in _M_NUMERIC | _M_INTEGER | _M_TEXT | _M_FLAGS:
            continue
        if v in ("", None):
            out[f] = None
            continue
        if f in _M_NUMERIC:
            try:
                out[f] = float(str(v).replace(",", "").replace("%", "").replace("£", "").strip())
            except ValueError:
                raise ApiError(f"“{v}” isn't a number: check the {f.replace('_', ' ')}.") from None
            if out[f] < 0:
                raise ApiError(f"The {f.replace('_', ' ')} can't be negative.")
        elif f in _M_INTEGER:
            try:
                out[f] = int(float(v))
            except ValueError:
                raise ApiError(f"“{v}” isn't a whole number.") from None
        elif f in _M_FLAGS:
            out[f] = 1 if v in (True, 1, "1", "true") else 0
        else:
            out[f] = str(v).strip()[:200] or None
    for d in ("started_on", "fixed_until", "statement_on", "property_valued_on"):
        if out.get(d):
            try:
                dt.date.fromisoformat(out[d][:10])
            except ValueError:
                raise ApiError(f"The {d.replace('_', ' ')} should look like 2027-03-31.") from None
    if out.get("rate_type") and out["rate_type"] not in ("fixed", "variable", "tracker", "discount"):
        raise ApiError("Unknown rate type.")
    if out.get("repayment_type") and out["repayment_type"] not in ("repayment", "interest_only", "part_and_part"):
        raise ApiError("Unknown kind of mortgage.")
    return out


def _log_event(mortgage_id, on, kind, amount=None, rate=None, note=None):
    with db.tx() as c:
        dup = c.execute("SELECT id FROM mortgage_events WHERE mortgage_id=? AND happened_on=? AND kind=? "
                        "AND IFNULL(amount,-1)=IFNULL(?,-1)", (mortgage_id, on, kind, amount)).fetchone()
        if dup:
            return dup["id"]
        return c.execute("INSERT INTO mortgage_events(mortgage_id,happened_on,kind,amount,rate,note,created_at) "
                         "VALUES(?,?,?,?,?,?,?)", (mortgage_id, on, kind, amount, rate, note, db.now())).lastrowid


def _yearly(schedule: list[dict]) -> list[dict]:
    points = [r for i, r in enumerate(schedule) if i % 12 == 0][:41]
    if schedule and (not points or points[-1] is not schedule[-1]):
        points.append(schedule[-1])
    return points


@route("GET", "/api/mortgages")
def api_mortgages(req, m, q, body):
    items = [mort.summarise(x) for x in mort.all_mortgages()]
    s = retirement.settings()
    return {"items": items, "assets": db.rows("SELECT * FROM assets ORDER BY sort, id"),
            "stop_age": s.get("stop_age"), "dob": s.get("dob"), "market": ukrules.MARKET}


@route("GET", "/api/mortgages/{mid}")
def api_mortgage(req, m, q, body):
    row = mort.get(_int(m["mid"]))
    if not row:
        raise ApiError("That mortgage isn't there any more.", 404)
    summary = mort.summarise(row)
    months = min(summary["months_left"] or 0, 480) or 0
    schedule = []
    if summary["balance"] is not None and summary["monthly_payment"] and months:
        schedule = mort.amortise(summary["balance"], row["rate"], summary["monthly_payment"], months,
                                 dt.date.today().replace(day=1),
                                 interest_only=(row["repayment_type"] == "interest_only"))
    return {"record": row, "summary": summary, "schedule": schedule[:480], "curve": _yearly(schedule),
            "events": db.rows("SELECT * FROM mortgage_events WHERE mortgage_id=? ORDER BY happened_on DESC, "
                              "id DESC LIMIT 40", (row["id"],))}


@route("POST", "/api/mortgages")
def api_add_mortgage(req, m, q, body):
    vals = _mortgage_values(body or {})
    vals["name"] = vals.get("name") or vals.get("lender") or "Mortgage"
    vals["created_at"] = db.now()
    cols = list(vals)
    with db.tx() as c:
        mid = c.execute(f"INSERT INTO mortgages({','.join(cols)}) VALUES({','.join('?' * len(cols))})",  # nosec B608  # validated columns
                        tuple(vals.values())).lastrowid
    if vals.get("statement_balance") is not None and vals.get("statement_on"):
        _log_event(mid, vals["statement_on"][:10], "statement", vals["statement_balance"], None,
                   "Balance from a statement")
    return {"ok": True, "id": mid, "summary": mort.summarise(mort.get(mid))}


@route("PATCH", "/api/mortgages/{mid}")
def api_patch_mortgage(req, m, q, body):
    mid = _int(m["mid"])
    if not mort.get(mid):
        raise ApiError("That mortgage isn't there any more.", 404)
    vals = _mortgage_values(body or {})
    if "name" in vals and not vals["name"]:
        raise ApiError("A mortgage needs a name.")
    if vals:
        db.execute(f"UPDATE mortgages SET {', '.join(f'{k}=?' for k in vals)} WHERE id=?",  # nosec B608  # validated columns
                   (*vals.values(), mid))
    if vals.get("statement_balance") is not None and vals.get("statement_on"):
        _log_event(mid, vals["statement_on"][:10], "statement", vals["statement_balance"], None,
                   "Balance from a statement")
    return {"ok": True, "summary": mort.summarise(mort.get(mid))}


@route("DELETE", "/api/mortgages/{mid}")
def api_delete_mortgage(req, m, q, body):
    db.execute("DELETE FROM mortgages WHERE id=?", (_int(m["mid"]),))
    return {"ok": True}


@route("POST", "/api/mortgages/{mid}/events")
def api_mortgage_event(req, m, q, body):
    b = body or {}
    row = mort.get(_int(m["mid"]))
    if not row:
        raise ApiError("Save the mortgage first.")
    kind = b.get("kind") or "overpayment"
    if kind not in ("statement", "overpayment", "rate_change", "valuation"):
        raise ApiError("Unknown kind of event.")
    on = str(b.get("happened_on") or db.today())[:10]
    try:
        dt.date.fromisoformat(on)
    except ValueError:
        raise ApiError("The date should look like 2026-10-15.") from None
    amount = _float(b.get("amount"), "The amount", 0, 100_000_000, allow_none=True)
    rate = _float(b.get("rate"), "The rate", 0, 30, allow_none=True)
    _log_event(row["id"], on, kind, amount, rate, (str(b.get("note") or "")[:200] or None))
    with db.tx() as c:
        if kind == "statement" and amount is not None:
            c.execute("UPDATE mortgages SET statement_balance=?, statement_on=? WHERE id=?", (amount, on, row["id"]))
        elif kind == "rate_change" and rate is not None:
            c.execute("UPDATE mortgages SET rate=? WHERE id=?", (rate, row["id"]))
        elif kind == "valuation" and amount is not None:
            if row.get("property_asset_id"):
                c.execute("UPDATE assets SET value=?, valued_on=? WHERE id=?", (amount, on, row["property_asset_id"]))
            else:
                c.execute("UPDATE mortgages SET property_value=?, property_valued_on=? WHERE id=?",
                          (amount, on, row["id"]))
    return {"ok": True, "summary": mort.summarise(mort.get(row["id"]))}


@route("GET", "/api/mortgages/{mid}/overpayment")
def api_overpayment(req, m, q, body):
    row = mort.get(_int(m["mid"]))
    if not row:
        raise ApiError("Save the mortgage first.")
    amount = _float(q.get("amount") or 0, "The amount", 0, 10_000_000)
    kind = q.get("kind") if q.get("kind") in ("monthly", "once") else "monthly"
    return mort.overpayment_effect(row, amount, kind)


@route("GET", "/api/mortgages/{mid}/rate-change")
def api_rate_change(req, m, q, body):
    row = mort.get(_int(m["mid"]))
    if not row:
        raise ApiError("Save the mortgage first.")
    rate = _float(q.get("rate"), "The rate", 0, 30)
    return mort.rate_change_effect(row, rate)


# ============================================================================ pensions and retirement

@route("GET", "/api/pensions")
def api_pensions(req, m, q, body):
    s = retirement.settings()
    dob = retirement.dob_of(s)
    rows = pens.all_rows()
    for r in rows:
        r["describe"] = pens.describe(r)
    return {"items": rows, "kinds": pens.KINDS, "indexation": pens.INDEXATION, "take": pens.TAKE,
            "state_pension": statepension.estimate(s, dob) if dob else None,
            "spa": statepension.describe_age(dob) if dob else None, "settings": s,
            "sipps": [p for p in portfolio.platforms_summary() if p["wrapper"] == "sipp"]}


@route("POST", "/api/pensions")
def api_add_pension(req, m, q, body):
    try:
        return {"ok": True, "id": pens.add(body or {})}
    except pens.PensionError as e:
        raise ApiError(str(e)) from None


@route("PATCH", "/api/pensions/{pid}")
def api_patch_pension(req, m, q, body):
    try:
        pens.update(_int(m["pid"]), body or {})
    except pens.PensionError as e:
        raise ApiError(str(e)) from None
    return {"ok": True}


@route("DELETE", "/api/pensions/{pid}")
def api_delete_pension(req, m, q, body):
    pens.remove(_int(m["pid"]))
    return {"ok": True}


def _day(iso: str | None) -> str:
    """15 October 2026, not 2026-10-15: these dates end up in sentences."""
    try:
        d = dt.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso or "")
    return f"{d.day} {d:%B %Y}"


def _theme_scenarios() -> list[dict]:
    w = themes.watch()
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    out = []
    for t in w["themes"]:
        if t not in themes.LIBRARY:
            continue
        e = stress.exposure(pos, tot) if t == "ai" else themes.exposure(pos, tot, t)
        val = e.get("ai_value") if t == "ai" else e.get("value")
        rp = stress.replay(t, val or 0.0, tot.get("invested") or 0.0, themes.LIBRARY[t].get("scenario_ref"))
        if rp and rp["loss"] > 0:
            out.append({"key": t, "label": f"The worst fall of the last five years in {themes.in_sentence(t)}, again",
                        "loss": rp["loss"],
                        "why": f"It fell {rp['depth'] * 100:.0f}% from {_day(rp['peak'])} to {_day(rp['trough'])}."})
    return out


@route("GET", "/api/retirement")
def api_retirement(req, m, q, body):
    try:
        out = retirement.analyse(full=q.get("full", "1") != "0", theme_scenarios=_theme_scenarios())
    except retirement.RetirementError as e:
        raise ApiError(str(e)) from None
    return out


@route("PATCH", "/api/retirement")
def api_patch_retirement(req, m, q, body):
    try:
        s = retirement.save(body or {})
    except retirement.RetirementError as e:
        raise ApiError(str(e)) from None
    return {"ok": True, "settings": s}


@route("POST", "/api/retirement/what-if")
def api_what_if(req, m, q, body):
    """One run with a lever moved: the sliders on the Retirement screen. Saves nothing."""
    b = body or {}
    s = retirement.settings()
    if retirement.missing(s, {}):
        raise ApiError("Fill in the basics first.")
    opts = {}
    if b.get("stop_age") not in (None, ""):
        opts["stop_age"] = _float(b["stop_age"], "The age", 40, 85)
    if b.get("spend_factor") not in (None, ""):
        opts["spend_factor"] = _float(b["spend_factor"], "The spending", 0, 3)
    if b.get("extra_saving") not in (None, ""):
        opts["extra_saving"] = _float(b["extra_saving"], "The saving", 0, 100000)
    if b.get("order") in retirement.ORDERS:
        opts["order"] = b["order"]
    if b.get("uniform") not in (None, ""):
        opts["uniform"] = _float(b["uniform"], "The return", -5, 15)
    data = retirement.gather(s)
    if b.get("spend_essential") not in (None, ""):
        s = dict(s, spend_essential=_float(b["spend_essential"], "Essentials", 0, 1_000_000))
    if "clear_mortgage_at_stop" in b:
        s = dict(s, clear_mortgage_at_stop=bool(b["clear_mortgage_at_stop"]))
    return retirement.project(s, data, opts)


# ============================================================================ the plan review

@route("GET", "/api/builder")
def api_builder(req, m, q, body):
    return builder.questions()


@route("PATCH", "/api/builder")
def api_builder_save(req, m, q, body):
    try:
        return builder.save_answers((body or {}).get("answers") or {})
    except retirement.RetirementError as e:
        raise ApiError(str(e)) from None


@route("GET", "/api/builder/draft")
def api_builder_draft(req, m, q, body):
    return builder.draft()


@route("POST", "/api/builder/apply")
def api_builder_apply(req, m, q, body):
    return builder.apply(body or {})


@route("GET", "/api/builder/written")
def api_written_plan(req, m, q, body):
    return builder.written_plan()


@route("GET", "/api/builder/written.html")
def api_written_page(req, m, q, body):
    """The written plan as a page of its own, to open in any browser and print: a phone's
    app window has no printer, and a page can be kept beside other papers."""
    import html
    w = builder.written_plan()
    parts = []
    for s in w["sections"]:
        items = "".join(f"<li>{html.escape(str(x))}</li>" for x in s["lines"])
        parts.append(f"<h2>{html.escape(s['title'])}</h2><ul>{items}</ul>")
    page = (f"<!doctype html><html lang=\"en-GB\"><head><meta charset=\"utf-8\"><title>{html.escape(w['title'])}</title>"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><style>"
            "body{font:15px/1.55 system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;color:#15202b;"
            "max-width:760px;margin:32px auto;padding:0 20px}h1{font-size:1.7rem;margin:0 0 4px}"
            "h2{font-size:1.1rem;margin:22px 0 6px;border-bottom:1px solid #dfe4ea;padding-bottom:4px}"
            "ul{margin:6px 0 0;padding-left:20px}li{margin:3px 0}.m{color:#6f7c8b;font-size:.9rem}"
            "@media print{body{margin:0}}</style></head><body>"
            f"<h1>{html.escape(w['title'])}</h1><p class=\"m\">Made {html.escape(w['made'])}</p>"
            + "".join(parts) + f"<p class=\"m\" style=\"margin-top:22px\">{html.escape(w['footer'])}</p></body></html>")
    return {"_file": page.encode("utf-8"), "_name": f"{config.APP_FILE_NAME} written plan {db.today()}.html",
            "_type": "text/html"}


@route("GET", "/api/builder/pack")
def api_review_pack(req, m, q, body):
    return {"_file": builder.review_pack().encode("utf-8"),
            "_name": f"{config.APP_FILE_NAME} review pack {db.today()}.md", "_type": "text/markdown"}


@route("GET", "/api/valuations")
def api_valuations(req, m, q, body):
    return {"fields": valuations.FIELDS, "values": valuations.values(), "old_after_days": valuations.OLD_AFTER_DAYS}


@route("PUT", "/api/valuations")
def api_save_valuations(req, m, q, body):
    try:
        return {"ok": True, "values": valuations.save(body or {})}
    except valuations.ValuationError as e:
        raise ApiError(str(e)) from None


@route("GET", "/api/xray")
def api_xray(req, m, q, body):
    return xray.run(settings=retirement.settings())


# ============================================================================ watch themes

@route("GET", "/api/watch")
def api_watch(req, m, q, body):
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    a = builder.answers()
    care = [t for t in (a.get("believe") or []) + (a.get("worry") or []) if t in themes.LIBRARY]
    return {"watch": themes.watch(), "suggestion": themes.suggest(pos, tot, care),
            "library": [{"key": k, "label": v["label"], "about": v["about"]} for k, v in themes.LIBRARY.items()]}


@route("PUT", "/api/watch")
def api_set_watch(req, m, q, body):
    b = body or {}
    chosen = [t for t in (b.get("themes") or []) if isinstance(t, str)]
    if b.get("legacy"):
        db.set_meta("watch", {})
        return {"ok": True, "watch": themes.watch()}
    if not chosen:
        raise ApiError("Pick at least one theme to watch.")
    return {"ok": True, "watch": themes.set_watch(b.get("main"), chosen, b.get("why"))}


@route("GET", "/api/instrument/{iid}/themes")
def api_instrument_themes(req, m, q, body):
    iid = _int(m["iid"])
    x = next((p for p in portfolio.positions() if p["instrument_id"] == iid), None)
    inst = db.one("SELECT i.*, s.name AS sleeve FROM instruments i LEFT JOIN sleeves s ON s.id=i.sleeve_id "
                  "WHERE i.id=?", (iid,))
    if not inst:
        raise ApiError("That holding isn't there any more.", 404)
    row = dict(inst, **(x or {}))
    row.setdefault("ai_share_set", inst["ai_share"] is not None)
    stored = themes._stored()
    out = []
    for k, t in themes.LIBRARY.items():
        if k == "rand":
            continue
        share, src = themes.share_of(row, k, stored)
        out.append({"theme": k, "label": t["label"], "share": share, "source": src})
    cls, how = classify.asset_class(row)
    oc, oc_how = classify.ocf(row)
    du, du_how = classify.duration(row)
    th = db.one("SELECT * FROM theses WHERE instrument_id=?", (iid,))
    return {"themes": out, "asset_class": cls, "asset_class_how": how, "asset_classes": classify.ASSET_CLASSES,
            "ocf": oc, "ocf_how": oc_how, "duration": du, "duration_how": du_how,
            "single": classify.is_single_company(row), "thesis": th,
            "known_as": (classify.known(row) or [None] * 5)[4]}


@route("PUT", "/api/instrument/{iid}/themes")
def api_set_instrument_themes(req, m, q, body):
    iid = _int(m["iid"])
    if not db.one("SELECT 1 FROM instruments WHERE id=?", (iid,)):
        raise ApiError("That holding isn't there any more.", 404)
    shares = (body or {}).get("shares") or {}
    with db.tx() as c:
        for theme, v in shares.items():
            if theme == "ai":
                c.execute("UPDATE instruments SET ai_share=? WHERE id=?",
                          (_float(v, "The AI share", 0, 100, allow_none=True), iid))
                continue
            if theme not in themes.LIBRARY:
                continue
            if v in (None, ""):
                c.execute("DELETE FROM exposures WHERE instrument_id=? AND theme=?", (iid, theme))
            else:
                c.execute("INSERT INTO exposures(instrument_id,theme,share,source,as_of) VALUES(?,?,?,?,?) "
                          "ON CONFLICT(instrument_id,theme) DO UPDATE SET share=excluded.share, "
                          "source=excluded.source, as_of=excluded.as_of",
                          (iid, theme, _float(v, f"The {theme} share", 0, 100), "you", db.today()))
    return {"ok": True}


@route("PUT", "/api/theses/{iid}")
def api_save_thesis(req, m, q, body):
    iid = _int(m["iid"])
    b = body or {}
    nc = str(b.get("next_check") or "")[:10] or None
    if nc:
        try:
            dt.date.fromisoformat(nc)
        except ValueError:
            raise ApiError("The next check date should look like 2027-02-05.") from None
    verdict = b.get("verdict") if b.get("verdict") in (None, "", "intact", "watch", "impaired", "broken") else None
    with db.tx() as c:
        c.execute("INSERT INTO theses(instrument_id,why,breakers,next_check,verdict,updated_at) VALUES(?,?,?,?,?,?) "
                  "ON CONFLICT(instrument_id) DO UPDATE SET why=excluded.why, breakers=excluded.breakers, "
                  "next_check=excluded.next_check, verdict=excluded.verdict, updated_at=excluded.updated_at",
                  (iid, str(b.get("why") or "")[:2000], str(b.get("breakers") or "")[:2000], nc,
                   verdict or None, db.now()))
        if isinstance(b.get("factors"), dict):
            grades = {k: str(v) for k, v in b["factors"].items() if k in FACTORS and str(v) in GRADES}
            c.execute("UPDATE theses SET factors=? WHERE instrument_id=?",
                      (json.dumps(grades | {"on": db.today()}) if grades else None, iid))
    return {"ok": True}


#: Seeking Alpha's factor grades, typed in during a review: one line per thesis card.
FACTORS = {"valuation": "Valuation", "growth": "Growth", "profitability": "Profitability",
           "momentum": "Momentum", "revisions": "EPS revisions"}
GRADES = ("A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F")


# ============================================================================ the catalogue and adding things

@route("GET", "/api/institutions")
def api_institutions(req, m, q, body):
    kinds = [k for k in (q.get("kinds") or "").split(",") if k] or None
    return {"items": registry.search(q.get("q") or "", q.get("country") or None, kinds, limit=25)}


@route("GET", "/api/institutions/{iid}")
def api_institution(req, m, q, body):
    if not registry.get(m["iid"]):
        raise ApiError("Not in the list.", 404)
    return registry.next_step(m["iid"])


# ============================================================================ importing

@route("POST", "/api/import/analyse")
def api_import_analyse(req, m, q, body):
    if not isinstance(body, (bytes, bytearray)) or not body:
        raise ApiError("No file arrived.")
    try:
        rep = inv.analyse(bytes(body), (q.get("name") or "file")[:200])
    except inv.ImportError_ as e:
        raise ApiError(str(e)) from None
    rep["platforms"] = [{"id": p["id"], "name": p["name"], "provider": p["provider"], "wrapper": p["wrapper"]}
                        for p in db.rows("SELECT id, name, provider, wrapper FROM platforms "
                                         "WHERE provider NOT IN ('card','sample') ORDER BY sort, id")]
    return rep


@route("POST", "/api/import/commit")
def api_import_commit(req, m, q, body):
    b = body or {}
    try:
        out = inv.commit(str(b.get("token") or ""), b.get("platform_id"), b.get("as_of"), b.get("columns"))
    except inv.ImportError_ as e:
        raise ApiError(str(e)) from None
    from ..market import store
    store.start_refresh()
    return out


@route("GET", "/api/inbox")
def api_inbox(req, m, q, body):
    return inbox.status()


@route("POST", "/api/inbox/open")
def api_inbox_open(req, m, q, body):
    return inbox.open_folder()


@route("POST", "/api/inbox/import")
def api_inbox_import(req, m, q, body):
    return inbox.import_waiting()


@route("GET", "/api/reminder")
def api_reminder(req, m, q, body):
    return reminders.state()


@route("POST", "/api/reminder/dismiss")
def api_reminder_dismiss(req, m, q, body):
    return reminders.dismiss()


@route("GET", "/api/reminder/calendar")
def api_reminder_calendar(req, m, q, body):
    return {"_file": reminders.ics().encode("utf-8"),
            "_name": f"{config.APP_FILE_NAME} - monthly statement reminder.ics", "_type": "text/calendar"}


@route("GET", "/api/rules-of-the-game")
def api_uk_rules(req, m, q, body):
    return {"items": ukrules.summary(), "checked": ukrules.CHECKED, "market": ukrules.MARKET}


def _json(v) -> str:
    return json.dumps(v, default=str)


# ============================================================================ the Budget tab

def _budget_on():
    if not config.settings.get("budget_on"):
        raise ApiError("The Budget tab is switched off. Switch it on in Settings.")


@route("GET", "/api/budget")
def api_budget(req, m, q, body):
    from ..budget import categories as bcat, engine as beng
    _budget_on()
    period = q.get("period") or beng.current_period()
    try:
        beng.bounds(period)
    except (ValueError, TypeError):
        raise ApiError("That month isn't valid.") from None
    return {"month": beng.month(period), "history": beng.history(12), "accounts": beng.accounts(),
            "categories": bcat.all_categories(), "previous": beng.shift(period, -1), "next": beng.shift(period, 1),
            "current": beng.current_period()}


@route("GET", "/api/budget/suggest")
def api_budget_suggest(req, m, q, body):
    from ..budget import engine as beng
    _budget_on()
    return {"items": beng.suggest_budgets(3)}


@route("PUT", "/api/budget/categories/{cid}")
def api_budget_set(req, m, q, body):
    from ..budget import engine as beng
    _budget_on()
    beng.set_budget(_int(m["cid"]), _float((body or {}).get("budget"), "The budget", 0, 1_000_000, allow_none=True))
    return {"ok": True}


@route("POST", "/api/budget/categories")
def api_budget_add_category(req, m, q, body):
    from ..budget import categories as bcat
    _budget_on()
    b = body or {}
    parent, name = str(b.get("parent") or "").strip()[:60], str(b.get("name") or "").strip()[:60]
    kind = b.get("kind") if b.get("kind") in ("in", "out", "save", "transfer") else "out"
    if not parent or not name:
        raise ApiError("A category needs a group and a name.")
    bcat.seed()
    with db.tx() as c:
        c.execute("INSERT OR IGNORE INTO txn_categories(parent,name,kind,sort) VALUES(?,?,?,999)", (parent, name, kind))
    return {"ok": True}


@route("GET", "/api/transactions")
def api_transactions(req, m, q, body):
    from ..budget import categories as bcat, engine as beng
    _budget_on()
    return {"items": beng.transactions(q.get("period") or None, q.get("q") or "", q.get("category") or "",
                                       q.get("platform") or "", q.get("uncategorised") == "1"),
            "categories": bcat.all_categories(), "accounts": beng.accounts()}


@route("PATCH", "/api/transactions/{tid}")
def api_transaction_patch(req, m, q, body):
    from ..budget import categories as bcat
    _budget_on()
    b = body or {}
    tid = _int(m["tid"])
    out = {"ok": True}
    if "category_id" in b:
        cid = b.get("category_id")
        cid = _int(cid) if cid not in (None, "") else None
        try:
            out = bcat.set_category(tid, cid, bool(b.get("remember")))
        except ValueError as e:
            raise ApiError(str(e), 404) from None
    if "note" in b:
        db.execute("UPDATE txns SET note=? WHERE id=?", (str(b["note"] or "")[:300] or None, tid))
    return out
