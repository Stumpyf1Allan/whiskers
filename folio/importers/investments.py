"""Investment files, whatever platform they came from.

Three kinds arrive:

* **Activity** — every trade, dividend and top-up. Freetrade's export (read by its own
  importer, which knows its quirks) and Trading 212's CSV export.
* **Holdings** — what is held today and what it is worth: the file Hargreaves Lansdown,
  AJ Bell, interactive investor and Vanguard let you download. A snapshot has no history,
  so it sets each holding's share count, cost and value as of the file's date, and
  replaces the previous snapshot for that platform rather than adding to it.
* **Bank statements** are recognised and turned away kindly: Whiskers keeps a bank
  account's balance, not its transactions, so the screen says to type the balance in.

Nothing is guessed silently. Every file is analysed first and shown — what it is, which
columns hold what, the rows it found, the platform it will go to — and only committed
when somebody says so (or, in the statements folder, when the layout is one the app
knows *and* the filename names the platform).
"""

from __future__ import annotations

import datetime as dt
import io
import json
import pathlib
import re
import secrets
import tempfile
import time

from .. import config, db
from ..brokers import freetrade, symbols, trading212
from .readers import Table, parse_amount, parse_date, parse_text, read_csv_bytes, read_ofx, read_qif

COLUMN_WORDS = {
    "quantity": ["units held", "no. of shares", "units", "quantity", "qty", "holding", "shares", "no of units"],
    "value": ["value (£)", "value £", "market value", "current value", "valuation", "total value", "value"],
    "cost": ["cost (£)", "book cost", "total cost", "purchase cost", "cost"],
    "price": ["price (pence)", "price (p)", "last price", "current price", "unit price", "price"],
    "symbol": ["code", "epic", "tidm", "ticker", "symbol", "sedol"],
    "isin": ["isin"],
    "name": ["stock", "investment name", "investment", "fund name", "fund", "security", "instrument",
             "holding name", "name", "description"],
}
PROFILE_LABELS = {"hargreaves_lansdown": "Hargreaves Lansdown", "aj_bell": "AJ Bell",
                  "interactive_investor": "interactive investor", "vanguard": "Vanguard Investor"}


class ImportError_(ValueError):
    pass


# ---------------------------------------------------------------------------- reading

