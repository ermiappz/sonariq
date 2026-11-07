# SonarIQ design hand-off

Source: Claude Design canvas **SonarIQ — Complete UI** (https://claude.ai/artifact/R5sHx6KPpwL2f3judW9W8x), exported Sat 7 Nov 2026. This folder is the design input for SPEC v2 and the build.

## What is in this folder

| Path | What it is | How to use it |
|---|---|---|
| `sonariq.css` | Tokens and component classes, copied verbatim from the canvas | The portal imports it as is. Class names (`sq-pill`, `sq-row`, `sq-formula` …) are the component names below. |
| `tokens.json` | The same tokens as JSON (dark, light, base, status words and glyphs) | Single source for the FreeCAD panel and any generated theme. |
| `panel.qss` | Starter Qt stylesheet for the FreeCAD dock, generated from the dark tokens | `dock.setStyleSheet(...)`; set `objectName = "SonarIQPanel"` and the dynamic properties noted in the file. |
| `screens/*.pdf` | One PDF per canvas page (exported from Claude Design) | Read page by page; artboard titles below say which is which. |
| `screens/*.png` | PNGs of the must-have artboards, if exported | Visual reference at 1:1. |

If a screen and this file disagree, the screen wins for layout and copy, and `sonariq.css` wins for colour, type and spacing.

## Non-negotiables (apply on every screen)

- Every status shows **icon + word**, never colour alone: Fail ✕ · Warning ! · Pass ✓ · Accepted with reason ⚑ · Cannot verify ? (dashed) · Dormant ○ · Not applicable —.
- Verdicts carry the **Rule engine** badge (`sq-engine`). AI text carries **AI explanation · numbers checked** (`sq-ai`). The AI never sets a status.
- The chat previews every model edit and waits for **Confirm**. Only four edits exist: add cabin block, move wall, set door width, set door fire class. The edit guard is deterministic code, not the model.
- Missing data becomes **Cannot verify**, never Pass and never a guess.
- No AI vendor or model name anywhere in the UI (Settings says “on-premises / approved cloud / off”).
- Panel = plain Qt widgets: no blur, no shadows, no web-only effects. Dock height in FreeCAD is 756 px; the panel content scrolls.
- People's names in the designs (e.g. Mikko Saari) are sample data. Benchmark results stay `[after run]` until the suite produces them.

## Sample data the whole UI uses

| Thing | Value |
|---|---|
| Model | Demo ship · Deck 5 · Fr 138–178 · MVZ 4/5 A-60 bulkhead at Fr 165 · Rev A → Rev B (OR-117) |
| Summary strip order | Fail · Warning · Cannot verify · Pass · Dormant |
| Counts Rev A | 1 · 1 · 1 · 89 · 4 (96 checks, 2.1 s) |
| Counts Rev B (after OR-117) | 4 · 1 · 1 · 86 · 4 (14 re-run, 3 changed: F-07, F-08, F-09) |
| Counts Rev B after fix 2 | 3 · 1 · 1 · 87 · 4 |
| P2 mid-run | 61 of 96 so far: 1 · 0 · 1 · 57 · 2 |
| Pack split (P1) | 64 / 20 / 12 checks; Class (DNV) pack = To verify |
| F-01 | Fire door FD-5-165P, MVZ 4/5 bulkhead, Deck 5 · Fr 165 · P, A-0 fitted vs A-60 required |
| W-01 | Corridor Deck 5 · Fr 152 · S, 900 mm vs PVAG 915 mm (36 in), warning (draft guideline) |
| U-01 | Door D-5-171-S, `Pset_DoorCommon.FireRating` empty → Cannot verify |
| F-07 | Stair 3B (Decks 4–7): required 1,380 mm, measured 1,350 mm; W = (N₁ + N₂ + 0.5 N₃ + 0.25 N₄) × 10 mm, N₁ 68 (D5), N₂ 44 (D6), N₃ 40 (D4), N₄ 24 (D7); Rev A needed 1,300 mm |
| F-08 | Dead-end corridor Deck 5 · Fr 146–150 · P, depth 4.2 m > width 1.2 m |
| F-09 | Corridor pinch Deck 5 · Fr 152 · S, 850 mm vs 900 mm |
| Fixes for F-07 | 1 widen to 1,400 mm (needs Structure) · **2 four cabins, one berth each → 1,340 ≤ 1,350 (applied)** · 3 one cabin → 1,320 · rejected idea: move block 10 frames forward → still 1,380 |
| H-01 (HVAC) | Duct VD-5-03 crosses the A-60 bulkhead at Fr 165 with no fire damper |
| RCRV | Research vessel, 28 on board (16 scientists, 12 crew); SOLAS >36-passenger rules Not applicable; D-02-114 30 in vs 32 in Fail (ADA 2010 §404.2.3); D-02-118 34 in Pass |
| BCF | `sonariq_rev-b.bcfzip`, 6 topics; P7 sends 2 decisions, 4 open findings |

Rule references in the designs are sample text. The engine build confirms each one against its source before the demo.

## Artboard index

Canvas pages: **0** Start here (index + tokens) · **6** FreeCAD window · **7** Panel states · **8** Portal · **9** Components, settings, review board.

### Page 6 · FreeCAD window (build target: FreeCAD addon, PySide dock + 3D highlights)

| ID | Size | Hand-off |
|---|---|---|
| F0 | 1440 × 900 | SonarIQ inside FreeCAD; the playable golden path: P1 → Analyse → P2 (1.4 s) → P3 → click F-01 → P4 → Chat → P5 (Send, Confirm, chip “Why does stair 3B fail?”, Apply fix 2) → Accept F-08 → P6 → P7 → Send opens W2. Chrome: menu, 2 toolbars, Combo View tree + Property View, status bar, DeckPlan, docked 380 px panel, fire-division legend bottom-left. Tree and Property View follow the selected finding. Pins select; F-01 pin opens P4; toolbar ▶ Analyse = panel Analyse. Ping ring plays once on Confirm. Errors: AI offline → E3; edit refused → E1. |
| F0 · P3 | 1440 × 900 | After Analyse on Rev A: F-01 solid outline + pin (selected, dashed accent box), W-01 warning outline, U-01 dashed outline. Tree shows status icons on FD-5-165P and D-5-171-S. Status bar: 1 fail · 1 warning · 1 cannot verify. |
| F0 · P5 | 1440 × 900 | Just after Confirm on OR-117: Rev B, cabin block × 4 hatched, static rings on the 4 places that changed (block, Stair 3B, dead end, pinch). Ring: 600 ms ease-out, once; reduced motion = no ring, counts highlight. |
| DeckPlan | 800 × 400 | Shared plan view (F0, E4, W3, W4, W8). Props: rev A/B, focus, pins, ping, pingStatic, fix2, accepted, hvac, legend, w, theme, onPick. A-60 4 px solid (MVZ bulkhead Fr 165), A-0 2 px solid (stair + lift enclosures), B-15 dashed (corridor bulkheads), B-0 dotted (cabin partitions). Ink is neutral; status shows only as element outline + pin with icon. Port at top, bow to the right; frame ruler every frame, labels every 5. three.js: same layers as meshes, pins as screen-space HTML. |

### Page 7 · Panel states, 380 × 860 (build target: PySide dock)

| ID | Hand-off |
|---|---|
| PanelHead (shared) | Header (wordmark, project · revision, Live, settings), context bar (profile chip, scope Selection / Deck 5 / Whole model, pack toggles), Analyse, summary strip (5 cells, click to filter), tabs Findings / Chat / History. Props: rev, mode idle/running/results, counts none/run/A/B/Bfix, tab, live, changed, filter, ai, runMeta. |
| Evidence (shared) | One card for panel (dark) and portal / print (light). Findings F-07 / F-01 / F-08 / D-02-114. Sections: header, rule + clause, required vs measured, formula (F-07) or model inputs, method, decision banner (F-08), actions. |
| P1 Idle | Before the first run; says what will run (96 checks in 3 packs). Analyse primary, Live toggle, scope segment, pack chips. Error: model not IFC4-mapped → footer shows the problem and Analyse disables. |
| P2 Running | Progress per pack (neutral bars, not status colours); Cancel keeps partial results marked partial. Findings stream in with a 900 ms tint. A crashed pack shows “stopped” and its checks count as Cannot verify, never Pass. |
| P3 Results | Grouped by discipline, then status. Row: status pill, ID + title, location chip, rule badge, one line of numbers. Summary cells filter. Pass and Dormant collapsed. Click row → select in 3D + P4; U-01 → E2. Group-by-location toggle. Empty pack: “No open findings in this pack.” |
| P4 Evidence | F-07 by default (F-01 in the golden-path click). Rule engine badge, rule + clause excerpt, required / measured / margin with per-value unit toggle, formula inputs clickable to highlight the spaces counted, Rev A note 1,300 mm, measurement method, actions Fix options · Accept with reason · Send to review · Zoom to. Missing input → chip shows ? and the verdict becomes Cannot verify. |
| P5 Chat | Golden path as one scroll (canvas shows it unrolled to 1,880 px; dashed line = 860 px fold): user message → edit preview (Confirm / Cancel) → ping card (14 re-run · 3 changed, rows clickable) → AI explanation (only engine numbers) → 3 fix cards, each re-checked by the engine → 1 rejected idea, collapsed → Applied: F-07 Pass 1,340 ≤ 1,350 mm. Placeholder “Ask a question or describe a change”; chips “What did my last change affect?”, “Why does stair 3B fail?”. |
| P6 Accept with reason | Modal: rule and numbers, required reason, who it goes to (Fire & life safety lead), who signs, what happens next. Engine verdict stays Fail; status becomes Accepted with reason only after approval. Empty reason → error message. |
| P7 Send to review | Decisions (2), open findings (4), recipients by discipline (FS 5, AC 1), BCF file (6 topics), OR-117 link. Send → portal W2. BCF write fails → file row Fail with Retry; nothing is sent half-way. |
| E1 Edit not allowed | Request outside the four edits; model unchanged. Offers Live, “which rules use this value”, and an example for each allowed edit. |
| E2 Cannot verify | Dashed card: what is missing, which rule needs it, that SonarIQ does not guess. Resolve by: add in FreeCAD, set here (allowed edit with preview), or confirm with a source (goes to the lead). |
| E3 AI offline | Offline banner with endpoint type and since-time, Retry. Lists what still works (Analyse, Live, evidence, accept, send, BCF). Input disabled; no queued messages. |
| E4 Live + ping | A: compact strip “Live · last check 2 s ago · 0 new”. B: ping lands, 14 re-run · 3 changed, Fail 1 → 4 and Pass 89 → 86 tinted for 2 s, rings in 3D. C: reduced motion: no ring, counts highlighted, polite live-region announcement. |

### Page 8 · Portal, 1440 × 900, dark or light (build target: React + three.js)

| ID | Hand-off |
|---|---|
| Rail + TopBar (shared) | Rail: Projects, Inbox (7), Model, Rules, Benchmark, Revisions, Settings; active = accent inset bar. TopBar: project, revision, search, units mm/in, user with role. |
| W1 Projects and upload | Demo ship (IFC4, Rev B 3·1·1·87·4, HVAC H-01) and RCRV (Navisworks → IFC, applicability, mapping to review). Drop zone for IFC4, OCX (.3docx), BCF; recent files checked / validating / to review / not read. Links: RCRV → W4-RCRV, Review mapping → W5, Open inbox → W2. |
| W2 Discipline inbox | Tabs: Fire & life safety 5, Structure 0, Architecture 0, HVAC 1, Systems 0, Accessibility 1. Columns: select, status, finding, location, rule, owner, age, decision. Bulk: Assign, Export BCF (approve stays one by one so each is signed). F-07 → W3. Empty tab explains why. |
| W3 Finding thread | Left: evidence card + 3D snapshot. Right: code-review style thread (engine events, designer decision from FreeCAD with time + revision, comments) then Approve / Request change / Decline (reason required). Approve adds a signed row (name · role · time · revision), Undo for 5 s. F-08 variant shows accept-with-reason. |
| W4 Model viewer | Deck selector, discipline layers, finding pins, measure tool (850 mm at Fr 152 · S), section box, deck stack (Stair 3B spans Decks 4–7). Right list = findings on this deck incl. H-01. Load error keeps the list and offers reload. |
| W4-RCRV | Applicability banner (28 on board; SOLAS >36-passenger rules listed as Not applicable with reason). Inches. D-02-114 Fail, D-02-118 Pass. Mesh-geometry caveat links to W5. |
| W5 Import mapping review | Navisworks layer / item → IFC class → deck, frame, side, MVZ, SOLAS category, berths. Matched / Needs review / Unmapped chips. Resolving one row applies to all matching elements. Keys J/K/A/E/U. Nothing unmapped is guessed; it becomes Cannot verify. Fed by `mapping_review.csv` from the RCRV conversion. |
| W6 Rulebook | Packs: Fire & life safety and Accessibility Verified; Class DNV To verify. Rule row: ID, clause, plain summary, applies to, parameters, status, tests. Detail: formula, inputs, units, when it returns Cannot verify, reviewer. |
| W7 Benchmark | 8 planted cases + 2 clean controls. Caught, missed, false alarms, run date and every Found cell are `[after run]`. Caught = expected status on the expected element and rule. |
| W8 Revision impact | Rev A vs Rev B via OR-117: 4 cabins added, 2 corridors reshaped, 14 checks re-run, 3 verdicts changed; side-by-side mini plans; W-01 shown as value changed, status unchanged. |

### Page 9 · Components, settings, review board

| ID | Hand-off |
|---|---|
| C1 Component sheet | Every component with states: status pill × 7 (dark + light), chips, rule badge (long refs wrap), measurement + unit toggle, formula, required vs measured, finding row (default, hover, selected, changed, accepted), summary strip, edit preview, ping card, fix card (verified, applied, rejected), chat messages, signed history, buttons, inputs, tabs, toggles, pins, legend, evidence card. |
| S1 Settings | Units (mm default, inches when the rule is in inches, m over 1 m), rule packs on/off with Verified / To verify, AI endpoint (on-premises, approved cloud, off; Test), what is and is not sent to the endpoint. |
| Q1 Meyer review board | Print board (light) for the 09:00 session: P3 (Rev A), P4 with F-01 and Fix options hidden, W3 with F-08. Five questions with writing space. Typed change, ping and fixes are deliberately left off. |

## Build order the design implies

1. Engine + sample model first: every number above must come out of the engine, not be typed into the UI.
2. Panel: PanelHead, P3, P4/Evidence, then P5. Use `panel.qss`; one widget per component in C1.
3. Portal: Rail/TopBar, W2, W3, W4 (+ RCRV variant), then W5 and the rest.
4. Q1 can be printed straight from the canvas for Q&A 1; it needs no code.
