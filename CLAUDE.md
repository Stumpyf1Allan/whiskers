# Whiskers: notes for Claude

Whiskers is a personal UK investment tracker: a Python standard-library web server, SQLite and
a vanilla JavaScript single-page app, shown in a pywebview window on Windows and Mac and inside
an Android app (Chaquopy). A few family members run their own copies, which update themselves
from this repository's GitHub releases.

**This repository is public.** Never commit personal data: plan files, holdings, amounts,
names, account details or keys.

## Rules for working here

1. When the owner has something to do, give step-by-step instructions.
2. Make only the edits the job needs. No drive-by refactors or renames.
3. Build or package once, at the end.
4. Work on a branch. Never push to `main`, tag, or publish a release without the owner's
   go-ahead: a push to `main` touching `folio/` or `android/` builds and publishes a phone
   update, and a published release updates everyone's copies (docs/PUBLISHING.md).
5. Keep token use low. Find things with grep and read only the part of a file you need
   (`app.js` alone is about 180 KB). Run the tests for what changed, and the full suite once
   at the end. Check in a browser only when the change is visual.
6. Words on screen: plain English, British spelling, short sentences. Whiskers helps people
   keep to their own plan; it never gives financial advice.

## Branches

Only two branches live on GitHub:

- `main`: the released version, 1.4.3 (tag `v1.4.3`): two-way sync, the AI watch's lenses and
  big picture, and automatic updates on Windows one-.exe copies. Start new work on a branch
  from `main`, and delete that branch once its PR is merged.
- `mega`: the abandoned 2.0 experiment, kept as a box of parts. Never merge it.

## Where things are

| Path | What |
|---|---|
| `run_whiskers.py` | Starts the app; `--no-window --port N` for the server alone |
| `folio/config.py` | Name, version, settings defaults (`DEFAULTS`), the update address |
| `folio/db.py` | The SQLite schema; new columns go in `ADDED_COLUMNS` (never rename or drop) |
| `folio/sync.py` | Two-way sync of every device through one encrypted file in OneDrive (1.4: newest change wins, the loser keeps a dated backup): `TABLES` and `SETTINGS` that travel |
| `folio/engine/` | The calculations: `portfolio`, `allocation`, `rules` (caps, parachute steps), `plan` (plan files), `builder` (the plan builder), `sections`, `retirement`, `pensions`, `statepension`, `mortgage`, `themes`, `signals`, `lens` (the Overview's buttons: main watch, whole market, your portfolio, top sectors), `classify`, `xray`, `stress`, `export`, `ukrules` (dated UK figures, with sources) |
| `folio/updates.py`, `selfupdate.py` | Finding, downloading and verifying a new version; on Windows one-.exe copies, `selfupdate.start_auto()` checks every 3 h and replaces the exe once the page has been idle 2 min (setting `auto_install_updates`) |
| `folio/brokers/` | Trading 212, Freetrade, Monzo. Read-only: a test fails if an order call appears |
| `folio/market/` | Prices: `sources.py`, `store.py`, `catalogue.py` (the series); `news.py` (the Overview's News: five outlets' feeds, grouped and ranked, kept in the device-only `news` table); `briefing.py` (the big picture written by Claude with the owner's own API key, per lens, device-only `briefings` table; never sends amounts) |
| `folio/importers/`, `inbox.py`, `reminders.py` | Files in, the statements folder, the monthly reminder |
| `folio/institutions/` | The list of UK and South African firms |
| `folio/web/server.py` | The HTTP server, `@route`, `ApiError`, `SETTABLE` (settings the page may change) |
| `folio/web/routes2.py` | Routes for the builder, sections, mortgage, retirement and import |
| `folio/web/static/` | `index.html`; `app.js` (the core: `VIEWS`, `ACTS`, `wire()`, `render()`, `SETTINGS_PANELS`); `builder.js`, `mortgage.js`, `retirement.js`, `importer.js`, which load after `app.js` and add their own `VIEWS` and `ACTS`; `charts.js`; `styles.css` |
| `android/` | The Android app (`android/RELEASE.md`) |
| `build/` | `whiskers.spec` (PyInstaller: add new modules to `hiddenimports`), `build_windows.bat`, `build_macos.sh` |
| `.github/workflows/` | `release.yml` (Windows and Mac builds for a `v*` tag), `android.yml` (phone build on a push to `main` touching `folio/` or `android/`). Every action is pinned to a commit SHA |
| `tests/` | pytest: `test_whiskers.py` (core), `test_sections.py` (1.1), `test_news.py` (1.2), `test_briefing.py` (1.3), `test_sync.py` (1.4 two-way sync), `test_updates.py` (updates and self-update) |

## Running and testing

```
python -m pytest -q        # about a minute, offline; each test gets a fresh data folder
WHISKERS_DATA_DIR=/tmp/w WHISKERS_FAKE_MARKET=1 python run_whiskers.py --no-window --port 18777
```

- Static files are served from the root (`/app.js`) and the API under `/api/` (`/api/bootstrap`).
- `WHISKERS_FAKE_MARKET=1` invents repeatable prices. Never point `WHISKERS_DATA_DIR` at a
  real data folder.
- `Try Whiskers 1.1 (test copy).bat` and `Try Whiskers 1.2 (test copy).bat` keep their own
  data folders. Leave `Start Whiskers.bat` out
  of a test zip: it opens the real one.
- In Claude's cloud sandbox, Playwright's Chromium is at `/opt/pw-browsers`. Stop a background
  server with the task tool, not `pkill -f` on a pattern that is also in your own command.
- Bandit: `bandit -c bandit.yaml -r .` should report nothing.
- Release and phone builds install only `requirements-lock.txt`, every file checked by sha256
  (`pip install --require-hashes`). `requirements.txt` and `requirements-dev.txt` stay the
  readable lists. After changing either, or to take newer versions, remake the lock with
  `uv pip compile requirements-dev.txt --universal --python-version 3.12 --generate-hashes
  --no-header --annotation-style line -o requirements-lock.txt` (add `--upgrade` for newer
  versions) and run the tests from a fresh venv installed from it.

## Conventions

- A new setting goes in `config.DEFAULTS` and `SETTABLE`, and in `sync.SETTINGS` if it should
  reach the phone.
- Amounts in sentences the engine writes are wrapped `[[£1,234]]`, so Hide amounts can mask them.
- Never change the data folder, the keychain service name or the update address: existing
  copies depend on them.
- `db.fingerprint()` uses SHA-1 to spot duplicate imports. Changing the hash would duplicate
  every import.
