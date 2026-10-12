#!/usr/bin/env bash
# Runs Gradle, and turns the reason for a failure (and any warnings) into annotations on
# the workflow run, which can be read from the run's summary without opening the logs.
#
#   bash ci/gradle.sh assembleRelease -PwhiskersAbis=arm64-v8a      (from android/)
set -uo pipefail
log=$(mktemp)
gradle --no-daemon --stacktrace "$@" 2>&1 | tee "$log"
status=${PIPESTATUS[0]}

annotate() {   # annotate LEVEL TITLE < lines
  tr -d '\r' | sed 's/%/%25/g' | awk 'BEGIN{ORS="%0A"} {print}' | sed "s/^/::$1 title=$2::/"
  echo
}
if [ "$status" -ne 0 ]; then
  grep -E "error:|ERROR:|^e: |FAILED|Exception|What went wrong" "$log" | grep -v "^\s*at " | head -n 40 \
    | annotate error "Gradle errors"
  awk '/What went wrong/{f=1} f{print; if (++n > 40) exit}' "$log" | annotate error "What went wrong"
  tail -n 30 "$log" | annotate error "End of the Gradle log"
else
  grep -iE "warning|chaquopy" "$log" | grep -viE "deprecat|has been compiled by a more recent" | head -n 25 \
    | annotate notice "Gradle warnings" || true
fi
rm -f "$log"
exit "$status"
