"""A made-up household to explore the app with, before connecting anything real.

The investments live on two platforms whose provider is 'sample'. Since 2.0 the rest of
a household comes too: a home and its mortgage, two pensions, savings in pounds and a
little money in South Africa, and the basics of a retirement plan. Each of those is
marked as the sample's own (notes or institution 'sample'), so it can all be removed
without touching anything real. Loading twice changes nothing — Mittens & Pence once
built a second household when its sample was loaded twice.

The holdings are real, well-known tickers so that live prices and charts work; the
share counts, costs, deposits and dividends are invented. With no internet the sample
still shows figures, from the prices written below.
"""

from __future__ import annotations

import datetime as dt

from .. import db
from ..brokers import symbols
from . import allocation

TEMPLATE = [  # name, target %, AI share of holdings in it (None = set per holding), cash?
    ("Global core", 40, None, False), ("Technology & AI", 18, 100, False),
    ("Healthcare", 7, 0, False), ("Consumer", 5, 0, False), ("Financials", 5, 0, False),
    ("Industrials", 5, 0, False), ("Commodities & gold", 6, 0, False), ("Energy", 3, 0, False),
    ("Defence", 2, 0, False), ("Gilts", 5, 0, False), ("Cash", 4, 0, True),
]

#: platform, symbol, exchange, name, currency, shares, £ price, £ cost, AI share
HOLDINGS = [
    ("ft", "VWRP", "LSE", "Vanguard FTSE All-World (Acc)", "GBP", 150, 128.0, 19000, 20),
    ("ft", "EMIM", "LSE", "iShares Core MSCI EM IMI", "GBP", 215, 32.0, 7000, 15),
    ("ft", "GOOGL", "US", "Alphabet (Class A)", "USD", 33, 185.0, 3400, 100),
    ("ft", "DGE", "LSE", "Diageo", "GBX", 230, 20.5, 3700, 0),
    ("ft", "SGLN", "LSE", "iShares Physical Gold", "GBX", 115, 55.0, 6200, 0),
    ("ft", "AZN", "LSE", "AstraZeneca", "GBX", 45, 120.0, 4600, 0),
    ("t212", "VUAG", "LSE", "Vanguard S&P 500 (Acc)", "GBP", 150, 99.0, 13500, 32),
    ("t212", "NVDA", "US", "NVIDIA", "USD", 70, 135.0, 5200, 100),
    ("t212", "MSFT", "US", "Microsoft", "USD", 14, 330.0, 3900, 100),
    ("t212", "GOOGL", "US", "Alphabet (Class A)", "USD", 35, 185.0, 3700, 100),
    ("t212", "BRK-B", "US", "Berkshire Hathaway (Class B)", "USD", 17, 360.0, 4300, 0),
    ("t212", "BA", "LSE", "BAE Systems", "GBX", 120, 17.5, 2300, 0),
    ("t212", "SHEL", "LSE", "Shell", "GBX", 110, 26.0, 2700, 0),
    ("t212", "IGLT", "LSE", "iShares Core UK Gilts", "GBX", 560, 10.5, 6100, 0),
    ("t212", "XPO", "US", "XPO", "USD", 42, 105.0, 1600, 0),
]

PLATFORMS = {"ft": ("Sample — Freetrade ISA", 0, 2400.0),
             "t212": ("Sample — Trading 212 ISA", 1, 1800.0)}


SAMPLE_DOB = "1965-06-20"
#: The retirement basics, used only when nobody has entered their own.
RETIREMENT = {"dob": SAMPLE_DOB, "stop_age": 63, "spend_essential": 1700, "spend_extra": 700,
              "salary": 46000, "contrib_pct": 9.8, "contrib_method": "net_pay", "saving_monthly": 300,
              "nation": "england", "state_pension": {"weekly": 214.5, "years": 31, "gaps": 2}}


