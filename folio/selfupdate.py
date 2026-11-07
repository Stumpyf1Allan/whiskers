"""One-click update for the Windows app: replace this exe with the verified download and
restart.

`updates.py` still only finds, downloads and verifies, and never runs anything. This
module is the one place that goes further, and only on a Windows copy built as a single
.exe, and only with a file `updates.download()` has already checked against the published
SHA-256. The steps, in order, each one able to stop with a plain message:

    1. get the verified file (download it if it isn't here yet);
    2. check its SHA-256 again, and that it sits in the updates folder;
    3. copy it next to this exe as `Whiskers.exe.new` and check the copy's SHA-256 too,
       so a full disk or a locked folder shows up now, while Whiskers is still running;
    4. start a tiny helper script that waits for Whiskers to close, moves the new file over
       the old one and starts it;
    5. close Whiskers.

If anything fails before step 4 nothing has changed and the old "Show the new version"
button still works. If the helper cannot replace the exe it starts the old one again, and
the update bar comes back.

The paths reach the helper through environment variables, never by being written into
the script, so a name with an odd character in it cannot become a command.
"""

from __future__ import annotations

import hashlib
import logging
import os
import pathlib
import shutil
import subprocess  # nosec B404  # one fixed script, argument list, never a shell string
import sys
import threading

from . import config, updates

log = logging.getLogger(__name__)

#: Fixed text. Nothing from the network or the page is ever put into it.
HELPER = """@echo off
setlocal
set /a tries=0
:wait
ping -n 2 127.0.0.1 >nul
move /y "%WHISKERS_NEW%" "%WHISKERS_DST%" >nul 2>&1
if not errorlevel 1 goto launch
set /a tries+=1
if %tries% lss 40 goto wait
>>"%WHISKERS_LOG%" echo %date% %time% could not replace the old Whiskers, started it again
:launch
start "" "%WHISKERS_DST%"
"""

#: Seconds between telling the page and closing, so it can show "Restarting".
EXIT_DELAY = 2.0


def _exit_now():  # pragma: no cover - replaced in tests
    os._exit(0)


def target() -> pathlib.Path | None:
    """The exe this copy is running from, if it is a frozen Windows copy; otherwise None
    (the Mac, a copy run from source, the phone: they keep "Show the new version")."""
    if updates.platform_key() != "windows" or not updates._is_frozen():
        return None
    try:
        return pathlib.Path(sys.executable).resolve()
    except OSError:
        return None


def can_install() -> bool:
    return target() is not None


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def _fail(message: str, status: str = "ready") -> dict:
    """Stop with a reason. The status goes back to `ready` so the banner still offers the
    by-hand route; the file is still there and still verified."""
    updates._set(status=status, error=message)
    return updates.state()


def _install() -> dict:
    updates._set(error="")
    dst = target()
    if dst is None:
        return _fail("This copy of Whiskers can't replace itself. Use “Show the new version”.",
                     status="idle")

    # 1. The verified file.
    if not updates.state().get("download"):
        updates.check(force=True)          # after a restart the address is forgotten
    entry = updates.state().get("download")
    if not entry:
        return _fail("There's nothing to download. Check for an update first.", status="idle")
    st = updates.state()
    if st["status"] != "ready" or not st.get("file"):
        st = updates.download()
    if st["status"] != "ready" or not st.get("file"):
        return st                          # download() has already said why

    # 2. Check it again, here, now.
    src = pathlib.Path(st["file"]).resolve()
    try:
        if src.parent != updates.downloads_dir().resolve():
            return _fail("The update isn't in Whiskers' updates folder, so it won't be used.")
        if src == dst:
            return _fail("Whiskers is running from the updates folder. Copy it somewhere "
                         "else first (your Desktop, say), then update from there.")
        if _sha256(src) != entry["sha256"]:
            return _fail("The downloaded file no longer matches its checksum. Download it again.")
    except OSError as e:
        return _fail(f"Whiskers couldn't read the download: {e}")

    # 3. A copy beside the old exe, checked, while the old one is still running.
    new = dst.with_name(dst.name + ".new")
    try:
        shutil.copyfile(src, new)
        if _sha256(new) != entry["sha256"]:
            new.unlink(missing_ok=True)
            return _fail("The copy beside Whiskers didn't match. Nothing was changed.")
    except OSError as e:
        try:
            new.unlink(missing_ok=True)
        except OSError:
            pass
        return _fail("Whiskers can't write beside itself here "
                     f"({e.strerror or e}). Use “Show the new version” and copy it over by hand.")

    # 4. The helper. CREATE_NO_WINDOW gives it a hidden console that `ping` and `move`
    # share; DETACHED_PROCESS would make Windows open a visible console for each of them.
    script = updates.downloads_dir() / "apply-update.cmd"
    try:
        script.write_text(HELPER, encoding="ascii", newline="\r\n")
        env = {k: v for k, v in os.environ.items()
               if k != "_MEIPASS2" and not k.startswith("_PYI")}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"    # the new exe must unpack for itself
        env["WHISKERS_NEW"] = str(new)
        env["WHISKERS_DST"] = str(dst)
        env["WHISKERS_LOG"] = str(config.logs_dir() / "update-helper.log")
        flags = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                 | getattr(subprocess, "CREATE_NO_WINDOW", 0))
        subprocess.Popen(  # nosec B603 B607  # cmd.exe on our own fixed script; values via env
            ["cmd.exe", "/c", str(script)], env=env, creationflags=flags, close_fds=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log.exception("could not start the update helper")
        try:
            new.unlink(missing_ok=True)
        except OSError:
            pass
        return _fail(f"The update couldn't be started ({e}). Use “Show the new version”.")

    # 5. Close, so the helper can move the file.
    updates._set(status="restarting", error="")
    threading.Timer(EXIT_DELAY, _exit_now).start()
    return updates.state()


def start() -> bool:
    """Run the whole thing on a worker thread: it may need to download first."""
    return updates._run("install", _install)
