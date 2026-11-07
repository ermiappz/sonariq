# Local testing (FreeCAD panel, portal, MCP), Sat 7 Nov

Written for macOS; Linux works the same (FreeCAD `Mod` folder: `~/.local/share/FreeCAD/Mod`).
The engine must run **on your machine**, because the FreeCAD panel sends it the path of the open IFC file.
`main` = `feature/simulate` with Simulate **off** by default.

## 1. Downloads

### From the VM (`mamo`), files in `~/sonariq/downloads/`

| File | Size | What it is | Needed? |
|---|---|---|---|
| `sonariq.bundle` | 23 MB | The git repo (`main` + `feature/simulate`); there is no git remote | **Yes** |
| `sonariq_cache.tgz` | 1.2 MB | `data/cache/`: cached AI explanations + the 500-run demo simulations | Recommended (AI cards work without gcloud; Simulate results open instantly) |
| `sonariq_rcrv.tgz` | 6.9 MB | RCRV mapping review CSV + RCRV Deck 3 and Deck 7 IFC | Optional (portal "Mapping review", RCRV checks) |

```bash
# use the same route you SSH in with, e.g.
gcloud compute scp "mamo:~/sonariq/downloads/*" ~/Downloads/ --zone <zone>
# or: scp ermias@<vm>:~/sonariq/downloads/* ~/Downloads/
```

### Software

| Tool | Version | Download |
|---|---|---|
| uv (Python 3.11 + deps) | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js (portal) | 20 LTS or newer | https://nodejs.org/en/download (or `brew install node`) |
| FreeCAD | 1.0.x | https://www.freecad.org/downloads.php |
| Google Cloud CLI (optional, live AI) | latest | https://cloud.google.com/sdk/docs/install |

## 2. Install

```bash
git clone -b main ~/Downloads/sonariq.bundle ~/sonariq && cd ~/sonariq
tar xzf ~/Downloads/sonariq_cache.tgz          # optional, recommended
tar xzf ~/Downloads/sonariq_rcrv.tgz           # optional
make setup        # uv sync --python 3.11 + portal npm install
make test         # expect: 63 passed
```

Already have a clone from the earlier bundle? `cd ~/sonariq && git fetch ~/Downloads/sonariq.bundle main:main feature/simulate:feature/simulate && git checkout main`
(if `main` is checked out, run `git checkout --detach` first, then fetch, then `git checkout main`).

**FreeCAD add-on** (one symlink):
```bash
MOD="$HOME/Library/Application Support/FreeCAD/Mod"   # FreeCAD 1.1: .../FreeCAD/v1-1/Mod
mkdir -p "$MOD" && ln -sf ~/sonariq/freecad_addon/SonarIQ "$MOD/SonarIQ"
```
Check in FreeCAD's Python console: `App.getUserAppDataDir()` shows the right folder; `import ifcopenshell` must work
(if not: BIM workbench → Utils → IfcOpenShell installer).

**AI (optional)**: `cp .env.example .env`, then `gcloud auth application-default login`. Without it the cards say
"Rule engine text" (or use the cached explanations from `sonariq_cache.tgz`). Nothing else depends on the AI.

## 3. Run

| Terminal | Command | Port |
|---|---|---|
| 1 | `make api` (Simulate off) or `make api-sim` (Simulate on) | 8765 |
| 2 | `make portal` | http://localhost:5173 |
| 3 (optional) | `make mcp` (stdio MCP server for an AI client) | — |

## 4. Test checklist

### FreeCAD panel
1. File → Open `~/sonariq/data/deck5_revA.ifc` (default NativeIFC importer; close the BIM Welcome dialog if shown).
   The SonarIQ panel docks on the right (if not: `import sonariq_panel; sonariq_panel.show_in_freecad()`).
2. **Analyse** (Ctrl+Shift+A) → **96 checks · 1 · 1 · 1 · 89 · 4**.
3. Click **F-01** → FD-5-165P turns orange and is selected; evidence card shows required A-60 / measured A-0, source text.
4. Open `deck5_revB.ifc` → Analyse → **4 · 1 · 1 · 86 · 4**. Click **F-07** → N₁ 68, 44, 40, 24 = **1,380 mm** vs 1,350.
   Fix options: 1,400 ✓ (needs Structure), 1,340 ✓, 1,320 ✓, "move 10 frames" ✕ rejected.
5. `deck5_revB_fix2.ifc` → **3 · 1 · 1 · 87 · 4**.
6. Chat tab: `set FD-5-165P to A-60` → preview → confirm → F-01 clears. `put a sauna in the lounge` → refused.
   `simulate night` with `make api` → "Simulate is off…" (with `make api-sim` → scenario preview).
7. RCRV (optional): the panel works on `data/rcrv/rcrv_deck_7.ifc`, but FreeCAD's own IFC import of RCRV decks is
   slow (minutes, thousands of mesh objects). Faster: `curl -s -XPOST localhost:8765/analyse -H 'content-type: application/json' -d '{"path":"data/rcrv/rcrv_deck_3.ifc"}' | head -c 400`
   → 41 checks, whole model (no Deck 5 in the file), F-02 door 29.4 in (748 mm). The door width is an upper bound; measure before showing.

### Portal (http://localhost:5173)
- **Projects** → Demo ship card shows the engine counts.
- **Inbox (W2)** per discipline → click F-08 → **Thread (W3)**: evidence card + source text; Approve / Request change / Decline (reason required for the last two).
- **Model (W4)**: That Open viewer with finding pins; list on the right.
- **Rules (W6)**: 15 rules; "Draft rule from clause" (needs gcloud; drafts never run until moved into the rulebook).
- **Mapping review (W5)**: needs `sonariq_rcrv.tgz`.
- **Simulate (W9/W10)**, with `make api-sim` only: saved 500-run results open from the list if you extracted `sonariq_cache.tgz`; new runs on a laptop take minutes.

### MCP
`make mcp` exposes analyse, get_finding, explain, propose_fixes, apply_edit (preview → confirm), recheck, export_bcf,
sources, open_revision; with `SIMULATE_ENABLED=1` also simulate / simulation_status / simulation_results.

## 5. Fixed today (so you don't hit them)
- `make test` no longer rewrites `data/*.ifc` with new GUIDs (git stays clean).
- FreeCAD panel crashed on non-UTF-8 locales (e.g. FreeCAD started from Finder without `LANG`). Fixed.
- Analysing a file without Deck 5 (RCRV decks) showed 0 checks → now falls back to the whole model and says so.
- After opening a file by path, switching back to Rev A kept the old model → now reloads.
- Chat: "night with FD-5-165P out" / "FD-5-165P is closed" now start a scenario. With Simulate off, chat says so.
- Portal: Model list pill overlap, Rules id/clause wrapping, W10 queue chart now shows the stair with the longest p95 queue.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Panel: "Engine not reachable" | `make api` not running, or another port: `export SONARIQ_ENGINE=http://127.0.0.1:8765` before starting FreeCAD |
| Port 8765/5173 busy | stop the old process (`lsof -i :8765`) |
| `make setup` fails on Python | `uv python install 3.11` |
| Viewer blank | hard refresh; check `portal/public/wasm/` exists after `npm install` |
