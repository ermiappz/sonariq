# Whole-ship viewer

Why this design: `docs/DECISIONS.md` M1–M10. Plan: `docs/PLAN.md`.

## Pipeline (engine)

```
IFC (2x3 / 4 / 4x3) ──ifcopenshell.geom──┐
RCRV glTF + properties.jsonl ────────────┼─> pipeline/tiles.py ─> raw GLB tiles + elements.json + meta.json + colors.bin
                                         │                      └─> scripts/node/pack_tiles.mjs (Meshopt + integrity check)
                                         └─ discipline: config/discipline_mapping.yaml (class first, then rules)
```

- `POST /models` (upload) or `POST /models/prepare` (`{revision | path | run | source: "rcrv"}`) stores the original
  under `data/models/<sha256[:16]>/original.ifc`, never changed, and converts once in the background.
  `GET /models/<id>` reports `state` and `progress` ("Preparing a fast web version"). Same bytes → same id → no new work.
- `GET /models/<id>/files/{index.json, elements.json, colors.bin, tiles/*.glb}` with
  `Cache-Control: public, max-age=31536000, immutable`. `meta.json` stays on the server; the properties card reads
  `GET /models/<id>/elements/<index>`.
- Rebuild RCRV by hand: `PYTHONPATH=engine:. .venv/bin/python -m sonariq.pipeline.build rcrv data/models/rcrv/web`
  (≈ 2 min, peak ≈ 4 GB), or `POST /models/prepare {"source": "rcrv"}`.

| Model | Elements | Triangles | Tiles | Size | Conversion |
|---|---|---|---|---|---|
| deck5_revB | 258 | 4,244 | 31 | 53 KB | 1.2 s |
| RCRV | 90,331 | 50.8 M | 551 | 196 MB | 111 s (read 42 s) |

Both pack with 0 vertex and 0 triangle mismatches; maximum quantisation error 0.21 mm (deck5) and 0.16 mm (RCRV).

## IDs

`elements.json[i] = [GlobalId, source id, IFC class, name]`; every vertex carries `i`. The viewer's GPU pick returns `i`.
RCRV GlobalIds are the same function `scripts/rcrv_to_ifc.py` uses, so findings on `rcrv_*.ifc` land on the tiles.
Aggregates without geometry (IfcStair → flights, IfcZone → spaces) resolve through `index.json.aliases`.
Proof: `tests/test_pipeline.py` (every finding of Rev B, every product GlobalId of RCRV decks 1, 5, 7) and
`portal/e2e/viewer.spec.mjs` (picks in the browser return the same GlobalId).

## Viewer (portal/src/viewer/ShipViewer.ts)

- Overview tiles first (≤ 4 M triangles), detail tiles streamed within 24 m of the camera (1.5 M triangle budget,
  6 requests in flight); tiles of a focused or picked element are loaded and pinned.
- Element state is one RGBA texture: colour + 0 hidden / 1–254 ghosted (x-ray) / 255 solid. Two passes when anything is
  ghosted (solid, then ghost with blending), one otherwise.
- Hover highlight, click select → properties card (class, GlobalId, source id, deck, discipline, SWBS, system,
  material, grade, thickness, fire rating), isolate / hide / show all, standard views (iso, top, port, starboard, bow,
  stern: bow = +x, port = +y), perspective / orthographic, zoom to cursor, deck selector (clips everything above).

## Tests

- `make test`: pipeline, models API, ID mapping.
- `portal/e2e/run.sh`: throwaway engine (8797) + Vite (5197) + headless Chromium with software GL; screenshots go to
  `docs/screenshots/m*.png`. This VM has no GPU, so frame rates measured here are lower bounds.

## Known limits

- glTF/GLB upload is not converted yet (IFC only); the RCRV glTF is a built-in source.
- Overview = biggest size-per-triangle parts, not exterior-visibility sampling.
- One RCRV sample out of 12 returns no hit in the pick test (a very small part); never a wrong element.

## Proof of accuracy (step 3)

- **Readiness** (`engine/sonariq/readiness.py`, `GET /readiness`): inventory (spaces, doors ± fire rating, stairs,
  plates ± thickness / material, stiffeners, pipes ± system / material, SWBS coverage, units) and per pack Ready /
  Partial (n) / Not possible with a one-line reason. Shown before Analyse and kept in every run; the latest per revision
  is saved to `data/readiness/readiness_<rev>.json`. Rules of a Not possible pack, and drafts, are not run and appear as
  Cannot verify with the reason.
