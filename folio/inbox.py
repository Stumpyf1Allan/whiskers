"""A folder to drop downloaded statements into, emptied whenever Refresh is pressed.

Brought from Mittens & Pence with both of its gates. A file goes in unattended only when
the app recognises its layout (Freetrade's export, Trading 212's, a holdings file it can
read) **and** it can tell, without guessing, which platform the file belongs to: the
filename names one platform distinctively, or the layout belongs to a provider of which
there is exactly one. Anything that fails a gate stays exactly where it is and is listed
on the Import screen for a person to deal with. Imported files move into "Filed", so it
is plain what has already gone in. Nothing is ever deleted.

The content decides what is new, not the filename: a renamed copy of a file already
imported is recognised and filed without importing it twice (and the per-row
fingerprints would make a second import harmless anyway).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import sys

from . import config, db

FOLDER_NAME = "Statements to import"
FILED = "Filed"
SUFFIXES = {".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls", ".ofx", ".qfx", ".qif", ".pdf"}

README = """Drop your statements in here
============================

This folder is where {app} looks for anything new.

Every month, download the file from each platform that can't update itself
(Freetrade's activity export, or the holdings file from Hargreaves Lansdown,
AJ Bell, interactive investor or Vanguard) and put it in here.

Then open {app} and press Refresh. Whatever it recognises goes in, and the
file moves into the "{filed}" folder so you can see what has already been
read. Anything it can't place is left here and listed on the Import screen.
Nothing is ever deleted.

Leave the platform's own filename alone if you can: it usually names the
platform, which is how {app} knows where the file belongs.
"""


def _documents() -> pathlib.Path | None:
    home = pathlib.Path.home()
    for cand in (home / "Documents", home / "OneDrive" / "Documents", home):
        if cand.exists():
            return cand
    return None


def default_folder() -> pathlib.Path:
    if config.android():
        return config.data_dir() / FOLDER_NAME
    base = _documents() or config.data_dir()
    return base / f"{config.APP_NAME} - {FOLDER_NAME}"


def folder(create: bool = True) -> pathlib.Path:
    chosen = str(config.settings.get("statements_folder") or "").strip()
    p = pathlib.Path(chosen).expanduser() if chosen else default_folder()
    if create:
        try:
            p.mkdir(parents=True, exist_ok=True)
            readme = p / README_NAME
            if not readme.exists():
                readme.write_text(README.format(app=config.APP_NAME, filed=FILED), encoding="utf-8")
        except OSError:
            pass
    return p


def _seen() -> dict:
    return db.get_meta("inbox_seen", {}) or {}


def digest_of(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:32]


README_NAME = "Read me.txt"


def waiting() -> list[pathlib.Path]:
    """Files to read: never the folder's own Read me, nor the hidden and half-written files
    other programs leave about (Excel's "~$" lock files, a download's ".part")."""
    root = folder()
    try:
        return sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES
                      and p.name != README_NAME and not p.name.startswith((".", "~$")))
    except OSError:
        return []


def _file_away(path: pathlib.Path, when: dt.date) -> pathlib.Path:
    dest = folder() / FILED / f"{when:%Y-%m}"
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / path.name
    n = 1
    while target.exists():
        target = dest / f"{path.stem} ({n}){path.suffix}"
        n += 1
    shutil.move(str(path), str(target))
    return target


def import_waiting() -> dict:
    """Run on Refresh. Returns what went in, what was already in, and what was left."""
    from .importers import investments as inv
    done, already, left = [], [], []
    seen = _seen()
    today = dt.date.today()
    plats = db.rows("SELECT id, name, provider, institution FROM platforms WHERE provider NOT IN ('card')")
    for path in waiting():
        try:
            digest = digest_of(path)
        except OSError as e:
            left.append({"file": path.name, "why": f"Couldn't be read: {e}"})
            continue
        if digest in seen:
            try:
                _file_away(path, today)
            except OSError:
                pass
            already.append({"file": path.name, "when": seen[digest].get("at")})
            continue
        try:
            raw = path.read_bytes()
            rep = inv.analyse(raw, path.name)
        except Exception as e:
            left.append({"file": path.name, "why": str(e)})
            continue
        if rep["kind"] not in ("freetrade", "trading212", "holdings"):
            left.append({"file": path.name, "why": rep.get("warnings", [None])[0] if rep.get("warnings")
                         else "Not an investment file the app can read on its own. Use the Import screen."})
            continue
        pid = rep.get("suggested_platform")
        if not pid:
            left.append({"file": path.name, "why": f"{rep['label']}, but the filename doesn't say which platform "
                                                   "it belongs to. Import it from the Import screen, or rename it "
                                                   "to include the platform's name."})
            continue
        try:
            out = inv.commit(rep["token"], pid)
        except Exception as e:
            left.append({"file": path.name, "why": str(e)})
            continue
        name = next((p["name"] for p in plats if p["id"] == pid), "a platform")
        seen[digest] = {"at": db.now(), "file": path.name, "platform": name}
        try:
            _file_away(path, today)
        except OSError:
            pass
        done.append({"file": path.name, "platform": name, "kind": rep["kind"],
                     "summary": out})
    db.set_meta("inbox_seen", seen)
    state = {"at": db.now(), "done": done, "already": already, "left": left}
    db.set_meta("inbox_last", state)
    return state


def status() -> dict:
    p = folder(create=False)
    return {"folder": str(p), "exists": p.exists(), "waiting": [x.name for x in waiting()] if p.exists() else [],
            "last": db.get_meta("inbox_last"), "default": str(default_folder()),
            "chosen": bool(str(config.settings.get("statements_folder") or "").strip())}


def open_folder() -> dict:
    p = folder()
    if config.android():
        return {"opened": False, "folder": str(p)}
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(p))  # nosec B606  # our own folder, never a path from the page
        elif sys.platform == "darwin":
            import subprocess  # nosec B404
            subprocess.Popen(["open", str(p)])  # nosec B603 B607
        else:
            import subprocess  # nosec B404
            subprocess.Popen(["xdg-open", str(p)])  # nosec B603 B607
        return {"opened": True, "folder": str(p)}
    except Exception as e:
        return {"opened": False, "folder": str(p), "why": str(e)}


def _json(v) -> str:
    return json.dumps(v, default=str)
