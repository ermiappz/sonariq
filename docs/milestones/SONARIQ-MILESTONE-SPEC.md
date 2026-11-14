# SonarIQ milestone: whole-ship viewer, proof of accuracy, section cutting, display modes, rendered rule callouts

Version 2 (13 Nov 2026). Part A is the original milestone. Part B adds what the hackathon winner (Complee) did better, and overrides Part A where they conflict. Part C sets the build order.

You are working in the SonarIQ repository. SonarIQ is a fire and life-safety compliance co-pilot for ship design, built in 36 hours at a hackathon (Meyer Turku challenge, Since AI 2026). I am turning it into a production-quality portfolio project and, later, a real design tool.

---

# PART A — Original milestone

## Why this milestone

At the hackathon the winning team showed the whole ship in the browser with rendered and x-ray views. Ours could only show one deck section, and loading was slow, because:

- the browser parsed and triangulated IFC at runtime while the user waited;
- the RCRV model had gone Navisworks → glTF → IFC, which bloated it;
- tens of thousands of separate meshes meant too many draw calls.

The fix is architectural: convert once on the server into a GPU-friendly format, and have the browser load only that.

## What I know about the repo (verify all of it)

- Web portal: React + Vite, design tokens in `sonariq.css` (dark and light themes, 8 discipline colour tokens), That Open Engine / web-ifc / three.js for 3D. The Studio page has the viewer on the left and the findings panel ("Panel v2") on the right.
- Engine: Python 3.11, FastAPI, also exposed as an MCP server. Deterministic checks using IfcOpenShell, Shapely, NetworkX, pint, YAML rule packs.
- Findings schema: `rule_id`, `status`, `entity_ids`, `location {deck, frame_from, frame_to, side}`, `required {value, unit, expr}`, `measured {value, unit, method}`, `clause {source, ref, text_excerpt}`, `evidence {kind, geometry_mm}`.
- Models: generated `deck5_revA` (compliant) and `deck5_revB` (owner change OR-117, +4 cabins), and the real research vessel RCRV (ShipConstructor production model, converted Navisworks → Autodesk APS → glTF → IFC).
- A FreeCAD panel exists. Out of scope here; do not break its API.

## Rules that must not be broken

1. **The engine judges, the AI explains.** Pass/fail and every number shown to the user come from the deterministic engine. Nothing may let an LLM produce a verdict, a measurement or a requirement. The number guard stays.
2. **The golden path keeps working.** `deck5_revA` → Analyse → 0 fails; `deck5_revB` → Stair 3B fails at 1,350 mm against 1,380 mm, plus the dead-end and corridor pinch findings. Add a test first if none exists.
3. **No design data leaves the machine** except the existing, documented Gemini explanation call. No CDN model processing, no third-party upload services, no telemetry. WASM and workers are served from our own origin.
4. **Wording is supportive.** SonarIQ is a companion that makes the engineer's work easier. Avoid copy implying engineers miss things.
5. **Licences:** MIT/Apache/BSD/MPL only. No AGPL (rules out xeokit).

## Phase 0: audit

Write `docs/AUDIT.md`: real layout, how to run web/engine/tests, what is broken on a clean checkout; versions of `@thatopen/*`, `web-ifc`, `three`; how models load today and where the time goes for the largest model; and a built / partial / missing table (with file refs) for: whole-ship view, x-ray, section plane, discipline filter, section-at-finding, deck slider, dimension overlays, BCF export, saved viewpoints, isolate/show all, linked Inbox ↔ Studio, source IDs from the CAD tool, and everything in Part B. Parts of this milestone may already have been started on a branch; check all branches.

That Open's API changed a lot between versions. Read the docs and type definitions for the versions you use. Never write against an API from memory.

## Phase 1: model pipeline (server-side conversion)