def _household(c) -> None:
    """The parts of the sample beyond investments, each marked as the sample's own."""
    home = c.execute("INSERT INTO assets(name,kind,value,currency,valued_on,is_home,notes,sort) "
                     "VALUES('Sample — Home','property',325000,'GBP',?,1,'sample',0)", (db.today(),)).lastrowid
    c.execute("INSERT INTO mortgages(name,lender,currency,original_amount,started_on,term_months,rate,rate_type,"
              "fixed_until,revert_rate,monthly_payment,repayment_type,statement_balance,statement_on,"
              "property_asset_id,overpay_allowance,notes,created_at) VALUES('Sample — Home mortgage','Nationwide',"
              "'GBP',180000,'2013-09-01',300,4.09,'fixed','2027-06-30',7.49,780,'repayment',96000,'2026-04-01',?,"
              "10,'sample',?)", (home, db.now()))
    c.execute("INSERT INTO pensions(name,kind,provider,currency,yearly,yearly_as_of,start_age,normal_age,"
              "early_reduction,commute_factor,indexation,accruing,accrual_yearly,nominee,notes,sort,created_at) "
              "VALUES('Sample — NHS Pension','db','NHS Business Services Authority','GBP',11800,'2026-03-31',63,67,"
              "5,12,'cpi',1,650,'',?,1,?)", ("sample", db.now()))
    c.execute("INSERT INTO pensions(name,kind,provider,currency,pot,pot_as_of,contrib_monthly,take,notes,sort,"
              "created_at) VALUES('Sample — Workplace pension pot','dc','Aviva','GBP',38000,'2026-04-05',180,"
              "'drawdown','sample',2,?)", (db.now(),))
    for name, ccy, country, cash, sort in (("Sample — Easy-access savings", "GBP", "GB", 14000, 20),
                                           ("Sample — Capitec savings", "ZAR", "ZA", 48000, 21)):
        c.execute("INSERT INTO platforms(name,provider,wrapper,flexible,in_plan,cash,cash_as_of,cash_source,"
                  "currency,country,institution,sort) VALUES(?, 'bank', 'cash', 0, 0, ?, ?, 'manual', ?, ?, "
                  "'sample', ?)", (name, cash, db.now(), ccy, country, sort))


def loaded() -> bool:
    return bool(db.scalar("SELECT COUNT(*) FROM platforms WHERE provider='sample'", (), 0))


