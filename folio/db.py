"""The database: one SQLite file in the data folder.

A connection per operation rather than one shared connection. The server answers on
several threads and prices refresh on another, and SQLite in WAL mode handles that
well as long as nobody holds a connection open across threads. Opening one costs well
under a millisecond.

Two conventions carried over from Mittens & Pence:

* **Unknown is not zero.** A cash balance nobody has given us is NULL, a cost nobody
  knows is NULL, and the screens say "—" rather than £0.
* **Schema changes are recorded steps.** `ADDED_COLUMNS` is applied on every start and
  is idempotent, so a column added in a later version reaches databases that already
  exist, not just new installs. A fix that only reaches new installs fixes nobody's data.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import sqlite3
import threading

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS log(id INTEGER PRIMARY KEY, at TEXT, kind TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS vault(ref TEXT PRIMARY KEY, blob BLOB);

-- An account at a provider: "Freetrade ISA", "Trading 212 ISA".
CREATE TABLE IF NOT EXISTS platforms(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  provider TEXT NOT NULL DEFAULT 'other',      -- freetrade | trading212 | other | sample
  wrapper TEXT NOT NULL DEFAULT 'isa',         -- isa | gia | sipp | lisa
  flexible INTEGER NOT NULL DEFAULT 0,         -- flexible ISA: withdrawals can be replaced
  cash REAL,                                   -- NULL = nobody has told us
  cash_as_of TEXT,
  cash_source TEXT,                            -- api | estimate | manual
  limit_gbp REAL,                              -- FSCS threshold for this firm (NULL = default)
  reported_total REAL,                         -- what the broker itself says it is all worth
  reported_at TEXT,
  last_sync TEXT, last_error TEXT,
  sort INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sleeves(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  target REAL NOT NULL DEFAULT 0,              -- percent of the whole portfolio
  band REAL,                                   -- tolerance in points; NULL = the 5/25 rule
  ai_share REAL,                               -- default AI-linked share of holdings in it
  is_cash INTEGER NOT NULL DEFAULT 0,
  colour TEXT,
  sort INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS instruments(
  id INTEGER PRIMARY KEY,
  isin TEXT UNIQUE,
  symbol TEXT NOT NULL,                        -- as the broker writes it: PCGH, SN., BRK-B
  exchange TEXT,                               -- LSE | US | XETRA | AMS | ...
  name TEXT,
  currency TEXT,                               -- trading currency, exactly as reported
  market_symbol TEXT,                          -- what the price feed calls it: PCGH.L
  sleeve_id INTEGER REFERENCES sleeves(id) ON DELETE SET NULL,
  ai_share REAL,                               -- 0-100; NULL = use the sleeve's default
  company TEXT,                                -- groups share classes / duplicates: Alphabet
  theme TEXT,                                  -- groups a thesis held in several wrappers
  notes TEXT,
  created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_instruments_symbol ON instruments(symbol);

CREATE TABLE IF NOT EXISTS positions(
  platform_id INTEGER NOT NULL REFERENCES platforms(id) ON DELETE CASCADE,
  instrument_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
  quantity REAL NOT NULL,
  cost REAL,                                   -- in pounds; NULL = unknown
  broker_value REAL,                           -- in pounds, as the broker valued it
  broker_price REAL,                           -- per share, in `broker_ccy`
  broker_ccy TEXT,
  valued_at TEXT,
  source TEXT NOT NULL,                        -- api | csv | manual | sample
  updated_at TEXT,
  PRIMARY KEY(platform_id, instrument_id)
);

CREATE TABLE IF NOT EXISTS trades(
  id INTEGER PRIMARY KEY,
  platform_id INTEGER NOT NULL REFERENCES platforms(id) ON DELETE CASCADE,
  instrument_id INTEGER REFERENCES instruments(id) ON DELETE CASCADE,
  traded_on TEXT NOT NULL,
  side TEXT NOT NULL,                          -- BUY | SELL | TRANSFER_IN | TRANSFER_OUT | SPLIT
  quantity REAL NOT NULL,
  price REAL, price_ccy TEXT,
  value_gbp REAL, fees_gbp REAL,
  ref TEXT, source TEXT,
  fp TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS ix_trades_inst ON trades(instrument_id, traded_on);

CREATE TABLE IF NOT EXISTS dividends(
  id INTEGER PRIMARY KEY,
  platform_id INTEGER NOT NULL REFERENCES platforms(id) ON DELETE CASCADE,
  instrument_id INTEGER REFERENCES instruments(id) ON DELETE CASCADE,
  paid_on TEXT NOT NULL,
  amount_gbp REAL NOT NULL,
  withheld_gbp REAL,
  ref TEXT, source TEXT,
  fp TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS cash_moves(
  id INTEGER PRIMARY KEY,
  platform_id INTEGER NOT NULL REFERENCES platforms(id) ON DELETE CASCADE,
  happened_on TEXT NOT NULL,
  kind TEXT NOT NULL,                          -- DEPOSIT | WITHDRAWAL | INTEREST | FEE | TRANSFER
  amount_gbp REAL NOT NULL,                    -- signed: money in is positive
  ref TEXT, source TEXT,
  fp TEXT UNIQUE
);

-- Daily closes, in the series' own major currency (pence already turned into pounds).
CREATE TABLE IF NOT EXISTS series(key TEXT NOT NULL, d TEXT NOT NULL, v REAL NOT NULL,
                                  PRIMARY KEY(key, d)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS series_meta(
  key TEXT PRIMARY KEY,
  source TEXT, currency TEXT, name TEXT,
  live REAL, live_at TEXT,                     -- latest traded price, when the feed has one
  fetched_at TEXT, last_ok TEXT, last_error TEXT
);

-- "This fund holds 4.1% Alphabet" — for the rules that care about true exposure.
CREATE TABLE IF NOT EXISTS lookthrough(
  fund_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
  company TEXT NOT NULL,
  weight REAL NOT NULL,
  as_of TEXT,
  PRIMARY KEY(fund_id, company)
);

CREATE TABLE IF NOT EXISTS rules(
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,                          -- company_cap | ai_cap | theme_cap
  subject TEXT,                                -- company or theme name
  trigger_pct REAL NOT NULL,
  target_pct REAL,
  basis TEXT NOT NULL DEFAULT 'direct',        -- direct | true
  note TEXT,
  enabled INTEGER NOT NULL DEFAULT 1
);

-- What the person decided, in calm weather, they would do if a light went red.
CREATE TABLE IF NOT EXISTS plans(topic TEXT PRIMARY KEY, body TEXT, updated_at TEXT);

CREATE TABLE IF NOT EXISTS snapshots(
  d TEXT PRIMARY KEY, value REAL, cash REAL, cost REAL, detail TEXT);

-- ---------------------------------------------------------------- 1.1: the optional sections
-- Everything below is purely additive: a 1.0 copy opening this database ignores these
-- tables, so going back a version never breaks anything.

-- Things owned that are not investments or cash: the house, mostly. One figure per thing,
-- so a mortgage links to its house rather than keeping a second value that can disagree.
CREATE TABLE IF NOT EXISTS assets(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'property',       -- property | vehicle | other
  value REAL,                                  -- NULL = nobody has said
  currency TEXT DEFAULT 'GBP',
  valued_on TEXT,
  is_home INTEGER NOT NULL DEFAULT 0,          -- the main home (inheritance tax's residence band)
  notes TEXT,
  sort INTEGER DEFAULT 0
);

-- Brought from Mittens & Pence, standing on its own rather than hanging off a bank
-- account: the mortgage is the record.
CREATE TABLE IF NOT EXISTS mortgages(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  lender TEXT,
  currency TEXT DEFAULT 'GBP',
  original_amount REAL,
  started_on TEXT,
  term_months INTEGER,
  rate REAL,                                   -- annual %, e.g. 4.29
  rate_type TEXT DEFAULT 'fixed',              -- fixed | variable | tracker | discount
  fixed_until TEXT,
  revert_rate REAL,
  monthly_payment REAL,
  payment_day INTEGER,
  repayment_type TEXT DEFAULT 'repayment',     -- repayment | interest_only | part_and_part
  statement_balance REAL,
  statement_on TEXT,
  property_value REAL,
  property_valued_on TEXT,
  property_asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
  overpay_allowance REAL,                      -- % of the balance a year without a charge
  erc_note TEXT,                               -- early repayment charges, in her words
  split_payments INTEGER DEFAULT 1,
  payment_category TEXT,
  notes TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS mortgage_events(
  id INTEGER PRIMARY KEY,
  mortgage_id INTEGER NOT NULL REFERENCES mortgages(id) ON DELETE CASCADE,
  happened_on TEXT NOT NULL,
  kind TEXT NOT NULL,                          -- statement | overpayment | rate_change | valuation
  amount REAL, rate REAL, note TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_mortgage_events ON mortgage_events(mortgage_id, happened_on);

-- Every pension: a final-salary or career-average promise (db), a pot (dc), an annuity
-- already bought, a South African retirement annuity (sa_ra). The State Pension is not a
-- row here; it lives with the retirement settings, from the person's own forecast.
CREATE TABLE IF NOT EXISTS pensions(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'dc',             -- db | dc | annuity | sa_ra
  provider TEXT,
  currency TEXT DEFAULT 'GBP',
  pot REAL, pot_as_of TEXT,                    -- a pot's value from its latest statement
  yearly REAL, yearly_as_of TEXT,              -- a promise: pension a year, today's money
  start_age REAL,                              -- when it will be (or was) taken
  normal_age REAL,                             -- the scheme's own pension age
  early_reduction REAL,                        -- % less for each year taken early
  lump_sum REAL,                               -- an automatic lump sum, as some schemes pay
  commute_pct REAL,                            -- % of the pension swapped for cash
  commute_factor REAL,                         -- £ of cash per £1 a year given up (often 12)
  indexation TEXT DEFAULT 'cpi',               -- cpi | capped | fixed | none
  index_cap REAL,                              -- capped or fixed increases, % a year
  accruing INTEGER NOT NULL DEFAULT 0,         -- still building up while working
  accrual_yearly REAL,                         -- extra pension a year earned per year worked
  contrib_monthly REAL,                        -- a pot: you and your employer, a month
  growth REAL,                                 -- a pot: % a year above inflation; NULL = plan's
  charges REAL,                                -- a pot: % a year
  take TEXT DEFAULT 'drawdown',                -- a pot: drawdown | annuity | lump
  spouse_pct REAL,
  nominee TEXT,
  in_plan INTEGER NOT NULL DEFAULT 0,          -- a pot you invest yourself, in the sleeves
  notes TEXT,
  sort INTEGER DEFAULT 0,
  created_at TEXT
);

-- How much of each holding a market force can move: "this fund is 21% AI, 8% healthcare".
-- The AI share keeps living on instruments.ai_share, so a 1.x copy still reads it.
CREATE TABLE IF NOT EXISTS exposures(
  instrument_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
  theme TEXT NOT NULL,
  share REAL NOT NULL,                         -- 0-100
  source TEXT,                                 -- you | factsheet | default
  as_of TEXT,
  PRIMARY KEY(instrument_id, theme)
);

-- Why a single company is owned, and what would change the person's mind.
CREATE TABLE IF NOT EXISTS theses(
  instrument_id INTEGER PRIMARY KEY REFERENCES instruments(id) ON DELETE CASCADE,
  why TEXT, breakers TEXT, next_check TEXT, verdict TEXT, updated_at TEXT
);

-- A file's column layout, remembered so the second month is a single click.
CREATE TABLE IF NOT EXISTS import_mappings(
  id INTEGER PRIMARY KEY,
  signature TEXT NOT NULL UNIQUE,
  institution_id TEXT, kind TEXT, mapping_json TEXT NOT NULL, label TEXT,
  uses INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now'))
);

-- Net worth once a day, counting the sections that are switched on.
CREATE TABLE IF NOT EXISTS networth(
  d TEXT PRIMARY KEY, own REAL, owe REAL, net REAL, detail TEXT
);
"""