- `POST /models` accepts IFC (IFC4, IFC2x3, IFC4x3; primary) and glTF/GLB (secondary). Store the original untouched.
- A background job converts it to the web format chosen in Part B §1. Report progress ("Preparing a fast web version"). Cache by content hash.
- Write a **metadata index** per model: stable ID (IFC GlobalId or source object ID), any source-tool ID in property sets, class, name, deck, discipline, SWBS group, material, key properties (thickness, grade, fire rating), bounding box.
- **Discipline classification** into structure, architecture/outfitting, HVAC, piping, electrical, fire safety, equipment, other. IFC class first, then `config/discipline_mapping.yaml` rules by name, layer, system path and SWBS. Report how many ended up in "other".
- **Ship coordinates:** frame grid and deck levels from the model when present; else metres from the aft perpendicular, with user-settable frame zero and spacing.
- Element IDs must match between engine findings and viewer geometry. Prove it with a test on `deck5_revB` and on RCRV.

## Phase 2: whole-ship viewer

- Whole ship navigable on a 16 GB laptop; geometry work in workers.
- Orbit, pan, zoom to cursor, fit, standard views (iso, top, port, starboard, bow, stern), perspective/ortho, first-person walk.
- Hover highlight, click select, properties card, isolate, hide, show all; model tree by deck and by discipline/SWBS.
- **Deck slider:** pick a deck, everything above is clipped.
- Empty, loading and error states in the existing design system.

## Phase 3: the section blade

- Three cut types: **cross section** (by frame number), **longitudinal** (offset from centreline), **deck plan** (height or deck).
- **Position, then cut.** Translucent blade with a bright outline where it meets the hull and a live readout ("Fr 152", "3.2 m PS of CL"). Drag, wheel, arrow keys for single-frame steps, slider + numeric field. Nothing clipped yet.
- **Cut** removes the near side, eases the camera to face the cut, and **caps** cut faces with solid fills and crisp section edges. Use That Open's clipping/section styling if the version provides fills and edges; otherwise stencil capping in three.js. Hollow shells are not acceptable; where source meshes are not closed solids, fall back to outlines and document it.
- Cap colour by discipline or material. Flip side, nudge and re-cut, orthographic "Section view", "Clear cut", up to three simultaneous cuts.
- **Section at finding** on each finding card. Save cut + camera + display mode as a named view.

## Phase 4: display modes and the View pane

A "View" pane on the right (tab next to Findings or collapsible section; justify in DECISIONS).

- Display mode: **Shaded**, **Shaded with edges** (default), **Realistic** (PBR, environment light, soft shadows, defaults per class), **X-ray**, **Lines** (hidden lines removed), **Wireframe**.
- **Disciplines:** checklist with the eight colours; show/hide and **solo** (solo = that discipline solid, the rest ghosted x-ray).
- **Colour by:** discipline (default), fire class of boundaries, finding status, deck, SWBS group.
- Modes combine with cuts (x-ray + cross section, Lines + deck plan).

## Phase 5: rendered rule callouts

When a finding is selected: frame the element in its real material, ghost the rest with nearby context, and float a **callout** with a leader line to an anchor on the element (readable while orbiting, never covering its element, hidden when occluded):

- title and status chip;
- **Is:** measured value or property ("Clear width 1,350 mm", "A-0 steel bulkhead");
- **Must be:** requirement with formula filled with the model's numbers;
- clause ref and location ("FSS Code Ch.13 §2.1.2 · Deck 5 · Fr 152 · SB");
- **source chips** on every input (Part B §4);
- actions: Section here, Isolate, Open evidence.

Draw `evidence.geometry_mm` in 3D: dimension lines (measured in status colour, required dashed), dead-end polylines, tinted volumes, rings. Material/fire-class findings: tint by what it is, outline in what it must be. Several findings → compact pins, active one expands. Survives cuts and mode changes. Unlocatable element → say so in the card. Build callouts as a reusable module (`anchor`, `content`, `actions`).

## Phase 6: quality, tests and proof

- Unit tests: pipeline, ID mapping, classification, frame grid, section maths.
- Playwright end-to-end: import → open → each display mode → each cut → select finding → callout visible. Screenshots to `docs/screenshots/`; look at them yourself and fix what is wrong. Test layouts at 1280, 1440 and 1920 px wide in both themes.
- `docs/PERFORMANCE.md`, measured for `deck5_revB`, RCRV and the largest open-licence IFC sample you can get: conversion time, converted size, time to first frame, fps while orbiting, draw calls, peak memory.
- Keyboard access, visible focus, both themes.
- Update `README.md`, `ARCHITECTURE.md`, and write `docs/VIEWER.md`.

