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


def _resp(*texts, stop="end_turn"):
    return {"stop_reason": stop, "content": [{"type": "text", "text": t} for t in texts]}


def test_parse_finds_json_after_prose_split_across_blocks():
    j = '{"headline": "H", "theme": "T", "markets": "M", "portfolio": "P"}'
    out = briefing.parse(_resp("Some notes {not json} here.\n", j[:30], j[30:]))
    assert out["theme"] == "T" and out["headline"] == "H"


def test_parse_handles_fences_and_spaces():
    out = briefing.parse(_resp('```json\n{ "headline": "H",\n "theme": "T", "markets": "M", "portfolio": "P" }\n```'))
    assert out["portfolio"] == "P"


def test_parse_says_when_cut_off():
    import pytest
    with pytest.raises(RuntimeError, match="ran out of room"):
        briefing.parse(_resp('{"headline": "H", "theme": "T', stop="max_tokens"))


def test_work_asks_again_for_just_the_json(monkeypatch):
    calls = []
    replies = [_resp("Searching done, here is my story but no JSON.", stop="pause_turn"),
               _resp("Still no JSON."),
               _resp('{"headline": "H", "theme": "T", "markets": "M", "portfolio": "P"}')]

    def fake_post(body, key):
        calls.append(body)
        return replies[len(calls) - 1]

    monkeypatch.setattr(briefing, "_post", fake_post)
    monkeypatch.setattr(briefing.security, "get", lambda ref: {"key": "k"})
    briefing._work(_facts(), "fp", "ai")
    assert len(calls) == 3 and calls[2]["tool_choice"]["name"] == "write_big_picture"
    assert [t["name"] for t in calls[2]["tools"]] == ["write_big_picture"]
    assert briefing.state("ai")["text"]["theme"] == "T"


def test_parse_reads_the_tool_call():
    resp = {"stop_reason": "tool_use", "content": [
        {"type": "text", "text": "Here it is."},
        {"type": "tool_use", "name": "write_big_picture",
         "input": {"headline": "H", "theme": "T", "markets": "M", "portfolio": "P"}}]}
    out = briefing.parse(resp)
    assert out["theme"] == "T" and out["headline"] == "H"
