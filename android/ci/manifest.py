"""Write latest-android.json: how the phone app finds out a newer build of itself exists.

    python android/ci/manifest.py Whiskers-1.0.0.12.apk --version 1.0.0.12 \
        --repo Stumpyf1Allan/whiskers --notes "What changed"

The same shape as the PC's latest.json (folio/updates.py reads both), with one download
under "android". The SHA-256 is what lets the app prove the file it downloaded is
byte-for-byte this build before it hands it to Android's installer.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("apk")
    ap.add_argument("--version", required=True)
    ap.add_argument("--repo", required=True, help="owner/name on GitHub")
    ap.add_argument("--tag", default="android")
    ap.add_argument("--notes", default="")
    ap.add_argument("--out", default="latest-android.json")
    a = ap.parse_args(argv)

    apk = pathlib.Path(a.apk)
    if not re.fullmatch(r"\d+(\.\d+){3}", a.version):
        raise SystemExit(f"{a.version!r} isn't a phone build number like 1.0.0.12")
    if " " in apk.name:
        raise SystemExit("GitHub renames files with spaces; give the APK a name without any")
    h = hashlib.sha256()
    with open(apk, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            h.update(chunk)
    manifest = {
        "version": a.version,
        "published": dt.date.today().isoformat(),
        "notes": a.notes.strip()[:500] or f"Whiskers {a.version} for Android.",
        "page": f"https://github.com/{a.repo}/releases/tag/{a.tag}",
        "downloads": {
            "android": {
                "url": f"https://github.com/{a.repo}/releases/download/{a.tag}/{apk.name}",
                "filename": apk.name,
                "sha256": h.hexdigest(),
                "bytes": apk.stat().st_size,
            },
        },
    }
    pathlib.Path(a.out).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