#: (table, column, definition) — applied on every start, idempotently.
ADDED_COLUMNS: list[tuple[str, str, str]] = [
    # 0.2: a bank or savings account whose cash sits outside the investment plan
    ("platforms", "in_plan", "INTEGER NOT NULL DEFAULT 1"),
    # 1.1: cash in rand (or anything else), and where the account is
    ("platforms", "currency", "TEXT DEFAULT 'GBP'"),
    ("platforms", "country", "TEXT"),
    ("platforms", "institution", "TEXT"),        # the catalogue's id, when picked from it
    ("platforms", "fee_year", "REAL"),           # what the platform charges, £ a year
    # 1.1: what a holding is, for the X-Ray
    ("instruments", "asset_class", "TEXT"),      # equity | bond | linker | cash | gold | commodity | property | crypto | mixed
    ("instruments", "duration", "REAL"),         # a bond fund's duration, years
    ("instruments", "ocf", "REAL"),              # a fund's yearly charge, %
    # 1.1: a thesis's factor grades, typed in during a review (JSON: grades and the date)
    ("theses", "factors", "TEXT"),
    # 1.1: why a sleeve is in the plan, in the person's own words, and the theme it rides on
    ("sleeves", "why", "TEXT"),
    ("sleeves", "theme", "TEXT"),
    ("sleeves", "breakers", "TEXT"),             # what would change the person's mind
    # 1.1: a parachute step names the sleeve it cuts and the sleeve the money goes to
    ("rules", "sleeve", "TEXT"),
    ("rules", "into_sleeve", "TEXT"),          # "into" is a word SQL keeps for itself
]

