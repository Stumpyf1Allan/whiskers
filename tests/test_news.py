"""Tests for 1.2: the Overview's News panel.

Every feed here is hand-made with invented headlines (the repository is public, and the tests
never use the internet).
"""

from __future__ import annotations

import datetime as dt
import email.utils
import json
import urllib.request

import pytest

from folio import config, db, net, sync
from folio.market import news

NOW = dt.datetime(2026, 10, 21, 12, 0, tzinfo=dt.timezone.utc)


def _stamp(hours_ago: float) -> str:
    return email.utils.format_datetime(NOW - dt.timedelta(hours=hours_ago))


def _feed(*stories) -> bytes:
    """stories: (title, link, hours_ago[, description])"""
    items = "".join(
        f"<item><title>{s[0]}</title><link>{s[1]}</link><pubDate>{_stamp(s[2])}</pubDate>"
        f"<description>{s[3] if len(s) > 3 else ''}</description></item>" for s in stories)
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>t</title>'
            f"{items}</channel></rss>").encode()


BBC = ("bbc.co.uk",)


# ============================================================================ reading a feed

def test_keeps_recent_news_and_drops_old_video_and_promotions():
    raw = _feed(
        ("Gilt yields fall after a weak jobs report", "https://www.bbc.co.uk/news/articles/aaa", 2),
        ("A feature written months ago", "https://www.bbc.co.uk/news/articles/bbb", 30 * 24),
        ("Watch: the chancellor on the budget", "https://www.bbc.co.uk/news/articles/ccc", 1),
        ("A clip", "https://www.bbc.co.uk/news/videos/ddd", 1),
        ("Our money newsletter", "https://www.bbc.co.uk/news/articles/eee", 1),
        ("From the future", "https://www.bbc.co.uk/news/articles/fff", -5),
    )
    got = news.parse_feed(raw, BBC, now=NOW)
    assert [g["title"] for g in got] == ["Gilt yields fall after a weak jobs report"]


def test_links_must_be_https_on_the_outlets_own_site():
    raw = _feed(
        ("Fine story about interest rates", "https://www.bbc.co.uk/news/articles/aaa", 1),
        ("Plain http story about wages", "http://www.bbc.co.uk/news/articles/bbb", 1),
        ("Other site story about pensions", "https://evil.example.com/news/ccc", 1),
        ("Lookalike host story about gilts", "https://bbc.co.uk.evil.example.com/ddd", 1),
        ("Script link story about banks", "javascript:alert(1)", 1),
    )
    assert [g["title"] for g in news.parse_feed(raw, BBC, now=NOW)] == ["Fine story about interest rates"]


def test_a_feed_with_a_doctype_or_entity_is_refused():
    bad = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel/></rss>'
    with pytest.raises(ValueError):
        news.parse_feed(bad, BBC, now=NOW)


def test_a_feed_that_is_too_large_or_broken_is_refused():
    with pytest.raises(ValueError):
        news.parse_feed(b"x" * (news.MAX_BYTES + 1), BBC, now=NOW)
    with pytest.raises(ValueError):
        news.parse_feed(b"<rss><channel>", BBC, now=NOW)


def test_headlines_are_plain_text():
    raw = _feed(("Shares &lt;b&gt;jump&lt;/b&gt; &amp;amp; the pound slips", "https://www.bbc.co.uk/news/articles/aaa", 1))
    assert news.parse_feed(raw, BBC, now=NOW)[0]["title"] == "Shares jump & the pound slips"


# ============================================================================ one story from many

def _it(title, pos=0, hours=1, summary=""):
    return {"title": title, "url": "https://x/" + title[:5], "pub": (NOW - dt.timedelta(hours=hours)).isoformat(),
            "summary": summary, "pos": pos}


def test_the_same_story_from_several_outlets_is_one_and_ranks_first():
    outlets = {
        "bbc": {"items": [_it("Inflation rises to 3.5% before the Budget", 0), _it("Starling founder sells shares", 1)]},
        "guardian": {"items": [_it("UK inflation jumps to 3.5% ahead of budget", 0)]},
        "sky": {"items": [_it("Apollo among suitors for spreads giant", 0), _it("Inflation at 3.5% as budget looms", 1)]},
    }
    top = news.rank(outlets, now=NOW)
    assert top[0]["outlets"] == 3
    assert top[0]["source"] == "BBC News"          # the first outlet in order supplies the headline
    assert len(top) == 3                           # three different stories, not five


def test_two_stories_that_only_share_a_common_word_stay_apart():
    a, b = _it("Bank of England holds rates"), _it("Bank holiday trading falls")
    assert not news.same_story(a, b)


def test_ties_go_to_the_higher_placed_then_the_newer_story():
    outlets = {"bbc": {"items": [_it("Alpha merger announced today", 3), _it("Beta results disappoint investors", 0)]}}
    assert news.rank(outlets, now=NOW)[0]["title"].startswith("Beta")
    outlets = {"bbc": {"items": [_it("Alpha merger announced today", 0, hours=5), _it("Beta results disappoint investors", 0, hours=1)]}}
    assert news.rank(outlets, now=NOW)[0]["title"].startswith("Beta")


def test_only_five_and_nothing_older_than_a_day_at_read_time():
    stories = [_it(f"Story{n} unique{n} topic{n} words{n}", n) for n in range(8)]
    stories.append(_it("Ancient tale gold silver", 0, hours=26))
    top = news.rank({"bbc": {"items": stories}}, now=NOW)
    assert len(top) == 5 and all("Ancient" not in t["title"] for t in top)


