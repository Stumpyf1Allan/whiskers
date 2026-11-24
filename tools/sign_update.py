"""Sign latest.json on the owner's PC, so a copy of Whiskers only installs what he signed.

The private key never goes to GitHub. It sits in a file on the PC, locked with a
passphrase, and is backed up (file text and passphrase) in a password manager.

    python tools/sign_update.py newkey          # once: make the key, print the public half
    python tools/sign_update.py sign latest.json
    python tools/sign_update.py check latest.json [latest.json.sig]
    python tools/sign_update.py check https://github.com/Stumpyf1Allan/whiskers/releases/latest/download/latest.json

`sign` writes latest.json.sig next to the file, then checks it against the public keys
built into this copy of the code (folio/config.py UPDATE_PUBLIC_KEYS).
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from folio import updates  # noqa: E402

DEFAULT_KEY = pathlib.Path.home() / ".whiskers-signing" / "update-key.pem"


def _public_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def newkey(path: pathlib.Path):
    if path.exists():
        sys.exit(f"{path} already exists. Not overwriting a signing key.")
    pw = getpass.getpass("Choose a passphrase for the key: ")
    if len(pw) < 12:
        sys.exit("Use at least 12 characters.")
    if getpass.getpass("Type it again: ") != pw:
        sys.exit("They didn't match. Nothing was written.")
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.BestAvailableEncryption(pw.encode()))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pem)
    print(f"\nKey saved to {path}")
    print("Back up the text of that file AND the passphrase (password manager).")
    print("\nPublic key (safe to share; goes in folio/config.py UPDATE_PUBLIC_KEYS):")
    print(_public_hex(key))


def sign(manifest: pathlib.Path, path: pathlib.Path):
    raw = manifest.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    print(f"Signing latest.json for version {data.get('version')}:")
    for k, d in (data.get("downloads") or {}).items():
        print(f"  {k:14} {d.get('filename')}  sha256 {str(d.get('sha256'))[:12]}…")
    pw = getpass.getpass("Passphrase for the signing key: ")
    key = serialization.load_pem_private_key(path.read_bytes(), pw.encode())
    sig = base64.b64encode(key.sign(raw)) + b"\n"
    out = manifest.with_name(manifest.name + updates.SIG_SUFFIX)
    out.write_bytes(sig)
    print(f"Wrote {out}")
    if not updates.signature_ok(raw, sig):
        sys.exit("WARNING: this key is not in UPDATE_PUBLIC_KEYS, so copies will refuse it.")
    print("Checked: copies of Whiskers will accept it.")


def _get(where: str) -> bytes:
    if where.startswith("https://"):
        req = urllib.request.Request(where, headers={"User-Agent": updates.USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310  # https only
            return r.read()
    return pathlib.Path(where).read_bytes()


def check(manifest: str, sig: str | None):
    raw = _get(manifest)
    s = _get(sig or manifest + updates.SIG_SUFFIX)
    version = json.loads(raw.decode("utf-8")).get("version")
    if updates.signature_ok(raw, s):
        print(f"Good signature on version {version}.")
    else:
        sys.exit(f"BAD or missing signature on version {version}. Copies will ignore it.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", type=pathlib.Path,
                    default=pathlib.Path(os.environ.get("WHISKERS_SIGNING_KEY", DEFAULT_KEY)))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("newkey")
    p = sub.add_parser("sign")
    p.add_argument("manifest", type=pathlib.Path)
    p = sub.add_parser("check")
    p.add_argument("manifest")
    p.add_argument("sig", nargs="?")
    a = ap.parse_args()
    if a.cmd == "newkey":
        newkey(a.key)
    elif a.cmd == "sign":
        sign(a.manifest, a.key)
    else:
        check(a.manifest, a.sig)


if __name__ == "__main__":
    main()
