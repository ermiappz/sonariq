#!/bin/sh
# End-to-end checks in headless Chromium (software GL). Starts a throwaway engine (8797, its own run store) and Vite
# (5197); never touches the live or dev services. usage: e2e/run.sh [spec.mjs ...]   (default: every *.spec.mjs)
set -e
cd "$(dirname "$0")/.."
ROOT=$(cd .. && pwd)
TMP=$(mktemp -d)
export SONARIQ_RUNS=$TMP/runs SONARIQ_REPORTS=$TMP/reports.json SONARIQ_VIEWS=$TMP/views.json SONARIQ_TASKS=$TMP/tasks.json SONARIQ_INCORRECT=$TMP/incorrect.json SONARIQ_REVISIONS=$TMP/revisions.sqlite
export SONARIQ_AI=off SONARIQ_RATE_LIMIT=0 PYTHONPATH=$ROOT/engine:$ROOT PYTHONUTF8=1
(cd "$ROOT" && .venv/bin/python -m uvicorn sonariq.api:app --app-dir engine --port 8797 --log-level warning) > $TMP/api.log 2>&1 &
API=$!
SQ_API=http://127.0.0.1:8797 npx vite --host 127.0.0.1 --port 5197 --strictPort --logLevel error > $TMP/vite.log 2>&1 &
VITE=$!
stop() { for p in $(ss -ltnp 2>/dev/null | grep -E ":5197 |:8797 " | grep -o "pid=[0-9]*" | cut -d= -f2); do kill $p; done; }
trap 'stop; [ -n "$E2E_KEEP" ] && echo "logs: $TMP" || rm -rf $TMP' EXIT
for i in $(seq 60); do curl -sf 127.0.0.1:8797/health >/dev/null && curl -sf 127.0.0.1:5197/ >/dev/null && break; sleep 1; done
fail=0
# each spec starts from an empty run store: otherwise Studio opens on the previous spec's newest run (e.g. the whole
# RCRV), and loading it on software GL starves the page while the next spec clicks
for s in ${@:-e2e/*.spec.mjs}; do rm -rf $TMP/runs/* $TMP/*.json $TMP/revisions $TMP/revisions.sqlite; node "$s" || fail=1; done
exit $fail