---

# PART B — Lessons from the winner (Complee). Overrides Part A where they conflict.

Complee won because they: (1) ran rules on the **whole real RCRV model** (330,760 source objects → 69,993 parts → 35,328 checked), (2) chose rules that fit **the data the model actually contains**, (3) showed **proof of accuracy** on screen, and (4) showed **where every value came from**. We keep what they lacked: evacuation simulation, AI explanations with the number guard, BCF and the CAD round trip, revision diff, and stronger design.

## B1. Viewer format: decide by measurement, not by preference

Two candidates. Spike both on the full RCRV during planning, then pick one and record why in `docs/DECISIONS.md`.

- **That Open Fragments** (current stack, MIT). Strong on IFC with built-in clipping, classifier, highlighter.
- **Custom glTF tile streaming in plain three.js**, which is what Complee shipped and is proven on this exact model. Their published numbers: ~50.8 M triangles, ~500 MB of geometry, 10 groups (structure, piping, openings, access, context, rest…), 851 Meshopt-compressed GLB tiles per group × spatial grid cell; an **overview** built only from faces visible from ~120 sampled exterior viewpoints (no simplification, interior faces skipped); **detail** tiles streamed within ~24 m of the camera with budgets of 1.5 M detail triangles, 512 MB resident and 6 parallel requests; the **element ID stored per vertex** so any click maps to its record; picking in a worker; an **integrity check** that decodes every compressed tile and compares positions (max deviation ~0.0005 mm). Live: 3.7 M triangles, ~900 draw calls, ~214 MB JS heap.

Constraints either way: whole RCRV must stream and stay pickable; element IDs must survive into the viewer; section capping and display modes from Part A must be achievable. For RCRV it is fine (probably better) to build viewer tiles directly from the glTF rather than through IFC, as long as IDs map to the engine's records. Targets: previously converted ship opens to first frame in under 10 s, orbits at 30 fps or better on a mid-range laptop GPU, rule checks on the whole ship in under 2 s.

## B2. Data-readiness report per model

Before analysis, show what the model can support:

- Inventory: counts of spaces/rooms, doors (with/without fire rating), stairs, corridors, plates (with/without thickness and steel grade), stiffeners, pipes (with/without material and system), SWBS coverage, units, missing-value counts.
- Rule-pack readiness: for each rule pack, **Ready** / **Partial (n elements lack data)** / **Not possible (e.g. no spaces in model)**, with the reason in one line.
- Shown as a card in the Studio and saved as `readiness.json` per model revision. Analysis runs only the rules that can run; the rest appear as Cannot verify with the reason.

## B3. Rule packs that fit real production data

Keep the fire and escape packs (they need spaces). Add a **structure & systems pack** that runs on property data in the RCRV, each rule with clause reference, a `verified_against_official_text: true/false` flag, and Cannot verify when data is missing:

- hull steel grade allowed set (IACS UR W11);
- steel grade vs plate thickness (IACS UR S6 table);
- oil fuel pipe material (SOLAS II-2/4.2.2.5.1);
- design/data quality (missing material, grade, thickness, status; error values).

Do not invent rule values. If an official value is not available in the repo, leave the rule as a draft that does not run, and say why in the UI (as Complee did with minimum thickness). Show "n of N rule values verified against official text" honestly.

## B4. Provenance on every value

Every input shown in a finding, callout or properties card carries a small source chip: **model** (file + element ID + property set), **derived** (computed by SonarIQ from named inputs), **public particulars**, **estimated**, **user-entered**, or **confirmed by <person/source, date>**. Clicking a chip shows the raw source. Store provenance in the finding schema (extend it backward-compatibly).

## B5. Ground-truth harness and accuracy banner

- Per scenario (`deck5_revA`, `deck5_revB`, RCRV structure & systems, RCRV fire/escape example if any), a hand-checked file `tests/ground_truth/<scenario>.yaml` listing expected findings (element ID, rule, status) and expected passes.
- An **independent scan** (a simple separate script, not the engine) that counts expected failures per rule as a cross-check.
- A test in CI that fails on any miss or false alarm.
- A banner in the Studio: "✓ 13/13 hand-checked findings found · 0 false alarms · 4/4 expected passes · counts match independent scan". Never hard-code it; compute it.

