"""Keeping the phone in step with the PC.

The PC is the main copy. Whenever its data changes, and after every refresh, it writes
an encrypted copy of that data into a folder the person chooses, normally inside
OneDrive, which carries it to the cloud. The phone is shown that file once, with
Android's own file picker (which can open files in OneDrive or Google Drive), keeps
permission to read it, and loads it whenever Whiskers opens, comes back to the front, or
refreshes. Prices and Trading 212 still refresh on the phone itself.

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
SETTINGS = ("isa_allowance", "fscs_limit", "user_name", "show_mortgage", "show_retirement")
#: Vault entries named after a platform's id, which a load can change.
PLATFORM_KEYS = ("t212", "monzo")
MIN_PASSPHRASE = 8
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}
#: Seconds to wait after a change before writing, so a burst of edits is one write.
DEBOUNCE = 4.0
VAULT_REF = "sync"
BACKUP_NAME = "whiskers-before-sync.db"

log = logging.getLogger(__name__)
_lock = threading.Lock()          # one write or load at a time
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
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    tmp = _state_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(_state_file())


def _update_state(**changes) -> dict:
    state = _state()
    state.update(changes)
    _save_state(state)
    return state


def role() -> str | None:
    """'pc' when this copy keeps a copy for the phone, 'phone' when it follows one."""
    r = _state().get("role")
    return r if r in ("pc", "phone") else None


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
           "label": state.get("label") or ""}
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


def seal(payload: bytes, passphrase: str, written_at: str) -> bytes:
    aesgcm = _aesgcm()
    salt = secrets.token_bytes(16)
    header = {"format": FORMAT, "written_at": written_at, "app_version": config.APP_VERSION,
              "kdf": dict(SCRYPT, name="scrypt", salt=base64.b64encode(salt).decode())}
    head = json.dumps(header, sort_keys=True).encode("utf-8") + b"\n"
    nonce = secrets.token_bytes(12)
    body = aesgcm(_derive(passphrase, salt, SCRYPT)).encrypt(
        nonce, zlib.compress(payload, 6), MAGIC + head)
    return MAGIC + head + nonce + body


def read_header(blob: bytes) -> tuple[dict, bytes, bytes]:
    """The readable header, and the rest. Nothing here is trusted until it decrypts."""
    if not blob.startswith(MAGIC):
        raise SyncError("That file isn't a copy of Whiskers from your PC.")
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
        raise SyncError("Your PC's copy was saved by a newer Whiskers. Update Whiskers on "
                        "this phone first.")
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
        raise SyncError("That passphrase doesn't open your PC's copy. Use the one you set on "
                        "the PC (it was checked exactly, capitals and spaces included).") from None
    try:
        data = json.loads(zlib.decompress(payload))
    except (zlib.error, ValueError):
        raise SyncError("That copy is damaged.") from None
    if not isinstance(data, dict) or not isinstance(data.get("tables"), dict):
        raise SyncError("That copy is damaged.")
    return header, data


# ---------------------------------------------------------------------------- the PC

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


def write_now() -> dict:
    if role() != "pc":
        raise SyncError("This copy isn't keeping a copy for your phone.")
    folder = pathlib.Path(_state().get("folder") or "")
    with _lock:
        try:
            if not folder.is_dir():
                raise SyncError(f"The folder {folder} isn't there any more. Choose it again in "
                                f"Settings.")
            when = db.now()
            payload = json.dumps(snapshot(), separators=(",", ":"), default=str).encode("utf-8")
            _write_file(folder, seal(payload, _passphrase(), when))
        except SyncError as e:
            _update_state(last_error=str(e))
            raise
        except OSError as e:
            _update_state(last_error=f"Couldn't save the copy: {e}")
            raise SyncError(f"Couldn't save the copy: {e}") from None
        _update_state(written_at=when, last_error="")
    return status()


def _write_quietly():
    try:
        write_now()
    except Exception as e:                  # recorded in the state; never stops the app
        log.warning("Couldn't save the copy for the phone: %s", e)


def after_change() -> None:
    """Something changed on the PC: write the phone's copy a few seconds from now, once."""
    global _timer
    if config.android() or role() != "pc":
        return
    with _timer_lock:
        if _timer is not None:
            _timer.cancel()
        _timer = threading.Timer(DEBOUNCE, _write_quietly)
        _timer.daemon = True
        _timer.start()


