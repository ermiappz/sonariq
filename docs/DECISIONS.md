# Decisions log (overnight build, 7 Nov 2026)

Each line is an assumption made without asking. Check the ones marked ★ at 08:00.

| # | Time (EET) | Decision | Why |
|---|---|---|---|
| 1 | 04:40 | ★ `docs/brief/` and `rules/seed_rules.yaml` were not on the VM. The brief was read from the live doc (claude.ai/artifact/4igkaVecwz1d4uYTBCrL4u) and its main tab saved to `docs/brief/brief_main.md`. | Only copy available |
| 2 | 04:40 | ★ The starter-kit `seed_rules.yaml` is missing, so I wrote `rules/seed_rules.yaml` (15 rules) from the brief, handoff.md and the W6 Rulebook artboard, using the design's IDs (R-FLS-01…05, R-ACC-01/02, R-DNV-01/02) and adding R-FLS-06…11. Replace it with the starter-kit file if that one is better; the engine reads whatever is there. | Engine needs a rulebook |
| 3 | 04:40 | `status: verified` means the clause and threshold match the widely cited text; Meyer still confirms at Q&A 1. Paragraph numbers I am not sure of are `verify`: R-FLS-02 dead end, R-FLS-04 corridor 900 mm, R-FLS-05 duct damper, R-FLS-08…11, and both DNV rules. | Honest status |
| 4 | 04:40 | The systems pipe-penetration check (II-2/9.3) is left out of the 15. HVAC duct damper (R-FLS-05) is the one cross-discipline check. | The prompt lists fire, escape, accessibility; hvac and structure as stubs |
| 5 | 04:40 | `.env` is a symlink to `~/.env` (APS keys there). Ignored by git. | Secrets never in git |
| 6 | 04:45 | APS: bucket `sonariq-rcrv-<clientid prefix>`, transient; signed-S3 multipart upload; job output `svf` with 2d + 3d views. State in `data/rcrv/aps_state.json` so a rerun resumes. | Build plan part B |
| 7 | 04:50 | Finding IDs = verdict prefix (F/W/U; H for hvac pack) + the rule's `finding_no`. This makes F-07 = stair formula, F-08 = dead end, F-09 = corridor width, as in the design, without typing IDs in the UI. | Stable, deterministic IDs |
| 8 | 04:50 | Dormant = a check on an element whose `SonarIQ_Ship.maturity` is `concept`. Computed, not reported. The 4 dormant checks are the 2 galley fire doors at Fr 205–212 × (R-FLS-01, R-FLS-10). | Brief: "concept zones stay quiet"; the design never defines Dormant |
| 9 | 04:50 | Deck 5 persons for a stair = berths of cabins in the stair's MVZ on Deck 5, counted from the model. Other decks from the stair's `persons_by_deck`. | Makes Stair 3B change when cabins are added (the indirect ripple) |
| 10 | 04:50 | FSS N1…N4 = persons per served deck sorted largest first. | Matches the design's worked example; FSS's exact ordering rule to confirm at Q&A 1 |
| 11 | 04:50 | Dead end = a corridor that is a leaf of the corridor adjacency graph, has no stair and no `escape_continues`. Fail when depth (long side) > width (short side). | Design text "a dead-end recess is no deeper than it is wide" |
| 12 | 04:50 | Rev B dead end: the existing cross corridor at Fr 146–150 P is shortened by the new cabin block to 4.2 m, rather than a new corridor being added. This keeps the check total at 96, as the design's Rev B counts require. | Contract counts |
| 13 | 04:50 | Location is read from `SonarIQ_Ship` (deck, frame, side), with geometry as the fallback. The cross corridor's pset says `146-150` even though its 1.2 m footprint spans Fr 146–147.5. | handoff.md location text |
| 14 | 04:50 | Door clear width = `IfcDoor.OverallWidth`. The generator writes the clear opening there. RCRV doors use the leaf's oriented bounding box instead. | No standard IFC clear-width property |
| 15 | 04:50 | The DNV pack is R-DNV-01 deck plate thickness on 12 IfcPlate panels, t ≥ 4.5 + 0.02·min(L,300) mm, plus R-DNV-02 as a placeholder with 0 checks. Both carry To verify. | Design shows 12 DNV checks and 2 placeholder rules |
| 16 | 04:55 | Portal pinned to @thatopen/components 2.4.x, web-ifc 0.0.66 and three 0.160 (known-compatible set). | Avoid version drift tonight |
