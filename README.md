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
| `portal/` | Web portal (Vite + React + TS + That Open Engine): Inbox, Thread, Model, Rules, Mapping, Simulate |
| `scripts/deploy_vm.sh`, `scripts/setup_freecad_mac.sh` | Hosted deployment (Caddy HTTPS + basic auth, systemd) and the one-line Mac setup |
| `tests/` | Rule tests (violation, control, exact threshold), handoff contract, impact, guards |

## Try it

| | |
|---|---|
| **Web portal (hosted)** | https://34-88-130-224.sslip.io (user `sonariq`; ask the team for the password) |
| **Downloads** | https://34-88-130-224.sslip.io/downloads/ (FreeCAD add-on, demo IFC models, Mac setup script) |
| **FreeCAD** | 1.0.x, free: https://www.freecad.org/downloads.php |

The rule engine, AI and simulation run on the server. On your own computer you only need **FreeCAD** and the
**SonarIQ add-on**: the panel uploads the IFC you open to the hosted engine and shows the results in FreeCAD.

### macOS: one command (about 5 minutes)

```bash
curl -fsSL -u sonariq https://34-88-130-224.sslip.io/downloads/setup_freecad_mac.sh -o setup_sonariq.sh && bash setup_sonariq.sh
```

curl asks for the password once, then the script asks for it again (it writes it to `~/.sonariq.json` for the panel). It:
1. installs FreeCAD with Homebrew if it is missing (or tells you to download it from https://www.freecad.org/downloads.php
   and drag it to Applications: pick the Apple Silicon build on M1–M4 Macs, Intel otherwise);
2. installs the add-on into `~/Library/Application Support/FreeCAD/Mod/SonarIQ` (and `v1-1/Mod` for FreeCAD 1.1);
3. downloads the demo models to `~/SonarIQ/` (`deck5_revA.ifc`, `deck5_revB.ifc`, `deck5_revB_fix2.ifc`, `rcrv_deck_7.ifc`);
4. writes the panel settings to `~/.sonariq.json` (engine URL + login);
5. checks that the engine answers.

Then in FreeCAD: **File → Open → `~/SonarIQ/deck5_revA.ifc`** (close the BIM welcome dialog if it appears). The SonarIQ
panel docks on the right; press **Analyse** (Ctrl+Shift+A). Expected on Rev A: **96 checks · 1 Fail · 1 Warning ·
1 Cannot verify · 89 Pass · 4 Dormant**. Click **F-01**: door FD-5-165P is selected and coloured. Rev B (`deck5_revB.ifc`)
gives 4 · 1 · 1 · 86 · 4 with F-07 (Stair 3B, 1,380 mm required vs 1,350 mm). The full checklist is in
`docs/LOCAL_TESTING.md`.

If macOS blocks FreeCAD on first launch: System Settings → Privacy & Security → *Open Anyway*. If the panel does not
appear: View → Panels → Python console, `import sonariq_panel; sonariq_panel.show_in_freecad()`.

### Windows / Linux (manual, about 10 minutes)

1. Install FreeCAD 1.0 from https://www.freecad.org/downloads.php.
2. Download `SonarIQ-addon.zip` and the models from https://34-88-130-224.sslip.io/downloads/ and unzip the add-on into
   FreeCAD's `Mod` folder (`App.getUserAppDataDir()` in FreeCAD's Python console shows the folder; on Windows usually
   `%APPDATA%\FreeCAD\Mod`, on Linux `~/.local/share/FreeCAD/Mod`).
3. Create `~/.sonariq.json` (Windows: `C:\Users\<you>\.sonariq.json`):
   ```json
   {"engine": "https://34-88-130-224.sslip.io/api", "user": "sonariq", "password": "<password>"}
   ```
4. Restart FreeCAD, open a model, press **Analyse**.

