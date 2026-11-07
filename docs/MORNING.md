# Good morning · SonarIQ status, Sat 7 Nov 06:00 EET

**The core works and every handoff number comes from the engine.** Rev A gives 96 checks: 1 Fail · 1 Warning · 1 Cannot verify · 89 Pass · 4 Dormant (64 / 20 / 12 per pack). Rev B (OR-117) gives 4 · 1 · 1 · 86 · 4, with F-07, F-08 and F-09 changed. Fix 2 gives 3 · 1 · 1 · 87 · 4. Stair 3B: 1,300 mm (Rev A), 1,380 mm (Rev B), 1,340 mm (fix 2). There are 49 tests, all green. The panel runs in real FreeCAD 1.0, and the RCRV is converted to IFC.

**One number differs from the design:** the OR-117 ping re-runs **11** checks, not 14. Why: `docs/DECISIONS.md` #17. The design copy needs to say 11, or Meyer tells us what else they would re-check.

## Print for 09:00

`docs/meyer_qa1.md`: the rule-readings table to tick, Rev A / Rev B results, Stair 3B worked out, and 8 questions. It is generated from live engine runs (`make qa`). Print it with any Markdown viewer, or paste it into a doc.

## What to test first (15 min, on the Mac)

1. `git pull && uv sync --python 3.11 && make test`: expect **49 passed**.
2. `make api` in one terminal and leave it running.
3. Install the add-on (README, "FreeCAD on macOS", step 4: one symlink). Open FreeCAD → File → Open `data/deck5_revA.ifc`. If a BIM Welcome dialog appears, close it.
4. The SonarIQ panel docks on the right. Press **Analyse** and expect 96 checks, 1 · 1 · 1 · 89 · 4. Click **F-01**: FD-5-165P should turn orange and be selected in the 3D view.
5. Open `data/deck5_revB.ifc`, then Analyse, then click **F-07**: you should see the formula with N₁ 68 (Deck 5, counted from the model), 44, 40, 24 = 1,380 mm.
6. Portal (optional): `make portal`, then open http://localhost:5173: Inbox (W2), click F-08 (W3 thread), Model (W4 viewer with pins), Rules (W6), Mapping review (W5).

Already checked on the VM: FreeCAD 1.0 under xvfb (NativeIFC import, 251 objects with GlobalId, Analyse = 96, F-01 selects FD-5-165P; `make fc-check`), and the portal in headless Chromium.

## What works

| Part | State |
|---|---|
| Test deck | `scripts/make_deck.py` → `data/deck5_revA.ifc`, `deck5_revB.ifc`, `deck5_revB_fix2.ifc` (IFC4, `SonarIQ_Ship` pset, stable GlobalIds) |
| Rule engine | 15 rules in `rules/seed_rules.yaml`, 14 measure functions; Fail / Warning / Cannot verify / Pass / Dormant / Not applicable; locations as Deck · Fr · Side |
| Impact (ping) | Diff by GlobalId + dependency index; a test proves nothing outside the re-run set changed |
| Edits and fixes | The four edits only (guard is code); preview → confirm; F-07 fixes re-checked by the engine: 1,400 mm (needs Structure) ✓, 4 × 1 berth 1,340 ✓, one cabin 1,320 ✓, move 10 frames 1,380 ✕ (rejected) |
| MCP server | `engine/mcp_server.py`: 8 tools, works over stdio |
| HTTP API | `make api`, port 8765, used by the panel and the portal |
| BCF | BCF 2.1 zip, one topic per open finding or decision, with the IFC GlobalId selected |
| AI guard | Any explanation with a number not in the finding is rejected. Without an endpoint the engine's own wording is used |
| FreeCAD panel | PanelHead, P1, P3 (grouped by discipline, summary filters), P4 evidence card (formula, method, unit toggle, fix options, accept with reason, send to review, zoom to); design/panel.qss |
| Portal | Rail + TopBar, W1, W2, W3, W4 (That Open viewer + pins), W5, W6 on the live API. Approvals are not persisted yet |
| RCRV | NWD → APS SVF → glTF (1.9 GB) + properties → IFC4: 90,331 objects, 86,593 classified, ~4,000 unmapped → `mapping_review.csv`. `rcrv_full.ifc` (192 MB) + `rcrv_deck_1..7.ifc`. `docs/rcrv_report.md` has counts and 10 doors in inches and mm |
| Speed | Analyse 0.04 s plus 0.9 s IFC load; ping 0.04 s (`make bench`) |

## Not done / weak

- **AI explanations are off.** Qwen isn't enabled in Vertex AI for project `fairway-379dc` (404 in every region tried). It's one console click; see `docs/BLOCKERS.md`. Everything else works without it.
- **Live mode, chat edits and the ping animation** were deliberately not built (round 2). The Chat tab says so.
- **RCRV door widths are upper bounds** where the block's parts are not separated (frame included). On RCRV Deck 3, door `A-CLASS DOOR MA60CX (LI)-509` measures **29.4 in (748 mm) → Fail**. It's a real candidate for the ADA story, but measure it in FreeCAD before showing it to anyone. The planted D-02-114 / D-02-118 cases are not planted yet.
- RCRV stairs and ladders have no flight geometry, so their width checks are **Cannot verify** (correct, but noisy). RCRV fire classes are not in the source, so the SOLAS rules would be Cannot verify even if they applied.
- The starter-kit `seed_rules.yaml` was not on the VM; I wrote the rulebook myself (DECISIONS #2). If you have the original, compare the two.
- Portal decisions live in the browser only. The panel's accept-with-reason goes to the engine session (in memory).

## Open questions for Meyer (also in the printout)

1. FSS Ch.13 §2.1.2: N₁…N₄ ordered by size, or by deck nearest the stair first?
2. Dead ends: is "depth ≤ width" your reading, and is II-2/13.3.1.2 the paragraph you cite?
3. Corridor 900 mm: which paragraph do you use (we cite FSS Ch.13 §2.1.2, *verify*)?
4. Fire doors in A-class divisions: is II-2/9.2.2.1.1 (+ 9.4.1.1.1) the right citation for "door ≥ bulkhead class"?
5. RCRV: are we right that the >36-passenger SOLAS rules don't apply, and is ADA §404.2.3 the accessibility reference OSU used?
6. Which single DNV rule would you most like to see (the current plate-thickness rule is a placeholder)?
7. Location words: is Deck · Fr · Side enough, or do you add MVZ / room number?

## Decisions to check (★ in DECISIONS.md)

#1 brief source, #2 self-written rulebook, #17 re-run count 11, #25 RCRV deck names.
