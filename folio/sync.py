"""Keeping all of someone's devices in step (1.4: two-way).

Every device both reads and writes one shared, encrypted file. A computer keeps it in a
folder the person chooses, normally inside OneDrive, which carries it to the cloud. A
phone is shown that file once, with Android's own file picker (which can open files in
OneDrive or Google Drive), and keeps permission to read and write it.

When Whiskers opens, comes back to the front or refreshes, it reads the file's header.
If another device has saved since, its copy is loaded (this device's database is backed
up first). A few seconds after anything is changed here, this device saves its copy over
the file, after checking nobody else saved meanwhile.

Clashes (both changed things before either saw the other's): the newest change wins and
becomes everyone's copy. The device whose changes lost keeps a dated backup of its own
database and shows a note naming it, so nothing is silently lost.

Refreshes (prices, Trading 212, Monzo, the daily value history) are not changes: each
device does its own, so a refresh never makes a device "newest" over real edits. On a
load, days of value history only this device has are kept.

Copies from 1.0 to 1.3 had a 'pc' that wrote and a 'phone' that read. Those states are
converted to the one 'shared' role; the file name is unchanged, so the phone's earlier
pick still works (it is asked to pick the file once more, to be allowed to write).

What travels: platforms, holdings, trades, dividends, cash movements, sleeves, rules,
look-through weights, the written plans, the daily value history, the plan's settings
kept in `meta`, and the ISA and protection limits.

What never travels: the vault (each device keeps its own Trading 212 and Monzo keys,
and the phone's are moved onto the matching platforms after a load), price history
(each device fetches its own), the log, and each device's own preferences (theme,
hidden amounts, updates).

The file lives in a cloud folder, so it is locked with a passphrase typed once on each
device: scrypt turns the passphrase into a key, AES-GCM encrypts, and the readable
header (format, when it was written) is authenticated too, so a changed byte anywhere
is refused rather than loaded.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import os
import pathlib
import platform as _platform
import secrets
import sqlite3
import threading
import time
import zlib

from . import android, config, db, security

FILE_NAME = "Whiskers phone copy.whiskers"
MAGIC = b"WHISKERS-SYNC\n"
FORMAT = 1
#: Parents before children, so every reference exists by the time it is inserted.
TABLES = ("meta", "sleeves", "platforms", "instruments", "positions", "trades", "dividends",
          "cash_moves", "lookthrough", "rules", "plans", "snapshots",
          # 1.1: the optional sections travel too
          "assets", "mortgages", "mortgage_events", "pensions", "exposures", "theses", "networth")
SETTINGS = ("isa_allowance", "fscs_limit", "user_name", "show_mortgage", "show_retirement",
            "show_news")
#: Vault entries named after a platform's id, which a load can change.
PLATFORM_KEYS = ("t212", "monzo")
MIN_PASSPHRASE = 8
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}
#: Seconds to wait after a change before writing, so a burst of edits is one write.
DEBOUNCE = 4.0
VAULT_REF = "sync"
#: Backups in the data folder: before an ordinary load, and before a clash was lost.
LOAD_BACKUP = "whiskers-before-load-"
CLASH_BACKUP = "whiskers-before-sync-"
KEEP_BACKUPS = 5
#: Daily history a refresh writes on each device; a load keeps the days only this one has.
HISTORY = ("snapshots", "networth")

log = logging.getLogger(__name__)
_lock = threading.Lock()          # one write or load at a time
_state_lock = threading.RLock()   # one change to sync.json at a time
_timer_lock = threading.Lock()
_timer: threading.Timer | None = None


class SyncError(Exception):
    pass


# ---------------------------------------------------------------------------- state

def _state_file() -> pathlib.Path:
    return config.data_dir() / "sync.json"


def _state() -> dict:
    try:
        got = json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return _upgrade(got) if isinstance(got, dict) else {}


def _upgrade(state: dict) -> dict:
    """Turn a 1.3 'pc' or 'phone' state into 'shared', and give the device its id."""
    old, changed = state.get("role"), False
    if old in ("pc", "phone"):
        state["role"] = "shared"
        # What this device last wrote (pc) or loaded (phone), in the form _tag gives it.
        state["loaded_tag"] = _tag({"written_at": state.get(
            "written_at" if old == "pc" else "source_written_at")})
        if old == "phone":
            state["needs_write_grant"] = True
        changed = True
    if state.get("role") == "shared" and not state.get("device"):
        state["device"] = secrets.token_hex(8)
        changed = True
    if changed:
        with _state_lock:
            _save_state(state)
    return state


def _save_state(state: dict) -> None:
    tmp = _state_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(_state_file())


def _update_state(**changes) -> dict:
    with _state_lock:
        state = _state()
        state.update(changes)
        _save_state(state)
    return state


def role() -> str | None:
    """'shared' when this device keeps in step with the others, otherwise None."""
    return "shared" if _state().get("role") == "shared" else None


def device_name() -> str:
    """How the other devices name this one in their notes."""
    if config.android():
        return "Android phone"
    return (_platform.node() or "Computer")[:60]


def _version(header: dict | None) -> int:
    try:
        return max(0, int((header or {}).get("version") or 0))
    except (TypeError, ValueError):
        return 0


def _tag(header: dict) -> str:
    """Which save of the file this is. A file from 1.3 has only its time."""
    return f"{header.get('device') or ''}|{_version(header)}|{header.get('written_at') or ''}"


def _edited_at(header: dict) -> str:
    """When the newest real change in that save was made (a 1.3 file: when it was saved)."""
    return str(header.get("edited_at") or header.get("written_at") or "")


def suggested_folder() -> str:
    """Where a PC would most likely want the file: a Whiskers folder inside OneDrive."""
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        base = os.environ.get(var)
        if base and pathlib.Path(base).is_dir():
            return str(pathlib.Path(base) / "Whiskers")
    cloud = pathlib.Path.home() / "Library" / "CloudStorage"
    if cloud.is_dir():
        for d in sorted(cloud.glob("OneDrive*")):
            return str(d / "Whiskers")
    return ""


def status() -> dict:
    state = _state()
    out = {"role": role(), "device": "phone" if config.android() else "computer",
           "file_name": FILE_NAME, "written_at": state.get("written_at"),
           "loaded_at": state.get("loaded_at"), "source_written_at": state.get("source_written_at"),
           "last_error": state.get("last_error") or "", "folder": state.get("folder") or "",
           "label": state.get("label") or "", "device_name": device_name(),
           "saved_by": state.get("saved_by") or "", "waiting": bool(state.get("dirty")),
           "clash": state.get("clash") or None,
           "needs_write_grant": bool(state.get("needs_write_grant"))}
    if not config.android():
        out["suggested_folder"] = suggested_folder()
        out["can_encrypt"] = _aesgcm(quiet=True) is not None
    return out


def _passphrase() -> str:
    p = (security.get(VAULT_REF) or {}).get("passphrase") or ""
    if not p:
        raise SyncError("The passphrase isn't stored on this device any more. Set it up again "
                        "in Settings.")
    return p


def _check_passphrase(p: str) -> str:
    if len(p) < MIN_PASSPHRASE:
        raise SyncError(f"Use a passphrase of at least {MIN_PASSPHRASE} characters. A few "
                        f"unrelated words are easy to type and hard to guess.")
    return p


# ---------------------------------------------------------------------------- the lock

def _aesgcm(quiet: bool = False):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM
    except Exception:
        if quiet:
            return None
        raise SyncError("This copy of Whiskers can't encrypt (the cryptography package is "
                        "missing), so it won't put your data in a cloud folder.") from None


def _derive(passphrase: str, salt: bytes, params: dict) -> bytes:
    try:
        n, r, p = int(params["n"]), int(params["r"]), int(params["p"])
    except (KeyError, TypeError, ValueError):
        raise SyncError("That copy is damaged.") from None
    # The header is read before anything is authenticated, so a doctored one must not be
    # able to ask for gigabytes of memory.
    if not (2 ** 10 <= n <= 2 ** 16 and n & (n - 1) == 0 and 1 <= r <= 16 and 1 <= p <= 4):
        raise SyncError("That file's settings aren't ones Whiskers writes.")
    return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32,
                          maxmem=128 * r * n + 2 ** 20)


def seal(payload: bytes, passphrase: str, written_at: str, extra: dict | None = None) -> bytes:
    """extra: who saved it and which save it is (device, device_name, version, edited_at,
    replaced), all in the authenticated header."""
    aesgcm = _aesgcm()
    salt = secrets.token_bytes(16)
    header = dict(extra or {})
    header.update({"format": FORMAT, "written_at": written_at, "app_version": config.APP_VERSION,
                   "kdf": dict(SCRYPT, name="scrypt", salt=base64.b64encode(salt).decode())})
    head = json.dumps(header, sort_keys=True).encode("utf-8") + b"\n"
    nonce = secrets.token_bytes(12)
    body = aesgcm(_derive(passphrase, salt, SCRYPT)).encrypt(
        nonce, zlib.compress(payload, 6), MAGIC + head)
    return MAGIC + head + nonce + body


def read_header(blob: bytes) -> tuple[dict, bytes, bytes]:
    """The readable header, and the rest. Nothing here is trusted until it decrypts."""
    if not blob.startswith(MAGIC):
        raise SyncError("That file isn't a shared copy of Whiskers.")
    rest = blob[len(MAGIC):]
    end = rest.find(b"\n", 0, 4096)
    if end < 0:
        raise SyncError("That copy is damaged.")
    head = rest[:end + 1]
    try:
        header = json.loads(head)
    except ValueError:
        raise SyncError("That copy is damaged.") from None
    if not isinstance(header, dict) or not isinstance(header.get("kdf"), dict):
        raise SyncError("That copy is damaged.")
    try:
        fmt = int(header.get("format") or 0)
    except (TypeError, ValueError):
        raise SyncError("That copy is damaged.") from None
    if fmt > FORMAT:
        raise SyncError("The shared copy was saved by a newer Whiskers. Update Whiskers on "
                        "this device first.")
    return header, head, rest[end + 1:]


def unseal(blob: bytes, passphrase: str) -> tuple[dict, dict]:
    header, head, rest = read_header(blob)
    aesgcm = _aesgcm()
    try:
        salt = base64.b64decode(header["kdf"]["salt"], validate=True)
    except (KeyError, TypeError, binascii.Error):
        raise SyncError("That copy is damaged.") from None
    key = _derive(passphrase, salt, header["kdf"])
    try:
        payload = aesgcm(key).decrypt(rest[:12], rest[12:], MAGIC + head)
    except Exception:
        raise SyncError("That passphrase doesn't open the shared copy. Use the one you set on "
                        "your first device (it was checked exactly, capitals and spaces "
                        "included).") from None
    try:
        data = json.loads(zlib.decompress(payload))
    except (zlib.error, ValueError):
        raise SyncError("That copy is damaged.") from None
    if not isinstance(data, dict) or not isinstance(data.get("tables"), dict):
        raise SyncError("That copy is damaged.")
    return header, data


# ---------------------------------------------------------------------------- the file

def snapshot() -> dict:
    """Every travelling table, read inside one transaction so they agree with each other."""
    db.init()
    con = db.connect()
    try:
        con.execute("BEGIN")
        tables = {}
        for t in TABLES:
            cur = con.execute(f"SELECT * FROM {t}")  # nosec B608  # t is one of TABLES
            tables[t] = {"columns": [d[0] for d in cur.description],
                         "rows": [list(r) for r in cur.fetchall()]}
        con.execute("COMMIT")
    finally:
        con.close()
    return {"format": FORMAT, "tables": tables,
            "settings": {k: config.settings.get(k) for k in SETTINGS}}


def _write_file(folder: pathlib.Path, blob: bytes) -> pathlib.Path:
    target = folder / FILE_NAME
    tmp = folder / (FILE_NAME + ".tmp")
    tmp.write_bytes(blob)
    for attempt in range(4):
        try:
            tmp.replace(target)
            return target
        except PermissionError:
            # OneDrive holds a file open for a moment while it uploads it.
            if attempt == 3:
                raise
            time.sleep(0.5)
    return target


def _read_source(uri: str) -> bytes:
    if not uri.startswith("content://"):
        raise SyncError("Choose the shared copy with the file picker.")
    if android.read_document is None:
        raise SyncError("Only the Whiskers app on a phone can open a file by its picker address.")
    try:
        got = android.read_document(uri) or {}
    except Exception as e:                  # whatever the Java side threw
        got = {"error": f"{type(e).__name__}: {e}"}
    if got.get("error"):
        raise SyncError(f"Couldn't read the shared copy: {got['error']}")
    try:
        return base64.b64decode(got.get("body") or "", validate=True)
    except binascii.Error:
        raise SyncError("Couldn't read the shared copy.") from None



def _write_source(uri: str, blob: bytes) -> None:
    if android.write_document is None:
        raise SyncError("Update the Whiskers app on this phone so it can save to the shared copy.")
    try:
        got = android.write_document(uri, base64.b64encode(blob).decode()) or {}
    except Exception as e:                  # whatever the Java side threw
        got = {"error": f"{type(e).__name__}: {e}"}
    if got.get("error"):
        raise SyncError(f"Couldn't save to the shared copy: {got['error']}")


def _read_blob(state: dict) -> bytes | None:
    """The shared file as it is now, or None if a computer's folder doesn't have it yet."""
    if state.get("uri"):
        return _read_source(state["uri"])
    folder = pathlib.Path(state.get("folder") or "")
    if not state.get("folder") or not folder.is_dir():
        raise SyncError(f"The folder {folder} isn't there any more. Choose it again in Settings.")
    try:
        return (folder / FILE_NAME).read_bytes()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise SyncError(f"Couldn't read the shared copy: {e}") from None


def _write_blob(state: dict, blob: bytes) -> None:
    if state.get("uri"):
        _write_source(state["uri"], blob)
    else:
        _write_file(pathlib.Path(state["folder"]), blob)


def _backup(prefix: str) -> str:
    """Keep this device's database as it is, dated; the last few of each kind are kept."""
    name = f"{prefix}{time.strftime('%Y-%m-%d-%H%M%S')}.db"
    src, dst = db.connect(), sqlite3.connect(str(config.data_dir() / name))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    for old in sorted(config.data_dir().glob(prefix + "*.db"))[:-KEEP_BACKUPS]:
        try:
            old.unlink()
        except OSError:
            pass
    return name


