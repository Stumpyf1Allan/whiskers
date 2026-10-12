#!/usr/bin/env bash
# Starts the phone app on an Android emulator and checks it does its job, end to end:
# Python starts inside the app, the page loads, other apps are refused, prices come in
# through the phone's own network engine, the spreadsheet export builds, and every screen
# draws. Screenshots, the API's answers and the phone's log go to $OUT for a person to see.
#
#   bash android/ci/emulator-check.sh path/to/test.apk out-dir
#
# Uses the debug build: only a debug build lets `run-as` read the app's key, which is
# how this script gets in the way the app's own page does.
set -Eeuo pipefail
APK="$1"
OUT="$2"
PKG=io.github.stumpyf1allan.whiskers
BASE=http://127.0.0.1:18766
mkdir -p "$OUT"
FAILED=""

note() { echo "$*" | tee -a "$OUT/summary.txt"; }
fail() { note "FAILED: $*"; echo "::error::$*"; FAILED=1; }
finish() {
  adb logcat -d > "$OUT/logcat-full.txt" 2>/dev/null || true
  adb logcat -d -s Whiskers WhiskersPage python.stdout python.stderr AndroidRuntime \
    > "$OUT/logcat-whiskers.txt" 2>/dev/null || true
  if [ -n "$FAILED" ]; then
    # The last of the phone's own log, where a crash or a Python error shows up.
    tail -n 60 "$OUT/logcat-whiskers.txt" | tr -d '\r' | sed 's/%/%25/g' \
      | awk 'BEGIN{ORS="%0A"} {print}' | sed 's/^/::error title=Phone log::/' || true
    echo
    exit 1
  fi
}
trap 'fail "Stopped at line $LINENO: $BASH_COMMAND"' ERR
trap finish EXIT

shot() { adb exec-out screencap -p > "$OUT/$1.png"; }
api() { curl -fsS --max-time 60 -H "X-Whiskers-Key: $KEY" "$@"; }

note "Installing $(basename "$APK")"
adb logcat -c || true
adb install -r -t "$APK" > /dev/null
adb shell am start -W -n "$PKG/.MainActivity" > /dev/null
adb forward tcp:18766 tcp:8766 > /dev/null

started=""
for _ in $(seq 1 120); do
  if curl -fs --max-time 5 -o /dev/null "$BASE/"; then started=1; break; fi
  sleep 2
done
if [ -z "$started" ]; then fail "Whiskers' server never answered inside the app"; exit 1; fi
note "Python started and the server answered"
sleep 8
shot 01-first-start

code=$(curl -s --max-time 10 -o /dev/null -w '%{http_code}' "$BASE/api/bootstrap")
if [ "$code" = 401 ]; then note "Without the key the API refuses (401), as it should for other apps";
else fail "Without the key the API answered $code instead of 401"; fi

KEY=$(adb shell run-as "$PKG" cat files/whiskers/phone-key | tr -d '\r\n')
[ -n "$KEY" ] || { fail "Couldn't read the app's key"; exit 1; }

api "$BASE/api/bootstrap" > "$OUT/bootstrap.json"
python3 - "$OUT/bootstrap.json" <<'PY' | tee -a "$OUT/summary.txt"
import json, sys
b = json.load(open(sys.argv[1]))
assert b["app"]["android"] is True, b["app"]
print(f"Bootstrap: Whiskers {b['app']['version']}, android={b['app']['android']}, "
      f"browser_tls={b['browser_tls']}")
PY

# No tour over the screenshots from here on.
api -X PATCH -H 'Content-Type: application/json' -d '{"toured": true}' "$BASE/api/settings" > /dev/null

api -X POST -H 'Content-Type: application/json' -d '{}' "$BASE/api/sample/load" > "$OUT/sample.json"
api -X POST -H 'Content-Type: application/json' -d '{"force": true}' "$BASE/api/refresh" > /dev/null
for _ in $(seq 1 150); do
  api "$BASE/api/refresh" > "$OUT/refresh.json"
  if python3 -c 'import json,sys; sys.exit(1 if json.load(open(sys.argv[1]))["running"] else 0)' "$OUT/refresh.json"; then break; fi
  sleep 3
done
api "$BASE/api/settings" > "$OUT/settings.json"
python3 - "$OUT/settings.json" <<'PY' | tee -a "$OUT/summary.txt"
import json, sys
s = json.load(open(sys.argv[1]))["sources"]
print(f"Prices: {s['ok']} of {s['total']} series fetched; browser_tls={s['browser_tls']}, "
      f"engine={s.get('engine')!r}, problem={s.get('browser_tls_problem')!r}")
for f in s["failing"][:20]:
    print(f"  not working: {f['key']}: {(f['last_error'] or '')[:160]}")
PY
python3 -c 'import json,sys; s=json.load(open(sys.argv[1]))["sources"]; sys.exit(0 if s["ok"] > 0 else 1)' "$OUT/settings.json" \
  || fail "No price series came in at all"

if api -X POST -H 'Content-Type: application/json' -d '{"symbol": "VWRP.L"}' "$BASE/api/check-symbol" > "$OUT/check-symbol.json"; then
  note "Yahoo, through the phone's engine: $(cat "$OUT/check-symbol.json")"
else fail "check-symbol failed"; fi

if api -o "$OUT/export.xlsx" "$BASE/api/export/xlsx" && python3 - "$OUT/export.xlsx" <<'PY' | tee -a "$OUT/summary.txt"
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
sheets = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet")]
assert sheets, z.namelist()
print(f"Spreadsheet export: {len(sheets)} sheets")
PY
then :; else fail "The spreadsheet export didn't build"; fi

if api -o "$OUT/plan.json" "$BASE/api/plan/export" && python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$OUT/plan.json"; then
  note "Plan export: valid JSON"
else fail "The plan export didn't build"; fi

# Every screen, as the person will see it.
n=2
for v in overview holdings allocation ai markets activity settings; do
  adb shell am start -n "$PKG/.MainActivity" --es whiskers.view "$v" > /dev/null
  sleep 7
  shot "$(printf '%02d' $n)-$v"
  n=$((n + 1))
done

# The back button steps back to the overview rather than leaving the app.
adb shell input keyevent KEYCODE_BACK
sleep 3
shot "$(printf '%02d' $n)-after-back"
focus=$(adb shell dumpsys activity activities | grep -m1 -E 'topResumedActivity|mResumedActivity' || true)
case "$focus" in
  *"$PKG"*) note "Back from Settings stayed in Whiskers" ;;
  *) fail "Back from Settings left the app: $focus" ;;
esac

adb logcat -d | grep -q "FATAL EXCEPTION" && fail "The app crashed (see logcat)" || true
note "Done"
