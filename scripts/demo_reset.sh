#!/usr/bin/env bash
# Start the demo empty: archive (never delete) all stored runs, BCF exports, uploaded IFCs and the engine's
# in-memory history to data/archive/<timestamp>/, then restart the engine so its session is fresh.
#   scripts/demo_reset.sh                 # this checkout's data/ (on the VM run it in ~/sonariq-deploy)
#   scripts/demo_restore.sh <timestamp>   # put an archive back
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${SONARIQ_DATA:-$ROOT/data}"
TS="$(date +%Y%m%d-%H%M%S)"
A="$DATA/archive/$TS"
mkdir -p "$A"

# engine port: the hosted service when it runs from this checkout, else make api's 8765
PORT="${SONARIQ_PORT:-}"
SVC=""
if systemctl --user cat sonariq-api >/dev/null 2>&1 && \
   systemctl --user cat sonariq-api | grep -q "WorkingDirectory=$ROOT\$"; then
  SVC=sonariq-api
  PORT="${PORT:-$(systemctl --user cat sonariq-api | grep -o -- '--port [0-9]*' | awk '{print $2}')}"
fi
PORT="${PORT:-8765}"

# what the engine holds only in memory (history, decisions, sign-offs): snapshot it into the archive
curl -fs "http://127.0.0.1:$PORT/history" -o "$A/history.json" 2>/dev/null || echo "  (engine not reachable on $PORT: no history snapshot)"

moved=0
[ -d "$DATA/runs" ] && [ -n "$(ls -A "$DATA/runs" 2>/dev/null)" ] && { mv "$DATA/runs" "$A/runs"; moved=1; }
[ -d "$DATA/uploads" ] && [ -n "$(ls -A "$DATA/uploads" 2>/dev/null)" ] && mv "$DATA/uploads" "$A/uploads"
if ls "$DATA"/out/*.bcfzip >/dev/null 2>&1; then mkdir -p "$A/out"; mv "$DATA"/out/*.bcfzip "$A/out/"; fi
mkdir -p "$DATA/runs"
echo "{\"archived\": \"$TS\", \"from\": \"$DATA\"}" > "$A/ARCHIVE.json"

if [ -n "$SVC" ]; then
  systemctl --user restart "$SVC"
  for _ in $(seq 1 40); do curl -fs "http://127.0.0.1:$PORT/health" >/dev/null && break; sleep 1; done
  echo "engine restarted ($SVC, port $PORT)"
else
  echo "restart the engine (make api / make api-sim) to clear its in-memory history"
fi
echo "archived to $A ($( [ $moved = 1 ] && ls "$A/runs" | wc -l || echo 0) runs)"
echo "restore with: scripts/demo_restore.sh $TS"
