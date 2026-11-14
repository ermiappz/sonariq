# Whole-ship viewer milestone: plan (steps 2–9)

Decisions behind this plan: `docs/DECISIONS.md` § Milestone (M1–M10). Audit: `docs/AUDIT.md`. Spec:
`docs/milestones/SONARIQ-MILESTONE-SPEC.md`. Every step ends with: tests green (golden path, ground truth from step 3),
Playwright screenshots looked at, docs updated, commit, one line in `docs/PROGRESS.md`.

**Cut first if budget runs short** (in this order): first-person walk (2.6) → Realistic display mode (5.2) → traceability
matrix (4.3) → longitudinal cut (6.4) → three simultaneous cuts (6.5, keep one) → tinted volumes / rings in callouts
(8.3) → demo run-through steps after "section at finding" (9.1). Never cut: ID mapping proof, ground-truth harness,
provenance chips, golden path, saved revisions are immutable (7.2).

---

## Step 2 — Pipeline + whole-ship streaming viewer with picking and ID mapping (A1, A2, B1)

| # | Task | Files | Done when | Proof |
|---|---|---|---|---|
| 2.1 | Tile writer as a library: element list + triangles in → Meshopt GLB tiles per (level, group, deck, 8 m slice), element index per vertex, `index.json`, `elements.json`, `colors.bin`, integrity check (decode and compare) | `engine/pipeline/tiles.py`, `scripts/node/pack_tiles.mjs` (from `spikes/b1/to_tiles.py`, `pack.mjs`) | same outputs as the spike on RCRV; deck5 IFC converts in < 5 s | `tests/test_pipeline.py::test_tiles_roundtrip` (small mesh → tiles → decode → same positions within quantisation step) |
| 2.2 | Sources: IFC via `ifcopenshell.geom` iterator (any schema IFC2x3/IFC4/IFC4x3), RCRV glTF via `spikes/b1/common.py` logic | `engine/pipeline/sources.py` | deck5_revB and RCRV both produce tiles | `test_pipeline.py::test_ifc_source_deck5` |
| 2.3 | Metadata index per model: stable id (GlobalId), source id (`Tag` / dbid / ShipConstructor PartGUID), class, name, deck, discipline, SWBS, material, thickness, grade, fire rating, bbox | `engine/pipeline/index.py` → `meta.json` | every element has id, class, discipline, bbox | `test_pipeline.py::test_meta_fields` |
| 2.4 | Discipline classification: IFC class first, then `config/discipline_mapping.yaml` rules (name, layer, system, SWBS); count of "other" reported | `config/discipline_mapping.yaml`, `engine/pipeline/disciplines.py` | RCRV "other" count printed in `meta.json` summary | `test_pipeline.py::test_discipline_rules` |
| 2.5 | API: `POST /models` (IFC primary, GLB secondary; original kept untouched under `data/models/<sha>/`), background job with progress ("Preparing a fast web version"), cache by content hash; `GET /models/<sha>/status`, static tiles with `Cache-Control: immutable` | `engine/sonariq/models_api.py`, `api.py` (include router) | re-upload of same file returns cached in < 100 ms | `tests/test_models_api.py` |
| 2.6 | Viewer: plain three.js, overview then detail streaming (24 m radius, 1.5 M detail tris, 6 parallel), GPU picking (id per vertex), hover highlight, click select, properties card, isolate / hide / show all, fit, standard views (iso/top/port/stbd/bow/stern), perspective/ortho, deck slider (clip above) | `portal/src/viewer/ShipViewer.ts`, `portal/src/viewer/picking.ts`, `portal/src/components/Viewer3D.tsx`, Studio wiring | whole RCRV opens in Studio; click returns the engine's element | Playwright `e2e/viewer.spec.ts`: open RCRV, first frame < 10 s (software GL), pick 10 known elements |
| 2.7 | ID proof: finding element GUIDs resolve to tile elements | `tests/test_id_mapping.py` | deck5_revB: every finding GUID in `elements.json`; RCRV: every `rcrv_deck_n.ifc` GlobalId in RCRV `elements.json` | the test |
| 2.8 | Ship coordinates: frame grid from model (`frame_spacing_m`) or metres from AP with settable frame zero/spacing | `engine/pipeline/index.py`, viewer readout | readout "Fr 152" on deck5 matches engine location | `test_pipeline.py::test_frames` |

Studio keeps the old IFC path as fallback only if conversion fails (state message, not silent).

## Step 3 — Readiness, structure & systems pack, provenance, ground truth + banner (B2–B5)

