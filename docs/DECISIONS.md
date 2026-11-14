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
| 16 | 05:20 | Portal pinned to @thatopen/components 2.3.0 + fragments 2.3.0 + web-ifc 0.0.59 + three 0.160.1, the peer set components 2.3.0 declares. 2.4.x wants fragments 3 and three ≥ 0.175; 3.6 has a new API. | Avoid version drift tonight |
| 17 | 05:20 | ★ The OR-117 ping re-runs **11** checks, not 14. Re-run set = checks whose recorded dependencies touch the diff: COR-5-148-P and COR-5-152-S (R-FLS-04, R-ACC-01, R-FLS-02 each), the dead-end checks of their 3 neighbouring corridors (adjacency changed), Stair 3B's formula (berths in MVZ 4) and MVZ 4's length (members changed). Changed verdicts are exactly F-07, F-08, F-09, and a test proves no check outside the set changed. I did not pad dependencies to reach 14. The UI shows 11; the design copy "14 re-run" needs updating, or Meyer tells us what else they would re-check. | Real number over contract number |
| 18 | 05:20 | The svf-utils CLI (`svf-to-gltf`, 7.x and 8.0.0) fails under Node 26 with a top-level await syntax error. `scripts/node/svf_to_gltf.js` calls the same library directly and writes `properties.jsonl` from the SVF property database (the library has no sqlite output; `rcrv_to_ifc.py` builds `properties.sqlite` from it). | Blocker worked around in under 30 min |
| 19 | 05:20 | Edits act on the in-memory engine model (fast what-ifs and fixes). Writing edits back into the IFC for FreeCAD is not done tonight; the FreeCAD side edits the IFC itself. | Chat-driven edits are a wow feature, not tonight's goal |
| 20 | 05:20 | Fix 1 (widen Stair 3B to 1,400 mm) is checked by the engine on a model copy but is not one of the four chat edits; it is labelled "needs Structure". | The four-edit guard stays strict |
| 21 | 05:30 | Checked the add-on in real FreeCAD 1.0 on this VM (Debian package, xvfb): NativeIFC import gives 251 objects, all with GlobalId. The panel's Analyse returns 96 checks, and clicking F-01 selects FD-5-165P. FreeCAD 1.0's *legacy* IFC importer fails with ifcopenshell ≥ 0.8 (`USE_BREP_DATA`), so use the default NativeIFC importer (File → Open). On first BIM use, FreeCAD shows a Welcome dialog; close it. | Verified, not assumed |
| 22 | 05:30 | Portal: Rail + TopBar, W1 Projects, W2 Inbox, W3 Thread (evidence card + signed rows), W4 Viewer (That Open, pins at finding evidence boxes), W5 Mapping, W6 Rulebook, all reading the engine API through the Vite proxy. Signed approvals live in the browser for now (not persisted). | Build round 1 head start |
| 23 | 05:40 | RCRV object = the named Navisworks node that owns geometry (a block such as `A-CLASS DOOR MA60CX (RI)-118`); its Subentity / MESH children are its geometry. 303,504 geometry nodes → 90,331 objects. | Navisworks tree shape |
| 24 | 05:40 | RCRV IFC geometry: real triangles for doors, windows, stairs and bulkheads (IfcTriangulatedFaceSet, capped at 20k triangles per object); an 8-vertex box face set for pipes, ducts, structure and equipment. Their full meshes stay in the glTF for viewing. Full mesh IFC would be many GB. | File size vs checkability |
| 25 | 05:40 | RCRV decks = peaks of horizontal plate area by height: 7 levels at 1.8, 3.7, 5.8, 8.5, 11.3, 13.9, 16.5 m, named Deck 1…7 from the bottom. ★ Meyer/OSU deck names (e.g. "02 Deck") are not in the model; mapping to the GA names is open. | No deck names in source |
| 26 | 05:40 | RCRV vessel profile: research vessel, 28 on board (16 scientists, 12 crew), no passengers, accessibility on. Engine result: 9 rules Not applicable with the reason shown; accessibility runs in inches. | Brief: applicability is a free accuracy win |
| 27 | 05:40 | RCRV doors: only doors whose leaf was found (tall, thin part) go on the accessible route and get a clear width. The other 237 of 341 stay *Needs review* in mapping_review.csv. Where leaf = block width, the figure includes the frame (upper bound). Door / window / stair classes match the object *name* only, because files called `…DOORS.dwg` also contain brackets. | Measure honestly; nothing guessed |
| 28 | 05:40 | The design's RCRV sample doors D-02-114 (30 in, Fail) and D-02-118 (34 in, Pass) are planted cases. They are not yet planted on a copy of the RCRV deck; that belongs with the benchmark (round 2). | Not tonight's goal |
| 29 | 05:40 | Engine loader fast path: products whose body is only IfcTriangulatedFaceSet are read from coordinates directly, not re-tessellated. | RCRV deck load was 96 s |
| 30 | 12:10 | AI = Gemini `gemini-3.5-flash` on Vertex AI, location **`eu`** (confirmed with a test call; `global` also works but is not used). Google Gen AI SDK, `thinking_level=minimal`, max 300 output tokens, 8 s timeout → engine text, disk cache in `data/cache/ai/`, JSON mode via `response_json_schema`. Env `GEMINI_MODEL`, `GEMINI_LOCATION`, `SONARIQ_AI=off`. The Qwen / `LLM_BASE_URL` path is removed; `llm.Gateway` is the swap point. | User instruction, P0 |
| 31 | 12:10 | The endpoint `qwen_qwen3-0_6b-mg-one-click-deploy` was not found: `gcloud ai endpoints list` and `gcloud ai models list` return 0 items in us-central1 (also europe-west4/1, us-east1, us-west1). Nothing to delete. | Checked, not assumed |
| 32 | 12:00 | ~~Superseded by #36.~~ ★ **Stair 3A added** (Fr 126–130, MVZ 4, inboard aft, clear width 1,600 mm, persons_by_deck D4 36 / D6 40 / D7 20) because the evacuation simulation needs both escape stairs of MVZ 4. LOUNGE-5-125 now ends at Fr 126 and a new LOUNGE-5-132 fills Fr 130–134. **Findings are unchanged** (Rev A F-01, W-01, U-01; Rev B adds F-07, F-08, F-09), but the totals grow by 9 Pass checks: Rev A 105 = 1 · 1 · 1 · 98 · 4 (71 / 22 / 12), Rev B 4 · 1 · 1 · 95 · 4, fix 2 3 · 1 · 1 · 96 · 4. The OR-117 re-run is now **12** (Stair 3A's formula also counts MVZ 4 berths: 1,230 → 1,310 mm required, still Pass). The design's 96 / 89 and "14 re-run" copy needs updating; the UI reads the engine, so nothing is typed. | User instruction ("add 3A if missing; existing findings unchanged") |
| 33 | 12:20 | The SOLAS II-2/9.4.1.1 self-closing rule already exists as **R-FLS-10** (clause II-2/9.4.1.1.4, status verify): every door hosted in an A-class division (MVZ bulkheads, stair enclosures, galley boundary) must have `Pset_DoorCommon.SelfClosing = TRUE`; empty = Cannot verify. Not duplicated. The smoke what-if reads the same property: TRUE holds smoke, FALSE or empty = open (worst case). | Already in the rulebook |
| 34 | 12:20 | **Simulation model** (engine/sim, params in `engine/sim/params.yaml` with Circ.1533 paragraph refs, all `verify`): JuPedSim 1.4.2 CollisionFreeSpeedModel, dt 0.05 s; walkable = IfcSpace footprints minus IfcWall footprints plus IfcDoor openings; people spawn in their cabin at their response time (truncated log-normal, Annex 3 App.1 §3.2.2), speeds uniform per Table 3.1/3.4 group; each person heads for the stair landing with the shortest route. A stair is a capacity-limited exit: a JuPedSim queue on each landing, released at specific flow × flight clear width (0.88 p/m/s, stairs up, Annex 2 Table 1.2), shared with timed inflows from Decks 4, 6, 7 (persons_by_deck, arrival = response + U(15, 60) s), served in proportion to who is waiting. Secondary case: the closed stair's other-deck people move to the open stairs of the same MVZ. Night counterflow crew (§4.1.3) is not modelled; day public spaces at 2 m²/person × 75 % (SonarIQ assumption). | Thin prototype, honest labels |
| 35 | 12:20 | `SIMULATE_ENABLED` defaults to **off**, so `main` stays demo-ready when the branch merges; `make api-sim` (or `SIMULATE_ENABLED=1 make api`) turns it on. The portal shows the Simulate tab and the panel shows the Simulate button only when `/health` says so. | User instruction |
| 36 | 12:25 | ★ **Stair 3A = the MVZ 5 stair at Fr 170–174** (next to the lifts), as drawn in `design/screens/10-simulate.pdf` ("Stair 3A · MVZ 5"; people aft of Fr 165 reach it through FD-5-165P/S). The deck's former "Stair 3C" is renamed 3A (its door D-5-171-S still has no FireRating = U-01), and the aft stair added at 12:00 (#32) is removed. Contract counts are back to the design: Rev A 96 = 1 · 1 · 1 · 89 · 4, Rev B 4 · 1 · 1 · 86 · 4, fix 2 3 · 1 · 1 · 87 · 4, OR-117 re-run 11. | Design wins over my guess |
| 37 | 12:50 | **RAG**: public sources only, chunked by paragraph with citations: MSC.1/Circ.1533 (140 chunks), ADA 2010 Standards (744), proposed PVAG ch. V1–V11 from access-board.gov (636), COLREG rules text from Wikisource (41; the USCG PDF returned 403), our 15 rule readings, Meyer Q&A 1 notes. No SOLAS/FSS text; DNV link only. A Vertex AI RAG Engine corpus exists in europe-west4 (`ragCorpora/6917529027641081856`, 6 files) and works, but on our 15-question set it finds the right source + paragraph in **12/15** (median 1.8 s) against **14/15** (0.3 s) for the local SQLite index with `text-embedding-005` (europe-west4) over the same chunks. Default = local; `SQ_RAG_CORPUS=<corpus>` switches to RAG Engine. Embeddings are not served on the `eu` multi-region, so they run in europe-west4. | Measured, not assumed |
| 38 | 12:50 | Rule drafts from a clause are saved to `rules/drafts/*.yaml` with `status: draft`; the engine loads only `rules/seed_rules.yaml`, so a draft never sets a verdict until a human moves it in. | RAG never sets a verdict |
| 39 | 13:00 | ★ **Smoke what-if routing**: smoke-filled spaces are *avoided*, not removed from the walkable area. Each person picks the landing whose route crosses the least smoke (smoke metres × 5 + route metres) when they start and at every smoke step; people who still walk through smoke are counted as *exposed*. The fire origin itself is not walkable from t = 0. Why: at night smoke fills the MVZ 5 cabins (cabin doors are not self-closing) before anyone wakes (400–700 s), so making smoke-filled spaces non-walkable would trap everyone in them, which says more about the assumption than the design. | Spec said non-walkable + reroute; this keeps rerouting without trapping |
| 40 | 13:00 | The number guard now also checks number words ("seven", "forty-four"); "one" is skipped because it is usually a pronoun. Found when the hotspot analyst wrote "seven people". | A loophole closed |
| 41 | 14:00 | **Fire what-if is reported as exposure, not time.** In the cached night runs with the fire origin near Stair 3A (LOUNGE-5-180), p95 assembly time is unchanged against the same model without the fire, while every run has people walking through smoke and nobody switches stairs (numbers: `docs/DEMO_SCRIPT.md`, W10 smoke card, both computed from the runs). The summary now aggregates smoke exposure over all runs (`smoke_summary`) and the demo script says the fire shows in exposure. Not tuned to make the fire look bigger. | Report, don't hide |
| 42 | 14:00 | **Hosted demo** at `https://34-88-130-224.sslip.io` (Caddy, Let's Encrypt via sslip.io, basic auth; engine as a systemd user service with `SONARIQ_HOSTED=1` and Simulate on). Caddy binds the NIC address only because Tailscale already serves :443 on its interface. The FreeCAD panel uploads the open IFC to a remote engine (`POST /upload`); a byte-identical demo file maps to its revision so edits and cached simulations keep working. Engine and portal share one session. | User instruction: only FreeCAD on the Mac |

---

# Milestone: whole-ship viewer (14 Nov 2026)

Spec: `docs/milestones/SONARIQ-MILESTONE-SPEC.md`. Evidence: `docs/AUDIT.md`, `spikes/b1/`, raw results in
`data/rcrv/spike_b1/bench_*.json` (not in git: real-ship data). VM: 4 vCPU, 16 GB, **no GPU** (SwiftShader software GL),
so every fps below is a lower bound, not a laptop number.

## M1 — Viewer format: Meshopt glTF tiles in plain three.js (not Fragments)

Both prototypes were built on the full RCRV (50.84 M triangles, 90,331 elements), same machine, same bench script.

| Measure | glTF tiles | That Open Fragments 3.6.1 |
|---|---|---|
| Input it needs | the glTF as delivered | an IFC with real triangles: 7 files, **2.18 GB, 313 s** to write (the existing RCRV IFC is 91 % boxes) |
| Conversion | **38 s + 31 s pack** (peak 1.8 GB) | decks 2–7: **467 s** (peak 3.1 GB per deck); **deck 1 (679 MB IFC) killed at the 3.6 GB cap** |
| Output size | **205 MB** whole ship | 317 MB for decks 2–7 (≈ 450 MB projected with deck 1) |
| Time to first frame | **1.0–1.2 s** whole ship (overview complete 3.3 s) | 3.9 s for one deck (deck 7); six decks did **not** reach ready within 10 min |
| Draw calls | 271 overview, ≈ 230 close-up | 159 for deck 7 alone |
| Orbit fps (software GL) | 0.6 at 4.0 M triangles | 1.35 at 1.4 M triangles (one deck) |
| Browser memory | 103 MB JS heap, 1.4–1.9 GB process RSS | 56 MB heap for one deck; 4.2 GB RSS trying six decks |
| Picking → right element | 49/60 first hit, **60/60** after hiding enclosing parts | **not scored**: hits return real GlobalIds (IDs survive), but my harness could not align the test camera (loaded-deck boxes differ from the tile boxes by up to 12 m), 0/8 on decks 5–7 where tiles got 8/8 |
| Integrity check | decode every tile, 0 vertex / 0 triangle mismatches, max quantisation 0.16 mm | none built in |
| Capping / clipping | ours to write (stencil caps, M5) | `getSection()` gives edges and fills |

Decision: **glTF tiles**. It is the only option that loads the whole ship here, it converts the RCRV in about a minute
without an IFC hop, and picking returns the engine's ID. Fragments' real advantage (built-in section fills, raycast,
highlighter) does not offset an IFC hop that cannot finish deck 1 in 3.6 GB. Fragments also needs its worker served
from our origin (it defaults to unpkg; rule 3), which we solved in the spike, so that was not the deciding factor.
Cost accepted: we write capping, picking and display modes ourselves on one shader (M5, M9).

Small IFC models (deck5) go through the same tile writer (geometry from `ifcopenshell.geom`), so the Studio has one
viewer path. The old browser-side IFC loader stays only as a fallback when conversion fails, with a visible message.

## M2 — Libraries and versions

Portal stays on three 0.160.1 (shared with `@thatopen/components` 2.3.0 used by the Simulate 3D); GLTFLoader 0.160
supports `KHR_mesh_quantization` and `EXT_meshopt_compression`. Decoder: `meshoptimizer` npm (MIT), served from our
origin, because three's bundled decoder rejects vertex codec v1 (found in the spike). Encoder: same package in node at
conversion time. No new runtime dependency besides `meshoptimizer`. All MIT/Apache/BSD.

## M3 — Tiles layout

Per model: overview level (largest size-per-triangle elements ≥ 1 m, up to 4 M triangles) and detail level (the rest),
each split by discipline group × deck × 8 m slice; one draw call per tile. Positions uint16 quantised per tile, no
normals (flat shading from derivatives), element index per vertex. Detail streamed within 24 m of the camera, 1.5 M
triangle budget, 6 requests in flight. Tiles are content-addressed under `data/models/<sha>/` and served with
`Cache-Control: public, max-age=31536000, immutable`; Caddy already compresses. shortcut: overview by size-per-triangle,
not Complee's exterior-visibility sampling; upgrade if the overview shows holes from outside.

## M4 — ID mapping

- One `elements.json` per model: index → `[stable_id, source_id, ifc_class, name]`. Vertex attribute = index; GPU pick
  returns the index; the viewer looks up `stable_id`.
- `stable_id` = IFC GlobalId. For IFC input it is read from the file. For the RCRV glTF it is
  `compress(uuid5(NS, dbid))`, the exact function `scripts/rcrv_to_ifc.py` uses, so findings on `rcrv_deck_n.ifc` and
  the tiles agree without a lookup table. `source_id` = IFC `Tag`, or the Navisworks dbid, plus the ShipConstructor
  PartGUID in the metadata index when present.
- The engine never sees tiles; the viewer maps `finding.element.guid` → index. Proven by `tests/test_id_mapping.py`
  (deck5_revB and RCRV).

## M5 — Section and capping

three.js clipping planes in the tile shader; caps by the stencil method (back faces increment, front faces decrement,
then a plane quad where stencil ≠ 0) per cut, coloured by discipline or material. Section edges: CPU plane ∩ triangles
for tiles whose box crosses the plane, in a worker. Many ShipConstructor parts are closed solids, but pipe and mesh
objects are not guaranteed closed; where a mesh is open the cap would leak, so caps draw only for groups marked
closed (structure, architecture) and the rest get section outlines. This is documented in `docs/VIEWER.md`. If stencil
capping is too costly on a laptop GPU, the fallback is outlines only for all groups (spec allows it).

## M6 — Ship coordinates

The RCRV model has no frame grid and no deck names. Frames: metres from the aft end of the geometry with user-settable
frame zero and spacing (stored per model in `meta.json`); deck5 uses its `frame_spacing_m` (0.8 m). Decks: RCRV levels
from `rcrv_to_ifc.py` (plate-area peaks), deck5 from the storey.

## M7 — Provenance in the finding schema (backward compatible)

New optional key `provenance` on `measured`, `required` and every `formula.inputs[]` item:
`{kind: model|derived|public|estimated|user|confirmed, file, element, pset, prop, raw, inputs, by, date}`. Missing key
= old finding, the UI shows no chip. The existing `formula.inputs[].source` stays as it is. The engine fills it in
`checks.py` where the value is read; the AI never writes it.

## M8 — View pane placement

A **View** tab next to **Findings** in the right panel, not a collapsible section: the Findings list needs the full height
at scale (B6), and the tab keeps both one click away. Selection and cuts survive switching tabs.

## M9 — Display modes on one shader

All modes are uniforms/defines of the tile shader (shaded, edges via a screen-space id/depth pass, x-ray, lines,
wireframe via `wireframe`), plus a per-element colour texture for discipline solo and colour-by. Realistic = lights +
per-class colours, no shadows if they cost more than 2 draws per tile (cut first).

## M10 — Rules on real data (B3)

What the RCRV actually has (AUDIT § What the models contain): plates have thickness and grade (100 %), pipes have a
system name and usually a material value, there are **no spaces**. Hence:

- Fire & escape packs on RCRV: **Not possible** (no spaces), shown in readiness, never run.
- R-STR-01 hull steel grade allowed set (IACS UR W11): steel plates/stiffeners with a `CS ABS <grade>` material must name
  a W11 grade (A, B, D, E, AH/DH/EH/FH 32/36/40); aluminium is out of W11's scope (Not applicable, reason shown).
- R-STR-02 grade vs thickness (IACS UR S6): **draft, does not run** — the table is not in the repo, and S6 applies to ships
  ≥ 90 m (RCRV ≈ 67 m). The UI says so, like Complee's minimum thickness.
- R-SYS-01 oil fuel pipes (SOLAS II-2/4.2.2.5.1, "steel or other approved material"): steel → Pass; other metal →
  **Warning** (needs approval evidence), not Fail; no material value → Cannot verify. Systems: name contains FUEL OIL /
  FO OVERFLOW.
- R-DQ-01..03 data quality: missing grade/thickness on a plate; non-structural material on a plate (`AIR AIR`,
  `DETA COUPLE`, dim pads); error values (`Error`, `---`).
- `verified_against_official_text: false` for all of them: no official text in the repo. The banner shows "0 of N rule
  values verified against official text" honestly.
- Pipe attribute names were lost in the property export; material is found by pattern and insulation specs are
  excluded explicitly. shortcut: pattern match, upgrade by re-extracting attribute display names from the APS database.

## M11 — Model revisions (B11, added 14 Nov)

- **Model = a line of revisions; revision = draft until exported.** Every Analyse replaces the model's open draft;
  Export (BCF, report or CSV, from the Studio, the print page, the report dialog or the FreeCAD panel's BCF) freezes it
  as Rev A, B, C…; the next Analyse opens the next draft. Exporting an already saved run returns that revision.
- **Which model a run belongs to:** the upload choice ("New model" / "New revision of <model>") when given; else the
  three deck 5 demo files → "Deck 5 demo", the RCRV → "RCRV whole ship", an upload → the model that last read a file
  of that name, else a new model named after the file. The FreeCAD panel sends no choice, so it gets the inference.
- **Store:** SQLite `data/revisions.sqlite` (index) + `data/revisions/<model>/<seq>/` (snapshot.json, export.bcfzip,
  checks.csv, report.json). Saved = frozen: a trigger refuses any change except the label and refuses deletes; the
  files are chmod 444. The three export files are written at save time from the stored run, so every format is in the
  bundle whichever was clicked (the BCF from the stored run, not the live session: pins and sign-off comments of the
  session BCF are not in it).
- **Rule-pack version** = first 12 hex of sha-256 over that pack's rules as loaded (the YAML has no version field);
  it changes whenever a rule changes. **Model file hash** = sha-256 of the IFC the run read; RCRV (no single file) =
  sha-256 of `data/rcrv/manifest.json`, named in the snapshot as the basis.
- **Accuracy banner in the snapshot** = `/accuracy` computed at save time (only the revisions with hand-checked ground
  truth: A, B, RCRV); others store null.
- **Compare = one diff** (`engine/sonariq/revdiff.py`), also behind `/runs/diff`: match by check key (rule + element
  GlobalId); a finding left on both sides with the same rule and element name (or location) is a fallback match shown
  as "please confirm", only when that pairing is unique. On compact (whole-ship) runs passes are not in `checks`, so a
  finding that passes in the newer run counts as resolved with status "removed".
- **Reset all data** archives the revision store and saved views too (it used to keep views).

## M12 — Callouts (A5, added 14 Nov)

- **Module split:** `portal/src/viewer/callout.ts` is pure (content, placement, number guard) and unit-tested;
  `components/Callout.tsx` draws the card and leader; `ShipView` owns the anchor, pins and occlusion. Content comes
  only from the finding JSON (`calloutContent`); `strayNumbers` is the guard the unit test and e2e run on every card.
- **Anchor** = the evidence footprint raised to 2 m (the engine sends 2D footprints + floor z), else the element's
  box from the metadata index. Placement tries right / left / above / below the anchor box's screen rectangle and
  never overlaps it; a model filling the view gets the far corner.
- **Occlusion** = one extra depth pass at the anchor pixel (`ShipViewer.occluded`, uPass 3: solid elements only, the
  finding's own parts excluded, cuts applied), run once the view has been still for 300 ms. Occluded → the card
  collapses to a dashed pin. No CPU raycast: tiles have no BVH and RCRV has 50 M triangles.
- **Pins** only for findings with an evidence box (no element-box fetch per finding); at most 300 on screen.
- **Material / fire class:** the element is tinted with the status colour (what it is); a dashed outline labelled
  "must be A-60" shows what it must be. Tinted volumes were cut (plan cut-list); the footprint fill + ring stay.

## M13 — Demo run-through (B8, added 14 Nov)

- Runs on the **Deck 5 demo model**, not the RCRV: it has every finding kind with callouts and loads in seconds on any
  laptop; the RCRV whole-ship analysis takes minutes on this VM. The whole-ship story is in the README and screenshots.
- Deck 5 has no pipes, so step 6 solos HVAC and says so; the same step solos piping on a model that has it.
- The compare step needs a saved Rev A of the demo model. If there is none, step 3 analyses Rev A and saves it before
  analysing Rev B (said in the step 7 caption). Later plays reuse it, so the hosted store grows by one revision at most
  per demo, plus the BCF export of step 8 (Export = save, as everywhere else).
- Plays by itself (7 s per step after the step's action finishes); Space / → next, Esc stops, Pause holds.

## M14 — Merge to main (14 Nov)

The spec says "open a PR, do not merge". The user asked on 14 Nov to finish steps 8–9, merge to main and push, then
review it themselves. Merged with `--no-ff` so the milestone stays one reviewable merge; nothing was deployed.

## M15 — Projects → models → revisions (Studio reliability, 14 Nov)

Reconciled with step 7 (B11, M11). Differences from step 7, all deliberate:

- **Project level added.** `projects` table; every model has a `project_id`. The header's Project menu lists, creates
  and renames projects. Projects are never deleted from the UI. Demo run-through projects are the exception (M17).
- **A revision is one file version** (`source`: `demo:A|B|Bfix2`, `rcrv`, `path:<file>`) plus its analysis state. It can
  exist before any analysis (`run_id` NULL). Step 7 created a revision only on Analyse and kept one draft per model,
  which any file replaced. Now:
  - analysing a draft replaces its run;
  - analysing a saved revision opens a new draft of the same file (`Rev <letter of seq>`), which starts with that
    revision's marks and tasks;
  - an FreeCAD-panel run without a revision goes to the draft that read the same file, else to a new draft. The panel
    never names a revision; its runs go to the shared "Demo ship" project.
- **Scoped state:**
  - marks, tasks and saved views are kept per revision (`{"<revision id>": {...}}`). In step 7 they were global by
    check key, which is why Inbox (7) and Tasks leaked between models.
  - a saved revision's marks and tasks come from its snapshot, which now also stores tasks, and they cannot be changed:
    writes get 409 with "Analyse it again to start a new draft". Step 7 let marks change after an export because they
    were global.
  - requests without `revision_id` (the FreeCAD panel) use the revision of the engine's latest Analyse.
- **Migration** (on first open of a step 7 store): the old index is archived (`data/archive/<ts>-projects/`), as are
  the Deck 5 demo / RCRV snapshot folders. These were all made by demo runs and tests, so nothing is deleted. Any other
  model keeps its revisions (same ids and folders) in a project "Earlier uploads". "Demo ship" is then seeded:
  - Deck 5: Rev A, Rev B, Fix 2;
  - RCRV whole ship: Rev 1, if `data/rcrv` exists;
  - nothing analysed.

  Old global `tasks.json` / `incorrect.json` are archived (`<ts>-unscoped/`) on first read; there's no revision to
  give them to. Reset all data re-seeds the same way.
- **Revision menu** in the header: revisions of the open model, newest first, with fail / pass / cannot-verify counts
  ("not analysed" before the first run). It replaces step 7's "Open read-only / Back to current". Opening a saved
  revision is the same as switching to it, and the Studio shows it read-only. The Studio's Revisions tab shows only
  the open model.
- **Open model** lists the project's models; picking one opens its latest revision. Upload asks "New model in this
  project" or "New revision of <model>" right after the upload, and creates the revision before analysis. Step 7 asked
  in a "Save as" select at Analyse time.
- **Clear all** replaces the Studio's Close button, which was the model-list toggle (the toggle is now always "Open
  model"). "Save and clear" uses the step 7 save (POST /revisions/export, format report). Clearing closes the model in
  this browser only and deletes nothing.
- **Reset all data** moved from the sidebar into Settings → Danger zone and needs RESET typed.
- **Not scoped yet:**
  - the Revisions screen (the engine's whole run history);
  - the finding Thread, which reads the engine session's latest run.

  Both are as before; noted in the fix report.
- Steps 2 and 3 share one commit: the Clear all dialog is part of the same Studio rewrite.

## M16 — Demo that cannot get stuck (Studio reliability step 4, 14 Nov)

- **Own project.** Pressing ▶ Demo creates a throwaway project (`POST /projects/demo`: Deck 5 with Rev A and Rev B,
  `demo = 1`, expires in 1 h). The demo never writes into the user's project. The project is deleted, with its runs,
  marks and saved revisions, when:
  - Stop or Finish is pressed;
  - a `GET /projects` / `POST /projects/demo` call finds it expired.

  A closed tab therefore leaves it at most an hour. Demo projects are not listed in the Project menu.
- **Start and restore.** The project is created in the start handler, not in step 1, so React StrictMode's double
  effect can't make two. Stop and Finish restore the project, revision, panel tab and model list that were open. The
  display mode and cuts come back once the previous model is in the 3D again (at most 60 s).
- **Steps.** Every step has:
  - a precondition: the demo project is open, plus whatever the step needs;
  - a timeout: 20 s, or 60 s for loading the 3D;
  - an AbortSignal: Next, Skip and Stop abort the running step, so it stops changing the Studio;
  - an error state in the card: "Couldn't <action>: <reason>" with Retry and Skip step.

  Next, Pause and Stop are never disabled.
- **No conversion during the demo.** The viewer asks `/models/prepare` with `convert: false`. A model that isn't
  prepared shows "not prepared on the server yet" as the step 2 error and never starts a conversion. The deploy
  pre-converts every bundled model (step 1).
- **Compare.** Step 3 analyses and saves Rev A, then analyses Rev B, both in the demo project. Step 7 compares the two.
  Step 8's BCF export saves Rev B there too.