def _uploads() -> pathlib.Path:
    p = config.data_dir() / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - 2 * 86400
    for f in p.glob("*.upload"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass
    return p


def stash(raw: bytes, filename: str) -> str:
    token = secrets.token_hex(12)
    (_uploads() / f"{token}.upload").write_bytes(raw)
    (_uploads() / f"{token}.name").write_text(filename[:200], encoding="utf-8")
    return token


def unstash(token: str) -> tuple[bytes, str]:
    if not re.fullmatch(r"[0-9a-f]{24}", token or ""):
        raise ImportError_("That upload has expired. Drop the file in again.")
    f = _uploads() / f"{token}.upload"
    if not f.exists():
        raise ImportError_("That upload has expired. Drop the file in again.")
    name = (_uploads() / f"{token}.name")
    return f.read_bytes(), (name.read_text(encoding="utf-8") if name.exists() else "file")


def read_table(raw: bytes, filename: str) -> Table:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm", ".xltx")) or raw[:2] == b"PK":
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as t:
            t.write(raw)
            tmp = pathlib.Path(t.name)
        try:
            from .readers import read_excel
            return read_excel(tmp)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
    if name.endswith(".pdf") or raw[:5] == b"%PDF-":
        try:
            from .pdfstatement import read_pdf
        except Exception:
            raise ImportError_("Reading PDFs needs an extra part this copy doesn't have. "
                               "Download a CSV or Excel file instead.") from None
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as t:
            t.write(raw)
            tmp = pathlib.Path(t.name)
        try:
            return read_pdf(tmp, filename)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
    head = raw[:400].lstrip().upper()
    if name.endswith((".ofx", ".qfx")) or b"OFXHEADER" in head or b"<OFX>" in head:
        return read_ofx(raw, filename)
    if name.endswith(".qif") or head.startswith(b"!TYPE"):
        return read_qif(raw, filename)
    return read_csv_bytes(raw, filename)


def _norm(h: str) -> str:
    return re.sub(r"\s+", " ", (h or "").strip().lower())


def find_columns(header: list[str]) -> dict[str, int]:
    """Which column holds what, by its heading. Longer, more specific words win."""
    norm = [_norm(h) for h in header]
    out: dict[str, int] = {}
    taken: set[int] = set()
    for field in ("isin", "quantity", "value", "cost", "price", "symbol", "name"):
        best = None
        for word in COLUMN_WORDS[field]:
            for i, h in enumerate(norm):
                if i in taken or not h:
                    continue
                if h == word or (len(word) > 3 and word in h):
                    if field == "value" and ("change" in h or "gain" in h or "loss" in h or "%" in h):
                        continue
                    if field == "cost" and ("%" in h or "gain" in h):
                        continue
                    if field == "price" and ("change" in h or "%" in h):
                        continue
                    best = i
                    break
            if best is not None:
                break
        if best is not None:
            out[field] = best
            taken.add(best)
    return out


def _is_t212(header: list[str]) -> bool:
    h = {_norm(x) for x in header}
    return "action" in h and "time" in h and bool(h & {"no. of shares", "ticker", "isin"})


def _filename_date(filename: str) -> str | None:
    m = re.search(r"(20\d\d)[-_.]?(0[1-9]|1[0-2])[-_.]?([0-3]\d)", filename or "")
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None
    return None


def _guess_profile(header: list[str], filename: str) -> str | None:
    h = " | ".join(_norm(x) for x in header)
    f = (filename or "").lower()
    if "units held" in h or "price (pence)" in h or "hargreaves" in f or re.search(r"\bhl\b", f):
        return "hargreaves_lansdown"
    if "ajbell" in f.replace(" ", "") or "book cost" in h and "epic" in h:
        return "aj_bell"
    if "interactive" in f or ("market value" in h and "book cost" in h):
        return "interactive_investor"
    if "vanguard" in f:
        return "vanguard"
    return None


def holdings_rows(table: Table, cols: dict[str, int], pence: bool | None = None) -> tuple[list[dict], float | None, list[str]]:
    """Rows a holdings file describes, the cash line if there is one, and any warnings."""
    out, cash, warn = [], None, []
    price_hdr = _norm(table.header[cols["price"]]) if "price" in cols else ""
    in_pence = pence if pence is not None else ("pence" in price_hdr or "(p)" in price_hdr)
    for r in table.rows:
        def cell(f):
            i = cols.get(f)
            return r[i] if (i is not None and i < len(r)) else None
        name = parse_text(cell("name"))
        sym = parse_text(cell("symbol")).upper()
        isin = parse_text(cell("isin")).upper()
        qty = parse_amount(cell("quantity"))
        value = parse_amount(cell("value"))
        cost = parse_amount(cell("cost"))
        price = parse_amount(cell("price"))
        label = (name or sym or "").lower()
        if not label and not isin:
            continue
        if re.match(r"^(total|sub ?total|grand total|portfolio total)", label):
            continue
        if re.match(r"^(cash|uninvested cash|cash balance|available cash)", label) and value is not None:
            cash = (cash or 0.0) + value
            continue
        if value is None and qty is not None and price is not None:
            value = qty * (price / 100 if in_pence else price)
        if qty is None and value is None:
            continue
        if qty is None:
            warn.append(f"{name or sym}: no number of units, so it is recorded by value only.")
        if isin and not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin):
            isin = ""
        out.append({"name": name or sym or isin, "symbol": sym if re.fullmatch(r"[A-Z0-9.\-]{1,12}", sym or "") else "",
                    "isin": isin or None, "quantity": qty, "value": value, "cost": cost,
                    "price": (price / 100 if in_pence else price) if price is not None else None})
    return out, cash, warn