- **Structure & systems pack** (`rules/seed_rules.yaml` R-STR-01/02, R-SYS-01, R-DQ-01..03) on the RCRV's own data
  (`engine/sonariq/rcrv_model.py` reads the pipeline's metadata index): 36,826 checks in 1.4 s. R-STR-02 (UR S6) is a
  draft that does not run: its table is not in the repo. Every new rule says `verified_against_official_text: false`.
- **Provenance**: `measured.provenance` / `required.provenance` = `{kind: model | derived | public | estimated | user |
  confirmed, file, element, source_id, pset, prop, raw, inputs, source}`; chips on every card, click for the raw source.
- **Ground truth**: `tests/ground_truth/{deck5_revA, deck5_revB, rcrv_structure}.yaml`, `scripts/independent_scan.py`
  (no engine imports), `tests/test_ground_truth.py`, `GET /accuracy?revision=` → the Studio banner.
  Rev B: 6/6 found, 0 false alarms, 3/3 expected passes, scan agrees on R-FLS-01. RCRV: 96/96, 0, 3/3, scan agrees on all
  5 running rules (counts including passes and Cannot verify).
- **Whole-ship runs** (> 2,000 checks) store passes as compact rows: 70 MB → 4.2 MB for the RCRV.

## Findings at scale (step 4)

- `portal/src/components/FindingsList.tsx`: grouped by rule (worst status first), a count line per rule
  ("2,391 parts: 41 warning, 232 cannot verify, 2,118 pass"), filters for rule source (SOLAS/FSS, IACS, Class, Data
  quality, Accessibility), SWBS group, deck and status, one virtualised list (44 px rows, ≈ 15–30 rows in the DOM even
  with 36,481 passes). Arrow keys move the selection. The selected finding's full card (actions, chips) sits above.
- `TraceMatrix.tsx`: parts × rules on a canvas (visible window only), worst parts first; click a cell to select.
- `GET /runs/<id>/csv`: one row per check incl. compact passes, with source kinds; `#print/<run id>`: printable report
  (light theme) with banner, readiness, counts per rule, findings with sources. BCF export unchanged.

## Display modes and View pane (step 5)

- A **View** tab next to **Findings** (DECISIONS M8): display mode, disciplines, colour by.
- Modes (one tile shader + one screen-space pass): **Shaded**; **Shaded + edges** (default: element outlines from a
  full-resolution id buffer, a line wherever neighbouring pixels belong to different elements); **Realistic** (softer
  top light; no shadows: cut first); **X-ray** (everything ghosted, outlines in the theme ink); **Lines** (faces filled
  with the background, so only visible outlines remain: hidden lines removed); **Wireframe**.
- Element look is composed from explicit state (`ShipViewer.compose`): user-hidden, discipline off, focus, solo,
  x-ray, then colour = finding paint > colour-by > model colour, with selection and hover on top. So modes, solo,
  colour-by and a focused finding combine, and the clip planes apply to every pass (cuts keep their edges).
- Disciplines: 8 colour tokens `--disc-*` in `design/sonariq.css` (dark and light), show / hide / **solo** (solid,
  the rest x-ray). Colour by discipline (default), model colours, fire class of boundaries, finding status, deck, SWBS
  group (`GET /models/<id>/column/<field>` serves one metadata column).

## Section blade and capping (step 6)

- **Position, then cut** (`portal/src/components/SectionBar.tsx`, toolbar **Section**): cross section by frame,
  longitudinal by offset from the centreline, deck plan by height or by deck (deck floor + 1.5 m, through doors).
  Translucent blade in the accent colour with a bright line where it meets the hull (the slice of the loaded overview
  tiles of structure and architecture). Live readout: `Fr 152` (or `Fr 152 + 0.30 m` off-grid) with the distance from
  the aft end, `3.2 m PS of CL`, `Deck 5 + 1.5 m`. Drag the blade, wheel over it, arrow keys (one frame or 0.1 m;
  Shift = 10), slider, numeric field. Nothing is clipped until **Cut**.
- **Cut** removes the side the camera is on, eases the camera to face the cut (650 ms, none with reduced motion), caps
  the cut faces and draws section edges. **Re-cut** after a nudge keeps the side; **Flip** keeps the other side and
  turns the camera round; **Section view** = orthographic, facing the cut; **Clear cut**; **Add cut** (up to 3). Each
  cut is a chip to re-open, nudge or clear.
- **Frames** (DECISIONS M6): `GET /models/<id>/grid`. IFC: frame 0 at x = 0, spacing from `SonarIQ_Ship.frame_spacing_m`
  (the engine's rule, so Fr numbers match finding locations; default 0.8 m). RCRV: no frame grid, so Fr = metres from
  the aft end. `PUT /models/<id>/grid` sets frame zero and spacing per model (link under the bar), stored next to the
  tiles, never in the IFC.
- **Caps** (`portal/src/viewer/capping.ts`, M5): stencil method per cut and per closed group. The tiles crossing the
  plane are drawn into the stencil only (back faces +1, front faces −1, the tile shader as is, so hidden and ghosted
  elements count for nothing); a quad on the plane fills where the count is not 0, in the group's discipline colour,
  clipped by the other cuts and the deck selector. Caps draw for **structure** and **architecture** only: the CAD
  export does not guarantee closed meshes for pipes, ducts, cables and equipment, and a cap over an open mesh leaks.
  Those groups get **section outlines** in their discipline colour instead. Caps follow the element state: x-ray
  (everything ghosted) shows outlines only; solo shows caps on the soloed discipline if it is capped.
- **Section edges**: plane ∩ triangles on the CPU in a worker (`section.worker.ts`, maths in `section.ts`), on the
  tiles' own uint16 coordinates (every cut is axis-aligned), for every loaded tile crossing the cut; re-sliced when
  streaming loads new tiles. Ink on capped groups, discipline colour on open groups, hidden / ghosted elements left out.
  With **Shaded + edges** the screen-space element outlines also mark element boundaries inside a cap.
- Modes combine with cuts: every pass is clipped (solid, ghost, id buffer for edges and picking). Lines + deck plan
  reads as a GA plan; X-ray + cross section shows outlines.
- **Section at finding** (finding card): a deck plan through the room when the finding has a plan box on a deck
  (escape, doors, corridors), else a cross section on the frame through the element; the rest of the ship stays
  solid, the finding painted, the camera framing it (≥ 7 m around) on the cut.
- **Named views** (View pane → Saved views): `POST /views` `{name, model, cuts, camera, mode}`, `GET /views?model=`,
  `DELETE /views/<id>`; stored in `data/views.json` (`SONARIQ_VIEWS`). Opening one restores cuts, camera (position,
  target, projection, zoom) and display mode.
- Tests: `npm test` (`section.test.ts`: frames, readouts, plane sides, near side, steps, section at finding, slicing a
  quantised cube), `tests/test_views_api.py` (views + grid), `e2e/section.spec.mjs` (deck5 and the whole RCRV).