## B6. Scale-ready findings UI

With tens of thousands of checked parts: group findings by rule, then by status; filters for rule source (SOLAS/FSS, IACS, class, data quality), SWBS group, deck and status; virtualised lists; counts per rule ("12,902 parts: 12,017 pass, 6 fail, 879 cannot verify"). Default view shows fails first. Never render 35,000 rows at once.

## B7. Traceability, report and CSV

- **Traceability matrix:** parts × rules, coloured cells; click a cell to jump to the part.
- **Printable report** (findings, readiness, accuracy banner, provenance) and **CSV** export. Keep BCF export.

## B8. Scripted demo run-through

A "Demo run-through" button that tells the story by itself: readiness → whole ship → accuracy banner → one finding with callout and dimensions → section at finding → x-ray solo of piping → revision diff → BCF export. Space/→ steps manually, Esc stops. This is how portfolio visitors will see the product without a video.

## B9. Keep and surface SonarIQ's edge

Evacuation simulation (500 seeded runs, p95), AI explanation with number guard, BCF round trip + FreeCAD panel, revision diff, design quality. Make sure each is reachable from the new Studio and appears in the demo run-through.

## B10. Hosting

Stay on the existing VM behind Caddy with HTTPS. No temporary tunnels. Model tiles served with long cache headers and compression.

## B11. Model revisions

- **Export saves a revision.** Clicking Export (BCF, report or CSV) saves the current analysis as the next revision
  under that model: Rev A, Rev B, Rev C…
- **A saved revision can't be changed.** It stores the model file hash, rule-pack versions, all findings and their
  statuses, engineer marks (e.g. "Incorrect finding"), the readiness report, the accuracy banner, saved views, and the
  exported files.
- **New work starts the next draft revision** under the same model. That covers running a new analysis after an
  export, and uploading a new file via the upload dialog's choice of "New model" or "New revision of <model>".
- **Studio shows a revision timeline:** editable label, date, pass / fail / cannot-verify counts, and a download of that
  revision's bundle. You can open any past revision read-only.
- **Compare any two revisions:** new, resolved and still-open findings, matched by element ID, with fallback matches
  shown as "please confirm". Reuse and replace the existing revision-diff code rather than writing a second one.
- **Stored on the VM** (SQLite + files). "Reset all data" still clears everything.
- **Test:** Rev A (1 fail) → Rev B with OR-117 (4 fails) → Fix 2 (3 fails) gives the expected diff counts. Plus an e2e
  test: export → new analysis → export → timeline shows two revisions → compare shows the right counts.

---

# PART C — Build order and scope

If time or budget runs short, stop at the end of a step with everything working, document the gap, and move on. Priority order:

1. Audit + spike + decisions (planning session).
2. Pipeline + whole-ship streaming viewer with picking and ID mapping (A1, A2, B1).
3. Readiness report, structure & systems pack, provenance, ground-truth harness + banner (B2–B5). High value, modest cost.
4. Findings at scale, traceability, report/CSV (B6, B7).
5. Display modes + View pane + discipline solo (A4).
6. Section blade with capping (A3).
7. Model revisions (B11).
8. Rendered callouts with evidence geometry (A5).
9. Demo run-through (including the revision timeline and compare), docs, performance report, polish (B8, A6).

## How to work

- Branch `feat/whole-ship-viewer` (reuse it if it exists). Commit at the end of each step with a message saying what now works. Open a PR at the end; do not merge to main.
- Reuse existing design tokens and components. Keep changes inside the viewer, pipeline, findings UI, rule packs and their API routes; note anything else in DECISIONS.
- No model files over 20 MB or credentials in git; large models behind a download script.
- Commits authored by ermiappz / ermiarch@gmail.com. No history rewrites.
- Work autonomously. Ask only if something is destructive or truly blocked; otherwise choose, record in `docs/DECISIONS.md`, continue.

## When you finish

`docs/MILESTONE_REPORT.md`: what works (screenshots), what is partial, measured performance, decisions, known issues, and the five next tasks you recommend. Be exact about anything you could not verify.