def analyse(raw: bytes, filename: str) -> dict:
    """What a file is and what would be imported from it. Nothing is written."""
    token = stash(raw, filename)
    rep = {"token": token, "filename": filename, "kind": None, "label": None, "rows": 0,
           "preview": [], "columns": {}, "header": [], "warnings": [], "as_of": _filename_date(filename),
           "suggested_platform": None}
    try:
        rows = freetrade.read_rows(raw)
        if rows:
            days = [freetrade.uk_date(r.get("timestamp") or "") for r in rows]
            days = [d for d in days if d]
            rep.update(kind="freetrade", label="Freetrade activity export", rows=len(rows),
                       first=min(days) if days else None, last=max(days) if days else None,
                       preview=[{"date": freetrade.uk_date(r.get("timestamp") or ""), "type": r.get("type"),
                                 "title": r.get("title"), "amount": r.get("totalamount")} for r in rows[:12]])
            rep["suggested_platform"] = _suggest_platform(filename, "freetrade")
            return rep
    except freetrade.NotFreetrade:
        pass
    except Exception as e:  # nosec B110  # not Freetrade's layout: carry on with the other readers
        db.log("import.freetrade-check", str(e))
    try:
        table = read_table(raw, filename)
    except ImportError_:
        raise
    except Exception as e:
        raise ImportError_(f"That file couldn't be read as a spreadsheet or statement ({e}).") from None
    rep["header"] = table.header
    if not table.header or not table.rows:
        raise ImportError_("No rows found in that file.")
    if _is_t212(table.header):
        rep.update(kind="trading212", label="Trading 212 export", rows=len(table.rows),
                   preview=[dict(zip(table.header, r)) for r in table.rows[:12]])
        rep["suggested_platform"] = _suggest_platform(filename, "trading212")
        return rep
    cols = find_columns(table.header)
    if ("quantity" in cols or "value" in cols) and ("name" in cols or "symbol" in cols or "isin" in cols):
        hold, cash, warn = holdings_rows(table, cols)
        if hold:
            prof = _guess_profile(table.header, filename)
            rep.update(kind="holdings", profile=prof,
                       label=f"{PROFILE_LABELS.get(prof, 'A platform')}: holdings and values",
                       rows=len(hold), columns={k: table.header[v] for k, v in cols.items()},
                       preview=hold[:15], cash=cash, warnings=warn,
                       total=sum(h["value"] or 0 for h in hold) + (cash or 0))
            rep["suggested_platform"] = _suggest_platform(filename, None, prof)
            return rep
    lower = [_norm(h) for h in table.header]
    if any("date" in h for h in lower) and any(w in " ".join(lower) for w in ("amount", "debit", "credit", "paid", "money")):
        rep.update(kind="bank", label="A bank statement", rows=len(table.rows),
                   preview=[dict(zip(table.header, r)) for r in table.rows[:8]])
        rep["warnings"].append("This looks like a bank statement. Whiskers keeps a bank account's balance "
                               "rather than its transactions: type the balance in under Settings, Cash and "
                               "cards.")
        return rep
    raise ImportError_("That doesn't look like an investment file this app knows. It needs a column of "
                       "holdings (names, tickers or ISINs) and their units or values.")


PROFILE_WORDS = {"hargreaves_lansdown": {"hargreaves", "lansdown", "hl"}, "aj_bell": {"aj", "bell", "ajbell"},
                 "interactive_investor": {"interactive", "investor", "ii"}, "vanguard": {"vanguard"},
                 "freetrade": {"freetrade"}, "trading212": {"trading", "212", "t212", "trading212"}}


def _platform_words(p: dict) -> set[str]:
    words = _tokens(p["name"])
    inst = p.get("institution")
    if inst:
        try:
            from ..institutions import registry
            i = registry.get(inst) or {}
            for a in [i.get("name", "")] + list(i.get("aka") or []):
                words |= _tokens(a)
        except Exception:  # nosec B110  # the catalogue only adds aliases; matching works without it
            pass
    return words


def _suggest_platform(filename: str, provider: str | None, profile: str | None = None) -> int | None:
    plats = db.rows("SELECT id, name, provider, institution FROM platforms WHERE provider NOT IN ('card')")
    if provider:
        mine = [p for p in plats if p["provider"] == provider]
        if len(mine) == 1:
            return mine[0]["id"]
    hit = match_platform(filename, plats)
    if hit:
        return hit["id"]
    want = PROFILE_WORDS.get(profile or provider or "")
    if want:
        hits = [p for p in plats if _platform_words(p) & want]
        if len(hits) == 1:
            return hits[0]["id"]
    return None


NOISE = {"statement", "statements", "export", "exports", "download", "activity", "transactions", "history",
         "holdings", "portfolio", "valuation", "report", "account", "accounts", "csv", "xlsx", "pdf", "the",
         "and", "my", "isa", "sipp", "gia", "stocks", "shares", "data", "file", "copy", "new"}


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(t) > 1 and t not in NOISE
            and not t.isdigit()}


def match_platform(filename: str, plats: list[dict]) -> dict | None:
    """The one platform a filename names distinctively, or None. Two candidates is no answer."""
    words = _tokens(filename)
    hits = [p for p in plats if _platform_words(p) & words]
    return hits[0] if len(hits) == 1 else None


# ---------------------------------------------------------------------------- committing