def load() -> dict:
    if loaded():
        return {"created": False}
    made_sleeves = False
    if not db.scalar("SELECT COUNT(*) FROM sleeves", (), 0):
        with db.tx() as c:
            for i, (name, target, ai, is_cash) in enumerate(TEMPLATE):
                c.execute("INSERT INTO sleeves(name,target,ai_share,is_cash,sort) VALUES(?,?,?,?,?)",
                          (name, target, ai, 1 if is_cash else 0, i))
        made_sleeves = True
    sleeve_rows = db.rows("SELECT * FROM sleeves")
    yesterday = (dt.datetime.now() - dt.timedelta(days=1)).replace(microsecond=0).isoformat(sep=" ")
    today = dt.date.today()
    with db.tx() as c:
        ids = {}
        for key, (name, sort, cash) in PLATFORMS.items():
            cur = c.execute("INSERT INTO platforms(name,provider,wrapper,flexible,cash,cash_as_of,"
                            "cash_source,sort) VALUES(?, 'sample', 'isa', ?, ?, ?, 'manual', ?)",
                            (name, 1 if key == "t212" else 0, cash, yesterday, 10 + sort))
            ids[key] = cur.lastrowid
        for plat, sym, ex, name, ccy, qty, price, cost, ai in HOLDINGS:
            iid = symbols.upsert_instrument(c, sym, ex, name, None, ccy)
            c.execute("UPDATE instruments SET ai_share=COALESCE(ai_share, ?),"
                      " theme=CASE WHEN symbol='XPO' THEN COALESCE(theme,'Freight') ELSE theme END"
                      " WHERE id=?", (ai, iid))
            if not c.execute("SELECT sleeve_id FROM instruments WHERE id=?", (iid,)).fetchone()[0]:
                c.execute("UPDATE instruments SET sleeve_id=? WHERE id=?",
                          (allocation.suggest(name, sleeve_rows), iid))
            c.execute("INSERT INTO positions(platform_id,instrument_id,quantity,cost,broker_value,"
                      "valued_at,source,updated_at) VALUES(?,?,?,?,?,?,'sample',?)",
                      (ids[plat], iid, qty, cost, round(qty * price, 2), yesterday, yesterday))
            # A few purchases, so the charts have buy markers on them.
            for k in range(3):
                when = today - dt.timedelta(days=90 + 210 * k + len(sym) * 11)
                c.execute("INSERT OR IGNORE INTO trades(platform_id,instrument_id,traded_on,side,"
                          "quantity,value_gbp,source,fp) VALUES(?,?,?,?,?,?,'sample',?)",
                          (ids[plat], iid, when.isoformat(), "BUY", round(qty / 3, 4),
                           round(cost / 3, 2), db.fingerprint("sample", plat, sym, k)))
        # Paid in each tax year, and a little dividend income most months.
        for key, yearly in (("ft", 9000), ("t212", 7000)):
            for back in range(5, -1, -1):
                y = today.year - back
                for m, share in ((4, .4), (9, .3), (1, .3)):
                    d = dt.date(y if m >= 4 else y + 1, m, 10)
                    if d > today:
                        continue
                    c.execute("INSERT OR IGNORE INTO cash_moves(platform_id,happened_on,kind,"
                              "amount_gbp,source,fp) VALUES(?,?,'DEPOSIT',?,'sample',?)",
                              (ids[key], d.isoformat(), yearly * share,
                               db.fingerprint("sample-dep", key, d)))
        first = c.execute("SELECT id FROM instruments WHERE symbol='DGE'").fetchone()[0]
        second = c.execute("SELECT id FROM instruments WHERE symbol='SHEL'").fetchone()[0]
        for back in range(0, 24):
            d = (today.replace(day=15) - dt.timedelta(days=30 * back))
            for iid, base in ((first, 38.0), (second, 52.0)):
                if (back + iid) % 3 == 0:
                    c.execute("INSERT OR IGNORE INTO dividends(platform_id,instrument_id,paid_on,"
                              "amount_gbp,source,fp) VALUES(?,?,?,?,'sample',?)",
                              (ids["t212"] if iid == second else ids["ft"], iid, d.isoformat(),
                               base + back % 5, db.fingerprint("sample-div", iid, d)))
        if not c.execute("SELECT 1 FROM rules WHERE kind='company_cap' AND lower(subject)='alphabet'"
                         ).fetchone():
            c.execute("INSERT INTO rules(kind,subject,trigger_pct,target_pct,basis,note) VALUES"
                      "('company_cap','Alphabet',9.3,8,'direct','Sample rule: trim Alphabet back "
                      "to 8% when it passes 9.3%.')")
        _household(c)
    from . import retirement
    if not retirement.settings().get("dob"):
        retirement.save(RETIREMENT)
        db.set_meta("sample_retirement", SAMPLE_DOB)
    return {"created": True, "sleeves_created": made_sleeves}


def remove() -> dict:
    n = db.scalar("SELECT COUNT(*) FROM platforms WHERE provider='sample'", (), 0)
    with db.tx() as c:
        c.execute("DELETE FROM platforms WHERE provider='sample' OR institution='sample'")
        c.execute("DELETE FROM mortgages WHERE notes='sample'")
        c.execute("DELETE FROM pensions WHERE notes='sample'")
        c.execute("DELETE FROM assets WHERE notes='sample'")
        # Instruments nothing else refers to any more.
        c.execute("DELETE FROM instruments WHERE id NOT IN (SELECT instrument_id FROM positions)"
                  " AND id NOT IN (SELECT instrument_id FROM trades WHERE instrument_id IS NOT NULL)"
                  " AND id NOT IN (SELECT instrument_id FROM dividends WHERE instrument_id IS NOT NULL)")
        c.execute("DELETE FROM rules WHERE note LIKE 'Sample rule:%'")
    # The retirement basics go too, but only if they are still the sample's: somebody who
    # has typed in their own date of birth since keeps everything they entered.
    from . import retirement
    if db.get_meta("sample_retirement") and retirement.settings().get("dob") == db.get_meta("sample_retirement"):
        db.set_meta("retirement", {})
    db.set_meta("sample_retirement", None)
    return {"removed": n}
