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

- `main`: the released version, 1.1.1 (optional Mortgage and Retirement sections, the plan
  builder; docs/WHISKERS-1.1.md describes it). Start new work on a branch from `main`.
- `mega`: the abandoned 2.0 experiment, kept as a box of parts. Never merge it.

## Where things are

| Path | What |
|---|---|
| `run_whiskers.py` | Starts the app; `--no-window --port N` for the server alone |
| `folio/config.py` | Name, version, settings defaults (`DEFAULTS`), the update address |
| `folio/db.py` | The SQLite schema; new columns go in `ADDED_COLUMNS` (never rename or drop) |
| `folio/sync.py` | The phone's copy through OneDrive: `TABLES` and `SETTINGS` that travel |
| `folio/engine/` | The calculations: `portfolio`, `allocation`, `rules` (caps, parachute steps), `plan` (plan files), `builder` (the plan builder), `sections`, `retirement`, `pensions`, `statepension`, `mortgage`, `themes`, `signals`, `classify`, `xray`, `stress`, `export`, `ukrules` (dated UK figures, with sources) |
| `folio/brokers/` | Trading 212, Freetrade, Monzo. Read-only: a test fails if an order call appears |
| `folio/market/` | Prices: `sources.py`, `store.py`, `catalogue.py` (the series) |
| `folio/importers/`, `inbox.py`, `reminders.py` | Files in, the statements folder, the monthly reminder |
| `folio/institutions/` | The list of UK and South African firms |
| `folio/web/server.py` | The HTTP server, `@route`, `ApiError`, `SETTABLE` (settings the page may change) |
| `folio/web/routes2.py` | Routes for the builder, sections, mortgage, retirement and import |
| `folio/web/static/` | `index.html`; `app.js` (the core: `VIEWS`, `ACTS`, `wire()`, `render()`, `SETTINGS_PANELS`); `builder.js`, `mortgage.js`, `retirement.js`, `importer.js`, which load after `app.js` and add their own `VIEWS` and `ACTS`; `charts.js`; `styles.css` |
| `android/` | The Android app (`android/RELEASE.md`) |
| `build/` | `whiskers.spec` (PyInstaller: add new modules to `hiddenimports`), `build_windows.bat` |
| `tests/` | pytest: `test_whiskers.py` (core), `test_sections.py` (1.1), `test_sync.py`, `test_updates.py` |

## Running and testing

```
python -m pytest -q        # about a minute, offline; each test gets a fresh data folder
WHISKERS_DATA_DIR=/tmp/w WHISKERS_FAKE_MARKET=1 python run_whiskers.py --no-window --port 18777
```

- Static files are served from the root (`/app.js`) and the API under `/api/` (`/api/bootstrap`).
- `WHISKERS_FAKE_MARKET=1` invents repeatable prices. Never point `WHISKERS_DATA_DIR` at a
  real data folder.
- `Try Whiskers 1.1 (test copy).bat` keeps its own data folder. Leave `Start Whiskers.bat` out
  of a test zip: it opens the real one.
- In Claude's cloud sandbox, Playwright's Chromium is at `/opt/pw-browsers`. Stop a background
  server with the task tool, not `pkill -f` on a pattern that is also in your own command.
- Bandit: `bandit -c bandit.yaml -r .` should report nothing.

## Conventions

- A new setting goes in `config.DEFAULTS` and `SETTABLE`, and in `sync.SETTINGS` if it should
  reach the phone.
- Amounts in sentences the engine writes are wrapped `[[£1,234]]`, so Hide amounts can mask them.
- Never change the data folder, the keychain service name or the update address: existing
  copies depend on them.
- `db.fingerprint()` uses SHA-1 to spot duplicate imports. Changing the hash would duplicate
  every import.
