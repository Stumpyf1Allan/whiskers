"""1.2: the big picture written by Claude (only with the owner's own key)."""
import json

import pytest

from folio.market import briefing


def _facts():
    market = {"watch": {"main": "ai"}, "groups": {"ai": {"label": "Turning"}},
              "lights": [{"group": "ai", "title": "Nvidia", "level": "red", "words": "Down [[£1,234]] today"}]}
    pb = {"signals": [{"title": "Nvidia data-centre growth", "group": "ai", "value": 117.0, "op": "<",
                       "threshold": 30.0, "unit": "%", "firing": False, "kind": "manual", "updated": "2026-11-01"}],
          "firing": 0, "of": 8, "tier": {"label": "Normal", "text": "Do nothing."},
          "ladder": {"drop": 3.2, "rungs": [{"text": "Nothing", "active": True}]}}
    exp = {"ai_pct": 0.27, "ai_value": 32000.0, "top": [{"name": "Nvidia", "value": 9000.0}]}
    alloc = {"sleeves": [{"name": "Cash", "actual": 4.9, "target": 4.0, "status": "amber"}]}
    warns = [{"level": "red", "title": "Trim about [[£2,000]]", "detail": "From [[£9,000]]"}]
    return briefing.facts(market, pb, exp, alloc, warns, [{"title": "Chips slide", "source": "BBC"}])


def test_facts_never_carry_amounts():
    text = json.dumps(_facts())
    assert "£" not in text and "[[" not in text
    assert "32000" not in text and "9000" not in text
    assert '"share_of_portfolio_in_main_theme_pct": 27.0' in text


def test_key_is_checked_and_kept_in_the_vault():
    assert not briefing.has_key()
    with pytest.raises(ValueError):
        briefing.set_key("not-a-key")
    briefing.set_key("sk-ant-api03-" + "a" * 40)
    assert briefing.has_key()
    briefing.set_key("")
    assert not briefing.has_key()


def test_nothing_is_written_without_a_key():
    assert briefing.refresh(_facts(), "ai", force=True) is False
    assert briefing.state()["enabled"] is False


def test_parse_takes_the_last_json_and_the_sources():
    resp = {"content": [
        {"type": "text", "text": "Nvidia fell after results.",
         "citations": [{"url": "https://www.bbc.co.uk/news/x", "title": "BBC"}]},
        {"type": "text", "text": 'Here it is: {"headline": "Prices wobble", "theme": "A.", '
                                 '"markets": "B.", "portfolio": "C."}'}]}
    out = briefing.parse(resp)
    assert out["headline"] == "Prices wobble" and out["portfolio"] == "C."
    assert out["sources"] == [{"url": "https://www.bbc.co.uk/news/x", "title": "BBC"}]


def test_parse_refuses_a_missing_paragraph():
    with pytest.raises(RuntimeError):
        briefing.parse({"content": [{"type": "text", "text": '{"headline": "x", "theme": "A."}'}]})