def setup_pc(folder: str, passphrase: str) -> dict:
    if config.android():
        raise SyncError("This is the phone: choose your PC's copy instead.")
    _aesgcm()
    _check_passphrase(passphrase)
    path = pathlib.Path(os.path.expanduser(folder.strip().strip('"')))
    if not folder.strip() or not path.is_absolute():
        raise SyncError("Type the whole folder path, for example C:\\Users\\you\\OneDrive\\Whiskers.")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SyncError(f"Couldn't use that folder: {e}") from None
    security.put(VAULT_REF, {"passphrase": passphrase})
    _save_state({"role": "pc", "folder": str(path)})
    return write_now()


# ---------------------------------------------------------------------------- the phone

def _read_source(uri: str) -> bytes:
    if not uri.startswith("content://"):
        raise SyncError("Choose your PC's copy with the file picker.")
    if android.read_document is None:
        raise SyncError("Only the Whiskers app on a phone can follow your PC's copy.")
    try:
        got = android.read_document(uri) or {}
    except Exception as e:                  # whatever the Java side threw
        got = {"error": f"{type(e).__name__}: {e}"}
    if got.get("error"):
        raise SyncError(f"Couldn't read your PC's copy: {got['error']}")
    try:
        return base64.b64decode(got.get("body") or "", validate=True)
    except binascii.Error:
        raise SyncError("Couldn't read your PC's copy.") from None


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


def _backup_once() -> None:
    """Before the phone's own data is first replaced, keep it, in case it is wanted back."""
    target = config.data_dir() / BACKUP_NAME
    if target.exists():
        return
    src, dst = db.connect(), sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def load(data: dict) -> dict:
    """Replace this device's travelling tables with the PC's, in one transaction."""
    tables = data.get("tables") or {}
    if not isinstance(tables.get("platforms"), dict):
        raise SyncError("That copy is damaged.")
    db.init()
    _backup_once()
    counts = {}
    with db.tx() as c:
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


def _apply(blob: bytes, passphrase: str) -> tuple[dict, dict]:
    header, data = unseal(blob, passphrase)
    return header, load(data)


def setup_phone(uri: str, passphrase: str, label: str = "") -> dict:
    if not config.android():
        raise SyncError("Only the Whiskers app on a phone can follow your PC's copy.")
    with _lock:
        blob = _read_source(uri)
        header, counts = _apply(blob, passphrase)
        security.put(VAULT_REF, {"passphrase": passphrase})
        _save_state({"role": "phone", "uri": uri, "label": label[:200], "loaded_at": db.now(),
                     "source_written_at": header.get("written_at"), "last_error": ""})
    return dict(status(), loaded=True, counts=counts,
                message=f"Loaded your PC's copy: {counts.get('positions', 0)} holdings on "
                        f"{counts.get('platforms', 0)} platforms.")


def pull(force: bool = False) -> dict:
    """Load the PC's copy if it has been saved since the last load. Safe to call often."""
    if role() != "phone":
        return dict(status(), loaded=False)
    with _lock:
        state = _state()
        try:
            blob = _read_source(state.get("uri") or "")
            header, _, _ = read_header(blob)
            if not force and header.get("written_at") == state.get("source_written_at"):
                _update_state(last_error="")
                return dict(status(), loaded=False, unchanged=True)
            header, counts = _apply(blob, _passphrase())
        except SyncError as e:
            _update_state(last_error=str(e))
            raise
        _update_state(loaded_at=db.now(), source_written_at=header.get("written_at"),
                      last_error="")
    return dict(status(), loaded=True, counts=counts, written_at=header.get("written_at"))


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
