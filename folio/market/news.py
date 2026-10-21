"""The Overview's News panel: the day's five biggest business stories.

Five outlets publish a free public feed of their business news. Whiskers reads them, keeps
what is under a day old, treats the same story from several outlets as one, and ranks
stories by how many outlets carry them. Nothing here judges a story or favours a topic.
A story's headline and link are the first outlet's that carries it, in `OUTLETS` order, and
the link is always to that outlet's own site.

The result is kept in the `news` table on this device only: it goes stale in hours, so it
never travels to the phone's copy. A failed fetch leaves the last list in place.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import re
import threading
import time
import xml.etree.ElementTree as ET  # nosec B405  # only on text with no DOCTYPE or ENTITY: see parse_feed
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from .. import config, db, net

#: key, name, feed address, the hosts its links may point to. Order is the order a story's
#: headline is taken in: CNBC is last because some of its stories are for subscribers.
OUTLETS = (
    ("bbc", "BBC News", "https://feeds.bbci.co.uk/news/business/rss.xml",
     ("bbc.co.uk", "bbc.com")),
    ("guardian", "The Guardian", "https://www.theguardian.com/uk/business/rss",
     ("theguardian.com",)),
    ("sky", "Sky News", "https://feeds.skynews.com/feeds/rss/business.xml",
     ("news.sky.com", "sky.com")),
    ("ap", "AP", "https://flipboard.com/@associatedpress/business-and-finance-pbj3bpclz.rss",
     ("apnews.com",)),
    ("cnbc", "CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html",
     ("cnbc.com",)),
)
TOP = 5
MAX_AGE = dt.timedelta(hours=24)
MAX_BYTES = 2 * 1024 * 1024
STALE_AFTER = 15 * 60          # seconds before a visit starts a new fetch
FORCE_GAP = 2 * 60             # seconds between fetches when Refresh is pressed
FETCH_TIMEOUT = 10.0

_lock = threading.Lock()
_state = {"fetching": False}

# Link paths that are not a news story, and titles that say so.
_NOT_NEWS_PATH = re.compile(r"/(videos?|podcasts?|audio|live|opinion|commentisfree|newsletters?)(/|$)", re.I)
_NOT_NEWS_TITLE = re.compile(r"^(watch|video|listen|podcast)\b|newsletter|\bsponsored\b", re.I)

_STOP = frozenset("""a an the and or of to in on for with at by from as is are was were be been it its
this that these those after before over under into than more most less new says say said will would
could can may might up down out about amid ahead next last year week day today why how what who when
where which latest first has have had not no yes his her their our your we you they he she them us
uk""".split())


# ---------------------------------------------------------------------------- reading a feed

def _clean(text: str, limit: int) -> str:
    text = html.unescape(re.sub(r"<[^>]*>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _when(text: str) -> dt.datetime | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        d = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            d = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def _link_ok(url: str, hosts: tuple[str, ...]) -> bool:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or host.endswith("." + h) for h in hosts)


def parse_feed(raw: bytes, hosts: tuple[str, ...], now: dt.datetime | None = None,
               check_hosts: bool = True) -> list[dict]:
    """An RSS feed's stories, newest-looking first as the outlet ordered them. Keeps only
    https links on the outlet's own site, under a day old, that are news stories."""
    if len(raw) > MAX_BYTES:
        raise ValueError("The feed is larger than expected, so it was ignored.")
    body = raw.decode("utf-8", "replace")
    # A news feed never needs a DOCTYPE or an entity; a crafted one could use them to make
    # the parser balloon, so either one means the feed is refused.
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", body, re.I):
        raise ValueError("The feed has a DOCTYPE or entity, so it was ignored.")
    try:
        root = ET.fromstring(body)  # nosec B314  # DOCTYPE and ENTITY refused just above
    except ET.ParseError:
        raise ValueError("The feed couldn't be read.") from None
    now = now or dt.datetime.now(dt.timezone.utc)
    out, seen = [], set()
    for it in root.iter("item"):
        title = _clean(it.findtext("title") or "", 220)
        link = (it.findtext("link") or "").strip()
        pub = _when(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date") or "")
        if not title or not link or pub is None or link in seen:
            continue
        if check_hosts and not _link_ok(link, hosts):
            continue
        if _NOT_NEWS_PATH.search(urlparse(link).path) or _NOT_NEWS_TITLE.search(title):
            continue
        if pub < now - MAX_AGE or pub > now + dt.timedelta(hours=1):
            continue
        seen.add(link)
        out.append({"title": title, "url": link, "pub": pub.isoformat(),
                    "summary": _clean(it.findtext("description") or "", 400),
                    "pos": len(out)})
    return out


# ---------------------------------------------------------------------------- one story from many

def _words(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9][a-z0-9.%£$€]*", (text or "").lower().replace("-", " ")):
        w = w.rstrip(".")
        if w in _STOP or (len(w) < 3 and not any(c.isdigit() for c in w)):
            continue
        for suf in ("ing", "es", "s", "ed"):
            if len(w) > 5 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.add(w)
    return out


def same_story(a: dict, b: dict) -> bool:
    """Two shared key words in the headlines, or five across headline and summary with at
    least one of them in the headlines."""
    ta, tb = _words(a["title"]), _words(b["title"])
    shared_title = len(ta & tb)
    if shared_title >= 2:
        return True
    both = len((ta | _words(a.get("summary"))) & (tb | _words(b.get("summary"))))
    return shared_title >= 1 and both >= 5


def rank(outlets: dict, now: dt.datetime | None = None, top: int = TOP) -> list[dict]:
    """`outlets` is {key: {"items": [...]}}. The `top` biggest stories, biggest first."""
    now = now or dt.datetime.now(dt.timezone.utc)
    floor = (now - MAX_AGE).isoformat()
    names = {k: n for k, n, _, _ in OUTLETS}
    order = {k: i for i, (k, _, _, _) in enumerate(OUTLETS)}
    groups: list[list[tuple[str, dict]]] = []
    for key, _, _, _ in OUTLETS:
        for it in (outlets.get(key) or {}).get("items", []):
            if it["pub"] < floor:
                continue
            for g in groups:
                if any(same_story(it, other) for _, other in g):
                    g.append((key, it))
                    break
            else:
                groups.append([(key, it)])

    def sortkey(g):
        keys = {k for k, _ in g}
        best = min(it["pos"] for _, it in g)
        newest = max(it["pub"] for _, it in g)
        # most outlets first, then the one placed highest, then the newest
        return (-len(keys), best, _neg(newest))

    items = []
    for g in sorted(groups, key=sortkey)[:top]:
        key, it = min(g, key=lambda ki: order[ki[0]])
        items.append({"title": it["title"], "url": it["url"], "source": names[key],
                      "published": it["pub"], "outlets": len({k for k, _ in g})})
    return items


def _neg(iso: str) -> float:
    return -dt.datetime.fromisoformat(iso).timestamp()


# ---------------------------------------------------------------------------- fetching and keeping

def _fetch_one(key: str, url: str, hosts: tuple[str, ...]) -> dict:
    hdrs = {"Accept": "application/rss+xml,application/xml;q=0.9,text/xml;q=0.9,*/*;q=0.5"}
    try:
        try:
            raw = net.get(url, timeout=FETCH_TIMEOUT, headers=hdrs)
        except net.FetchError as e:
            if e.status in (401, 403, 406, 429):    # refused as a script: try as a browser
                raw = net.get(url, timeout=FETCH_TIMEOUT, headers=hdrs, browser=True)
            else:
                raise
        items = parse_feed(raw, hosts)
        return {"ok": True, "error": "", "items": items}
    except net.FetchError as e:
        return {"ok": False, "error": "offline" if e.offline else str(e)[:160], "items": None}
    except ValueError as e:
        return {"ok": False, "error": str(e), "items": None}
    except Exception as e:              # one outlet must never stop the rest
        db.log("news.error", f"{key}: {e}")
        return {"ok": False, "error": "unexpected problem", "items": None}


def _load() -> dict:
    found = db.rows("SELECT fetched_at, data FROM news WHERE id=1")
    if not found:
        return {"fetched_at": None, "outlets": {}}
    row = found[0]
    try:
        data = json.loads(row["data"])
    except ValueError:
        return {"fetched_at": None, "outlets": {}}
    data["fetched_at"] = row["fetched_at"]
    return data


def _save(data: dict):
    db.execute("INSERT INTO news(id, fetched_at, data) VALUES(1, ?, ?) "
               "ON CONFLICT(id) DO UPDATE SET fetched_at=excluded.fetched_at, data=excluded.data",
               (data["fetched_at"], json.dumps({"outlets": data["outlets"]})))


def _fake_outlets() -> dict:
    """Made-up headlines for WHISKERS_FAKE_MARKET=1: nothing is fetched."""
    now = dt.datetime.now(dt.timezone.utc)
    titles = ["Inflation figure surprises ahead of the Budget", "Two carmakers confirm merger talks",
              "Rate-setters split on the next move", "Oil climbs as producers hold output",
              "Shares slip as earnings season starts", "Water firm creditors back rescue deal"]
    out = {}
    for n, (key, _, _, _) in enumerate(OUTLETS):
        out[key] = {"ok": True, "error": "", "items": [
            {"title": t, "url": f"https://example.com/fake-news/{i}",
             "pub": (now - dt.timedelta(hours=1 + i)).isoformat(), "summary": "", "pos": i}
            for i, t in enumerate(titles[: 3 + (n % 3)])]}
    return out


def refresh(force: bool = False) -> bool:
    """Start a background fetch if the list is old enough. True if one was started."""
    with _lock:
        if _state["fetching"]:
            return False
        data = _load()
        age = _age(data)
        if age is not None and age < (FORCE_GAP if force else STALE_AFTER):
            return False
        _state["fetching"] = True
    threading.Thread(target=_work, daemon=True, name="news").start()
    return True


def _age(data: dict) -> float | None:
    if not data.get("fetched_at"):
        return None
    try:
        t = dt.datetime.fromisoformat(data["fetched_at"].replace(" ", "T"))
    except ValueError:
        return None
    return max(0.0, (dt.datetime.now() - t).total_seconds())


def _work():
    try:
        old = _load()
        if config.fake_market():
            new = _fake_outlets()
        else:
            with ThreadPoolExecutor(max_workers=len(OUTLETS)) as ex:
                futs = {k: ex.submit(_fetch_one, k, url, hosts) for k, _, url, hosts in OUTLETS}
                got = {k: f.result() for k, f in futs.items()}
            new = {}
            for k, r in got.items():
                before = (old.get("outlets") or {}).get(k) or {}
                if r["items"] is None:      # failed: keep what we had, say what went wrong
                    new[k] = {"ok": False, "error": r["error"], "items": before.get("items", []),
                              "last_ok": before.get("last_ok")}
                else:
                    new[k] = {"ok": True, "error": "", "items": r["items"], "last_ok": db.now()}
        _save({"fetched_at": db.now(), "outlets": new})
    except Exception as e:
        db.log("news.error", str(e))
    finally:
        _state["fetching"] = False


def state() -> dict:
    """What the panel shows. Never waits on the network."""
    data = _load()
    outlets = data.get("outlets") or {}
    status = []
    for key, name, _, _ in OUTLETS:
        o = outlets.get(key) or {}
        items = o.get("items") or []
        status.append({"key": key, "name": name, "ok": bool(o.get("ok")), "error": o.get("error", ""),
                       "newest": max((i["pub"] for i in items), default=None),
                       "checked": bool(o)})
    checked = [s for s in status if s["checked"]]
    return {"enabled": True, "items": rank(outlets), "updated": data.get("fetched_at"),
            "fetching": _state["fetching"], "status": status,
            "failed": bool(checked) and not any(s["ok"] for s in checked),
            "fake": config.fake_market()}