def _match(old: tuple | None, new: dict[int, tuple]) -> int | None:
    """The platform in the new data that an old one's key belongs to: same provider and
    name, or failing that the only platform with that provider."""
    if not old:
        return None
    same = [pid for pid, key in new.items() if key == old]
    if same:
        return same[0]
    provider = [pid for pid, key in new.items() if key[0] == old[0]]
    return provider[0] if len(provider) == 1 else None


def load(data: dict) -> dict:
    """Replace this device's travelling tables with the shared copy's, in one transaction."""
    tables = data.get("tables") or {}
    if not isinstance(tables.get("platforms"), dict):
        raise SyncError("That copy is damaged.")
    db.init()
    counts = {}
    with db.tx() as c:
        mine = {}
        for t in HISTORY:
            cur = c.execute(f"SELECT * FROM {t}")  # nosec B608  # t is one of HISTORY
            mine[t] = ([d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()])
        old = {r["id"]: (r["provider"], r["name"])
               for r in c.execute("SELECT id, provider, name FROM platforms")}
        keys = [(r["ref"], r["blob"]) for r in c.execute("SELECT ref, blob FROM vault")
                if r["ref"].split(":", 1)[0] in PLATFORM_KEYS]
        for t in reversed(TABLES):
            c.execute(f"DELETE FROM {t}")  # nosec B608  # t is one of TABLES
        for t in TABLES:
            spec = tables.get(t) or {}
            cols_in = list(spec.get("columns") or [])
            here = {r["name"] for r in c.execute(f"PRAGMA table_info({t})")}
            cols = [x for x in cols_in if x in here]
            if not cols:
                continue
            idx = [cols_in.index(x) for x in cols]
            sql = (f"INSERT INTO {t}({','.join(cols)}) "  # nosec B608  # columns this table has
                   f"VALUES({','.join('?' * len(cols))})")
            rows = [[row[i] for i in idx] for row in spec.get("rows") or []]
            c.executemany(sql, rows)
            counts[t] = len(rows)
        for t, (cols, rows) in mine.items():      # days only this device has stay
            if rows:
                c.executemany(f"INSERT OR IGNORE INTO {t}({','.join(cols)}) "  # nosec B608
                              f"VALUES({','.join('?' * len(cols))})", rows)
        new = {r["id"]: (r["provider"], r["name"])
               for r in c.execute("SELECT id, provider, name FROM platforms")}
        for ref, blob in keys:
            kind, _, pid = ref.partition(":")
            try:
                target = _match(old.get(int(pid)), new)
            except ValueError:
                target = None
            c.execute("DELETE FROM vault WHERE ref=?", (ref,))
            if target is not None:
                c.execute("INSERT INTO vault(ref, blob) VALUES(?,?) ON CONFLICT(ref) DO UPDATE "
                          "SET blob=excluded.blob", (f"{kind}:{target}", blob))
    settings = {k: v for k, v in (data.get("settings") or {}).items() if k in SETTINGS}
    if settings:
        config.settings.update(settings)
    return counts



