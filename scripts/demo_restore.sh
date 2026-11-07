#!/usr/bin/env bash
# Put an archived demo state back: runs, uploads and BCF exports from data/archive/<timestamp>/.
# The runs that exist now are archived first (nothing is deleted). The archive itself is kept.
#   scripts/demo_restore.sh <timestamp>      (scripts/demo_restore.sh with no argument lists the archives)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${SONARIQ_DATA:-$ROOT/data}"
if [ $# -lt 1 ]; then echo "archives:"; ls -1 "$DATA/archive" 2>/dev/null || true; exit 1; fi
A="$DATA/archive/$1"
[ -d "$A" ] || { echo "no archive $A"; exit 1; }

if [ -n "$(ls -A "$DATA/runs" 2>/dev/null)" ]; then
  TS="$(date +%Y%m%d-%H%M%S)-before-restore"
  mkdir -p "$DATA/archive/$TS" && mv "$DATA/runs" "$DATA/archive/$TS/runs"
  echo "current runs archived to $DATA/archive/$TS"
fi
mkdir -p "$DATA/runs"
[ -d "$A/runs" ] && cp -a "$A/runs/." "$DATA/runs/"
[ -d "$A/uploads" ] && mkdir -p "$DATA/uploads" && cp -an "$A/uploads/." "$DATA/uploads/"
[ -d "$A/out" ] && mkdir -p "$DATA/out" && cp -an "$A/out/." "$DATA/out/"
echo "restored $(ls "$DATA/runs" | wc -l) runs from $A (the portal shows them within 2 s; history snapshot: $A/history.json)"
