# Phase 0 audit (14 Nov 2026)

Everything below was checked on this VM unless marked **not checked**.

## Branches

- `feat/whole-ship-viewer` = `feature/simulate` = 75342a2. `main` (2aef3c5) has the same tree (`git diff HEAD main`
  is empty); it only adds 24 merge commits. No other branches, no stashes. Nothing of this milestone was started in git.
- Untracked before this session: `docs/milestones/`, `spikes/b1/` (an earlier session's spike, see below), `graphify-out/`.

## Layout and how to run

- `engine/sonariq` (FastAPI `api.py`, `model.py`, `engine.py`, `checks.py`, `rules.py`, `bcf.py`, `llm.py`, `rag.py`),
  `engine/sim`, `engine/mcp_server.py`, `rules/seed_rules.yaml` (15 rules), `portal/` (React + Vite),
  `freecad_addon/SonarIQ`, `scripts/`, `tests/`, `design/` (tokens + CSS, aliased as `@design`).
- `make setup`, `make api` (8765), `make portal` (5173), `make test`. Python 3.11 venv via uv.
- Tests: `PYTHONPATH=engine:. .venv/bin/python -m pytest -q` → **82 passed in 18 s**.
- Golden path holds and is covered by `tests/test_contract.py` and `tests/test_rules.py`: Rev A 1 fail (F-01);
  Rev B fails F-01, F-07 (Stair 3B 1,350 mm against 1,380 mm), F-08 (dead end 4.2 m against 1.2 m), F-09 (850 against 900 mm).
  Load 0.8 s, analyse 0.01–0.04 s.

## Broken on a clean checkout

- `npm run build` fails: `tsc -b` reports 2 unused-variable errors in `portal/src/App.tsx` (lines 67, 105). The deploy
  scripts avoid it by calling `npx vite build` directly.
- `npx eslint .` reports 75 problems (56 errors, mostly `no-explicit-any`).
- No CI (`.github/` absent), no Playwright in the repo, no `tests/ground_truth/`, no `config/discipline_mapping.yaml`.

## Versions (installed)

`@thatopen/components` 2.3.0, `@thatopen/fragments` 2.3.0, `web-ifc` 0.0.59, `three` 0.160.1, `camera-controls` 2.7.3,
`three-mesh-bvh` 0.7.0. All MIT. `@thatopen/components-front` is not installed. Current Fragments is 3.6.1 with a
different API (worker-based `FragmentsModels`, `IfcImporter`); the spike uses 3.6.1 + three 0.182 + web-ifc 0.0.79.

## How models load today

- `portal/src/screens/Studio.tsx`: fetches the run's IFC (`GET /runs/<id>/ifc` or `/model-file`) and parses it in the
  browser with `OBC.IfcLoader` (web-ifc WASM from `portal/public/wasm`, own origin). Upload cap 60 MB, IFC4 only.
- No server-side conversion, no cache, no metadata index, no `POST /models`.
- **The RCRV IFC is mostly boxes**: `scripts/rcrv_to_ifc.py` writes real triangles for 1,071 of 86,308 objects (doors,
  windows, stairs, bulkheads) and an 8-vertex box for the rest. The real meshes exist only in
  `data/rcrv/gltf/` (313 MB glTF JSON + 160 `.bin`, 2.2 GB). So a whole-ship view must be built from the glTF.
- Source glTF: 303,504 mesh nodes, 175,659 meshes, **50.84 M triangles** instanced, 90,331 engine objects.
- Where the time goes for the largest model the Studio can open today (`rcrv_deck_1.ifc`, 46 MB, mostly boxes): web-ifc
  parse + triangulation on the main thread in the browser, then one `EdgesGeometry` pass per fragment (skipped above
  3 M vertices). Not timed per phase here; the whole-ship path replaces it (DECISIONS M1).


## Built / partial / missing

| Feature | State | Where |
|---|---|---|
| Whole-ship view | **missing** — one IFC per run, parsed in the browser; RCRV IFC is boxes | `portal/src/screens/Studio.tsx:64` |
| X-ray | partial — every element grey + edges, focused element outlined on top | `Studio.tsx:118` (`ghost`) |
| Section plane / blade / caps | **missing** | — |
| Discipline filter (viewer) | **missing** — DISCS chips choose rule packs, not visibility | `Studio.tsx:17` |
| Section at finding | **missing** | — |
| Deck slider | **missing** | — |
| Dimension overlays | partial — 2D lines + HTML labels from `overlaySpec` for 4 rules | `Studio.tsx:37`, `:191` |
| BCF export | built (2.1, GUID selection, pins as viewpoints) | `engine/sonariq/bcf.py`, `POST /export/bcf` |
| Saved viewpoints | partial — simulation pins only; no named views in Studio | `api.py:789` |
| Isolate / show all | built for the focused finding | `Studio.tsx:211` |
| Linked Inbox ↔ Studio | partial — Studio → Thread; no Inbox → Studio jump to a finding | `App.tsx:111` |
| Source IDs from the CAD tool | partial — RCRV dbid in `properties.sqlite` / mapping CSV; IFC `Tag` not read by the engine | `scripts/rcrv_to_ifc.py`, `model.py` |
| Server-side conversion, metadata index, `POST /models` (A1) | **missing** | — |
| Readiness report (B2) | **missing** (mapping CSV lists unmapped RCRV objects) | `GET /rcrv/mapping` |
| Structure & systems pack (B3) | **missing** — only R-DNV-01 deck plate thickness on deck5 (to verify) | `rules/seed_rules.yaml` |
| Provenance (B4) | partial — `formula.inputs[].source` on R-FLS-03 | `checks.py` (`stair_width_formula`) |
| Ground truth + banner (B5) | partial — `make eval` planted-violation benchmark 12/12; no per-scenario YAML, no independent scan, no banner | `scripts/eval.py`, `docs/EVAL.md` |
| Findings at scale (B6) | **missing** — flat card list | `Studio.tsx:405` |
| Traceability, report, CSV (B7) | partial — reports freeze a run (`/reports`); no matrix, no CSV | `api.py:312` |
| Demo run-through (B8) | **missing** (scripted text only: `docs/DEMO_SCRIPT.md`) | — |
| Kept edge (B9): simulation, AI + guard, BCF, FreeCAD, revision diff | built | `engine/sim`, `llm.py`, `bcf.py`, `freecad_addon`, `GET /runs/diff` |
| Hosting (B10) | built — Caddy + HTTPS on the VM, gzip; no long cache headers for model files yet | `scripts/caddy_write.sh` |

## Spec claims that do not match the repo

- Finding schema: the real keys are `rule`, `check_key`, `status`, `element {guid, name, ifc_class}`, `location
  {deck, frame, side, label}`, `required`, `measured`, `margin`, `formula {text, inputs[]}`, `evidence {guids, related,
  bbox, z}`. There is no `rule_id`, `entity_ids`, `clause {…}` object or `evidence.geometry_mm`.
- There are no discipline colour tokens in `design/sonariq.css`; the eight colours are hex literals in `Studio.tsx`.
- `formula.inputs[].source` already exists (`model`, `persons_by_deck`): the seed for provenance (B4).

## What the models contain (grounds B2/B3)

**deck5_revA / revB** (IFC4, metres, one storey): 85/90 spaces with category, deck, frame, side, MVZ (12 corridors,
58/62 cabins with berths); 68 doors, 67 with `FireRating`, 68 with `SelfClosing`; 75/80 walls all with `FireRating`;
2 stairs with `persons_by_deck`; 12 plates **without thickness or grade properties**; no `IfcMaterial`; no `Tag`.

**RCRV** (`spikes/b1/inspect_readiness.py`, 90,331 objects, model units inches):

| What | Count | Data present |
|---|---|---|
| Spaces, corridors, room names | 0 | none: fire/escape packs are Not possible |
| Doors / hatches | 149 / 128 | fire class only inside the name (e.g. "A-CLASS DOOR MA60CX"), no property |
| Plates | 9,716 | thickness 100 %, material 100 %, ShipConstructor PartGUID 100 %, SWBS-like code (`V1`) 8,922 |
| Stiffeners | 11,771 | material 100 %, profile name, PartGUID 100 %; no thickness property |
| Pipes | 43,678 | DWG block attributes on 42,845; a material-like value on 39,145 |
| Ducts / cable tray | 7,364 / 3,861 | almost no properties |

- Plate grades: CS ABS A 6,828, AL 5083-H116 2,493, ABS B 38, D 27, DH36 9, EH36 8, AH36 2; non-hull entries such as
  `DETA COUPLE` 118, `SS 316L` 109, `AIR AIR` 20 (a data-quality hit). Thickness is a fraction string (`5/16"`).
- Pipe systems (48), e.g. FUEL OIL - 541: 1,544 parts, LUBE OIL - 542: 697, FO OVERFLOW AND VENT: 847. Fuel oil
  materials are mostly ASTM A106 Gr B / A105 / A234 WPB, with 18 `ASTM B210` (aluminium tube), 13 ductile iron,
  1 bronze, 1 aluminium and 210 without a material value: real candidates for SOLAS II-2/4.2.2.5.1.
- **Risk:** the pipe attribute *names* were lost in `properties.jsonl` (every attribute is keyed
  `LcOpDwgAttribTag`, positions shift when a value is empty). Material is found by pattern for now, and that also
  matches insulation specs (`ASTM F683-10`, 6,835). Re-extract with display names from the SVF property database, or
  keep pattern matching and say so. **Not checked** whether the display names survive in the APS database.
- Error values: `Error` ×2, `---` ×2, `<None>` ×17.
- IACS UR S6 applies to ships of 90 m and above; RCRV geometry is 66.7 m long. The steel grade vs thickness rule must
  be Not applicable or informative on RCRV, with the reason shown. Official table text is not in the repo.

## Spike B1 status

Option 2, glTF tiles (done by an earlier session, numbers in `data/rcrv/spike_b1/`):

| Measure | Value |
|---|---|
| Conversion glTF → 565 raw tiles | 38 s, peak 1.8 GB RSS |
| Meshopt pack + integrity check | 31 s; 999 MB → **205 MB**; 0 vertex and 0 triangle mismatches |
| Max quantisation deviation | 0.16 mm |
| First frame (headless, software GL) | 1.0–1.2 s; overview (4.0 M triangles, 271 draw calls) complete at 3.3 s |
| Close-up with streaming | 227–233 draw calls, 5.06 M triangles, 130 MB JS heap, 1.5 GB browser RSS |
| Picking | 49/60 right on the first hit, **60/60** after hiding enclosing parts |
| fps | 0.55–0.6 with SwiftShader: **not a valid fps number**; this VM has no GPU |

Option 1, Fragments 3.6.1: see `docs/DECISIONS.md` M1 for the measured comparison and the choice.
