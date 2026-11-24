#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="$root/tmp/wrangler_run/site_landing_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$out"
copy_site() {
  mkdir -p "$2"
  (cd "$1" && tar cf - --exclude=__pycache__ --exclude=serve.py --exclude=START_WINDOWS.bat --exclude=README_RUN.txt .) | (cd "$2" && tar xf -)
}
copy_site "$root/web/landing" "$out"
copy_site "$root/scenes/room/site" "$out/room"
copy_site "$root/scenes/hallway-bedroom/site" "$out/hallway"
copy_site "$root/scenes/bedroom-early/site" "$out/bedroom"
copy_site "$root/scenes/hallway-bedroom-4k/site" "$out/hallway-4k"
cd "$root/tmp/wrangler_run"
npx wrangler pages deploy "$(basename "$out")" --project-name namma-space --branch main --commit-dirty=true