# ---------------------------------------------------------------------------- keeping in step

def _write(state: dict, over: dict | None = None) -> None:
    """Save this device's copy over the file. over: the header of a save by another
    device that this one never loaded and is replacing (a clash this device won)."""
    when = db.now()
    changed_at = state.get("changed_at")
    edited = (changed_at if state.get("dirty") else state.get("content_edited_at")) or when
    version = max(_version(over), int(state.get("loaded_version") or 0)) + 1
    extra = {"device": state["device"], "device_name": device_name(), "version": version,
             "edited_at": edited}
    if over is not None:
        extra["replaced"] = {"device": over.get("device") or "",
                             "device_name": over.get("device_name") or "",
                             "version": _version(over)}
    payload = json.dumps(snapshot(), separators=(",", ":"), default=str).encode("utf-8")
    _write_blob(state, seal(payload, _passphrase(), when, extra))
    with _state_lock:
        now = _state()
        # A change made while this was being written still needs saving.
        still = bool(now.get("dirty")) and now.get("changed_at") != changed_at
        now.update(written_at=when, loaded_tag=_tag(dict(extra, written_at=when)),
                   loaded_version=version, content_edited_at=edited, saved_by=device_name(),
                   dirty=still, last_error="")
        _save_state(now)


def _loaded(header: dict, backup: str, note: dict | None) -> None:
    changes = dict(loaded_tag=_tag(header), loaded_version=_version(header), loaded_at=db.now(),
                   source_written_at=header.get("written_at"),
                   saved_by=header.get("device_name") or "another device",
                   content_edited_at=_edited_at(header), dirty=False, last_error="",
                   last_backup=backup)
    if note:
        changes["clash"] = note
    _update_state(**changes)


