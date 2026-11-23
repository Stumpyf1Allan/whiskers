"""The Overview's big picture, written by Claude from today's readings and the news.

Optional. It runs only on a device where the owner has added their own Anthropic API key
(Settings → The big picture). Without a key, or if a call fails, the Overview keeps the
fixed-rule version from `engine/narrative.py`, so the family's copies are unchanged.

What is sent: the lights, signals, percentages, sleeve drift, the names of the largest AI
holdings and the day's headlines. Never money amounts: anything the engine wraps in
[[ ]] is replaced before it leaves the device. Claude may also search the web for the
latest news. The result is kept per lens in the device-only `briefings` table and rewritten only when
the readings have changed and the last one is a few hours old, or when asked.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import threading
import urllib.error
import urllib.request

from .. import db, security

KEY_REF = "claude_api"
MODEL = "claude-sonnet-5-5"
API = "https://api.anthropic.com/v1/messages"
REWRITE_AFTER = 4 * 3600          # seconds: the readings changed and the last one is this old
FORCE_GAP = 120                   # seconds: the Rewrite button, not more often than this
SEARCHES = 4

_lock = threading.Lock()
_state: dict = {"writing": set()}

SYSTEM = """You write "The big picture" for Whiskers, a personal investment tracker used by a \
UK investor. You are given today's readings as JSON. You may search the web for the latest \
market and AI-industry news from the past few days.

Write three short paragraphs that read as one coherent story, not a list of readings:
1. theme: the focus they chose (in "focus": the AI trade, the whole market, one sector, or \
their own portfolio). Explain what its price lights say and, if it has any, what their own \
signals say, whether they agree, and why, using what is actually happening in the news \
(earnings, guidance, policy, big moves). Name the events and dates. For their own portfolio, \
explain what is driving it, from its largest exposures and the news.
2. markets: markets in general and the economy, joined to the news: rates, credit, fear, \
growth, anything moving markets this week. Say how it connects to paragraph 1.
3. portfolio: what this means for this person's own portfolio and plan: their exposure, \
sleeves out of band, what their own playbook, ladder and agreed steps say applies today.

