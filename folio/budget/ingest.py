"""Bank statements into the Budget tab.

Mittens & Pence's readers do the reading (CSV, Excel, OFX, QIF and PDF statements); its
profiles know the big UK and South African banks' layouts, and anything else is mapped by
the column-guesser, which remembers the answer for next month. Every row is fingerprinted,
so importing a statement that overlaps last month's adds only what is new: most banks only
let you download a rolling window.
"""

from __future__ import annotations

from .. import db
from ..importers import mapping as mapping_mod
from ..importers import profiles as profiles_mod
from ..importers.investments import ImportError_, read_table
from ..importers.readers import parse_amount, parse_date, parse_text
from . import categories

CREDIT_WORDS = ("credit", "deposit", "received", "refund", "salary", "transfer in", "paid in", "money in")


def _sign_mode(prof: dict, mapping: dict, recs: list[dict]) -> str:
    sign = prof.get("sign", "auto")
    if sign != "auto":
        return sign
    if "debit" in mapping and "credit" in mapping:
        return "debit_credit"
    amounts = [parse_amount(r.get("amount")) for r in recs[:300]]
    amounts = [a for a in amounts if a is not None]
    if amounts and all(a >= 0 for a in amounts):
        return "type_signed" if "type" in mapping else "out_positive"
    return "signed"


def import_statement(raw: bytes, filename: str, plat: dict) -> dict:
    if plat.get("provider") != "bank":
        raise ImportError_("A bank statement goes into a bank account. Choose one, or add it first.")
    categories.seed()
    table = read_table(raw, filename)
    if not table.header or not table.rows:
        raise ImportError_("No rows found in that statement.")
    profile = profiles_mod.detect(table.header)
    remembered = mapping_mod.recall(table.signature())
    if remembered and remembered.get("kind") == "transactions":
        mapping = {k: int(v) for k, v in remembered["mapping"].items() if isinstance(v, (int, float, str)) and str(v).isdigit()}
    elif profile and profiles_mod.get(profile).get("kind") == "transactions":
        mapping = profiles_mod.resolve_columns(profile, table.header)
    else:
        mapping = mapping_mod.suggest(table, "transactions")["mapping"]
    if "date" not in mapping or not ({"amount"} <= set(mapping) or {"debit", "credit"} <= set(mapping)):
        raise ImportError_("Couldn't find the date and amount columns in that statement. "
                           "A CSV straight from the bank's website usually works best.")
    prof = profiles_mod.get(profile or "generic")
    recs = mapping_mod.apply_mapping(table, mapping)
    sign = _sign_mode(prof, mapping, recs)
    ccy = (plat.get("currency") or "GBP").upper()
    added = skipped = 0
    warnings: list[str] = []
    seen, dates = [], []
    last_balance = None
    rows = []
    for r in recs:
        on = parse_date(r.get("date"))
        if not on:
            skipped += 1
            continue
        desc = parse_text(r.get("description")) or parse_text(r.get("merchant")) or parse_text(r.get("type")) or "(no description)"
        if sign == "debit_credit":
            amount = (parse_amount(r.get("credit")) or 0.0) - abs(parse_amount(r.get("debit")) or 0.0)
        else:
            amount = parse_amount(r.get("amount"))
            if amount is None:
                d, cr = parse_amount(r.get("debit")), parse_amount(r.get("credit"))
                if d is not None or cr is not None:
                    amount = (cr or 0.0) - abs(d or 0.0)
            if amount is None:
                skipped += 1
                continue
            if sign == "out_positive":
                amount = -abs(amount)
            elif sign == "type_signed":
                t = parse_text(r.get("type")).lower()
                amount = abs(amount) if any(w in t for w in CREDIT_WORDS) else -abs(amount)
        bal = parse_amount(r.get("balance"))
        ref = parse_text(r.get("reference"))
        seen.append(amount)
        dates.append(on)
        if bal is not None and (last_balance is None or on >= last_balance[0]):
            last_balance = (on, bal)
        fp = db.fingerprint(plat["id"], on, desc[:80], round(amount, 2), ref or "", bal if bal is not None else "")
        rows.append((plat["id"], on, desc[:300], round(amount, 2), ccy, bal, fp, db.now()))
    with db.tx() as c:
        for row in rows:
            cur = c.execute("INSERT OR IGNORE INTO txns(platform_id,posted_on,description,amount,currency,"
                            "balance_after,fingerprint,created_at) VALUES(?,?,?,?,?,?,?,?)", row)
            if cur.rowcount:
                added += 1
            else:
                skipped += 1
        if last_balance is not None:
            # The statement's own closing balance is better than anything typed in earlier.
            c.execute("UPDATE platforms SET cash=?, cash_as_of=?, cash_source='statement' WHERE id=? "
                      "AND (cash_as_of IS NULL OR cash_as_of <= ?)",
                      (last_balance[1], f"{last_balance[0]} 23:59:00", plat["id"], f"{last_balance[0]} 23:59:00"))
    if seen and all(a <= 0 for a in seen):
        warnings.append("Every row was read as money out. If that looks wrong, the bank's file may "
                        "mark money in some other way: tell Allan via the Help button.")
    mapping_mod.remember(table.signature(), "transactions", mapping, plat.get("institution"), profile)
    done = categories.apply(only_uncategorised=True, platform_id=plat["id"])
    return {"rows": len(recs), "added": added, "skipped": skipped, "categorised": done,
            "first": min(dates) if dates else None, "last": max(dates) if dates else None,
            "warnings": warnings, "profile": profile}
