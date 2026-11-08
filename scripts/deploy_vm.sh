#!/usr/bin/env bash
# Deploy SonarIQ (portal + engine API + downloads) on this VM, behind Caddy (HTTPS + basic auth).
#
#   scripts/deploy_vm.sh            # deploy branch main (default)
#   BRANCH=feature/simulate scripts/deploy_vm.sh
#
# Layout
#   ~/sonariq-deploy            detached worktree of the repo at $BRANCH (dev work in ~/sonariq never touches it)
#   ~/.sonariq_deploy           SQ_USER / SQ_PASS for the site (created once, never in git)
#   /srv/sonariq/portal         built portal (vite build)
#   /srv/sonariq/downloads      FreeCAD add-on zip, demo IFCs, Mac setup script, git bundle
#   systemd --user sonariq-api  uvicorn on 127.0.0.1:$PORT (SONARIQ_HOSTED=1, Simulate on)
#   /etc/caddy/Caddyfile        scripts/caddy_write.sh: v2 = public portal + /downloads, /api by portal key or login (panel)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="${BRANCH:-main}"
DEPLOY="${DEPLOY:-$HOME/sonariq-deploy}"
PORT="${PORT:-8780}"
SRV=/srv/sonariq
SIM="${SIMULATE_ENABLED:-1}"

IP="$(curl -fs -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip \
  || curl -fs https://ifconfig.me)"
HOST="${SQ_HOST:-${IP//./-}.sslip.io}"
# Bind Caddy to the NIC address only: Tailscale may already hold :443 on its own interface.
NIC="$(curl -fs -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip || hostname -I | awk '{print $1}')"
URL="https://$HOST"

# ---------------------------------------------------------------- credentials (once)
CRED="$HOME/.sonariq_deploy"
if [ ! -f "$CRED" ]; then
  umask 077
  printf 'SQ_USER=sonariq\nSQ_PASS=%s\n' "$(python3 -c 'import secrets;print(secrets.token_urlsafe(12))')" > "$CRED"
fi
# shellcheck disable=SC1090
. "$CRED"
# the portal's API key (sent by the browser, so not a secret; it only keeps the API off the open internet). Kept in
# the same git-ignored file; generated once.
if [ -z "${SQ_PORTAL_KEY:-}" ]; then
  SQ_PORTAL_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(9))')"
  printf 'SQ_PORTAL_KEY=%s\n' "$SQ_PORTAL_KEY" >> "$CRED"
fi
export SQ_PORTAL_KEY

echo "==> code: $BRANCH -> $DEPLOY"
if [ ! -d "$DEPLOY/.git" ] && [ ! -f "$DEPLOY/.git" ]; then
  git -C "$REPO" worktree add --detach "$DEPLOY" "$BRANCH"
else
  git -C "$DEPLOY" checkout -q --detach "$BRANCH"
fi
git -C "$DEPLOY" log --oneline -1

# shared, git-ignored data from the dev checkout (AI + simulation caches, RCRV outputs, Gemini config)
mkdir -p "$REPO/data/cache" "$REPO/data/rcrv"
for d in data/cache data/rcrv; do
  [ -L "$DEPLOY/$d" ] || { rm -rf "${DEPLOY:?}/$d"; ln -s "$REPO/$d" "$DEPLOY/$d"; }
done
[ -e "$REPO/.env" ] && ln -sfn "$REPO/.env" "$DEPLOY/.env"

echo "==> engine deps"
(cd "$DEPLOY" && uv sync -q --python 3.11)

echo "==> portal build"
(cd "$DEPLOY/portal" && npm ci --silent --no-audit --no-fund && VITE_SQ_KEY="$SQ_PORTAL_KEY" npx vite build --logLevel error)
sudo mkdir -p "$SRV/portal" "$SRV/downloads/models"
sudo rsync -a --delete "$DEPLOY/portal/dist/" "$SRV/portal/"

echo "==> downloads"
TMP="$(mktemp -d)"
(cd "$DEPLOY/freecad_addon" && zip -qr "$TMP/SonarIQ-addon.zip" SonarIQ -x '*/__pycache__/*' '*.pyc' 'SonarIQ/config.json')
sed -e "s#__URL__#$URL#g" -e "s#__USER__#$SQ_USER#g" "$DEPLOY/scripts/setup_freecad_mac.sh" > "$TMP/setup_freecad_mac.sh"
git -C "$REPO" bundle create "$TMP/sonariq.bundle" main feature/simulate >/dev/null 2>&1 || true
sudo cp "$TMP"/* "$SRV/downloads/"
sudo cp "$DEPLOY"/data/deck5_revA.ifc "$DEPLOY"/data/deck5_revB.ifc "$DEPLOY"/data/deck5_revB_fix2.ifc "$SRV/downloads/models/"
for f in rcrv_deck_7.ifc rcrv_deck_3.ifc; do
  [ -f "$REPO/data/rcrv/$f" ] && sudo cp "$REPO/data/rcrv/$f" "$SRV/downloads/models/"
done
rm -rf "$TMP"
sudo chmod -R a+rX "$SRV"

echo "==> engine service (systemd --user, port $PORT)"
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/sonariq-api.service" <<EOF
[Unit]
Description=SonarIQ engine API (hosted)
After=network-online.target

[Service]
WorkingDirectory=$DEPLOY
Environment=PYTHONPATH=engine:.
Environment=PYTHONUTF8=1
Environment=SONARIQ_HOSTED=1
Environment=SIMULATE_ENABLED=$SIM
ExecStart=$DEPLOY/.venv/bin/python -m uvicorn sonariq.api:app --app-dir engine --host 127.0.0.1 --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable -q sonariq-api
systemctl --user restart sonariq-api

echo "==> caddy ($URL, mode ${CADDY_MODE:-v2})"
HOST="$HOST" NIC="$NIC" PORT="$PORT" SQ_USER="$SQ_USER" SQ_PASS="$SQ_PASS" SQ_PORTAL_KEY="$SQ_PORTAL_KEY" CADDY_MODE="${CADDY_MODE:-v2}" "$REPO/scripts/caddy_write.sh"

echo "==> health"
for _ in $(seq 1 40); do
  curl -fs "http://127.0.0.1:$PORT/health" >/dev/null && break
  sleep 1
done
curl -fs "http://127.0.0.1:$PORT/health" | head -c 200; echo
for _ in $(seq 1 30); do
  # from the VM itself the public IP does not hairpin, so connect to the NIC with the public name (real TLS)
  code="$(curl -s -o /dev/null -w '%{http_code}' --resolve "$HOST:443:$NIC" -u "$SQ_USER:$SQ_PASS" "$URL/api/health" || true)"
  [ "$code" = 200 ] && break
  sleep 2
done
echo "public $URL/api/health -> HTTP ${code:-?}"
echo
echo "Portal:    $URL   (user $SQ_USER, password in $CRED)"
echo "Downloads: $URL/downloads/"
echo "Mac:       curl -fsSL $URL/downloads/setup_freecad_mac.sh -o setup_sonariq.sh && bash setup_sonariq.sh"
