"""What the Android app plugs in.

The phone app (android/ in this repository) runs this same Python package inside the
app. At start-up its Java side fills these in (android/app/src/main/python/
whiskers_android.py does the plugging). Everywhere else they stay empty, and the shared
code asks config.android() before relying on any of them.
"""

from __future__ import annotations

from typing import Callable

#: GET a URL through the phone's own network stack:
#: (url, headers, timeout in seconds) -> {"status", "headers", "body" (base64), "via"},
#: or {"error": reason} for a connection that never completed. From Android 14 that
#: stack is Chromium's, the one Chrome itself uses, so Yahoo sees a browser's handshake
#: just as it does from curl_cffi on the PC.
fetch: Callable[[str, dict, float], dict] | None = None

#: "chromium" when fetch goes through that built-in Chrome engine; "android" when the
#: phone is older than Android 14 and only has its standard connection.
engine: str = ""

#: Open a web page or an email address in the phone's own apps. Returns False if nothing
#: on the phone could open it.
open_url: Callable[[str], bool] | None = None

#: Hand a downloaded, checksum-verified update to Android's installer. Returns "started";
#: "allow" when the person must first let Whiskers install apps (Android has just opened
#: that switch for them); or a short reason it couldn't.
install: Callable[[str], str] | None = None

#: Read a file the person chose with Android's file picker (the PC's copy, kept in
#: OneDrive or Google Drive), by its content:// address: {"body": base64} or
#: {"error": reason}. The app keeps permission to read that one file, so it works on
#: later days too (folio/sync.py).
read_document: Callable[[str], dict] | None = None
