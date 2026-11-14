#!/usr/bin/env bash
# Staging: portal v2 at https://<host>/next, its own engine on 127.0.0.1:8781 (systemd --user sonariq-next).
# The staging engine reads the live run store (so FreeCAD Export links resolve) and keeps its own reports/tasks.
# The live engine (sonariq-api) is not restarted; Caddy is reloaded gracefully with the live part unchanged.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
NEXT="${NEXT:-$HOME/sonariq-next}"
LIVE="${LIVE:-$HOME/sonariq-deploy}"
BRANCH="${BRANCH:-feature/simulate}"
NEXT_PORT="${NEXT_PORT:-8781}"
. "$HOME/.sonariq_deploy"
: "${SQ_PORTAL_KEY:?run scripts/deploy_vm.sh once first (it creates SQ_PORTAL_KEY)}"
if [ ! -e "$NEXT/.git" ]; then git -C "$REPO" worktree add --detach "$NEXT" "$BRANCH"; else git -C "$NEXT" checkout -q --detach "$BRANCH"; fi
git -C "$NEXT" log --oneline -1
mkdir -p "$NEXT/data"
for d in data/cache data/rcrv; do [ -L "$NEXT/$d" ] || { rm -rf "${NEXT:?}/$d"; ln -s "$REPO/$d" "$NEXT/$d"; }; done
[ -e "$REPO/.env" ] && ln -sfn "$REPO/.env" "$NEXT/.env"
(cd "$NEXT" && uv sync -q --python 3.11)
(cd "$NEXT/portal" && npm ci --silent --no-audit --no-fund && VITE_BASE=/next/ VITE_SQ_KEY="$SQ_PORTAL_KEY" npx vite build --logLevel error --outDir dist-next)
sudo mkdir -p /srv/sonariq/next && sudo rsync -a --delete "$NEXT/portal/dist-next/" /srv/sonariq/next/ && sudo chmod -R a+rX /srv/sonariq/next
cat > "$HOME/.config/systemd/user/sonariq-next.service" <<EOF
[Unit]
Description=SonarIQ engine API (staging /next)
[Service]
WorkingDirectory=$NEXT
Environment=PYTHONPATH=engine:.
Environment=PYTHONUTF8=1
Environment=SONARIQ_HOSTED=1
Environment=SIMULATE_ENABLED=1
Environment=SONARIQ_NODE_BIN=$(readlink -f "$(command -v node)")
Environment=SONARIQ_RUNS=$LIVE/data/runs
ExecStart=$NEXT/.venv/bin/python -m uvicorn sonariq.api:app --app-dir engine --host 127.0.0.1 --port $NEXT_PORT
Restart=always
[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload && systemctl --user enable -q sonariq-next && systemctl --user restart sonariq-next
for _ in $(seq 1 40); do curl -fs "http://127.0.0.1:$NEXT_PORT/health" >/dev/null && break; sleep 1; done
IP="$(curl -fs -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip)"
NIC="$(curl -fs -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip)"
HOST="${IP//./-}.sslip.io" NIC="$NIC" PORT=8780 SQ_USER="$SQ_USER" SQ_PASS="$SQ_PASS" SQ_PORTAL_KEY="$SQ_PORTAL_KEY" CADDY_MODE="${CADDY_MODE:-v2}" "$REPO/scripts/caddy_write.sh"
echo "staging: https://${IP//./-}.sslip.io/next/"