| # | Task | Files | Done when | Proof |
|---|---|---|---|---|
| 3.1 | Readiness report: inventory (spaces, doors ± fire rating, stairs, corridors, plates ± thickness/grade, stiffeners, pipes ± material/system, SWBS coverage, units, missing counts) + per pack Ready / Partial (n) / Not possible (reason) → `readiness.json` per revision; `GET /readiness` | `engine/sonariq/readiness.py`, `api.py` | deck5: fire Ready; RCRV: fire Not possible (no spaces), structure Ready | `tests/test_readiness.py` |
| 3.2 | Engine reads RCRV property data: plates thickness (inch fractions → mm via pint), grade, pipe system + material from `properties.sqlite` / meta | `engine/sonariq/model.py` (RCRV loader), `engine/sonariq/rcrv_props.py` | Element has `props` with provenance | test |
| 3.3 | Pack `structure_systems`: R-STR-01 hull steel grade allowed set (IACS UR W11), R-STR-02 grade vs thickness (UR S6, draft: table not in repo, applies ≥ 90 m), R-SYS-01 oil fuel pipe material (SOLAS II-2/4.2.2.5.1), R-DQ-01..03 data quality (missing material/grade/thickness, error values, non-structural material on a plate). Each with `verified_against_official_text` | `rules/seed_rules.yaml`, `checks.py`, `rules.py` | runs on whole RCRV in < 2 s; unknown → Cannot verify | `tests/test_structure_pack.py` |
| 3.4 | Provenance (M7): `provenance` on measured, required and each formula input; API exposes it; card chips | `checks.py`, `engine.py`, `portal/src/components/SourceChip.tsx` | every number in a card has a chip | `tests/test_provenance.py` (every fail/warn has provenance on measured) |
| 3.5 | Ground truth: `tests/ground_truth/{deck5_revA,deck5_revB,rcrv_structure}.yaml` hand-checked; `scripts/independent_scan.py` (no engine imports) counts expected failures per rule; `tests/test_ground_truth.py` fails on any miss / false alarm / count mismatch; `GET /accuracy` | listed | CI-style test green | the test |
| 3.6 | Banner in Studio computed from `/accuracy` | `Studio.tsx` | "✓ n/n hand-checked findings found · 0 false alarms · …" | Playwright screenshot |

## Step 4 — Findings at scale, traceability, report / CSV (B6, B7)

| # | Task | Files | Done when | Proof |
|---|---|---|---|---|
| 4.1 | Findings grouped by rule then status, counts per rule ("12,902 parts: …"), fails first | `portal/src/components/FindingsList.tsx` | RCRV structure run shows grouped list | Playwright |
| 4.2 | Filters (rule source, SWBS, deck, status) + virtualised list (fixed row height, windowed render; no new dependency) | same | never more than ~60 rows in DOM | Playwright counts DOM rows |
| 4.3 | Traceability matrix parts × rules (canvas), click → select part | `portal/src/components/TraceMatrix.tsx` | click selects in 3D | Playwright |
| 4.4 | CSV export + printable report (findings, readiness, banner, provenance); BCF unchanged | `api.py` `GET /runs/<id>/csv`, `portal/src/screens/Report.tsx` (print CSS) | CSV row count = checks | `tests/test_export.py` |

## Step 5 — Display modes, View pane, discipline solo (A4)

| # | Task | Files | Done when | Proof |
|---|---|---|---|---|
| 5.1 | View tab next to Findings (M8) | `Studio.tsx`, `portal/src/components/ViewPane.tsx` | tab switch keeps selection | Playwright |
| 5.2 | Modes in the tile shader: Shaded, Shaded + edges (default; screen-space normal/id edges), Realistic (hemisphere + directional light, per-class defaults), X-ray, Lines (edges only, hidden removed by depth pre-pass), Wireframe | `portal/src/viewer/modes.ts` | each mode screenshot reads well in both themes | Playwright per mode |
| 5.3 | Discipline checklist with 8 colours (tokens added to `design/sonariq.css`), show / hide / solo (solo = solid, rest x-ray) | `ViewPane.tsx`, `design/sonariq.css` | solo piping works on RCRV | Playwright |
| 5.4 | Colour by discipline / fire class / finding status / deck / SWBS (writes the element colour texture) | `modes.ts` | | Playwright |

## Step 6 — Section blade with capping (A3)

| # | Task | Files | Done when | Proof |
|---|---|---|---|---|
| 6.1 | Section maths: frame ↔ x, offset from CL ↔ y, deck ↔ z; plane from cut type + position | `portal/src/viewer/section.ts` | | `portal/src/viewer/section.test.ts` (node --test) |
| 6.2 | Blade: translucent plane + hull outline, live readout, drag / wheel / arrows (one frame) / slider + field; nothing clipped until Cut | `section.ts`, `SectionBar.tsx` | | Playwright |
| 6.3 | Cut: clip near side, camera eases to face, stencil caps (M5) coloured by discipline; section edges from CPU plane ∩ triangles on tiles crossing the plane; outlines-only fallback where meshes are open (documented) | `section.ts`, `capping.ts` | cap visible on deck5 and RCRV | Playwright screenshot |
| 6.4 | Flip, nudge + re-cut, ortho "Section view", Clear cut; longitudinal + deck plan | | | Playwright |
| 6.5 | Up to 3 cuts; "Section at finding" on cards; named views (cut + camera + mode) saved via `/views` | `api.py`, `Studio.tsx` | | `tests/test_views_api.py` |

## Step 7 — Model revisions (B11)

