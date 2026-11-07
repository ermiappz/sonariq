# SonarIQ

**A co-pilot inside the ship design tool. When an engineer changes something, it says which safety rules break, where, and why.**

Since AI 2026 · Meyer Turku challenge. One deterministic rule engine serves three surfaces: a FreeCAD dock panel, a web portal for discipline reviewers, and an MCP server any AI client or CAD adapter can call. See `docs/SPEC.md`.

| Path | What |
|---|---|
| `engine/sonariq/` | IFC4 → model, rule checks, analyse, impact (ping), the four edits, fixes, BCF, AI guard, HTTP API |
| `engine/mcp_server.py` | MCP server: analyse, get_finding, explain, propose_fixes, apply_edit, recheck, export_bcf |
| `rules/seed_rules.yaml` | The 15 rules: clause, reading, thresholds, status. Thresholds live here, not in code. |
| `scripts/make_deck.py` | Writes the Deck 5 test model: `data/deck5_revA.ifc`, `deck5_revB.ifc` (OR-117), `deck5_revB_fix2.ifc` |
| `scripts/aps_translate.py`, `scripts/node/svf_to_gltf.js`, `scripts/rcrv_cache.py`, `scripts/rcrv_to_ifc.py` | RCRV .nwd → SVF → glTF + properties → IFC4 |
| `freecad_addon/SonarIQ/` | FreeCAD 1.x dock panel (P1, P3, P4), styled by `design/panel.qss` |
| `portal/` | Vite + React + TS + Tailwind + That Open Engine (scaffold; screens in build round 1) |
| `tests/` | Rule tests (violation, control, exact threshold), handoff contract, impact, guards |

## Quick start (Linux or macOS)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # once
uv sync --python 3.11                              # engine deps
make test        # builds the test deck, runs 49 tests
make api         # engine HTTP API on http://127.0.0.1:8765 (the FreeCAD panel talks to this)
make mcp         # MCP server on stdio
make bench       # timing gate: Analyse < 3 s, ping < 2 s
make qa          # rewrites docs/meyer_qa1.md from live engine runs
```

## FreeCAD on macOS (about 15 minutes)

1. Install FreeCAD 1.x from freecad.org (Apple Silicon or Intel build). Open it once, then quit.
2. Check IfcOpenShell: open View → Panels → Python console and type `import ifcopenshell`. If that errors, use BIM workbench → Utils → IfcOpenShell installer.
3. Get the repo and the engine:
   ```bash
   git clone <repo> ~/sonariq && cd ~/sonariq
   curl -LsSf https://astral.sh/uv/install.sh | sh
   uv sync --python 3.11 && make test
   ```
4. Install the add-on. It is a symlink, so `git pull` updates it. The folder depends on the FreeCAD version: open the Python console and run `App.getUserAppDataDir()`, then link into its `Mod` folder:
   ```bash
   MOD="$HOME/Library/Application Support/FreeCAD/Mod"        # FreeCAD 1.0
   # MOD="$HOME/Library/Application Support/FreeCAD/v1-1/Mod"  # FreeCAD 1.1
   mkdir -p "$MOD" && ln -s ~/sonariq/freecad_addon/SonarIQ "$MOD/SonarIQ"
   ```
5. Start the engine in a terminal and leave it running: `cd ~/sonariq && make api`.
6. Start FreeCAD and open `~/sonariq/data/deck5_revA.ifc` (File → Open; FreeCAD 1.x opens IFC natively). The SonarIQ panel docks on the right after about 2 seconds. If it doesn't, run in the Python console: `import sonariq_panel; sonariq_panel.show_in_freecad()`.
7. Press **Analyse** (or Ctrl+Shift+A). Expected on Rev A: 96 checks, 1 Fail · 1 Warning · 1 Cannot verify · 89 Pass · 4 Dormant. Click **F-01**: door FD-5-165P is selected and coloured in the 3D view, and the evidence card opens.
8. For Rev B, open `data/deck5_revB.ifc` and press Analyse again. The panel sends the open file's path, so the engine checks whichever IFC is open.

If the panel says "Engine not reachable", the API is not running (step 5). Set `SONARIQ_ENGINE=http://host:8765` before starting FreeCAD to use an engine on another machine.

## AI explanations (optional)

The engine needs no AI and no network. To turn on explanations, set `LLM_BASE_URL` and `LLM_MODEL` in `.env`; any OpenAI-compatible endpoint works (see `.env.example`). Every explanation is checked: if it contains a number that is not in the finding, it is thrown away and the engine's own wording is shown. The demo uses an open Qwen model on Vertex AI (managed API). Production would deploy the same open model in an EU region (GCP europe-north1) or on Meyer's own servers. Status: `docs/BLOCKERS.md`.

## RCRV (real ship)

`make rcrv` runs the cloud conversion. The file is public. Production would use an on-premises converter. Outputs: `data/rcrv/rcrv_full.ifc` (portal), `data/rcrv/rcrv_deck_<n>.ifc` (FreeCAD), `data/rcrv/mapping_review.csv` (portal W5), `docs/rcrv_report.md`. Large outputs are not committed.

## Rules of the house

- Verdicts come only from the rule engine. AI text is labelled and number-checked.
- Missing data → **Cannot verify**, never Pass, never a guess.
- Only four model edits exist: add cabin block, move wall, set door width, set door fire class. The guard is code.
- Secrets live in `.env` (git-ignored).
