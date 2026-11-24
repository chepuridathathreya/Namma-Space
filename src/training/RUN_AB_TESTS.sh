#!/bin/bash
set -uo pipefail
cd "$(dirname "$0")/.."

DEFAULT_RUNS=(default:30000 quality:30000 poseopt:30000 flat:30000 fast:15000)

if [ "${1:-}" = "--worker" ]; then
  shift
  RUNS=("$@")
  [ "${#RUNS[@]}" -gt 0 ] || RUNS=("${DEFAULT_RUNS[@]}")
  SCENE=$(python3 -c "import json; print(json.load(open('scene.json'))['scene'])")
  if ! command -v ns-train >/dev/null 2>&1; then
    for CONDA_SH in "$HOME/miniconda3/etc/profile.d/conda.sh" "$HOME/anaconda3/etc/profile.d/conda.sh"; do
      [ -f "$CONDA_SH" ] && source "$CONDA_SH" && break
    done
    set +u
    conda activate "$HOME/miniconda3/envs/namma3dgs" || { echo " STOPPED: could not activate the namma3dgs environment"; exit 1; }
    set -u
  fi
  echo "=============================================================================="
  echo " A/B TRAINING TESTS for $SCENE: ${RUNS[*]}"
  echo " started $(date '+%Y-%m-%d %H:%M:%S')"
  echo "=============================================================================="
  mkdir -p results logs
  ( cd dataset/colmap/sparse/0 && python -m zipfile -c "../../../../results/${SCENE}_colmap_sparse.zip" cameras.bin images.bin points3D.bin ) \
    && echo " camera model packed for the laptop: results/${SCENE}_colmap_sparse.zip"
  for RUN in "${RUNS[@]}"; do
    PROFILE="${RUN%%:*}"; STEPS="${RUN##*:}"
    EARLIER="results/${SCENE}_${PROFILE}_result.zip"
    [ -f "$EARLIER" ] && mv "$EARLIER" "${EARLIER%.zip}_before_$(date +%Y%m%d_%H%M%S).zip"
    echo; echo ">>>>>>>>>> RUN $PROFILE ($STEPS steps) started $(date '+%H:%M:%S')"
    bash scripts/STEP2_train_on_remote.sh "$STEPS" 1 gpu "$PROFILE"
    echo "<<<<<<<<<< RUN $PROFILE ended with exit code $? at $(date '+%H:%M:%S')"
  done
  echo
  python - "$SCENE" "${RUNS[@]}" <<'EOF'
import json, os, sys, zipfile
scene, runs = sys.argv[1], sys.argv[2:]
print("==============================================================================")
print(" RESULTS (held-out frames: higher PSNR and SSIM are better, lower LPIPS is better)")
print("==============================================================================")
print(f" {'profile':<10}{'steps':>7}{'PSNR':>8}{'SSIM':>8}{'LPIPS':>8}{'gaussians':>11}{'train min':>11}  result zip")
for run in runs:
    profile, steps = run.split(":")
    path = f"results/{scene}_{profile}_result.zip"
    if not os.path.exists(path):
        print(f" {profile:<10}{steps:>7}   FAILED, no result zip (read the log above for this run)")
        continue
    with zipfile.ZipFile(path) as archive:
        timing = dict(line.split(": ", 1) for line in archive.read("timing.txt").decode().splitlines() if ": " in line)
    shown = lambda key, digits: f"{float(timing[key]):.{digits}f}" if key in timing else "-"
    print(f" {profile:<10}{steps:>7}{shown('heldout_psnr', 2):>8}{shown('heldout_ssim', 3):>8}{shown('heldout_lpips', 3):>8}{timing.get('gaussians', '-'):>11}{float(timing.get('train_seconds', 0)) / 60:>11.1f}  {path}")
print()
print(f" Carry to the laptop folder workspace/from_gpu: every results/{scene}_*_result.zip and results/{scene}_colmap_sparse.zip")
EOF
  echo " finished $(date '+%Y-%m-%d %H:%M:%S')"
  exit 0
fi

[ -f scene.json ] && [ -d dataset/images ] || { echo "STOPPED: run this from inside an unzipped bundle: bash scripts/RUN_AB_TESTS.sh"; exit 1; }
mkdir -p logs results
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="$(pwd)/logs/ab_tests_$STAMP.log"
UNIT="namma-ab-$STAMP"
if command -v systemd-run >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  echo " starting the tests as their own service ($UNIT) so the memory guard cannot kill them with this session"
  systemd-run --user --unit="$UNIT" --collect --working-directory="$(pwd)" bash -c 'bash scripts/RUN_AB_TESTS.sh --worker "$@" > "$0" 2>&1' "$LOG" "$@" >/dev/null || { echo "STOPPED: systemd-run failed"; exit 1; }
  RUNNING() { systemctl --user is-active --quiet "$UNIT.service"; }
else
  echo " systemd-run not available, starting with nohup instead"
  nohup bash scripts/RUN_AB_TESTS.sh --worker "$@" > "$LOG" 2>&1 &
  PID=$!
  RUNNING() { kill -0 "$PID" 2>/dev/null; }
fi
echo " log: $LOG"
echo " You can close this window; the tests keep running. To watch again: tail -f $LOG"
for _ in $(seq 1 30); do [ -s "$LOG" ] && break; sleep 1; done
tail -n +1 -F "$LOG" &
TAILPID=$!
while RUNNING; do sleep 5; done
sleep 2
kill "$TAILPID" 2>/dev/null
