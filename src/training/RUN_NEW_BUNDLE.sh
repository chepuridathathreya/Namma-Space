#!/bin/bash
set -uo pipefail

ZIP="${1:-}"
if [ -z "$ZIP" ] || [ ! -f "$ZIP" ]; then
  echo "usage: bash RUN_NEW_BUNDLE.sh /path/to/<scene>_to_remote.zip [steps] [downscale] [cache] [profile: default|scalereg|quality]"
  exit 1
fi
shift

PY="$(command -v python3 || command -v python)"
[ -n "$PY" ] || { echo "STOPPED: python not found"; exit 1; }

WORKSPACE="$(cd "$(dirname "$0")" && pwd)"
BUNDLES="$WORKSPACE/bundles"
STAMP="$(date +%Y%m%d_%H%M%S)"
INCOMING="$BUNDLES/.incoming_$STAMP"
mkdir -p "$INCOMING"

echo "=============================================================================="
echo " NEW BUNDLE - unzip and train"
echo "=============================================================================="
echo " zip       : $ZIP"
echo " workspace : $WORKSPACE"
"$PY" -m zipfile -e "$ZIP" "$INCOMING" || { echo "STOPPED: could not unzip"; exit 1; }
TOP="$(ls "$INCOMING" | head -1)"
[ -n "$TOP" ] || { echo "STOPPED: the zip is empty"; exit 1; }
DEST="$BUNDLES/${TOP}_$STAMP"
mv "$INCOMING/$TOP" "$DEST" && rmdir "$INCOMING"
[ -f "$DEST/scripts/STEP2_train_on_remote.sh" ] || { echo "STOPPED: this zip is not a NammaSpace bundle (no scripts/STEP2_train_on_remote.sh)"; exit 1; }
[ -f "$DEST/scene.json" ] || { echo "STOPPED: no scene.json in the bundle"; exit 1; }
echo " unzipped  : $DEST"
echo " scene     : $("$PY" -c "import json; d=json.load(open('$DEST/scene.json')); print(d['scene'], '-', d['frames'], 'frames,', d['points'], 'points')" 2>/dev/null || echo "(could not read scene.json here)")"
echo " frames    : $(ls "$DEST/dataset/images" | wc -l) full size, $(ls "$DEST/dataset/images_2" | wc -l) half size"
mkdir -p "$DEST/logs" "$DEST/results"

UNIT="namma-train-$STAMP"
if command -v systemd-run >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  echo " starting training as its own service ($UNIT) so the memory guard cannot kill it with this session"
  systemd-run --user --unit="$UNIT" --collect --working-directory="$DEST" bash scripts/STEP2_train_on_remote.sh "$@" >/dev/null || { echo "STOPPED: systemd-run failed"; exit 1; }
  RUNNING() { systemctl --user is-active --quiet "$UNIT.service"; }
else
  echo " systemd-run not available, starting with nohup instead"
  ( cd "$DEST" || exit 1; nohup bash scripts/STEP2_train_on_remote.sh "$@" > logs/nohup.out 2>&1 & echo $! > logs/pid )
  PID="$(cat "$DEST/logs/pid")"
  RUNNING() { kill -0 "$PID" 2>/dev/null; }
fi

for _ in $(seq 1 60); do
  LOG="$(ls -t "$DEST"/logs/step2_*.log 2>/dev/null | head -1)"
  [ -n "$LOG" ] && break
  sleep 1
done
if [ -n "${LOG:-}" ]; then
  tail -n +1 -F "$LOG" &
  TAILPID=$!
fi
while RUNNING; do sleep 5; done
sleep 2
[ -n "${TAILPID:-}" ] && kill "$TAILPID" 2>/dev/null

RESULT="$(ls -t "$DEST"/results/*_result.zip 2>/dev/null | head -1)"
echo
echo "=============================================================================="
if [ -n "$RESULT" ]; then
  echo " DONE. RESULT ZIP TO CARRY BACK TO THE LAPTOP:"
  echo "   $RESULT  ($(du -h "$RESULT" | cut -f1))"
else
  echo " NO RESULT ZIP WAS PRODUCED. Read the last lines above or the log: ${LOG:-$DEST/logs}"
fi
echo "=============================================================================="
