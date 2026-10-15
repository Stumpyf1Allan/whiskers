"""A copy of the figures to read on a phone without the Whiskers app: an iPhone, say.

From Mittens & Pence. One HTML file with everything inside it, laid out for a small
screen: put it somewhere private that the phone can open (your own iCloud Drive, Google
Drive or OneDrive), or email it to yourself, and tap it. Opening it needs no internet,
and nothing in it calls out: no scripts, no pictures from anywhere, no fonts to fetch.

It is a snapshot, not an app, and it says so at the top in words, because a stale
balance that looks current is worse than none. Android phones have the real app, which
follows the PC by itself.
"""

from __future__ import annotations

import datetime as dt
import html
import logging
import re

from .. import config
from . import allocation, overall, pensions as pens, portfolio, retirement

log = logging.getLogger(__name__)

MONTHS = ("January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December")
SYMBOL = {"GBP": "£", "ZAR": "R", "USD": "$", "EUR": "€"}
DOT = {"red": "#c62828", "amber": "#b26a00", "green": "#2e7d32", "ok": "#2e7d32"}
MAX_HOLDINGS = 25


# ---------------------------------------------------------------------------- words

def _e(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _plain(text) -> str:
    """The app's [[£x]] amount markers removed, and the words made safe to show."""
    return _e(re.sub(r"\[\[(.*?)\]\]", r"\1", str(text or "")))


def _money(value, currency: str = "GBP", dp: int | None = None) -> str:
    """Unknown is not zero: a missing figure prints as a dash, as it does in the app."""
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    places = dp if dp is not None else (0 if abs(v) >= 1000 else 2)
    sym = SYMBOL.get(currency, f"{currency} ")
    return f"{'−' if v < 0 else ''}{sym}{abs(v):,.{places}f}"


def _pct(value, dp: int = 1) -> str:
    return "—" if value is None else f"{value:.{dp}f}%"


def _day(iso, long: bool = False) -> str:
    """'15 Oct 2026', or '15 October 2026'. Built by hand: strftime's no-padding flag
    is %-d on a Mac and %#d on Windows."""
    try:
        d = dt.date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return _e(iso)
    m = MONTHS[d.month - 1]
    return f"{d.day} {m if long else m[:3]} {d.year}"


def _clock(t: dt.datetime) -> str:
    hour = t.hour % 12 or 12
    return f"{hour}:{t.minute:02d} {'am' if t.hour < 12 else 'pm'}"


def _dot(level: str | None) -> str:
    colour = DOT.get(level or "")
    return f'<span class="dot" style="background:{colour}"></span>' if colour else '<span class="dot none"></span>'


def _rows(pairs: list[tuple[str, str]]) -> str:
    return "".join(f'<div class="kv"><span>{k}</span><b>{v}</b></div>' for k, v in pairs)


# ---------------------------------------------------------------------------- the parts

def _net_worth(s: dict) -> str:
    b = s["balance"]
    parts = "".join(f'<div class="kv"><span>{_e(k)}</span><b>{_money(v)}</b></div>' for k, v in b["own"].items() if v)
    owes = "".join(f'<div class="kv"><span>{_e(k)}</span><b>{_money(v)}</b></div>' for k, v in b["owe"].items() if v)
    promised = sum(float(p.get("yearly") or 0) for p in b.get("promised") or [])
    out = f"""<section><h2>Net worth</h2>
  <div class="big">{_money(b["net"])}</div>
  <p class="muted">What you own, {_money(b["total_own"])}, less what you owe, {_money(b["total_owe"])}.</p>
  <h3>What you own</h3>{parts or '<p class="muted">Nothing yet.</p>'}"""
    if owes:
        out += f"<h3>What you owe</h3>{owes}"
    if promised:
        out += (f'<p class="muted">Pensions also promise {_money(promised)} a year for life, '
                "which isn't counted as money you own.</p>")
    if b.get("unconverted"):
        out += '<p class="warn">Some cash in another currency had no exchange rate yet, so it is left out.</p>'
    return out + "</section>"


def _tiles(s: dict) -> str:
    items = []
    for t in s.get("tiles") or []:
        if t.get("value") is None and t.get("level") == "none":
            continue
        value = _money(t.get("value")) if t.get("value") is not None else ""
        label = f' <span class="muted">{_e(t["value_label"])}</span>' if t.get("value_label") else ""
        lines = "".join(f"<div>{_plain(x)}</div>" for x in t.get("lines") or [])
        items.append(f'<div class="tile">{_dot(t.get("level"))}<b>{_e(t["title"])}</b>'
                     f'<div class="val">{value}{label}</div><div class="small muted">{lines}</div></div>')
    return f'<section><h2>How each part is doing</h2><div class="tiles">{"".join(items)}</div></section>' if items else ""


def _retirement() -> str:
    try:
        r = retirement.analyse(full=False)
    except Exception as e:  # a plan that can't run yet is said so, not hidden
        return f'<section><h2>Retirement</h2><p class="muted">{_e(e)}</p></section>'
    if not r.get("ready"):
        need = ", ".join(r.get("missing") or []) or "a few details"
        return (f'<section><h2>Retirement</h2><p class="muted">The year-by-year plan needs {_e(need)} first: '
                "the plan review on the computer asks for them.</p></section>")
    p = r["plan"]
    head = (f'<div class="big good">Lasts to {p["horizon"]:.0f}</div>' if p.get("lasts")
            else f'<div class="big bad">Runs short at about {int(p["runs_out_at"] or p["first_short"] or 0)}</div>')
    rows = [(f"When you stop, at {p['stop_age']:.0f}", _money((p.get("at_stop") or {}).get("liquid")))]
    fl = p.get("income_floor") or {}
    if fl.get("guaranteed"):
        rows.append((f"Guaranteed income from {int(fl['age'])}",
                     f"{_money(fl['guaranteed'])} a year" + (f" ({fl['covers'] * 100:.0f}% of essentials)" if fl.get("covers") else "")))
    if p.get("mortgage_free_age"):
        rows.append(("Mortgage clear at", f"{int(p['mortgage_free_age'])}"))
    sp = r.get("state_pension") or {}
    if sp.get("weekly"):
        rows.append(("State Pension", f"{_money(sp['weekly'], dp=2)} a week from {p['spa']:.0f}"))
    iht = p.get("iht") or {}
    if iht.get("tax"):
        rows.append(("Inheritance tax at the end, roughly", _money(iht["tax"])))
    return (f"<section><h2>Retirement</h2>{head}{_rows(rows)}"
            '<p class="small muted">In today\'s money, on the plan\'s assumptions. Rough figures, not a forecast.</p></section>')


def _coming_up(s: dict) -> str:
    items = s.get("this_year") or []
    if not items:
        return ""
    li = "".join(f'<li><span class="when">{_day(x["when"])}</span><b>{_plain(x["what"])}</b>'
                 f'<div class="small muted">{_plain(x.get("detail"))}</div></li>' for x in items)
    return f'<section><h2>Coming up</h2><ul class="dates">{li}</ul></section>'


def _investments() -> str:
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    if not pos and not tot.get("cash"):
        return ""
    total = tot.get("total") or 0.0
    rows = [("Total", _money(total))]
    if tot.get("gain") is not None and not tot.get("cost_unknown"):
        rows.append(("Gain on what you paid", f"{_money(tot['gain'])} ({(tot.get('gain_pct') or 0) * 100:+.1f}%)"))
    if tot.get("cash"):
        rows.append(("Cash on the platforms", _money(tot["cash"])))
    if tot.get("dividends_12m"):
        rows.append(("Dividends, last 12 months", _money(tot["dividends_12m"])))
    by_value = sorted(pos, key=lambda x: -(x.get("value") or 0))
    shown = by_value[:MAX_HOLDINGS]
    body = "".join(
        f'<tr><td>{_e(x["name"])}<div class="small muted">{_e(x.get("platform") or "")}</div></td>'
        f'<td class="num">{_money(x.get("value"))}<div class="small muted">'
        f'{_pct((x.get("value") or 0) / total * 100) if total else "—"}</div></td></tr>' for x in shown)
    rest = by_value[MAX_HOLDINGS:]
    if rest:
        body += (f'<tr><td class="muted">And {len(rest)} more</td>'
                 f'<td class="num muted">{_money(sum(x.get("value") or 0 for x in rest))}</td></tr>')
    out = f"<section><h2>Your investments</h2>{_rows(rows)}"
    if body:
        out += f'<h3>What you hold</h3><table>{body}</table>'
    try:
        v = allocation.view(pos, tot)
        sl = [r for r in v.get("sleeves") or [] if r.get("status") not in ("cash", "unassigned")]
        if sl:
            colour = {"ok": "green", "amber": "amber", "red": "red"}
            trs = "".join(f'<tr><td>{_dot(colour.get(r["status"]))}{_e(r["name"])}</td>'
                          f'<td class="num">{_pct(r.get("actual"))}<div class="small muted">target {_pct(r.get("target"), 0)}</div></td></tr>'
                          for r in sl)
            out += f"<h3>Against your plan</h3><table>{trs}</table>"
    except Exception:
        log.exception("phone copy: the sleeves")
    return out + "</section>"


def _accounts() -> str:
    tot = portfolio.totals()
    plats = [p for p in tot.get("platforms") or [] if p.get("kind") == "bank"]
    if not plats:
        return ""
    def cover(p: dict) -> str:
        if not p.get("scheme"):
            return ""
        cur = p.get("currency") or "GBP"
        limit = p.get("limit_native") if p.get("limit_native") is not None else p.get("limit")
        return f"{p['scheme']} covers up to {_money(limit, cur if p.get('limit_native') is not None else 'GBP', dp=0)}"

    trs = "".join(
        f'<tr><td>{_e(p["name"])}<div class="small muted">{_e(cover(p))}</div></td>'
        f'<td class="num">{_money(p.get("cash_native"), p.get("currency") or "GBP")}'
        + (f'<div class="small muted">{_money(p.get("cash"))}</div>' if (p.get("currency") or "GBP") != "GBP" else "")
        + "</td></tr>" for p in plats)
    return f"<section><h2>Cash and savings</h2><table>{trs}</table></section>"


def _mortgages(s: dict) -> str:
    ms = (s.get("balance") or {}).get("mortgages") or []
    if not ms:
        return ""
    out = "<section><h2>Mortgage</h2>"
    for m in ms:
        rows = [("Still owed", _money(m.get("balance"))), ("Monthly payment", _money(m.get("monthly_payment"), dp=2))]
        if m.get("rate") is not None:
            rows.append(("Rate", f"{m['rate']:.2f}% {_e(m.get('rate_type') or '')}".strip()))
        if m.get("fixed_until"):
            rows.append(("Fixed until", _day(m["fixed_until"])))
        if m.get("payoff_on"):
            d = dt.date.fromisoformat(str(m["payoff_on"])[:10])
            rows.append(("Clears", f"{MONTHS[d.month - 1]} {d.year}"))
        if m.get("ltv") is not None:
            rows.append(("Loan to value", f"{m['ltv'] * 100:.0f}%"))
        title = _e(m.get("name") or "Mortgage") + (f' <span class="muted">{_e(m["lender"])}</span>' if m.get("lender") else "")
        out += f"<h3>{title}</h3>{_rows(rows)}"
    if any(m.get("estimated") for m in ms):
        out += '<p class="small muted">Balances between statements are worked out from the payments, not read from the lender.</p>'
    return out + "</section>"


def _pensions() -> str:
    rows = pens.all_rows()
    if not rows:
        return ""
    li = "".join(f'<li><b>{_e(p["name"])}</b><div>{_e(pens.describe(p))}</div>'
                 + (f'<div class="small muted">{_e(p["provider"])}</div>' if p.get("provider") else "")
                 + (f'<div class="small muted">Nominated: {_e(p["nominee"])}</div>' if p.get("nominee")
                    else '<div class="small muted">No nomination recorded</div>' if p.get("kind") != "annuity" else "")
                 + "</li>" for p in rows)
    return f"<section><h2>Pensions</h2><ul>{li}</ul></section>"


def _look_at(s: dict) -> str:
    ws = (s.get("warnings") or [])[:10]
    if not ws:
        return ""
    li = "".join(f'<li>{_dot(w.get("level"))}<b>{_plain(w["title"])}</b>'
                 f'<div class="small muted">{_plain(w.get("detail"))}</div></li>' for w in ws)
    return f'<section><h2>Things to look at</h2><ul class="looks">{li}</ul></section>'


def _big_picture(s: dict) -> str:
    bp = s.get("big_picture") or {}
    parts = [("Your money", bp.get("you")), (bp.get("theme_title") or "Your watch", bp.get("theme")),
             ("Markets and the economy", bp.get("markets")), ("What it means for your investments", bp.get("portfolio"))]
    body = "".join(f"<h3>{_e(t)}</h3><p>{_plain(x)}</p>" for t, x in parts if x)
    if not body:
        return ""
    return (f"<section><h2>The big picture</h2>{body}"
            '<p class="small muted">Written from the figures by fixed rules. Not advice.</p></section>')


# ---------------------------------------------------------------------------- the page

CSS = """
:root{color-scheme:light dark;--bg:#f4f5f7;--card:#fff;--ink:#16181d;--muted:#5d6470;--line:#e3e6eb;--good:#2e7d32;--bad:#c62828;--warn:#fff4e5;--warn-ink:#7a4a00}
@media (prefers-color-scheme:dark){:root{--bg:#111316;--card:#1b1e23;--ink:#eceef2;--muted:#9aa2ae;--line:#2c3038;--good:#5fbf68;--bad:#ff6b6b;--warn:#3a2a10;--warn-ink:#ffcf8a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-text-size-adjust:100%}
main{max-width:640px;margin:0 auto;padding:16px 16px 40px}
header h1{margin:6px 0 2px;font-size:1.5rem}
.stamp{background:var(--warn);color:var(--warn-ink);border-radius:10px;padding:10px 12px;margin:12px 0 16px;font-size:.92rem}
section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:0 0 14px}
h2{font-size:1.1rem;margin:0 0 8px}
h3{font-size:.95rem;margin:14px 0 6px}
p{margin:6px 0}
.big{font-size:2rem;font-weight:650;letter-spacing:-.01em}
.big.good,.big.bad{font-size:1.6rem;margin-bottom:6px} .big.good{color:var(--good)} .big.bad{color:var(--bad)}
.kv{display:flex;justify-content:space-between;gap:12px;padding:5px 0;border-bottom:1px solid var(--line)}
.kv:last-child{border-bottom:0}
.kv span{color:var(--muted)} .kv b{text-align:right;font-weight:600}
table{width:100%;border-collapse:collapse}
td{padding:7px 0;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
td.num{text-align:right;white-space:nowrap;padding-left:12px;font-variant-numeric:tabular-nums}
.small{font-size:.84rem} .muted{color:var(--muted)}
.warn{background:var(--warn);color:var(--warn-ink);border-radius:8px;padding:8px 10px;font-size:.9rem}
.tiles{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.tile{border:1px solid var(--line);border-radius:12px;padding:10px}
.tile .val{font-size:1.15rem;font-weight:600;margin:4px 0}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:1px}
.dot.none{background:transparent;border:1px solid var(--muted)}
ul{list-style:none;margin:0;padding:0}
ul li{padding:8px 0;border-bottom:1px solid var(--line)} ul li:last-child{border-bottom:0}
.when{display:block;color:var(--muted);font-size:.84rem}
footer{color:var(--muted);font-size:.8rem;text-align:center;margin-top:18px}
@media (max-width:360px){.tiles{grid-template-columns:1fr}}
"""


def build(now: dt.datetime | None = None) -> bytes:
    """The whole page, as bytes ready to save."""
    now = now or dt.datetime.now()
    s = overall.summary()
    made = f"{_day(now.date().isoformat(), long=True)} at {_clock(now)}"
    name = str(config.settings.get("user_name") or "").strip()
    parts = []
    for fn in (lambda: _net_worth(s), lambda: _tiles(s), _retirement, lambda: _coming_up(s), _investments,
               _accounts, lambda: _mortgages(s), _pensions, lambda: _look_at(s), lambda: _big_picture(s)):
        try:
            parts.append(fn())
        except Exception:
            # One part that can't be drawn never costs the rest of the page.
            log.exception("phone copy: a part failed")
    page = f"""<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="{_e(config.APP_NAME)}">
<meta name="robots" content="noindex">
<title>{_e(config.APP_NAME)}: {_e(_day(now.date().isoformat()))}</title>
<style>{CSS}</style></head>
<body><main>
<header><div class="muted small">{_e(config.APP_NAME)}{(" for " + _e(name)) if name else ""}</div><h1>Your money at a glance</h1></header>
<div class="stamp"><b>A snapshot from {made}.</b> These figures don't change by themselves: make a new copy on the
computer (Settings, then <i>A copy for your phone</i>) to bring them up to date.</div>
{"".join(parts)}
<footer>Made by {_e(config.APP_NAME)} {_e(config.APP_VERSION)} from the figures on the computer. A personal tool for keeping to your own plan; not financial advice.</footer>
</main></body></html>
"""
    return page.encode("utf-8")


def filename() -> str:
    """The same name every time, so a new copy replaces the old one in a cloud folder
    and anything pointing at it keeps working."""
    return f"{config.APP_FILE_NAME} - your money at a glance.html"
