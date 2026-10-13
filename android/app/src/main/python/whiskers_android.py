"""The Android app's way into Whiskers.

MainActivity (Java) calls start() once, on a background thread, as the app opens. It
points Whiskers at the app's private folder, plugs what the phone itself can do into
folio.android, starts the same local server the PC runs, and returns the address the
app's full-screen browser opens. That address carries this copy's key after the '#':
the page keeps it, and the server answers no one without it (config.phone_key()), so
other apps on the phone cannot read the portfolio through the loopback address.

Everything else is the shared code in folio/, copied into the app when it is built.
"""

from __future__ import annotations

import json
import os
import tempfile

#: The Java class that does the phone's side (android/app/src/main/java/...).
NATIVE = "io.github.stumpyf1allan.whiskers.Native"

_httpd = None
_url: str | None = None


def start(files_dir: str, cache_dir: str, version: str = "", verbose: bool = False) -> str:
    """Start Whiskers and return the address to open. Safe to call again: when Android
    brings the window back while Python is still running, the server already is too."""
    global _httpd, _url
    if _url:
        return _url
    # Before anything from folio is imported: these decide where the data lives and
    # that the API demands the key.
    os.environ["WHISKERS_ANDROID"] = "1"
    os.environ["WHISKERS_PHONE"] = "1"
    os.environ["WHISKERS_DATA_DIR"] = os.path.join(files_dir, "whiskers")
    os.makedirs(cache_dir, exist_ok=True)
    os.environ["TMPDIR"] = cache_dir              # the spreadsheet export writes temp files
    tempfile.tempdir = cache_dir

    from folio import config
    if version:
        # The phone build's own number (1.0.0.12): the update check compares it with
        # latest-android.json, and every module reads it from here.
        config.APP_VERSION = version
    from folio import android
    plug_in(android)

    from folio import db, main
    from folio.web import server
    main._setup_logging(verbose)
    db.init()
    # The same port as the PC, so a Monzo client set up there (its redirect address
    # names the port) works here too. Another app holding it moves Whiskers along.
    _httpd, port = server.serve(port=server._free_port(config.PREFERRED_PORT), block=False)
    main._startup_jobs()
    _url = f"http://127.0.0.1:{port}/#key={config.phone_key()}"
    return _url


def plug_in(android) -> None:
    """Connect folio.android to the Java side. Everything crosses as plain strings."""
    from java import jclass  # Chaquopy's bridge; it exists only inside the app
    native = jclass(NATIVE)

    def fetch(url: str, headers: dict, timeout: float) -> dict:
        return json.loads(str(native.fetch(url, json.dumps(headers), int(timeout * 1000))))

    android.fetch = fetch
    android.open_url = lambda url: bool(native.openUrl(url))
    android.install = lambda path: str(native.installApk(path))
    android.read_document = lambda uri: json.loads(str(native.readDocument(uri)))
    android.engine = str(native.engine())