_init_lock = threading.Lock()
_initialised: set[str] = set()


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(config.db_path()), timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=8000")
    return con


def init():
    path = str(config.db_path())
    with _init_lock:
        if path in _initialised:
            return
        con = connect()
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(SCHEMA)
            _apply_added_columns(con)
        finally:
            con.close()
        _initialised.add(path)


def _apply_added_columns(con):
    for table, column, ddl in ADDED_COLUMNS:
        have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        if column not in have:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def forget_initialised():
    """Tests point the app at a fresh folder; the next call must build the schema."""
    with _init_lock:
        _initialised.clear()


@contextlib.contextmanager
def tx():
    init()
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        yield con
        con.execute("COMMIT")
    except BaseException:
        try:
            con.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        con.close()


def rows(sql: str, params=()) -> list[dict]:
    init()
    con = connect()
    try:
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


def one(sql: str, params=()) -> dict | None:
    got = rows(sql, params)
    return got[0] if got else None


def scalar(sql: str, params=(), default=None):
    init()
    con = connect()
    try:
        r = con.execute(sql, params).fetchone()
        return default if r is None or r[0] is None else r[0]
    finally:
        con.close()


def execute(sql: str, params=()) -> int:
    with tx() as c:
        return c.execute(sql, params).rowcount


def get_meta(key: str, default=None):
    v = scalar("SELECT value FROM meta WHERE key=?", (key,))
    if v is None:
        return default
    try:
        return json.loads(v)
    except ValueError:
        return v


def set_meta(key: str, value):
    with tx() as c:
        c.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, json.dumps(value, default=str)))


def log(kind: str, detail=None):
    try:
        with tx() as c:
            c.execute("INSERT INTO log(at,kind,detail) VALUES(?,?,?)",
                      (now(), kind, json.dumps(detail, default=str)[:4000]))
            c.execute("DELETE FROM log WHERE id < (SELECT MAX(id) - 2000 FROM log)")
    except sqlite3.Error:
        pass


def fingerprint(*parts) -> str:
    """A de-duplication key, not a security measure. It has to stay SHA-1: every stored
    trade, dividend and cash movement is matched on it, so a different hash would make the
    next import treat the whole history as new."""
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8"),
                        usedforsecurity=False).hexdigest()


def now() -> str:
    """Local wall-clock time, second precision, as text. Naive on purpose: everything
    stored here is compared with other naive local times, never with aware ones."""
    return dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")


def today() -> str:
    return dt.date.today().isoformat()
