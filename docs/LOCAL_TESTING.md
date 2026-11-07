# Testing SonarIQ · hosted portal + FreeCAD on your Mac

Everything except FreeCAD runs on the VM (`mamo`). Your Mac needs only FreeCAD and the SonarIQ add-on: the panel
uploads the IFC you open to the hosted engine and draws the results in FreeCAD.

| | |
|---|---|
| Portal | https://34-88-130-224.sslip.io |
| Downloads | https://34-88-130-224.sslip.io/downloads/ |
| Login | user `sonariq`; the password is in `~/.sonariq_deploy` on the VM (`cat ~/.sonariq_deploy`) |
| FreeCAD | 1.0.x · https://www.freecad.org/downloads.php (Apple Silicon build on M1–M4, Intel otherwise) |

## 1. Set up the Mac (one command)

```bash
curl -fsSL -u sonariq https://34-88-130-224.sslip.io/downloads/setup_freecad_mac.sh -o setup_sonariq.sh && bash setup_sonariq.sh
```
Type the password when curl asks, and again when the script asks. The script installs FreeCAD (Homebrew) if it is missing, installs the add-on,
downloads the demo models to `~/SonarIQ/`, writes `~/.sonariq.json` (engine URL + login) and checks the engine.
No Homebrew? Install FreeCAD from the link above, drag it to Applications, run the script again.

Downloads it uses (all under `/downloads/`): `SonarIQ-addon.zip`, `models/deck5_revA.ifc`, `models/deck5_revB.ifc`,
`models/deck5_revB_fix2.ifc`, `models/rcrv_deck_7.ifc`, `models/rcrv_deck_3.ifc`; `sonariq.bundle` is the whole git repo
(only needed for the local developer setup in §5).

## 2. FreeCAD checklist

1. FreeCAD → **File → Open → `~/SonarIQ/deck5_revA.ifc`**. Close the BIM welcome dialog if it appears.
   The SonarIQ panel docks on the right (if not: View → Panels → Python console,
   `import sonariq_panel; sonariq_panel.show_in_freecad()`). The footer says *Rule engine ready*.
2. **Analyse** (Ctrl+Shift+A) → **96 checks · 1 · 1 · 1 · 89 · 4**, meta line says *Rev A*.
3. Click **F-01** → FD-5-165P turns orange and is selected; evidence card: required A-60, measured A-0, source text.
4. Open `deck5_revB.ifc` → Analyse → **4 · 1 · 1 · 86 · 4**, *Rev B*. Click **F-07** → N₁ 68, 44, 40, 24 =
   **1,380 mm** required vs 1,350 mm. Fix options: 1,400 ✓ (needs Structure), 1,340 ✓, 1,320 ✓, "move 10 frames" ✕.
5. `deck5_revB_fix2.ifc` → **3 · 1 · 1 · 87 · 4**.
6. Chat tab: `set FD-5-165P to A-60` → preview → confirm → F-01 clears. `put a sauna in the lounge` → refused.
   `simulate night` → scenario preview → run (500 runs is minutes; cached demo scenarios open at once).
7. **Send to review** → the BCF is saved next to the open IFC (`~/SonarIQ/sonariq_rev-*.bcfzip`).
8. RCRV: `~/SonarIQ/rcrv_deck_7.ifc` → Analyse → no Deck 5 in the file, so the panel switches to *whole model*.
   FreeCAD's own IFC import of RCRV decks is slow (minutes for Deck 3, thousands of mesh objects); that is FreeCAD,
   not the panel.

The panel and the portal share one engine session, so what you analyse in FreeCAD shows in the portal Inbox.

## 3. Portal checklist (https://34-88-130-224.sslip.io)

- **Projects** → Demo ship card with the engine counts; RCRV card.
- **Inbox (W2)** per discipline → click **F-08** → **Thread (W3)**: evidence card + source text; Approve /
  Request change / Decline (a reason is required for the last two).
- **Model (W4)**: That Open viewer with finding pins and the list on the right.
- **Rules (W6)**: 15 rules; *Draft rule from clause* (AI draft, never runs until moved into the rulebook).
- **Mapping review (W5)**: RCRV Navisworks → IFC mapping rows that need a person.
- **Simulate (W9/W10)**: saved 500-run results in the list (Rev A, OR-117 ± fix 2, fire what-if); open one → replay,
  heatmap, queue chart, congestion list, *Try fixes*, 3D toggle.

## 4. If something is off

| Symptom | Fix |
|---|---|
| Panel: *Engine not reachable* | `cat ~/.sonariq.json` on the Mac (URL ends in `/api`, password right); `curl -u sonariq https://34-88-130-224.sslip.io/api/health` |
| Panel: *This document has no IFC file path* | open the `.ifc` with File → Open (not Import, not a saved .FCStd) |
| Portal shows *Engine not reachable* | on the VM: `systemctl --user status sonariq-api`, `journalctl --user -u sonariq-api -n 50` |
| Site down | on the VM: `sudo systemctl status caddy`; redeploy with `scripts/deploy_vm.sh` |

## 5. Optional: everything on the Mac (developers)

```bash
curl -fsSL -u sonariq https://34-88-130-224.sslip.io/downloads/sonariq.bundle -o ~/Downloads/sonariq.bundle
git clone -b main ~/Downloads/sonariq.bundle ~/sonariq && cd ~/sonariq
curl -LsSf https://astral.sh/uv/install.sh | sh     # uv (Python 3.11)
# Node.js 20+: https://nodejs.org/en/download
make setup && make test
make api            # terminal 1 (make api-sim = with Simulate)
make portal         # terminal 2 → http://localhost:5173
mv ~/.sonariq.json ~/.sonariq.hosted.json   # the panel then uses the local engine on 127.0.0.1:8765
```

## Fixed on 7 Nov (so you don't hit them)

- The panel could analyse the engine's current model instead of the document on screen (NativeIFC single-document
  mode keeps the path on the document). Fixed; it now refuses rather than guess.
- The panel crashed on non-UTF-8 locales (FreeCAD started from Finder without `LANG`).
- Files without Deck 5 (RCRV decks) gave 0 checks → whole model, with a note.
- After a file opened by path, switching back to Rev A kept the old model.
- `make test` rewrote `data/*.ifc` with new GUIDs (git always dirty).
- Chat: "night with FD-5-165P out", "FD-5-165P is closed" start a scenario; with Simulate off, chat says so.
- Portal: Model list pill overlap, Rules id/clause wrapping, W10 queue chart shows the stair with the longest p95 queue.