def test_no_topic_is_favoured():
    outlets = {"bbc": {"items": [_it("AI chip maker unveils new product line", 0), _it("Wheat prices rise on poor harvest", 1)]},
               "sky": {"items": [_it("Wheat prices climb after poor harvest", 0)]}}
    assert "Wheat" in news.rank(outlets, now=NOW)[0]["title"]


# ============================================================================ fetching and keeping

def _fake_net(monkeypatch, feeds: dict):
    def get(url, **k):
        v = feeds.get(url)
        if isinstance(v, Exception):
            raise v
        if v is None:
            raise net.FetchError("HTTP 404", status=404, url=url)
        return v
    monkeypatch.setattr(net, "get", get)


def _run():
    news._state["fetching"] = True
    news._work()


def _all_feeds(titles_by_key, hours=1):
    host = {"bbc": "https://www.bbc.co.uk/news/articles/", "guardian": "https://www.theguardian.com/business/",
            "sky": "https://news.sky.com/story/", "ap": "https://apnews.com/article/", "cnbc": "https://www.cnbc.com/2026/10/21/"}
    out = {}
    for key, _, url, _ in news.OUTLETS:
        out[url] = _feed(*[(t, host[key] + f"{n}", hours) for n, t in enumerate(titles_by_key.get(key, []))])
    return out


def test_one_outlet_down_does_not_stop_the_rest(monkeypatch):
    feeds = _all_feeds({"bbc": ["Mortgage rates ease again this month"], "guardian": ["Mortgage rates ease again for lenders"]})
    feeds[news.OUTLETS[2][2]] = net.FetchError("Couldn't connect: boom", offline=True)
    _fake_net(monkeypatch, feeds)
    _run()
    st = news.state()
    assert st["items"] and st["items"][0]["outlets"] == 2
    sky = next(s for s in st["status"] if s["key"] == "sky")
    assert not sky["ok"] and sky["error"] == "offline"
    assert not st["failed"]


def test_a_failed_fetch_keeps_the_last_list(monkeypatch):
    _fake_net(monkeypatch, _all_feeds({"bbc": ["Retail sales beat forecasts in September"]}))
    _run()
    assert news.state()["items"]
    _fake_net(monkeypatch, {})              # everything 404s
    _run()
    st = news.state()
    assert st["items"] and st["failed"]     # still the old list, and it says it couldn't update


def test_it_survives_a_restart_and_is_not_in_the_phones_copy(monkeypatch):
    _fake_net(monkeypatch, _all_feeds({"bbc": ["Retail sales beat forecasts in September"]}))
    _run()
    db.forget_initialised()
    db.init()
    assert news.state()["items"]
    assert "news" not in sync.TABLES
    assert "show_news" in sync.SETTINGS


def test_refresh_waits_between_fetches(monkeypatch):
    calls = []
    monkeypatch.setattr(news.threading, "Thread", lambda target, **k: type("T", (), {"start": lambda self: calls.append(1)})())
    assert news.refresh() is True
    news._state["fetching"] = False
    db.execute("INSERT INTO news(id, fetched_at, data) VALUES(1, ?, '{}')", (db.now(),))
    assert news.refresh() is False                    # fresh: no fetch
    assert news.refresh(force=True) is False          # even Refresh waits two minutes
    old = (dt.datetime.now() - dt.timedelta(minutes=3)).replace(microsecond=0).isoformat(sep=" ")
    db.execute("UPDATE news SET fetched_at=?", (old,))
    assert news.refresh(force=True) is True
    news._state["fetching"] = False
    assert news.refresh() is False                    # 3 minutes old is fresh enough for a visit
    assert len(calls) == 2


def test_fake_market_fetches_nothing(monkeypatch):
    monkeypatch.setenv("WHISKERS_FAKE_MARKET", "1")
    monkeypatch.setattr(net, "get", lambda *a, **k: pytest.fail("fetched in fake mode"))
    _run()
    st = news.state()
    assert st["fake"] and len(st["items"]) == 5


def test_a_browser_style_retry_when_an_outlet_refuses_a_script(monkeypatch):
    seen = []

    def get(url, **k):
        seen.append(k.get("browser", False))
        if not k.get("browser"):
            raise net.FetchError("HTTP 403", status=403, url=url)
        return _feed(("Oil climbs as producers hold output", "https://www.bbc.co.uk/news/articles/z", 1))
    monkeypatch.setattr(net, "get", get)
    r = news._fetch_one("bbc", news.OUTLETS[0][2], BBC)
    assert r["ok"] and seen == [False, True]


# ============================================================================ the route and setting

@pytest.fixture()
def server():
    from folio.web import server as srv
    httpd, port = srv.serve(port=srv._free_port(18877), block=False)
    yield port
    httpd.shutdown()


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=30) as r:
        return json.loads(r.read())


def test_route_answers_at_once_and_can_be_switched_off(server, monkeypatch):
    monkeypatch.setattr(news, "refresh", lambda force=False: False)
    a = _get(server, "/api/news")
    assert a["enabled"] and a["items"] == [] and not a["failed"]
    req = urllib.request.Request(f"http://127.0.0.1:{server}/api/settings", method="PATCH",
                                 data=json.dumps({"show_news": False}).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()
    assert _get(server, "/api/news") == {"enabled": False}
    assert config.settings.get("show_news") is False


def test_news_is_on_by_default_and_reaches_the_page():
    assert config.DEFAULTS["show_news"] is True
    from folio.web import server as srv
    assert "show_news" in srv.SETTABLE