Rules:
- Plain English, British spelling, short sentences. 70-120 words per paragraph.
- Describe and explain. Never recommend buying or selling, never predict prices. You may \
say what the person's own rules say applies.
- No money amounts in pounds or dollars for the person's holdings. Percentages are fine.
- Only state news you found in the headlines given or in your searches. If unsure, leave it out.
- When you have finished, hand over the result by calling the write_big_picture tool once, \
with the headline (one sentence, at most 18 words, summing up today) and the three paragraphs."""

WRITE_TOOL = {
    "name": "write_big_picture",
    "description": "Hand over the finished big picture.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string", "description": "One sentence, at most 18 words."},
            "theme": {"type": "string"},
            "markets": {"type": "string"},
            "portfolio": {"type": "string"},
        },
        "required": ["headline", "theme", "markets", "portfolio"],
    },
}


# ---------------------------------------------------------------------------- the key

def has_key() -> bool:
    return bool((security.get(KEY_REF) or {}).get("key"))


def set_key(key: str) -> None:
    key = re.sub(r"\s", "", str(key or ""))
    if not key:
        security.drop(KEY_REF)
        return
    if not re.fullmatch(r"sk-ant-[A-Za-z0-9_\-]{20,200}", key):
        raise ValueError("That doesn't look like an Anthropic API key (they start sk-ant-).")
    security.put(KEY_REF, {"key": key})


# ---------------------------------------------------------------------------- what is sent

def _no_amounts(text: str) -> str:
    return re.sub(r"\[\[.*?\]\]", "an amount", str(text or ""))


def facts(market: dict, pb: dict | None, exp: dict, alloc: dict, warns: list[dict],
          headlines: list[dict], focus: dict | None = None) -> dict:
    """Everything Claude is told, with no money amounts."""
    w = market.get("watch") or {}
    main = w.get("main") or "ai"
    lights = [{"group": x.get("group"), "title": x.get("title"), "level": x.get("level"),
               "since": x.get("since"), "direction": x.get("direction"), "words": _no_amounts(x.get("words"))}
              for x in market.get("lights", [])]
    out = {
        "date": dt.date.today().isoformat(),
        "focus": {"title": (focus or {}).get("title"), "reading": (focus or {}).get("label"),
                  "share_of_portfolio_pct": round(focus["share"] * 100, 1) if (focus or {}).get("share") else None,
                  "lights": [{k: x.get(k) for k in ("title", "level", "since", "direction")}
                             | {"words": _no_amounts(x.get("words"))} for x in (focus or {}).get("lights", [])],
                  "turns_at_points": (focus or {}).get("turn_at")} if focus else None,
        "main_theme": w.get("main_title") or "The AI trade",
        "readings": {g: v.get("label") for g, v in (market.get("groups") or {}).items()},
        "how_readings_work": "Each light scores green 0, amber 1, red 2. A theme reads Turning at half "
                             "its worst (4 points of the AI trade's 8). Lights are price-based.",
        "lights": lights,
        "share_of_portfolio_in_main_theme_pct": round((exp.get("ai_pct") or 0) * 100, 1)
        if main == "ai" and exp.get("ai_pct") is not None else None,
        "largest_ai_holdings": [t.get("name") for t in (exp.get("top") or [])[:5]],
        "sleeves_out_of_band": [{"name": r["name"], "actual_pct": round(r["actual"], 1), "target_pct": r["target"]}
                                for r in alloc.get("sleeves", []) if r.get("status") in ("red", "amber")],
        "things_to_look_at": [{"level": x.get("level"), "title": _no_amounts(x.get("title")),
                               "detail": _no_amounts(x.get("detail"))} for x in (warns or [])[:10]],
        "headlines": [{"title": h.get("title"), "source": h.get("source"), "outlets": h.get("outlets"),
                       "published": h.get("published")} for h in (headlines or [])[:8]],
    }
    if pb:
        out["playbook"] = {
            "signals": [{"title": r["title"], "group": r["group"], "value": r.get("value"),
                         "fires_when": f"{r['op']} {r['threshold']:g} {r.get('unit') or ''}".strip(),
                         "firing": r.get("firing"), "entered_by_hand_on": r.get("updated")
                         if r.get("kind") == "manual" else None} for r in pb["signals"]],
            "tier": f"{pb['firing']} of {pb['of']} firing: {pb['tier']['label']} ({pb['tier']['text']})",
            "portfolio_below_its_high_pct": (pb.get("ladder") or {}).get("drop"),
            "ladder_now": next((r["text"] for r in (pb.get("ladder") or {}).get("rungs", []) if r.get("active")), None),
        }
    return out


def _fingerprint(f: dict) -> str:
    keep = {k: v for k, v in f.items() if k != "headlines"}
    keep["headlines"] = [h["title"] for h in f.get("headlines", [])[:3]]
    return hashlib.sha256(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------- storage

def _load(key: str) -> dict:
    row = db.one("SELECT written_at, data FROM briefings WHERE key=?", (key,))
    if not row:
        return {}
    try:
        data = json.loads(row["data"])
    except ValueError:
        return {}
    data["written_at"] = row["written_at"]
    return data


def _save(key: str, data: dict) -> None:
    db.execute("INSERT INTO briefings(key, written_at, data) VALUES(?, ?, ?) "
               "ON CONFLICT(key) DO UPDATE SET written_at=excluded.written_at, data=excluded.data",
               (key, data.get("written_at"), json.dumps({k: v for k, v in data.items() if k != "written_at"})))


def _age(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return (dt.datetime.now() - dt.datetime.fromisoformat(iso.replace(" ", "T"))).total_seconds()
    except ValueError:
        return None


# ---------------------------------------------------------------------------- writing

def refresh(f: dict, key: str = "ai", force: bool = False) -> bool:
    """Start writing in the background if it is due. True if started."""
    if not has_key():
        return False
    with _lock:
        if key in _state["writing"]:
            return False
        old = _load(key)
        age, fail_age = _age(old.get("written_at")), _age(old.get("failed_at"))
        last = min((a for a in (age, fail_age) if a is not None), default=None)
        fp = _fingerprint(f)
        if force:
            if last is not None and last < FORCE_GAP:
                return False
        elif old.get("error"):
            if fail_age is not None and fail_age < 30 * 60:
                return False
        elif age is not None and (old.get("fingerprint") == fp or age < REWRITE_AFTER):
            return False
        _state["writing"].add(key)
    threading.Thread(target=_work, args=(f, fp, key), daemon=True, name="briefing").start()
    return True


def _post(body: dict, key: str) -> dict:
    req = urllib.request.Request(API, data=json.dumps(body).encode("utf-8"), method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # nosec B310  # Anthropic's fixed https address
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        if e.code == 401:
            raise RuntimeError("your API key was refused. Check it in Settings.") from None
        raise RuntimeError(f"error {e.code}{': ' + msg if msg else ''}") from None
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"couldn't reach Anthropic ({getattr(e, 'reason', e)})") from None


def _json_in(text: str) -> dict | None:
    """The last JSON object in the text that has the three paragraphs, or None."""
    text = re.sub(r"```(?:json)?", "", text)
    dec = json.JSONDecoder()
    found = None
    for m in re.finditer(r"\{", text):
        try:
            got, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(got, dict) and any(k in got for k in ("theme", "markets", "portfolio")):
            found = got
    return found


def _text(resp: dict) -> str:
    return "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")


def parse(resp: dict) -> dict:
    """The three paragraphs and the sources Claude used."""
    got = next((b.get("input") for b in reversed(resp.get("content", []))
                if b.get("type") == "tool_use" and b.get("name") == WRITE_TOOL["name"]
                and isinstance(b.get("input"), dict)), None) or _json_in(_text(resp))
    if got is None:
        cut = " (it ran out of room)" if resp.get("stop_reason") == "max_tokens" else ""
        raise RuntimeError(f"its answer wasn't in the expected shape{cut}.")
    out = {k: re.sub(r"\s+", " ", str(got.get(k) or "")).strip() for k in ("headline", "theme", "markets", "portfolio")}
    if not (out["theme"] and out["markets"] and out["portfolio"]):
        raise RuntimeError("its answer was missing a paragraph.")
    out["sources"] = parse_sources(resp)
    return out


def parse_sources(resp: dict) -> list:
    sources, seen = [], set()
    for b in resp.get("content", []):
        for c in b.get("citations") or []:
            url = c.get("url")
            if url and url.startswith("https://") and url not in seen:
                seen.add(url)
                sources.append({"url": url, "title": (c.get("title") or url)[:120]})
    return sources[:6]


def _describe(resp: dict) -> dict:
    """What came back, for the log when it couldn't be read: no readings, just the shape."""
    return {"stop_reason": resp.get("stop_reason"),
            "blocks": [b.get("type") for b in resp.get("content", [])][:40],
            "text_end": _text(resp)[-600:]}


