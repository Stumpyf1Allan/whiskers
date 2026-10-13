"""Keeping the phone in step with the PC (folio/sync.py).

Each test plays both devices in turn: a PC with its own data folder that keeps a copy in
a stand-in OneDrive folder, then a phone with a different data folder, its own wrong
figures and its own Trading 212 key, which reads that file the way the Android app does.
"""

from __future__ import annotations

import base64
import json
import threading
import time

import pytest

from folio import android, config, db, security, sync
from folio.brokers import symbols

from .test_whiskers import _req, server  # noqa: F401  (server is a fixture)

PASS = "correct horse battery"
URI = "content://com.microsoft.skydrive.content.StorageAccessProvider/document/1"


def as_device(monkeypatch, tmp_path, name: str, phone: bool):
    monkeypatch.setenv("WHISKERS_DATA_DIR", str(tmp_path / name))
    if phone:
        monkeypatch.setenv("WHISKERS_ANDROID", "1")
    else:
        monkeypatch.delenv("WHISKERS_ANDROID", raising=False)
    db.forget_initialised()
    config.settings._data = None
    db.init()


def platform(name: str, provider: str, cash=None) -> int:
    with db.tx() as c:
        return c.execute("INSERT INTO platforms(name,provider,wrapper,flexible,cash) "
                         "VALUES(?,?,?,?,?)", (name, provider, "isa", 0, cash)).lastrowid


def holding(pid: int, symbol: str, qty: float, name: str) -> int:
    with db.tx() as c:
        iid = symbols.upsert_instrument(c, symbol, "US", name, None, None)
        c.execute("INSERT INTO positions(platform_id,instrument_id,quantity,cost,source,updated_at)"
                  " VALUES(?,?,?,?,?,?)", (pid, iid, qty, qty * 10, "csv", db.now()))
    return iid


@pytest.fixture()
def pc(monkeypatch, tmp_path):
    """The PC: Freetrade (id 1) and Trading 212 (id 2), one holding, a copy kept in OneDrive."""
    as_device(monkeypatch, tmp_path, "pc", phone=False)
    ft = platform("Freetrade ISA", "freetrade")
    platform("Trading 212 ISA", "trading212", cash=5880)
    holding(ft, "NVDA", 10, "NVIDIA")
    db.set_meta("plan_loaded", {"at": "2026-10-01 09:00:00"})
    config.settings.update({"fscs_limit": 78000, "theme": "dark"})
    folder = tmp_path / "OneDrive" / "Whiskers"
    sync.setup_pc(str(folder), PASS)
    return folder / sync.FILE_NAME


def phone(monkeypatch, tmp_path, file):
    """The phone: its own wrong data, its own Trading 212 key (on platform id 1), a cached
    price, and Android's file reading pointed at the PC's file."""
    as_device(monkeypatch, tmp_path, "phone", phone=True)
    t212 = platform("Trading 212 ISA", "trading212")
    platform("Old Freetrade", "freetrade")
    security.put(f"t212:{t212}", {"api_key": "phone-key", "api_secret": "phone-secret"})
    with db.tx() as c:
        c.execute("INSERT INTO series(key,d,v) VALUES('SEC:NVDA','2026-10-01',100.0)")
    config.settings.update({"theme": "light"})
    monkeypatch.setattr(android, "read_document",
                        lambda uri: {"body": base64.b64encode(file.read_bytes()).decode()})


def names() -> list[tuple]:
    return [(r["id"], r["name"]) for r in db.rows("SELECT id, name FROM platforms ORDER BY id")]


# ---------------------------------------------------------------------------- the PC

def test_the_pc_writes_an_encrypted_copy_to_the_folder(pc):
    blob = pc.read_bytes()
    assert blob.startswith(sync.MAGIC)
    assert b"NVIDIA" not in blob and b"Freetrade" not in blob, "the copy is readable as it stands"
    header, _, _ = sync.read_header(blob)
    assert header["written_at"] and header["kdf"]["name"] == "scrypt"
    assert sync.status()["role"] == "pc" and sync.status()["written_at"]


