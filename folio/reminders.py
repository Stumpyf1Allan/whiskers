"""The monthly reminder to fetch statements: a strip across the top of the app, and an
entry in the person's own calendar.

From Mittens & Pence, which explains at length why it is not an email: a program on
somebody's own computer has no mail server, and teaching people to type an email
password into an app is the wrong habit. Their calendar repeats the entry every month
and alerts them wherever they are, phone included.

The day may be 1 to 31; 29, 30 and 31 all mean the last day of the month, which the
calendar expresses exactly (BYMONTHDAY=-1) rather than skipping short months.
"""

from __future__ import annotations

import calendar
import datetime as dt
import uuid

from . import config, db

LAST_DAY = 29


def chosen_day() -> int:
    try:
        return max(1, min(31, int(config.settings.get("reminder_day") or 1)))
    except (TypeError, ValueError):
        return 1


def day_in(year: int, month: int, day: int | None = None) -> int:
    day = chosen_day() if day is None else day
    return min(day, calendar.monthrange(year, month)[1])


def next_due(after: dt.date | None = None) -> dt.date:
    today = after or dt.date.today()
    this = dt.date(today.year, today.month, day_in(today.year, today.month))
    if this >= today:
        return this
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return dt.date(year, month, day_in(year, month))


def _needs_files() -> list[str]:
    """Platforms that only update from a file: the ones a reminder is for. Known from the
    files already imported, or from the catalogue saying the platform's route is a file."""
    out = []
    for p in db.rows("SELECT id, name, provider, institution FROM platforms WHERE provider NOT IN ('card','bank','sample')"):
        if p["provider"] == "trading212":
            from .brokers import trading212
            if trading212.credentials(p["id"]):
                continue
        has_file = db.scalar("SELECT COUNT(*) FROM positions WHERE platform_id=? AND source IN ('csv','import')",
                             (p["id"],), 0)
        by_file = False
        if p.get("institution") and p["institution"] != "sample":
            try:
                from .institutions import registry
                by_file = registry.next_step(p["institution"])["route"] == "file"
            except Exception:  # nosec B110  # the catalogue only adds to what the files already say
                by_file = False
        if has_file or by_file or p["provider"] == "freetrade":
            out.append(p["name"])
    return out


def state(today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    on = bool(config.settings.get("reminder_on", True))
    due_on = dt.date(today.year, today.month, day_in(today.year, today.month))
    platforms = _needs_files()
    last = str(db.get_meta("last_import") or "")
    done = bool(last) and last[:10] >= due_on.isoformat()
    due = on and bool(platforms) and today >= due_on and not done
    dismissed = str(config.settings.get("reminder_dismissed") or "")
    prev = (due_on.replace(day=1) - dt.timedelta(days=1))
    return {"on": on, "day": chosen_day(), "day_means_last": chosen_day() >= LAST_DAY,
            "due_on": due_on.isoformat(), "next_due": next_due(today).isoformat(),
            "month": prev.strftime("%B %Y"), "platforms": platforms, "due": due, "done": done,
            "show_banner": bool(due and dismissed != due_on.isoformat())}


def dismiss(today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    config.settings.update({"reminder_dismissed": dt.date(today.year, today.month,
                                                          day_in(today.year, today.month)).isoformat()})
    return state(today)


def _fold(line: str) -> str:
    raw = line.encode("utf-8")
    if len(raw) <= 73:
        return line
    out, chunk = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > 73:
            out.append(chunk.decode("utf-8"))
            chunk = b""
        chunk += b
    out.append(chunk.decode("utf-8"))
    return "\r\n ".join(out)


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")


def ics(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    from . import inbox
    day = chosen_day()
    start = next_due(today)
    rule = "FREQ=MONTHLY;BYMONTHDAY=-1" if day >= LAST_DAY else f"FREQ=MONTHLY;BYMONTHDAY={day}"
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    title = "Download last month's statements"
    body = (f"Download last month's file from each platform {config.APP_NAME} can't update on its own, "
            f"drop them into the \"{inbox.folder(create=False).name}\" folder, then open {config.APP_NAME} "
            f"and press Refresh.")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{config.APP_FILE_NAME}//Statement reminder//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "BEGIN:VEVENT", f"UID:{uuid.uuid4()}@{config.APP_SLUG}",
             f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
             f"DTEND;VALUE=DATE:{start + dt.timedelta(days=1):%Y%m%d}", f"RRULE:{rule}",
             f"SUMMARY:{_esc(title)}", f"DESCRIPTION:{_esc(body)}", "TRANSP:TRANSPARENT",
             "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_esc(title)}", "TRIGGER:PT9H", "END:VALARM",
             "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(ln) for ln in lines) + "\r\n"