### Everything on your own machine (developers)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # Python 3.11 + deps
# Node.js 20+ for the portal: https://nodejs.org/en/download
git clone <repo or sonariq.bundle from /downloads> ~/sonariq && cd ~/sonariq
make setup       # uv sync + portal npm install
make test        # builds the test deck, runs the tests
make api         # engine on http://127.0.0.1:8765 (make api-sim = with Simulate)
make portal      # portal on http://localhost:5173
make mcp         # MCP server on stdio
```
Link the add-on instead of copying it (`ln -s ~/sonariq/freecad_addon/SonarIQ "<Mod folder>/SonarIQ"`) and delete
`~/.sonariq.json`, so the panel uses the local engine (it then sends the file path instead of uploading).
`make bench` (Analyse < 3 s, ping < 2 s), `make qa` (rewrites `docs/meyer_qa1.md`), `make eval` (benchmarks, see `docs/EVAL.md`).

### Hosting (the VM)

`scripts/deploy_vm.sh` deploys branch `main` (or `BRANCH=...`) from a separate worktree (`~/sonariq-deploy`): engine as a
systemd user service (`sonariq-api`, 127.0.0.1:8780, `SONARIQ_HOSTED=1` so only files under `data/` can be opened,
Simulate on), the built portal and the downloads in `/srv/sonariq`, and Caddy on `https://<ip>.sslip.io` with a
Let's Encrypt certificate and basic auth (password in `~/.sonariq_deploy`). Re-run it after merging to `main`.
Logs: `journalctl --user -u sonariq-api -f`, `sudo journalctl -u caddy -f`.

## AI explanations (optional)

The engine needs no AI and no network. Explanations use Gemini (`gemini-3.5-flash`) on Vertex AI, EU multi-region location `eu`, through the Google Gen AI SDK with Application Default Credentials (on a Mac: `gcloud auth application-default login`) (`GEMINI_MODEL`, `GEMINI_LOCATION`, `GOOGLE_CLOUD_PROJECT`; `SONARIQ_AI=off` turns it off). Every explanation is checked: if it contains a number that is not in the facts it was given, it is thrown away and the engine's own wording is shown. Slow answers (> 8 s) also fall back to the engine text. Answers are cached on disk (`data/cache/ai/`). The model sits behind `engine/sonariq/llm.py:Gateway`, so it can be swapped.

## Simulate (evacuation, behind `SIMULATE_ENABLED`)

`make api-sim` starts the engine with Simulate on (`make api` keeps it off). Rules and simulation compute; AI only suggests and explains; the engineer decides.

- **Model**: JuPedSim CollisionFreeSpeedModel on the Deck 5 walkable area read from the IFC (spaces − walls + door openings); Stairs 3A and 3B are capacity-limited exits with a queue on each landing, shared with timed inflows from Decks 4, 6, 7 (`persons_by_deck`). Parameters: `engine/sim/params.yaml` (MSC.1/Circ.1533 paragraph refs, status *verify*). Details: `docs/SIMULATE.md`.
- **Use it**: panel **Simulate** or chat (*simulate a night evacuation*, *what if Stair 3B is out?*, *fire near stair 3A*); portal **Simulate** (W9 setup, W10 results + replay, compare + fix explorer).
- **Every result screen says**: Deck 5 sub-model with inflows from Decks 4, 6, 7 · design insight, not a full-ship Circ.1533 analysis.
- `make sim-precompute` caches the demo simulations (500 runs each) and writes `docs/DEMO_SCRIPT.md` from the results. `make eval` runs the rules benchmark, simulation sanity checks, AI evals and the golden path, and appends to `docs/EVAL.md`.

## Sources (RAG)

Public sources only: MSC.1/Circ.1533, 2010 ADA Standards, the proposed PVAG, COLREG rules text, our rule readings and Q&A notes (no SOLAS/FSS text; DNV link only). `make rag` rebuilds the local index (`data/rag/`, embeddings `text-embedding-005` in europe-west4) from `data/rag/src/`. Used for **Source text** on evidence cards, cited answers to *why* questions, and **Draft rule from clause** (saved to `rules/drafts/`, never run until a human moves it into the rulebook). RAG never sets a verdict.

## RCRV (real ship)

`make rcrv` runs the cloud conversion. The file is public. Production would use an on-premises converter. Outputs: `data/rcrv/rcrv_full.ifc` (portal), `data/rcrv/rcrv_deck_<n>.ifc` (FreeCAD), `data/rcrv/mapping_review.csv` (portal W5), `docs/rcrv_report.md`. Large outputs are not committed.

## Rules of the house

- Verdicts come only from the rule engine. AI text is labelled and number-checked.
- Missing data → **Cannot verify**, never Pass, never a guess.
- Only four model edits exist: add cabin block, move wall, set door width, set door fire class. The guard is code.
- Secrets live in `.env` (git-ignored).
