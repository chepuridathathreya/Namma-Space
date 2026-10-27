#!/bin/bash
set -uo pipefail
cd "$(dirname "$0")/.."

ITERS="${1:-30000}"
FACTOR="${2:-1}"
CACHE="${3:-gpu}"
PROFILE="${4:-default}"

case "$PROFILE" in
  default)  METHOD="splatfacto"; MODEL_ARGS=() ;;
  scalereg) METHOD="splatfacto"; MODEL_ARGS=(--pipeline.model.use-scale-regularization True) ;;
  quality)  METHOD="splatfacto-big"; MODEL_ARGS=(--pipeline.model.use-scale-regularization True --pipeline.model.use-bilateral-grid True) ;;
  *) echo " STOPPED: unknown profile '$PROFILE' (use default, scalereg or quality)"; exit 1 ;;
esac

banner() { echo; echo "=============================================================================="; echo " STEP 2 - $1"; echo "=============================================================================="; }
fail() { echo; echo " STOPPED: $1"; exit 1; }
stamp() { date '+%Y-%m-%d %H:%M:%S'; }

[ -f scene.json ] || fail "scene.json not found. Unzip the bundle and run: bash scripts/STEP2_train_on_remote.sh (from the unzipped folder)"
SCENE=$(python3 -c "import json; print(json.load(open('scene.json'))['scene'])")
mkdir -p logs results outputs
LOG="logs/step2_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1
START_ALL=$(date +%s)

banner "1/4 prepare the environment and check the data"
if ! command -v ns-train >/dev/null 2>&1; then
  for CONDA_SH in "$HOME/miniconda3/etc/profile.d/conda.sh" "$HOME/anaconda3/etc/profile.d/conda.sh"; do
    [ -f "$CONDA_SH" ] && source "$CONDA_SH" && break
  done
  set +u
  conda activate "$HOME/miniconda3/envs/namma3dgs" || fail "could not activate the namma3dgs environment"
  set -u
fi
export CUDA_HOME="${CONDA_PREFIX:-}"
export PATH="${CONDA_PREFIX:-}/bin:$PATH"
export TORCH_CUDA_ARCH_LIST="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1)"
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
command -v ns-train >/dev/null 2>&1 || fail "ns-train (nerfstudio) not found"
echo " scene       : $SCENE"
echo " GPU         : $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1)"
echo " settings    : $ITERS steps, downscale $FACTOR, image cache on $CACHE, profile $PROFILE ($METHOD ${MODEL_ARGS[*]:-})"
HELP=$(ns-train "$METHOD" --help 2>&1) || fail "ns-train $METHOD --help failed; this nerfstudio does not know the method $METHOD"
for FLAG in "${MODEL_ARGS[@]:-}"; do
  case "$FLAG" in --*) echo "$HELP" | grep -q -- "$FLAG" || fail "this nerfstudio has no option $FLAG; check ns-train $METHOD --help" ;; esac