def test_a_short_passphrase_is_refused(monkeypatch, tmp_path):
    as_device(monkeypatch, tmp_path, "pc", phone=False)
    with pytest.raises(sync.SyncError, match="at least"):
        sync.setup_pc(str(tmp_path / "OneDrive"), "short")
    assert sync.role() is None


def test_a_change_rewrites_the_copy_a_few_seconds_later(pc, monkeypatch):
    monkeypatch.setattr(sync, "DEBOUNCE", 0.05)
    before = pc.read_bytes()
    platform("Vanguard ISA", "other")
    sync.after_change()
    sync.after_change()                  # a burst of changes is one write
    deadline = time.time() + 5
    while pc.read_bytes() == before and time.time() < deadline:
        time.sleep(0.05)
    _, data = sync.unseal(pc.read_bytes(), PASS)
    assert ["Vanguard ISA"] == [r[1] for r in data["tables"]["platforms"]["rows"] if r[1] == "Vanguard ISA"]


def test_requests_that_change_things_ask_for_a_new_copy(server, monkeypatch):  # noqa: F811
    calls = []
    monkeypatch.setattr(sync, "after_change", lambda: calls.append(1))
    ok = {"Content-Type": "application/json"}
    assert _req(server, "/api/settings")[0] == 200
    assert calls == [], "reading changed nothing"
    assert _req(server, "/api/settings", "PATCH", ok, json.dumps({"user_name": "Allan"}).encode())[0] == 200
    assert calls == [1]
    _req(server, "/api/check-symbol", "POST", ok, json.dumps({"symbol": "VWRP.L"}).encode())
    assert calls == [1], "trying a symbol saves nothing"


# ---------------------------------------------------------------------------- the phone

def test_the_phone_loads_the_pcs_copy_and_keeps_its_own_key(pc, monkeypatch, tmp_path):
    phone(monkeypatch, tmp_path, pc)
    out = sync.setup_phone(URI, PASS, sync.FILE_NAME)
    assert out["loaded"] and sync.role() == "phone"
    assert names() == [(1, "Freetrade ISA"), (2, "Trading 212 ISA")]
    assert db.scalar("SELECT quantity FROM positions p JOIN instruments i ON i.id=p.instrument_id "
                     "WHERE i.symbol='NVDA'") == 10
    # The phone's own Trading 212 key followed its platform to the PC's id for it.
    assert security.get("t212:2") == {"api_key": "phone-key", "api_secret": "phone-secret"}
    assert security.get("t212:1") is None
    assert db.get_meta("plan_loaded") == {"at": "2026-10-01 09:00:00"}
    assert db.scalar("SELECT COUNT(*) FROM series") == 1, "the phone's price history stays"
    assert config.settings.get("fscs_limit") == 78000
    assert config.settings.get("theme") == "light", "a preference stays with its own device"
    assert (config.data_dir() / sync.BACKUP_NAME).exists(), "the phone's own data was kept first"


def test_a_wrong_passphrase_changes_nothing(pc, monkeypatch, tmp_path):
    phone(monkeypatch, tmp_path, pc)
    with pytest.raises(sync.SyncError, match="passphrase"):
        sync.setup_phone(URI, "not the right one", "")
    assert names() == [(1, "Trading 212 ISA"), (2, "Old Freetrade")]
    assert sync.role() is None


def test_a_changed_byte_is_refused(pc, monkeypatch, tmp_path):
    blob = bytearray(pc.read_bytes())
    blob[-5] ^= 0x01                                  # in the encrypted part
    pc.write_bytes(bytes(blob))
    phone(monkeypatch, tmp_path, pc)
    with pytest.raises(sync.SyncError):
        sync.setup_phone(URI, PASS, "")
    assert names() == [(1, "Trading 212 ISA"), (2, "Old Freetrade")]