Added 14 Nov at the user's request, before the callouts. A *model* is a line of revisions (the three deck 5 demo files
are one model, the RCRV another, an upload is a new model or a new revision of one). A *revision* is a draft (the
latest analysis, replaced by the next Analyse) until an Export saves it; then it is frozen and the next Analyse opens
the next draft.

| # | Task | Files | Done when | Proof |
|---|---|---|---|---|
| 7.1 | Store: SQLite `data/revisions.sqlite` (`SONARIQ_REVISIONS`) with `models` and `revisions` (model, seq, letter, label, draft/saved, run id, file sha-256, counts) + files under `data/revisions/<model>/<seq>/`. Every Analyse attaches its run to the model's draft (model from the request, else demo file → "Deck 5 demo", RCRV → "RCRV", else same file name, else new model) | `engine/sonariq/revisions.py`, `api.py` (`/analyse`) | | `tests/test_revisions.py` |
| 7.2 | Export saves: `POST /revisions/export {run_id, format}` (bcf / report / csv) freezes the draft as Rev A, B, C… with `snapshot.json` (file hash, rule-pack versions = hash of each pack's rules, all checks with statuses, incorrect marks + decisions, readiness, accuracy banner, saved views of that file) and `export.bcfzip`, `checks.csv`, `report.json`; exporting an already saved run returns that revision. A SQLite trigger refuses changes to a saved revision except its label | `revisions.py`, `api.py`; Studio Export / Report / CSV, report dialog | second export of the same run = same revision; UPDATE on a saved row fails | `test_revisions.py` |
| 7.3 | Timeline in Studio: label (editable, `PATCH /revisions/<id>`), date, pass / fail / cannot verify, bundle download (`GET /revisions/<id>/bundle`, zip of the folder); open a past revision read-only (no Analyse, no marking, banner says so) | `portal/src/components/RevisionTimeline.tsx`, `Studio.tsx` | | Playwright |
| 7.4 | Upload choice: "New model" / "New revision of <model>" | `Studio.tsx` | | Playwright |
| 7.5 | Compare: one diff function (`engine/sonariq/revdiff.py`) replaces `/runs/diff`'s body: findings matched by element ID (check key), else by rule + element name / location → "please confirm"; new / resolved / still open / changed. `GET /revisions/compare?a=&b=`; the Revisions screen uses the same function | `revdiff.py`, `api.py`, timeline compare | | `test_revisions.py`: A (1 fail) → B (4) → Fix 2 (3) counts |
| 7.6 | Reset all data archives the revision store too | `api.py` | | `test_revisions.py` |
| 7.7 | e2e: export → new analysis → export → timeline shows two revisions → compare shows the right counts | `portal/e2e/revisions.spec.mjs` | | Playwright |

## Step 8 — Rendered callouts with evidence geometry (A5)

| # | Task | Files | Done when | Proof |
|---|---|---|---|---|
| 8.1 | Reusable callout module (`anchor`, `content`, `actions`), leader line, occlusion test via pick buffer, never covers its element | `portal/src/viewer/callout.ts`, `Callout.tsx` | | Playwright |
| 8.2 | Content: title + status chip, Is, Must be (formula filled with engine numbers), clause + location, source chips, actions Section here / Isolate / Open evidence | | numbers only from the finding JSON | Playwright + guard test that the callout text has only numbers present in the finding |
| 8.3 | Evidence in 3D: dimension lines (measured solid, required dashed) from existing `overlaySpec`, dead-end polyline, tinted volume / ring; material findings tint "is", outline "must be" | | | Playwright |
| 8.4 | Several findings → pins, active expands; survives cuts and mode changes; unlocatable → said in card | | | Playwright |

## Step 9 — Demo run-through, docs, performance report, polish (B8, A6, B11)

| # | Task | Files | Done when | Proof |
|---|---|---|---|---|
| 9.1 | Demo run-through button: readiness → whole ship → banner → finding + callout → section at finding → x-ray solo piping → revision timeline + compare → BCF; Space/→ step, Esc stops | `portal/src/components/DemoRun.tsx` | | Playwright walks all steps |
| 9.2 | `docs/PERFORMANCE.md`: deck5_revB, RCRV, largest open IFC sample available offline (else say so): conversion time, size, first frame, fps (marked software GL), draw calls, peak memory | `scripts/perf_report.mjs` | | the script output |
| 9.3 | Layouts 1280 / 1440 / 1920 × both themes, keyboard focus | | screenshots in `docs/screenshots/` | Playwright |
| 9.4 | README, ARCHITECTURE, `docs/VIEWER.md`, `docs/MILESTONE_REPORT.md`; PR to main (not merged) | | | |

## Test harness

- Python: `make test` (pytest). New: pipeline, models API, ID mapping, readiness, structure pack, provenance, ground truth.
- Browser: `e2e/` with `playwright-core` + the cached Chromium (`~/.cache/ms-playwright/chromium-1248`, SwiftShader).
  `make e2e` starts a throwaway engine (port 8790) + `vite preview`, never the live services.
- RCRV-dependent tests skip with a reason when `data/rcrv/` is absent (it is not in git).
