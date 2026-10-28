#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="$root/tmp/wrangler_run/site_landing"
mkdir -p "$out"
cp -r "$root/home/." "$out/"
mkdir -p "$out/room" "$out/hallway" "$out/bedroom"
cp -r "$root/01_room/site/." "$out/room/"
cp -r "$root/02_hallway_bedroom/site/." "$out/hallway/"
cp -r "$root/03_bedroom_early/site/." "$out/bedroom/"
cd "$root/tmp/wrangler_run"
npx wrangler pages deploy site_landing --project-name namma-space --branch main --commit-dirty=true