def test_a_doctored_header_is_refused_too(pc, monkeypatch, tmp_path):
    blob = pc.read_bytes()
    header, head, rest = sync.read_header(blob)
    header["written_at"] = "2099-01-01 00:00:00"
    forged = sync.MAGIC + json.dumps(header, sort_keys=True).encode() + b"\n" + rest
    pc.write_bytes(forged)
    phone(monkeypatch, tmp_path, pc)
    with pytest.raises(sync.SyncError):
        sync.setup_phone(URI, PASS, "")


def test_an_unchanged_copy_is_not_loaded_again(pc, monkeypatch, tmp_path):
    phone(monkeypatch, tmp_path, pc)
    sync.setup_phone(URI, PASS, "")
    platform("Typed on the phone", "other")
    assert sync.pull() == dict(sync.status(), loaded=False, unchanged=True)
    assert "Typed on the phone" in [n for _, n in names()], "nothing was reloaded"
    assert sync.pull(force=True)["loaded"]
    assert "Typed on the phone" not in [n for _, n in names()], "the PC's copy wins"


def test_a_newer_copy_from_the_pc_is_loaded(pc, monkeypatch, tmp_path):
    _, data = sync.unseal(pc.read_bytes(), PASS)
    phone(monkeypatch, tmp_path, pc)
    sync.setup_phone(URI, PASS, "")
    data["tables"]["platforms"]["rows"].append(
        [9] + [None] * (len(data["tables"]["platforms"]["columns"]) - 1))
    cols = data["tables"]["platforms"]["columns"]
    row = data["tables"]["platforms"]["rows"][-1]
    row[cols.index("name")], row[cols.index("provider")] = "Bank", "bank"
    row[cols.index("wrapper")], row[cols.index("flexible")] = "cash", 0
    row[cols.index("in_plan")] = 0
    pc.write_bytes(sync.seal(json.dumps(data).encode(), PASS, "2099-01-01 00:00:00"))
    out = sync.pull()
    assert out["loaded"] and out["written_at"] == "2099-01-01 00:00:00"
    assert (9, "Bank") in names()


def test_a_copy_from_a_newer_whiskers_asks_for_an_update():
    head = json.dumps({"format": sync.FORMAT + 1, "kdf": {}}).encode() + b"\n"
    with pytest.raises(sync.SyncError, match="newer Whiskers"):
        sync.read_header(sync.MAGIC + head + b"x" * 40)


def test_only_a_file_chosen_in_the_picker_is_read(monkeypatch):
    monkeypatch.setattr(android, "read_document", lambda uri: pytest.fail("it was read"))
    with pytest.raises(sync.SyncError):
        sync._read_source("file:///data/data/io.github.stumpyf1allan.whiskers/files/x")


def test_a_problem_reading_is_kept_for_settings_to_show(pc, monkeypatch, tmp_path):
    phone(monkeypatch, tmp_path, pc)
    sync.setup_phone(URI, PASS, "")
    monkeypatch.setattr(android, "read_document", lambda uri: {"error": "UnknownHostException: offline"})
    with pytest.raises(sync.SyncError):
        sync.pull()
    assert "offline" in sync.status()["last_error"]


def test_stopping_forgets_the_passphrase(pc):
    sync.stop()
    assert sync.role() is None and security.get(sync.VAULT_REF) is None


def test_loads_and_writes_never_overlap(pc, monkeypatch, tmp_path):
    """Two pulls at once (the page and the refresh) take turns rather than collide."""
    phone(monkeypatch, tmp_path, pc)
    sync.setup_phone(URI, PASS, "")
    errors = []

    def pull():
        try:
            sync.pull(force=True)
        except Exception as e:      # pragma: no cover - the failure being looked for
            errors.append(e)
    threads = [threading.Thread(target=pull) for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == [] and names() == [(1, "Freetrade ISA"), (2, "Trading 212 ISA")]