def _sync(write: bool, force: bool = False) -> dict:
    """Bring this device and the shared file into step. Hold _lock.

    write: save this device's copy even if nothing changed here. force: load the file
    even if it is the save already loaded (never over changes not yet saved)."""
    state = _state()
    blob = _read_blob(state)
    header = read_header(blob)[0] if blob is not None else None
    dirty = bool(state.get("dirty"))
    new = header is not None and (_tag(header) != state.get("loaded_tag") or (force and not dirty))
    if new:
        header, data = unseal(blob, _passphrase())    # checked before anything changes
        if dirty and _edited_at(header) < (state.get("changed_at") or ""):
            _write(state, over=header)               # this device's changes are newer
            return {"saved": True}
        clash = dirty
        backup = _backup(CLASH_BACKUP if clash else LOAD_BACKUP)
        counts = load(data)
        by = header.get("device_name") or "another device"
        note = None
        if clash or (header.get("replaced") or {}).get("device") == state.get("device"):
            note = {"at": db.now(), "backup": backup, "by": by}
        _loaded(header, backup, note)
        return {"loaded": True, "counts": counts, "written_at": header.get("written_at"),
                "clash": note}
    if header is None or dirty or write:
        _write(state)
        return {"saved": True}
    return {}


def _run(write: bool, force: bool = False) -> dict:
    with _lock:
        try:
            out = _sync(write, force)
        except SyncError as e:
            _update_state(last_error=str(e))
            raise
        except OSError as e:
            _update_state(last_error=f"Couldn't save the copy: {e}")
            raise SyncError(f"Couldn't save the copy: {e}") from None
        if not out:
            _update_state(last_error="")
    return out


