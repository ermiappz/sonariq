#!/usr/bin/env bash
# SonarIQ on a Mac: FreeCAD + the SonarIQ panel, talking to the engine hosted on the VM.
# Nothing else is installed (no Python, Node or repo): rules, AI and simulation run on the VM.
#
#   curl -fsSL -u __USER__ __URL__/downloads/setup_freecad_mac.sh -o setup_sonariq.sh && bash setup_sonariq.sh
#
# (deploy_vm.sh fills in the URL and user when it publishes this script.)
set -euo pipefail

URL="__URL__"
SQ_USER="__USER__"
PASS="${SONARIQ_PASSWORD:-${1:-}}"
if [ -z "$PASS" ]; then
  read -r -s -p "SonarIQ password: " PASS </dev/tty
  echo
fi
DEST="$HOME/SonarIQ"
mkdir -p "$DEST"
dl() { curl -fsSL -u "$SQ_USER:$PASS" "$URL/downloads/$1" -o "$2"; }

echo "1/5 Checking the password and the engine…"
curl -fsS -u "$SQ_USER:$PASS" "$URL/api/health" >/dev/null || { echo "Wrong password or engine down ($URL)."; exit 1; }

echo "2/5 FreeCAD…"
if [ -n "${SONARIQ_SKIP_FREECAD:-}" ] || [ -d /Applications/FreeCAD.app ]; then
  echo "    found /Applications/FreeCAD.app"
elif command -v brew >/dev/null 2>&1; then
  brew install --cask freecad
else
  echo "    FreeCAD is not installed and Homebrew is missing."
  echo "    Download FreeCAD 1.0 for macOS (Apple Silicon or Intel) from https://www.freecad.org/downloads.php,"
  echo "    drag it to Applications, then run this script again."
  open "https://www.freecad.org/downloads.php" || true
  exit 1
fi

echo "3/5 SonarIQ add-on…"
dl SonarIQ-addon.zip "$DEST/SonarIQ-addon.zip"
for MOD in "$HOME/Library/Application Support/FreeCAD/Mod" "$HOME/Library/Application Support/FreeCAD/v1-1/Mod"; do
  mkdir -p "$MOD"
  rm -rf "$MOD/SonarIQ"
  unzip -q -o "$DEST/SonarIQ-addon.zip" -d "$MOD"
done

echo "4/5 Demo models → $DEST"
for f in deck5_revA.ifc deck5_revB.ifc deck5_revB_fix2.ifc; do
  dl "models/$f" "$DEST/$f"
done
dl models/rcrv_deck_7.ifc "$DEST/rcrv_deck_7.ifc" 2>/dev/null || true

echo "5/5 Panel settings → ~/.sonariq.json"
( umask 077
  printf '{"engine": "%s/api", "user": "%s", "password": "%s"}\n' "$URL" "$SQ_USER" "$PASS" > "$HOME/.sonariq.json" )

echo
echo "Done. In FreeCAD: File → Open → $DEST/deck5_revA.ifc, then press Analyse in the SonarIQ panel"
echo "(expect 96 checks: 1 · 1 · 1 · 89 · 4). Portal: $URL"
[ -n "${SONARIQ_SKIP_FREECAD:-}" ] || open -a FreeCAD || true