def _work(f: dict, fp: str, lens: str = "ai") -> None:
    try:
        key = (security.get(KEY_REF) or {}).get("key")
        body = {"model": MODEL, "max_tokens": 4000, "system": SYSTEM,
                "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": SEARCHES}, WRITE_TOOL],
                "messages": [{"role": "user", "content": "Today's readings:\n" + json.dumps(f, default=str)}]}
        try:
            resp = _post(body, key)
        except RuntimeError as e:
            if "error 400" not in str(e):
                raise
            body["tools"] = [WRITE_TOOL]   # web search not available on this key: write from the readings
            resp = _post(body, key)
        content = []                       # everything Claude has said so far, across pauses
        for _ in range(4):                 # a long search can pause part-way: let it carry on
            content += resp.get("content", [])
            if resp.get("stop_reason") != "pause_turn":
                break
            body["messages"] = body["messages"][:1] + [{"role": "assistant", "content": content}]
            resp = _post(body, key)
        whole = dict(resp, content=content)
        try:
            out = parse(whole)
        except RuntimeError:               # no answer handed over: ask once, and make it use the tool
            db.log("briefing.reply", _describe(whole))
            body["tools"] = [WRITE_TOOL]
            body["tool_choice"] = {"type": "tool", "name": WRITE_TOOL["name"]}
            body["messages"] = body["messages"][:1] + [
                {"role": "assistant", "content": _text(whole).strip() or "(no text)"},
                {"role": "user", "content": "Now hand over the finished big picture with the "
                                            "write_big_picture tool."}]
            again = _post(body, key)
            try:
                out = parse(again)
            except RuntimeError as e:
                d = _describe(again)
                db.log("briefing.reply", d)
                raise RuntimeError(f"{e} (Claude stopped with {d['stop_reason']}; "
                                   f"sent {', '.join(d['blocks']) or 'nothing'})") from None
            out["sources"] = parse_sources(whole) or out["sources"]
        _save(lens, dict(out, fingerprint=fp, written_at=db.now(), error="", failed_at=None))
    except Exception as e:
        old = _load(lens)
        _save(lens, dict(old, error=str(e)[:300], failed_at=db.now()))
        db.log("briefing.error", str(e)[:300])
    finally:
        _state["writing"].discard(lens)


def state(key: str = "ai") -> dict:
    data = _load(key)
    return {"enabled": has_key(), "writing": key in _state["writing"], "lens": key,
            "written_at": data.get("written_at"), "problem": data.get("error") or "",
            "text": {k: data.get(k) for k in ("headline", "theme", "markets", "portfolio")} if data.get("theme") else None,
            "sources": data.get("sources") or []}