def write_now() -> dict:
    """Save this device's copy now (loading first if another device saved since)."""
    if role() != "shared":
        raise SyncError("This device isn't keeping in step with your others yet.")
    return dict(status(), **_run(write=True))


def _write_quietly():
    try:
        _run(write=False)
    except Exception as e:                  # recorded in the state; never stops the app
        log.warning("Couldn't save the shared copy: %s", e)


def after_change() -> None:
    """Something was changed here: save the shared copy a few seconds from now, once.
    Refreshes don't call this; they aren't changes for clash purposes."""
    global _timer
    if role() != "shared":
        return
    _update_state(dirty=True, changed_at=db.now())
    with _timer_lock:
        if _timer is not None:
            _timer.cancel()
        _timer = threading.Timer(DEBOUNCE, _write_quietly)
        _timer.daemon = True
        _timer.start()


def pull(force: bool = False) -> dict:
    """On opening, coming back to the front and refreshing: load the shared copy if another
    device saved since, and save this device's changes if any are waiting. Safe to call often."""
    if role() != "shared":
        return dict(status(), loaded=False)
    out = _run(write=False, force=force)
    out.setdefault("loaded", False)
    if not out["loaded"] and not out.get("saved"):
        out["unchanged"] = True
    return dict(status(), **out)