done
FULL=$(ls dataset/images | wc -l); HALF=$(ls dataset/images_2 | wc -l)
echo " frames      : $FULL full size, $HALF half size"
[ "$FULL" -gt 30 ] && [ "$FULL" = "$HALF" ] || fail "image folders are missing or do not match"
[ -f dataset/colmap/sparse/0/images.bin ] || fail "dataset/colmap/sparse/0 is missing"
python - <<'EOF' || exit 1
import glob
import numpy as np
from PIL import Image
files = sorted(glob.glob("dataset/images/*.jpg"))
sample = files[:: max(1, len(files) // 8)][:8]
spread = np.mean([np.abs(np.asarray(Image.open(f).convert("RGB"), dtype=np.int16)[::8, ::8, 0] - np.asarray(Image.open(f).convert("RGB"), dtype=np.int16)[::8, ::8, 2]).mean() for f in sample])
print(f" colour check: red-vs-blue difference {spread:.1f} (grayscale would be 0.0)")
raise SystemExit(0 if spread >= 1.0 else 1)
EOF
[ $? -eq 0 ] || fail "images are grayscale. Training on them gives a grey scene. Ask the laptop side to re-extract in colour."
T_PREP=$(date +%s)

banner "2/4 training the 3D Gaussian splat"
rm -f logs/vram.csv
( while true; do nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits >> logs/vram.csv; sleep 2; done ) &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null' EXIT
echo " started at $(stamp)"
ns-train splatfacto \
  --data dataset \
  --output-dir outputs \
  --experiment-name "$SCENE" \
  --max-num-iterations "$ITERS" \
  --steps-per-save 2000 \
  --vis tensorboard \
  --pipeline.datamanager.cache-images "$CACHE" \
  colmap --colmap-path colmap/sparse/0 --images-path images --downscale-factor "$FACTOR"
RC=$?
T_TRAIN=$(date +%s)
[ "$RC" -eq 0 ] || fail "training failed (exit $RC). Log: $LOG. After fixing, you can continue with: RESUME=1 is not automatic here, resume from outputs/"
echo " finished at $(stamp)"

banner "3/4 exporting the splat file"
CFG=$(find outputs -path "*$SCENE*" -name config.yml | sort | tail -1)
[ -n "$CFG" ] || fail "no config.yml found after training"
RUNDIR=$(dirname "$CFG")
rm -rf results/export
ns-export gaussian-splat --load-config "$CFG" --output-dir results/export || fail "export failed"
PLY=$(find results/export -name '*.ply' | head -1)
[ -n "$PLY" ] || fail "export produced no .ply"
T_EXPORT=$(date +%s)

banner "4/4 packing the result zip"
PKG="results/pkg"; rm -rf "$PKG"; mkdir -p "$PKG"
cp "$PLY" "$PKG/splat.ply"
cp "$CFG" "$PKG/config.yml"
cp "$RUNDIR/dataparser_transforms.json" "$PKG/dataparser_transforms.json"
cp scene.json "$PKG/scene.json"
PEAK=$(sort -n logs/vram.csv | tail -1)
T_END=$(date +%s)
{
  echo "scene: $SCENE"
  echo "iterations: $ITERS"
  echo "downscale: $FACTOR"
  echo "cache: $CACHE"
  echo "profile: $PROFILE ($METHOD ${MODEL_ARGS[*]:-})"
  echo "prepare_seconds: $((T_PREP-START_ALL))"
  echo "train_seconds: $((T_TRAIN-T_PREP))"
  echo "export_seconds: $((T_EXPORT-T_TRAIN))"
  echo "total_seconds: $((T_END-START_ALL))"
  echo "ply_bytes: $(stat -c %s "$PKG/splat.ply")"
  echo "peak_gpu_memory_MiB_all_users: $PEAK"
  echo "gpu: $(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | head -1)"
  echo "finished: $(stamp)"
} > "$PKG/timing.txt"
cp "$LOG" "$PKG/step2.log"
ZIP="results/${SCENE}_${PROFILE}_result.zip"
rm -f "$ZIP"
( cd "$PKG" && python -m zipfile -c "../${SCENE}_${PROFILE}_result.zip" splat.ply config.yml dataparser_transforms.json scene.json timing.txt step2.log )
kill $SAMPLER 2>/dev/null

echo
echo "------------------------------------------------------------------------------"
echo " TIME TAKEN"
echo "------------------------------------------------------------------------------"
printf "  %-40s %8ss\n" "check and prepare" "$((T_PREP-START_ALL))"
printf "  %-40s %8ss\n" "training" "$((T_TRAIN-T_PREP))"
printf "  %-40s %8ss\n" "export" "$((T_EXPORT-T_TRAIN))"
printf "  %-40s %8ss\n" "TOTAL" "$((T_END-START_ALL))"
echo "------------------------------------------------------------------------------"
echo " peak GPU memory (whole GPU, other users included): ${PEAK} MiB"
echo
echo " STEP 2 FINISHED"
echo " RESULT ZIP TO SEND BACK: $(pwd)/$ZIP  ($(du -h "$ZIP" | cut -f1))"
echo " Copy it to the laptop folder 3_PUT_REMOTE_RESULT_HERE and run STEP 3."
