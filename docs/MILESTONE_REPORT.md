# Whole-ship viewer milestone: report

Branch `feat/whole-ship-viewer`, steps 1–9 of `docs/PLAN.md`, merged to `main` on 14 Nov at the user's request
(DECISIONS M14). Nothing was deployed: the live site still runs the previous `main`.

## What works

| Step | What | Screenshots |
|---|---|---|
| 1 | Audit; B1 spike on the full RCRV: Meshopt glTF tiles in plain three.js beat Fragments (DECISIONS M1) | `docs/AUDIT.md` |
| 2 | Engine converts any IFC (and the RCRV glTF) once into tiles; whole-ship streaming viewer; GPU picking; IFC GlobalId mapping | `m2-05-rcrv-whole.png`, `m2-04-properties.png` |
| 3 | Data-readiness report, structure & systems rule pack, provenance chip on every value, ground-truth harness + accuracy banner | `m3-01-readiness-revB.png`, `m3-02-banner-chips.png` |
| 4 | Findings at scale (virtualised, grouped, filtered), traceability matrix, printable report, CSV | `m4-02-matrix-revB.png`, `m4-05-rcrv-matrix.png` |
| 5 | Six display modes, View pane, discipline show / hide / solo, colour by | `m5-rcrv-dark-xray.png`, `m5-rcrv-solo-piping.png` |
| 6 | Section blade (cross, longitudinal, deck plan, three at once) with capped cut faces, section at finding, named views | `m6-09-rcrv-cross-cut.png`, `m6-07-deck5-section-at-finding.png` |
| 7 | Model revisions: Export saves a frozen revision; timeline, read-only open, compare, bundle | `m7-01-timeline-compare.png` |
| 8 | Rendered callouts: card with Is / Must be / formula / clause / sources / actions, leader, occlusion, pins, dimension lines, fire-class outline | `m8-01-deck5-callout-stair.png`, `m8-04-deck5-callout-dead-end.png`, `m8-05-deck5-callout-fire-class.png` |
| 9 | Demo run-through (8 steps, plays by itself); performance report; layouts 1280 / 1440 / 1920 × dark / light; keyboard focus; docs | `m9-04-demo-callout.png`, `m9-07-demo-compare.png`, `m9-layout-*.png` |

## Tests at the merge

- `make test`: engine pytest, all green (124 at the last run).
- `cd portal && npm test`: viewer unit tests (section maths; callout content, number guard, placement).
- `make e2e`: every spec in `portal/e2e/` in headless Chromium against a throwaway engine, including the whole
  RCRV where `data/rcrv/` exists (it does on this VM). Step 8 added `callout.spec.mjs`; step 9 `demo.spec.mjs`
  and `layouts.spec.mjs`.

## Measured performance

From `docs/PERFORMANCE.md` (software GL on a CPU-only VM: fps is a floor, not what a GPU gives):

| Model | Triangles | Web size | Conversion | First frame | fps orbiting | Draw calls | Peak JS heap |
|---|---|---|---|---|---|---|---|
| deck5_revB | 4,244 | 53 KB | 1 s | 0.6 s | 7.2 | 63 | 36 MB |
| RCRV whole ship | 50.8 M | 196 MB | 111 s | 2.5 s | 0.1 | 525 | 152 MB |
| buildingSMART Infra-Landscaping | 20,153 | 101 KB | 4 s | 1.4 s | 7.1 | 45 | 36 MB |

## Partial or cut

- **Tinted volumes** in callouts were cut (plan cut-list); footprint ring + tint and dimension lines are drawn.
- **Pins** only for findings with an evidence box; RCRV findings without one get no pin (their card still opens).
- **Callout anchor height** is 2 m above the evidence footprint: the engine sends 2D boxes plus floor z.
- **Unlocatable findings** say so in the card, but no deck5 / RCRV finding is unlocatable, so the e2e does not
  exercise that path.
- **Realistic mode** has no shadows (cut in step 5); edges are element outlines, not creases inside one element.
- **Caps** on structure and architecture only; open meshes (pipes, ducts, cables) get section outlines.
- **Demo run-through** runs on the Deck 5 demo model, not the RCRV (DECISIONS M13); step 6 solos HVAC there because
  Deck 5 has no pipes.
- **Performance on a real GPU was not measured**: this VM has none. The largest open IFC sample available is 2.3 MB;
  no larger open-licence ship IFC was found.

## Decisions

`docs/DECISIONS.md` M1–M14. New in steps 8–9: M12 (callout module, depth-pass occlusion, pins), M13 (demo on the
Deck 5 model; it saves a Rev A once if missing), M14 (merged to main on request).

## Known issues

- RCRV at 0.1 fps on software GL: orbiting the whole ship on this VM is a slide show. A laptop GPU should be far
  faster, but that is not measured here.
- The first RCRV accuracy banner takes about 20 s (independent scan), cached afterwards.
- The demo's compare step saves a Rev A of the demo model the first time it runs, and step 8 saves the BCF export
  as a revision (Export = save). On the hosted site each full demo play adds one saved revision.
- 1 in 12 RCRV pick samples hits nothing (it never returns a wrong id).
- The theme toggle is not remembered across reloads (it never was).

## Five next tasks

1. Measure on a real GPU laptop (Chrome, 1080p) and add the row to `docs/PERFORMANCE.md`; if the RCRV is below
   30 fps, add per-tile frustum + screen-size culling of the edge (id) pass, which doubles the draw calls today.
2. Engine: send `z1` (top) in `evidence` so callout anchors and tinted volumes use the real room height.
3. Pins for findings without an evidence box: batch the element-box lookup in one `/models/<id>/elements?ids=` call.
4. Deploy: run `scripts/deploy_next.sh` to `/next`, click through the demo on a real browser, then `deploy_vm.sh`.
5. Demo run-through on the RCRV as a second tour (whole ship, solo piping, a real hull finding) once GPU fps is known.