def clear_note() -> dict:
    _update_state(clash=None)
    return status()


def _join(where: dict, passphrase: str) -> dict:
    """Start keeping in step: load the shared copy if there is one, or save the first."""
    _check_passphrase(passphrase)
    with _lock:
        state = {"role": "shared", "device": _state().get("device") or secrets.token_hex(8),
                 **where}
        blob = _read_blob(state)
        header = data = None
        if blob is not None:
            header, data = unseal(blob, passphrase)  # a wrong passphrase changes nothing
        security.put(VAULT_REF, {"passphrase": passphrase})
        with _state_lock:
            _save_state(state)
        if data is None:
            _write(state)
            return dict(status(), loaded=False,
                        message="Saved the shared copy. Now set up your other devices.")
        backup = _backup(LOAD_BACKUP)
        counts = load(data)
        _loaded(header, backup, None)
    return dict(status(), loaded=True, counts=counts,
                message=f"Loaded the shared copy: {counts.get('positions', 0)} holdings on "
                        f"{counts.get('platforms', 0)} platforms.")


def setup_pc(folder: str, passphrase: str) -> dict:
    """A computer: keep in step through a folder (OneDrive)."""
    if config.android():
        raise SyncError("This is the phone: choose the shared copy instead.")
    _aesgcm()
    _check_passphrase(passphrase)
    path = pathlib.Path(os.path.expanduser(folder.strip().strip('"')))
    if not folder.strip() or not path.is_absolute():
        raise SyncError("Type the whole folder path, for example C:\\Users\\you\\OneDrive\\Whiskers.")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SyncError(f"Couldn't use that folder: {e}") from None
    return _join({"folder": str(path)}, passphrase)


def setup_phone(uri: str, passphrase: str, label: str = "") -> dict:
    """A phone: keep in step through the file chosen in Android's picker. With no
    passphrase, an existing set-up is pointed at a newly chosen file (to be allowed to
    write to it after 1.3) and brought into step."""
    if not config.android():
        raise SyncError("Only the Whiskers app on a phone can open a file by its picker address.")
    if not passphrase and role() == "shared" and (security.get(VAULT_REF) or {}).get("passphrase"):
        _update_state(uri=uri, label=label[:200], needs_write_grant=False)
        return dict(pull(), message="This phone can save to the shared copy now.")
    return _join({"uri": uri, "label": label[:200]}, passphrase)


def stop() -> dict:
    global _timer
    with _timer_lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
    security.drop(VAULT_REF)
    try:
        _state_file().unlink()
    except FileNotFoundError:
        pass
    return status()
