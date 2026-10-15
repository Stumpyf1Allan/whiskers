"""Tests for 2.0: one app with Overall, Investments, Budget, Mortgage and Retirement tabs.

Grouped like the rest: by what would go wrong for a person if the test didn't exist.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.request

import pytest

from folio import config, db, inbox, reminders
from folio.engine import (builder, mortgage as mort, overall, pensions, retirement, sample, statepension,
                          themes, uktax, xray)
from folio.importers import investments as inv

from .test_whiskers import add_platform, add_position


def _years_ago(n: float) -> str:
    return (dt.date.today() - dt.timedelta(days=round(n * 365.25))).isoformat()


def _basic_plan(**kw):
    s = {"dob": _years_ago(60.3), "stop_age": 60.3, "spend_essential": 1200, "spend_extra": 300,
         "horizon_age": 95, "nation": "england"}
    s.update(kw)
    retirement.save(s)


# ============================================================================ tax, the State Pension

def test_income_tax_and_national_insurance_on_50k():
    assert uktax.income_tax(50000, "england")["tax"] == pytest.approx(7486.0)
    assert uktax.national_insurance(50000) == pytest.approx(2994.40)
    assert uktax.income_tax(50000, "scotland")["tax"] == pytest.approx(8982.05)


@pytest.mark.parametrize("dob,months", [
    ("1959-12-31", 66 * 12), ("1960-04-06", 66 * 12 + 1), ("1960-05-10", 66 * 12 + 2),
    ("1961-03-06", 67 * 12), ("1977-04-05", 67 * 12), ("1978-04-06", 68 * 12),
])
def test_state_pension_age_follows_the_timetable_in_law(dob, months):
    assert statepension.age_months(dt.date.fromisoformat(dob))[0] == months


def test_a_forecast_beats_a_rough_figure_and_gaps_are_costed():
    dob = dt.date(1966, 3, 14)
    est = statepension.estimate({"state_pension": {"weekly": 221.5}}, dob)
    assert est["yearly"] == pytest.approx(221.5 * 52) and est["basis"] == "your forecast"
    rough = statepension.estimate({"state_pension": {"years": 9}, "stop_age": 60}, dob)
    assert rough["basis"].startswith("rough") and rough["weekly"] == 0.0     # under ten years: nothing
    gaps = statepension.estimate({"state_pension": {"years": 25, "gaps": 3}, "stop_age": 60}, dob)
    assert gaps["top_up"]["years"] == 3 and gaps["top_up"]["pays_back_years"] < 4


# ============================================================================ the mortgage

def _mortgage(**kw) -> int:
    row = {"name": "Home", "lender": "Nationwide", "statement_balance": 100000,
           "statement_on": dt.date.today().replace(day=1).isoformat(), "monthly_payment": 527.84, "rate": 4.0,
           "repayment_type": "repayment", "rate_type": "fixed", "created_at": db.now()}
    row.update(kw)
    with db.tx() as c:
        return c.execute(f"INSERT INTO mortgages({','.join(row)}) VALUES({','.join('?' * len(row))})",
                         tuple(row.values())).lastrowid


def test_a_payment_and_its_term_agree():
    assert mort.payment_for(100000, 4.0, 300) == pytest.approx(527.84, abs=0.01)
    assert mort.months_to_clear(100000, 4.0, 527.84) == 300


def test_a_payment_is_split_into_interest_and_capital():
    s = mort.summarise(mort.get(_mortgage()))
    assert s["interest_this_month"] == pytest.approx(333.33, abs=0.01)
    assert s["capital_this_month"] == pytest.approx(527.84 - 333.33, abs=0.02)
    assert s["months_left"] == 300


def test_overpaying_saves_interest_and_time_and_nothing_is_free():
    m = mort.get(_mortgage())
    r = mort.overpayment_effect(m, 200, "monthly")
    assert r["available"] and r["months_saved"] > 60 and r["interest_saved"] > 10000
    assert "Check yours" in r["caveat"]
    assert not mort.overpayment_effect(m, 0)["available"]


def test_a_payment_that_doesnt_cover_the_interest_is_said_so():
    s = mort.summarise(mort.get(_mortgage(monthly_payment=300)))
    assert s["never_clears"] is True


def test_a_rate_rise_raises_the_payment():
    r = mort.rate_change_effect(mort.get(_mortgage()), 6.0)
    assert r["available"] and r["payment_then"] > r["payment_now"]


def test_the_home_has_one_value_wherever_it_is_read():
    with db.tx() as c:
        home = c.execute("INSERT INTO assets(name,kind,value,is_home) VALUES('Home','property',300000,1)").lastrowid
    _mortgage(property_asset_id=home, property_value=999999)
    bs = overall.balance_sheet()
    assert bs["own"]["Property"] == 300000                       # not 300,000 + 999,999
    assert mort.summarise(mort.all_mortgages()[0])["property_value"] == 300000


# ============================================================================ pensions and the retirement plan

def test_a_final_salary_pension_is_income_not_money_owned():
    pensions.add({"name": "NHS Pension", "kind": "db", "yearly": 12000, "normal_age": 67})
    bs = overall.balance_sheet()
    assert "Pensions" not in bs["own"] and bs["promised"][0]["yearly"] == 12000


def test_a_pension_needs_a_name_and_sensible_numbers():
    with pytest.raises(pensions.PensionError):
        pensions.add({"kind": "dc", "pot": 1000})
    with pytest.raises(pensions.PensionError):
        pensions.add({"name": "Pot", "kind": "dc", "pot": "lots"})


def test_a_plan_needs_the_basics_before_it_runs():
    out = retirement.analyse(full=False)
    assert out["ready"] is False and "your date of birth" in out["missing"]


def test_enough_money_lasts_and_too_little_says_when_it_runs_short():
    pid = add_platform(cash=0)
    with db.tx() as c:
        c.execute("UPDATE platforms SET cash=? WHERE id=?", (900000, pid))
    _basic_plan()
    assert retirement.analyse(full=False)["plan"]["lasts"] is True
    with db.tx() as c:
        c.execute("UPDATE platforms SET cash=? WHERE id=?", (20000, pid))
    out = retirement.analyse(full=True)
    assert out["plan"]["lasts"] is False and out["plan"]["runs_out_at"] < 95
    assert out["levers"], "a plan that falls short says what would fix it"


def test_a_final_salary_pension_taken_early_is_reduced():
    _basic_plan(stop_age=62)
    pensions.add({"name": "NHS", "kind": "db", "yearly": 10000, "normal_age": 67, "start_age": 62, "early_reduction": 5})
    rows = retirement.analyse(full=False)["plan"]["rows"]
    paying = [r["db"] for r in rows if r["db"]]
    assert paying[0] == pytest.approx(7500, abs=1)               # five years early at 5% a year


def test_the_state_pension_starts_part_way_through_its_first_year():
    _basic_plan(dob=_years_ago(60.5), stop_age=60.5)              # born in 1966: State Pension at 67
    retirement.save({"state_pension": {"weekly": 200}})
    rows = retirement.analyse(full=False)["plan"]["rows"]
    first = next(r for r in rows if r["state"])
    assert 0 < first["state"] < 200 * 52                          # the half-year after 67
    assert rows[rows.index(first) + 1]["state"] == pytest.approx(200 * 52)


def test_a_uk_state_pension_paid_in_south_africa_is_frozen():
    _basic_plan(dob=_years_ago(68), stop_age=68)
    retirement.save({"state_pension": {"weekly": 200}, "retire_country": "za"})
    rows = retirement.analyse(full=False)["plan"]["rows"]
    assert rows[5]["state"] < rows[1]["state"]                     # less each year in today's money
    retirement.save({"retire_country": "uk"})
    rows = retirement.analyse(full=False)["plan"]["rows"]
    assert rows[5]["state"] == pytest.approx(rows[1]["state"])


def test_after_a_fixed_deal_the_plan_assumes_a_new_one_not_the_standard_rate():
    _basic_plan()
    end = (dt.date.today() + dt.timedelta(days=90)).isoformat()
    _mortgage(fixed_until=end, revert_rate=9.0, rate=3.0, monthly_payment=474.21)
    s, data = retirement.settings(), retirement.gather()
    base = retirement.project(s, data)["rows"]
    svr = retirement.project(s, data, {"revert_rate": "svr"})["rows"]
    assert base[2]["mortgage"] < svr[2]["mortgage"]


def test_a_fixed_payment_weighs_less_each_year_in_todays_money():
    _basic_plan()
    _mortgage()
    rows = retirement.analyse(full=False)["plan"]["rows"]
    assert rows[1]["mortgage"] > rows[5]["mortgage"] > 0


def test_pensions_left_over_count_for_inheritance_tax_unless_left_to_a_spouse():
    pid = add_platform(cash=0)
    with db.tx() as c:
        c.execute("UPDATE platforms SET cash=? WHERE id=?", (2000000, pid))
    _basic_plan()
    out = retirement.analyse(full=False)["plan"]
    assert out["iht"]["tax"] > 0
    retirement.save({"partner": True})
    assert retirement.analyse(full=False)["plan"]["iht"]["tax"] == 0


def test_a_what_if_saves_nothing():
    _basic_plan()
    before = retirement.settings()
    retirement.project(before, retirement.gather(), {"stop_age": 70})
    assert retirement.settings()["stop_age"] == before["stop_age"]


# ============================================================================ the plan review

def test_answers_the_retirement_tab_uses_are_stored_once():
    builder.save_answers({"stop_age": 61, "sp_weekly": 210})
    s = retirement.settings()
    assert s["stop_age"] == 61 and s["state_pension"]["weekly"] == 210
    retirement.save({"stop_age": 63})
    assert builder.answers()["stop_age"] == 63


def test_the_apps_own_defaults_are_not_counted_as_answers():
    a = builder.answers()
    assert "nation" not in a and "plan_to" not in a and "emergency_months" not in a
    builder.save_answers({"nation": "england"})
    assert builder.answers()["nation"] == "england"


def test_risk_is_the_lower_of_willing_and_able_and_a_real_sale_counts_most():
    _basic_plan(dob=_years_ago(40), stop_age=60)
    s = retirement.settings()
    bold = builder.risk_profile({"fall": "buy", "experience": "long", "prefer": "growth", "work": "very"}, s, None)
    timid = builder.risk_profile({"fall": "sell", "experience": "new", "prefer": "steady"}, s, None)
    assert timid["growth"] < bold["growth"] and timid["growth"] == min(timid["willing"], timid["able"])
    sold = builder.risk_profile({"fall": "buy", "did": "sold", "experience": "long", "prefer": "growth"}, s, None)
    assert sold["willing"] < bold["willing"]


def test_a_draft_changes_nothing_until_it_is_used():
    sample.load()
    before = [(x["name"], x["target"]) for x in db.rows("SELECT name, target FROM sleeves ORDER BY id")]
    builder.save_answers({"fall": "worry", "experience": "few", "prefer": "balanced", "believe": ["gold"]})
    d = builder.draft()
    assert sum(x["target"] for x in d["plan"]["sleeves"]) == pytest.approx(100)
    assert [(x["name"], x["target"]) for x in db.rows("SELECT name, target FROM sleeves ORDER BY id")] == before
    builder.apply({"sleeves": True, "rules": True, "watch": True, "plans": True})
    after = [x["name"] for x in db.rows("SELECT name FROM sleeves")]
    assert "Global core index" in after and themes.watch()["legacy"] is False


def test_the_written_plan_and_review_pack_are_made_without_errors():
    sample.load()
    w = builder.written_plan()
    assert w["sections"] and all(s["title"] for s in w["sections"])
    pack = builder.review_pack()
    assert pack.startswith("# Review pack") and "Not financial advice" in pack


def test_titles_keep_their_capitals_inside_a_sentence():
    assert themes.lower_first("The AI trade") == "the AI trade"
    assert themes.lower_first("UK companies") == "UK companies"
    assert themes.lower_first("Gold") == "gold"


# ============================================================================ the X-Ray

def test_the_xray_sees_through_a_world_fund():
    pid = add_platform()
    add_position(pid, "VWRP", "LSE", qty=100, broker_value=10000.0, valued_at=db.now())
    x = xray.run()
    ai = next(t for t in x["themes"] if t["theme"] == "ai")
    assert ai["pct"] == pytest.approx(0.206, abs=0.01)
    assert any(b["company"] for b in x["biggest_companies"])


# ============================================================================ files in, the folder, the reminder

def test_a_holdings_file_is_shown_before_it_goes_in_and_replaces_the_last_one():
    pid = add_platform("Hargreaves Lansdown ISA", "other")
    rep = inv.analyse(inv.sample_holdings_csv(), "hl-holdings.csv")
    assert rep["kind"] == "holdings" and rep["rows"] == 3 and rep["suggested_platform"] == pid
    assert not db.scalar("SELECT COUNT(*) FROM positions", (), 0)          # analysing writes nothing
    inv.commit(rep["token"], pid)
    assert db.scalar("SELECT COUNT(*) FROM positions WHERE platform_id=?", (pid,)) == 3
    rep2 = inv.analyse(inv.sample_holdings_csv(), "hl-holdings.csv")
    inv.commit(rep2["token"], pid)
    assert db.scalar("SELECT COUNT(*) FROM positions WHERE platform_id=?", (pid,)) == 3


def test_the_statements_folder_imports_what_it_can_place_and_leaves_the_rest(tmp_path):
    folder = tmp_path / "statements"
    config.settings.update({"statements_folder": str(folder)})
    pid = add_platform("Hargreaves Lansdown ISA", "other")
    inbox.folder()
    (folder / "hargreaves holdings.csv").write_bytes(inv.sample_holdings_csv())
    (folder / "mystery.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    out = inbox.import_waiting()
    assert [d["file"] for d in out["done"]] == ["hargreaves holdings.csv"]
    assert [x["file"] for x in out["left"]] == ["mystery.csv"]
    assert (folder / "mystery.csv").exists() and not (folder / "hargreaves holdings.csv").exists()
    assert db.scalar("SELECT COUNT(*) FROM positions WHERE platform_id=?", (pid,)) == 3
    # the same file again, renamed: recognised by its contents and filed, not imported twice
    (folder / "copy.csv").write_bytes(inv.sample_holdings_csv())
    again = inbox.import_waiting()
    assert [a["file"] for a in again["already"]] == ["copy.csv"]


def test_the_reminder_repeats_monthly_and_last_day_means_the_last_day():
    config.settings.update({"reminder_day": 31})
    ics = reminders.ics(dt.date(2026, 2, 3))
    assert "RRULE:FREQ=MONTHLY;BYMONTHDAY=-1" in ics and ics.endswith("\r\n")
    assert reminders.next_due(dt.date(2026, 2, 3)) == dt.date(2026, 2, 28)


# ============================================================================ money in other currencies

def test_rand_is_converted_and_never_counted_one_for_one():
    with db.tx() as c:
        c.execute("INSERT INTO platforms(name,provider,wrapper,cash,currency) VALUES('Capitec','bank','cash',10000,'ZAR')")
    bs = overall.balance_sheet()
    assert bs["unconverted"] == ["Capitec"] and "Cash" not in bs["own"]     # no rate yet: left out, and said so
    from .test_whiskers import price_series
    price_series("FX:ZAR", [23.26] * 5)                       # rand per pound
    from folio.market import store
    store._fx_cache.clear()
    bs = overall.balance_sheet()
    assert bs["own"]["Cash"] == pytest.approx(430, abs=1) and not bs["unconverted"]


# ============================================================================ the Budget tab

BANK_CSV = (b"Date,Description,Amount,Balance\n"
            b"01/10/2026,SALARY ACME LTD,2500.00,3100.00\n"
            b"03/10/2026,TESCO STORES 3021,-54.20,3045.80\n"
            b"05/10/2026,CORNER CAFE,-4.50,3041.30\n"
            b"06/10/2026,TRANSFER TO VANGUARD ISA,-300.00,2741.30\n")


def test_a_bank_statement_goes_in_once_and_is_sorted():
    config.settings.update({"budget_on": True})
    pid = add_platform("Barclays", "bank")
    with db.tx() as c:
        c.execute("UPDATE platforms SET provider='bank' WHERE id=?", (pid,))
    from folio.budget import categories, engine, ingest
    plat = db.one("SELECT * FROM platforms WHERE id=?", (pid,))
    first = ingest.import_statement(BANK_CSV, "barclays.csv", plat)
    again = ingest.import_statement(BANK_CSV, "barclays.csv", plat)
    assert first["added"] == 4 and again["added"] == 0
    tesco = db.one("SELECT t.*, c.name FROM txns t JOIN txn_categories c ON c.id=t.category_id WHERE description LIKE 'TESCO%'")
    assert tesco["name"] == "Groceries"
    assert db.scalar("SELECT cash FROM platforms WHERE id=?", (pid,)) == pytest.approx(2741.30)
    m = engine.month("2026-10")
    assert m["in"] == pytest.approx(2500) and m["saved"] == pytest.approx(300)
    cafe = db.one("SELECT id FROM txns WHERE description='CORNER CAFE'")
    coffee = db.scalar("SELECT id FROM txn_categories WHERE name='Coffee & snacks'")
    categories.set_category(cafe["id"], coffee, remember=True)
    assert db.scalar("SELECT COUNT(*) FROM txn_rules WHERE pattern='corner cafe'") == 1


def test_the_budget_counts_on_overall_only_when_it_is_switched_on():
    keys = lambda: [t["key"] for t in overall.summary()["tiles"]]  # noqa: E731
    assert "budget" not in keys()
    config.settings.update({"budget_on": True})
    assert "budget" in keys()


# ============================================================================ market data that stops

def test_ons_monthly_series_are_read_and_odd_rows_skipped():
    from folio.market import sources
    payload = {"description": {"cdid": "D7BT"}, "years": [{"date": "2025", "value": "138.2"}],
               "months": [{"date": "2026 JUL", "value": "141.0"}, {"date": "2026 AUG", "value": "141.4"},
                          {"date": "2026 SEP", "value": ""}, {"date": "rubbish", "value": "1"}]}
    assert sources.parse_ons_json(payload) == [("2026-07-01", 141.0), ("2026-08-01", 141.4)]
    with pytest.raises(sources.SourceError):
        sources.parse_ons_json({"years": []})


def test_a_light_whose_source_stopped_publishing_is_left_out_not_shown_as_current():
    from folio.engine import signals, themes
    from folio.market import store
    defn = next(d for d in themes.lights_for("inflation") if d["key"] == "uk_cpi")
    key = store.ref_key("UKCPI")

    def monthly(end: dt.date, n: int = 30):
        out, y, m = [], end.year, end.month
        for i in range(n):
            out.append((f"{y:04d}-{m:02d}-01", 100.0 + (n - i) * 0.3))
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        return sorted(out)

    store._save(key, {"points": monthly(dt.date(2025, 3, 1))}, "fred:GBRCPIALLMINMEI", replace=True)
    r = signals.reading(defn)
    assert r["level"] == "none" and "1 Mar 2025" in r["words"]
    # a figure from last month is what a monthly series normally looks like
    last_month = (dt.date.today().replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    store._save(key, {"points": monthly(last_month)}, "ons:test", replace=True)
    assert signals.reading(defn)["level"] in ("green", "amber", "red")


def test_valuations_typed_by_hand_keep_their_date_and_age():
    from folio.engine import valuations
    old = (dt.date.today() - dt.timedelta(days=200)).isoformat()
    v = valuations.save({"cape_us": {"value": "38.4", "on": old, "note": "multpl"}, "erp": {"value": "4.1%"}})
    assert v["cape_us"]["value"] == 38.4 and v["cape_us"]["old"] and not v["erp"]["old"]
    with pytest.raises(valuations.ValuationError):
        valuations.save({"fpe_us": {"value": "lots"}})
    with pytest.raises(valuations.ValuationError):
        valuations.save({"fpe_us": {"value": "21", "on": "2999-01-01"}})
    assert "erp" not in valuations.save({"erp": {"value": ""}})          # a blank clears it
    assert any("CAPE" in x and "now old" in x for x in valuations.lines())
    assert "Valuations, typed in by hand" in builder.review_pack()


def test_the_app_asks_before_moving_the_main_watch_and_never_when_it_was_picked():
    from folio.engine import portfolio, rules, themes
    pid = add_platform(cash=0.0)
    add_position(pid, "SGLN", exchange="LSE", name="iShares Physical Gold ETC", broker_value=6000.0, valued_at=db.now())
    add_position(pid, "IGLT", exchange="LSE", name="iShares Core UK Gilts UCITS ETF", broker_value=3000.0,
                 valued_at=db.now())
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    assert rules._watch_moved(pos, tot) is None                  # the original AI watch is left alone
    themes.set_watch("rates", ["rates", "gold"], None)
    db.set_meta("builder", {"answers": {"main_theme": "auto"}, "at": {}, "mood": {}})
    w = rules._watch_moved(pos, tot)
    assert w and w["level"] == "info" and "Make gold your main watch?" in w["detail"]
    db.set_meta("builder", {"answers": {"main_theme": "rates"}, "at": {}, "mood": {}})
    assert rules._watch_moved(pos, tot) is None                  # picked by name: theirs to keep


def test_the_mortgage_tile_says_whether_it_outlives_work():
    from folio.engine import overall
    retirement.save({"dob": _years_ago(55), "stop_age": 60})
    payoff = dt.date.today() + dt.timedelta(days=round(8 * 365.25))
    assert overall._clear_by(payoff).endswith("3 years after you stop")
    assert overall._clear_by(dt.date.today() + dt.timedelta(days=365)).endswith("before you stop")


def test_a_theme_outside_the_watch_that_turns_red_is_listed_but_never_moves_the_dial():
    from folio.engine import signals
    from folio.market import store
    from .test_whiskers import price_series
    price_series(store.ref_key("BRENT"), [100.0] * 260 + [100.0 - i for i in range(1, 46)], currency="USD")
    moved = signals.moved_outside()
    oil = next((x for x in moved if x["theme"] == "oil"), None)
    assert oil and any("fall" in r["title"].lower() for r in oil["reds"])
    assert all(x["theme"] != "ai" for x in moved)              # the original watch is watched
    assert "oil" not in signals.evaluate()["groups"]          # and the dial never counts it


def test_a_thesis_keeps_its_factor_grades_and_the_review_pack_shows_them():
    from folio.web import routes2
    pid = add_platform()
    iid = add_position(pid, "AZN", exchange="LSE", name="AstraZeneca", broker_value=5000.0, valued_at=db.now())
    routes2.api_save_thesis(None, {"iid": str(iid)}, {}, {"why": "Oncology pipeline", "breakers": "Pipeline fails",
                            "factors": {"valuation": "C-", "growth": "A", "momentum": "Z", "nonsense": "A"}})
    row = db.one("SELECT factors FROM theses WHERE instrument_id=?", (iid,))
    f = json.loads(row["factors"])
    assert f["valuation"] == "C-" and f["growth"] == "A" and "momentum" not in f and "nonsense" not in f and f["on"]
    assert "Factor grades" in builder.review_pack()
    routes2.api_save_thesis(None, {"iid": str(iid)}, {}, {"why": "Oncology pipeline", "factors": {}})
    assert db.one("SELECT factors FROM theses WHERE instrument_id=?", (iid,))["factors"] is None


# ============================================================================ the sample household

def test_the_sample_household_comes_out_completely_and_keeps_your_own_details():
    sample.load()
    assert db.scalar("SELECT COUNT(*) FROM pensions", (), 0) == 2 and mort.all_mortgages()
    sample.remove()
    for t in ("pensions", "mortgages", "assets", "platforms"):
        assert not db.scalar(f"SELECT COUNT(*) FROM {t}", (), 0), t  # nosec B608
    assert retirement.settings()["dob"] is None
    # somebody's own date of birth is never replaced by the sample's
    retirement.save({"dob": "1964-02-02"})
    sample.load()
    sample.remove()
    assert retirement.settings()["dob"] == "1964-02-02"


# ============================================================================ the local server

@pytest.fixture()
def server():
    from folio.web import server as srv
    httpd, port = srv.serve(port=srv._free_port(18866), block=False)
    yield port
    httpd.shutdown()


def _get(port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=60) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), ""


NEW_SCREENS = ("/api/overall", "/api/assets", "/api/mortgages", "/api/pensions", "/api/retirement",
               "/api/builder", "/api/builder/draft", "/api/builder/written", "/api/xray", "/api/watch",
               "/api/institutions?q=hargreaves", "/api/inbox", "/api/reminder")


def test_every_new_screen_answers_on_an_empty_copy(server):
    for path in NEW_SCREENS:
        status, body, ctype = _get(server, path)
        assert status == 200, (path, body[:200])
        assert "error" not in json.loads(body), path


def test_every_new_screen_answers_with_the_sample_household(server):
    sample.load()
    for path in NEW_SCREENS + ("/api/mortgages/1", "/api/instrument/1/themes"):
        status, body, _ = _get(server, path)
        assert status == 200, (path, body[:300])
    status, body, ctype = _get(server, "/api/builder/written.html")
    assert status == 200 and b"<h1>" in body and "text/html" in ctype


def test_a_copy_for_a_phone_is_one_page_with_nothing_that_calls_out(server):
    sample.load()
    add_position(add_platform(name="<b>Odd & name</b>", cash=10.0), "ABC", name="<i>A fund</i>",
                 broker_value=1234.0, valued_at=db.now())
    from folio.engine import phonecopy
    page = phonecopy.build().decode("utf-8")
    assert page.startswith("<!doctype html>") and "A snapshot from" in page
    for part in ("Net worth", "How each part is doing", "Retirement", "Your investments", "Mortgage", "Pensions",
                 "Cash and savings", "Coming up"):
        assert f"<h2>{part}</h2>" in page, part
    assert "[[" not in page and "<script" not in page.lower() and "src=" not in page
    assert "http://" not in page and "https://" not in page
    assert "&lt;i&gt;A fund&lt;/i&gt;" in page and "<i>A fund</i>" not in page
    assert "R48,000" in page                     # rand shown as rand, with pounds beside it
    status, body, ctype = _get(server, "/api/export/phone")
    assert status == 200 and "text/html" in ctype and body.startswith(b"<!doctype html>")


def test_a_copy_for_a_phone_works_on_an_empty_copy():
    from folio.engine import phonecopy
    page = phonecopy.build().decode("utf-8")
    assert "Net worth" in page and "needs" in page          # the plan says what it still needs


def test_the_budget_answers_only_when_it_is_switched_on(server):
    assert _get(server, "/api/budget")[0] == 400
    config.settings.update({"budget_on": True})
    status, body, _ = _get(server, "/api/budget")
    assert status == 200 and "month" in json.loads(body)


def test_the_new_routes_never_use_error_for_anything_but_failure():
    from .test_whiskers import ROOT
    src = (ROOT / "folio" / "web" / "routes2.py").read_text(encoding="utf-8")
    assert '"error":' not in src


def test_a_built_app_carries_the_institution_catalogue_and_the_test_copy_keeps_apart():
    from .test_whiskers import ROOT
    spec = (ROOT / "build" / "whiskers.spec").read_text(encoding="utf-8")
    assert '"institutions/data"' in spec and "folio.web.routes2" in spec
    bat = (ROOT / "Try Whiskers 2.0 (test copy).bat").read_text(encoding="utf-8")
    assert 'WHISKERS_DATA_DIR=%LOCALAPPDATA%\\Whiskers 2.0 test' in bat
