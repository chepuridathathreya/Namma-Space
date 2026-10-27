#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="$root/tmp/wrangler_run/site_all"
mkdir -p "$out"
cp -r "$root/01_room/site/." "$out/"
mkdir -p "$out/hallway" "$out/bedroom" "$out/home"
cp -r "$root/02_hallway_bedroom/site/." "$out/hallway/"
cp -r "$root/03_bedroom_early/site/." "$out/bedroom/"
cp "$root/home/index.html" "$out/home/index.html"
cd "$root/tmp/wrangler_run"
npx wrangler pages deploy site_all --project-name namma-space --branch main --commit-dirty=true