def commit(token: str, platform_id: int, as_of: str | None = None, columns: dict | None = None) -> dict:
    raw, filename = unstash(token)
    if platform_id in (None, ""):
        raise ImportError_("Choose which platform this file belongs to.")
    plat = db.one("SELECT * FROM platforms WHERE id=?", (int(platform_id),))
    if not plat:
        raise ImportError_("Choose which platform this file belongs to.")
    rep = analyse(raw, filename)
    kind = rep["kind"]
    if kind == "freetrade":
        out = freetrade.import_csv(plat["id"], raw)
        out["cash_estimate"] = freetrade.cash_estimate(plat["id"])
    elif kind == "trading212":
        if trading212.credentials(plat["id"]):
            raise ImportError_(f"{plat['name']} updates itself from Trading 212, so its file isn't needed "
                               "(importing it as well would count every trade twice).")
        out = import_t212(plat["id"], read_table(raw, filename))
    elif kind == "holdings":
        table = read_table(raw, filename)
        cols = find_columns(table.header)
        if columns:
            for field, heading in columns.items():
                if heading in table.header:
                    cols[field] = table.header.index(heading)
        out = apply_holdings(plat["id"], table, cols, as_of or rep.get("as_of") or db.today())
    elif kind == "bank":
        raise ImportError_("Whiskers keeps a bank account's balance, not its transactions: type the balance "
                           "in under Settings, Cash and cards.")
    else:
        raise ImportError_("That file isn't one this app can import.")
    db.set_meta("last_import", db.now())
    out["kind"] = kind
    out["platform"] = plat["name"]
    return out


def apply_holdings(platform_id: int, table: Table, cols: dict[str, int], as_of: str) -> dict:
    """Set the platform's holdings to what the file says, as of its date."""
    hold, cash, warn = holdings_rows(table, cols)
    if not hold:
        raise ImportError_("No holdings found in that file.")
    stamp = f"{as_of[:10]} 16:30:00"
    seen = []
    with db.tx() as c:
        for h in hold:
            sym = h["symbol"] or ""
            # A London ticker is up to four or five letters; a seven-character SEDOL is a fund's
            # code, with no price feed behind it, so its value comes from the file.
            ticker = bool(sym) and bool(re.fullmatch(r"[A-Z][A-Z0-9]{0,4}\.?", sym))
            ident = sym if ticker else (h["isin"] or sym or h["name"][:12].upper())
            iid = symbols.upsert_instrument(c, ident, "LSE" if ticker else None, h["name"], h["isin"], "GBP")
            if not ticker:
                c.execute("UPDATE instruments SET market_symbol=NULL WHERE id=?", (iid,))
            qty = h["quantity"] if h["quantity"] is not None else 1.0
            value = h["value"]
            c.execute("INSERT INTO positions(platform_id,instrument_id,quantity,cost,broker_value,broker_price,"
                      "broker_ccy,valued_at,source,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) "
                      "ON CONFLICT(platform_id,instrument_id) DO UPDATE SET quantity=excluded.quantity,"
                      " cost=COALESCE(excluded.cost, positions.cost), broker_value=excluded.broker_value,"
                      " broker_price=excluded.broker_price, broker_ccy='GBP', valued_at=excluded.valued_at,"
                      " source=excluded.source, updated_at=excluded.updated_at",
                      (platform_id, iid, qty, h["cost"], value, (value / qty) if (value is not None and qty) else None,
                       "GBP", stamp, "import", db.now()))
            seen.append(iid)
        gone = c.execute(f"SELECT instrument_id FROM positions WHERE platform_id=? AND source='import' "  # nosec B608  # placeholders only
                         f"AND instrument_id NOT IN ({','.join('?' * len(seen))})", (platform_id, *seen)).fetchall()
        for g in gone:
            c.execute("DELETE FROM positions WHERE platform_id=? AND instrument_id=? AND source='import'",
                      (platform_id, g[0]))
        if cash is not None:
            c.execute("UPDATE platforms SET cash=?, cash_as_of=?, cash_source='import' WHERE id=?",
                      (cash, stamp, platform_id))
        c.execute("UPDATE platforms SET last_sync=?, last_error=NULL, reported_total=?, reported_at=? WHERE id=?",
                  (db.now(), sum(h["value"] or 0 for h in hold) + (cash or 0), stamp, platform_id))
    return {"holdings": len(hold), "removed": len(gone), "cash": cash, "warnings": warn, "as_of": as_of[:10]}


T212_SIDES = {"buy": "BUY", "sell": "SELL"}


def import_t212(platform_id: int, table: Table) -> dict:
    """Trading 212's CSV export: trades, dividends, deposits, withdrawals and interest."""
    idx = {_norm(h): i for i, h in enumerate(table.header)}

    def get(r, *names):
        for n in names:
            i = idx.get(n)
            if i is not None and i < len(r) and r[i] not in (None, ""):
                return r[i]
        return None
    rep = {"rows": len(table.rows), "trades": 0, "dividends": 0, "cash": 0, "skipped": 0}
    with db.tx() as c:
        for r in table.rows:
            action = (get(r, "action") or "").strip().lower()
            day = parse_date(get(r, "time"))
            if not day:
                rep["skipped"] += 1
                continue
            total = parse_amount(get(r, "total", "total (gbp)"))
            ref = get(r, "id") or ""
            isin = (get(r, "isin") or "").strip().upper() or None
            ticker = (get(r, "ticker") or "").strip()
            side = next((v for k, v in T212_SIDES.items() if k in action), None)
            if side and (isin or ticker):
                qty = parse_amount(get(r, "no. of shares")) or 0.0
                ccy = (get(r, "currency (price / share)") or "").strip() or None
                ex = symbols.exchange_from(None, isin, ccy)
                iid = symbols.upsert_instrument(c, ticker, ex, get(r, "name"), isin, ccy)
                fees = sum(abs(parse_amount(get(r, k)) or 0.0) for k in
                           ("charge amount", "stamp duty reserve tax", "currency conversion fee",
                            "stamp duty", "transaction fee", "finra fee"))
                fp = db.fingerprint("t212csv", platform_id, ref or (day, isin, side, qty, total))
                rep["trades"] += c.execute(
                    "INSERT OR IGNORE INTO trades(platform_id,instrument_id,traded_on,side,quantity,price,price_ccy,"
                    "value_gbp,fees_gbp,ref,source,fp) VALUES(?,?,?,?,?,?,?,?,?,?,'csv',?)",
                    (platform_id, iid, day, side, qty, parse_amount(get(r, "price / share")), ccy,
                     abs(total or 0.0), fees, ref, fp)).rowcount
            elif "dividend" in action and (isin or ticker):
                ex = symbols.exchange_from(None, isin, None)
                iid = symbols.upsert_instrument(c, ticker, ex, get(r, "name"), isin, None)
                fp = db.fingerprint("t212csv", platform_id, "div", ref or (day, isin, total))
                rep["dividends"] += c.execute(
                    "INSERT OR IGNORE INTO dividends(platform_id,instrument_id,paid_on,amount_gbp,withheld_gbp,ref,"
                    "source,fp) VALUES(?,?,?,?,?,?,'csv',?)",
                    (platform_id, iid, day, total or 0.0, abs(parse_amount(get(r, "withholding tax")) or 0.0),
                     ref, fp)).rowcount
            elif action in ("deposit", "withdrawal") or "interest" in action:
                kind = "DEPOSIT" if action == "deposit" else "WITHDRAWAL" if action == "withdrawal" else "INTEREST"
                amt = abs(total or 0.0) * (-1 if kind == "WITHDRAWAL" else 1)
                fp = db.fingerprint("t212csv", platform_id, kind, ref or (get(r, "time"), amt))
                rep["cash"] += c.execute(
                    "INSERT OR IGNORE INTO cash_moves(platform_id,happened_on,kind,amount_gbp,ref,source,fp) "
                    "VALUES(?,?,?,?,?,'csv',?)", (platform_id, day, kind, amt, ref, fp)).rowcount
            else:
                rep["skipped"] += 1
        c.execute("UPDATE platforms SET last_sync=?, last_error=NULL WHERE id=?", (db.now(), platform_id))
    rep["positions"] = freetrade.rebuild_positions(platform_id)
    return rep


def sample_holdings_csv() -> bytes:
    """A holdings file in the shape Hargreaves Lansdown uses, for the tests and the tour."""
    out = io.StringIO()
    out.write("Account summary,,,,,,\n,,,,,,\n")
    out.write("Code,Stock,Units held,Price (pence),Value (£),Cost (£),Gain/loss (£)\n")
    out.write('VWRL,Vanguard FTSE All-World UCITS ETF,"1,200",11250,"13,500.00","11,000.00","2,500.00"\n')
    out.write("SGLN,iShares Physical Gold ETC,150,5520,8280.00,6900.00,1380.00\n")
    out.write('B3X7QG6,Royal London Short Duration Gilts M Acc,"8,000.123",104.5,"8,360.13","8,100.00",260.13\n')
    out.write("Cash,,,,1250.00,,\n")
    out.write('Total,,,,"31,390.13",,\n')
    return out.getvalue().encode("utf-8")


def _json(v) -> str:
    return json.dumps(v, default=str)
