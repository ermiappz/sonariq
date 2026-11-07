# SonarIQ SPEC v2

Version 2 · 7 Nov 2026 (overnight build) · inputs: the SonarIQ brief (`docs/brief/`, live doc linked there), `design/handoff.md`, `design/screens/*.pdf`, `rules/seed_rules.yaml`. Where they disagree, the brief wins for scope and handoff.md wins for numbers and copy.

**SonarIQ is a co-pilot in the ship design tool. When an engineer changes something, it says which safety rules break, where, and why.** One deterministic rule engine serves three surfaces. Verdicts come only from the engine. The model writes explanations and only uses numbers the engine produced.

## 1 · Surfaces

| Surface | Who | Build target | Talks to |
|---|---|---|---|
| FreeCAD panel (page 6/7: F0, P1–P7, E1–E4) | Designer | `freecad_addon/` PySide dock, objectName `SonarIQPanel`, `design/panel.qss` | Engine over local HTTP (`engine/sonariq/api.py`, port 8765). The MCP server wraps the same functions. |
| Web portal (page 8: W1–W8) | Discipline reviewers, class | `portal/` Vite + React + TS + Tailwind, `design/sonariq.css` as is, @thatopen/components + web-ifc | Same HTTP API |
| SonarIQ MCP server | Any AI client or CAD adapter | `engine/mcp_server.py` (stdio) | Engine in-process |

The engine runs offline and needs no AI and no network. The AI endpoint is optional: on-premises, approved cloud, or off. The demo uses Qwen on Vertex AI through an OpenAI-compatible URL. No vendor or model name appears in the UI.

## 2 · Data model

**IFC4 is the model.** The engine reads standard IFC entities and property sets, plus one SonarIQ property set for the ship words IFC lacks.

| IFC entity | Standard data read | `SonarIQ_Ship` properties |
|---|---|---|
| IfcBuilding (the ship) | Name | `vessel_type`, `persons_on_board`, `passengers`, `length_m`, `accessibility` |
| IfcBuildingStorey | Elevation | `deck` (e.g. 5) |
| IfcSpace | Footprint (extruded profile) | `category` (cabin, corridor, stair, service, galley, public), `deck`, `frame` ("146-150"), `side` (P/S/C), `mvz`, `solas_category`, `berths`, `escape_continues`, `accessible_route`, `maturity` |
| IfcZone | Members via IfcRelAssignsToGroup | `category` = mvz, `mvz` |
| IfcWall | Pset_WallCommon.FireRating, footprint | `deck`, `frame`, `side`, `mvz_boundary` |
| IfcDoor / IfcWindow | Pset_DoorCommon.FireRating, SelfClosing; Pset_WindowCommon.FireRating; OverallWidth; host via IfcRelVoidsElement + IfcRelFillsElement | `deck`, `frame`, `side`, `accessible_route`, `maturity` |
| IfcStair + IfcStairFlight | Flight solid (clear width = short side) | `persons_by_deck` (JSON, e.g. `{"4":40,"6":44,"7":24}`), `decks_served`, `mvz`, `encloses` (wall names) |
| IfcDuctSegment / IfcDamper | Axis, position | `deck`, `frame`, `side` |
| IfcPlate | Solid thickness | `category` = deck_plate |

Frames are 800 mm apart and Fr 0 is at x = 0, so x = frame × 0.8 m. +y is port. Location is written **Deck 5 · Fr 152 · S** and is read from `SonarIQ_Ship`, with geometry as the fallback. Missing data is never guessed: the check becomes **Cannot verify** and names the missing property.

**Persons on the modelled deck are counted, not typed.** For a stair, the Deck 5 persons are the sum of `berths` of the cabins in the stair's MVZ on Deck 5. The other decks come from `persons_by_deck`. This is why adding cabins on Deck 5 moves Stair 3B.

**Maturity.** An element with `maturity = concept` is checked but its verdict is **Dormant**: computed, not reported as an open finding (the brief's "concept zones stay quiet").

## 3 · Rule packs per discipline

| Pack (UI group) | YAML pack | Rules | Demo depth |
|---|---|---|---|
| Fire & life safety · SOLAS II-2, FSS Ch.13 | `fire`, `escape` | R-FLS-01…04, 06…11 | Full |
| Accessibility · PVAG 2013 draft, ADA 2010 | `accessibility` | R-ACC-01, R-ACC-02 | Full; works in inches |
| Class · DNV (To verify) | `class_dnv` | R-DNV-01, R-DNV-02 | Placeholder clauses; verdicts carry To verify |
| HVAC | `hvac` | R-FLS-05 | One check (H-01); off in the default panel run |
| Structure (OCX) | `structure` | — | Stub: OCX reader not built |

A rule in `rules/seed_rules.yaml` holds the source, clause, clause text, our reading, threshold parameters, severity, applicability and status. The engine code holds only measure functions (`engine/sonariq/checks.py`). Applicability comes from the vessel profile: a rule for ships carrying more than 36 passengers is **Not applicable** on the RCRV (28 on board). It is listed, not hidden.

## 4 · Check, verdict and finding

A **check** is one rule applied to one element. Each check returns one verdict: Fail ✕ · Warning ! · Cannot verify ? · Pass ✓ · Dormant ○ · Not applicable —. "Accepted with reason ⚑" is a review state on top of a Fail and only counts after approval.

```json
{
  "id": "F-07", "check_key": "R-FLS-03|<stair GlobalId>", "rule": "R-FLS-03",
  "source": "FSS Code", "clause": "Ch.13 §2.1.2", "clause_text": "…", "rule_status": "verified",
  "pack": "escape", "discipline": "fire_life_safety", "status": "fail",
  "title": "Stair narrower than the people it serves need",
  "element": {"guid": "…", "name": "Stair 3B", "ifc_class": "IfcStair"},
  "location": {"deck": "5", "frame": "160-164", "side": "C", "label": "Stair 3B · Decks 4–7"},
  "required": {"value": 1380, "unit": "mm", "op": ">="},
  "measured": {"value": 1350, "unit": "mm"},
  "margin":   {"value": -30, "unit": "mm"},
  "formula": {"text": "W = (N1 + N2 + 0.5 N3 + 0.25 N4) × 10 mm",
              "inputs": [{"name": "N1", "deck": "5", "value": 68, "source_guids": ["…cabins…"]}, "…"],
              "worked": "(68 + 44 + 20 + 6) × 10 = 1,380 mm"},
  "method": "Clear width = short side of the stair flight solid …",
  "missing": [], "evidence": {"guids": ["…"], "bbox": [x0, y0, x1, y1], "z": 12.0},
  "depends_on": ["<guids>", "berths:5:MVZ 4"], "revision": "B"
}
```

**Finding IDs** are `<prefix>-<finding_no>`. The prefix is F (Fail), W (Warning) or U (Cannot verify), and H for the hvac pack. `finding_no` comes from the rule in YAML, so F-07 is always the stair formula. A second element failing the same rule gets `F-07.2`.

**Impact analysis (the ping).** Revisions are diffed by GlobalId: added, removed, or changed (a hash of attributes, psets and geometry). Each check records the GlobalIds and derived keys it read (`depends_on`, for example `berths:5:MVZ 4`). The re-run set is every check whose dependencies touch the diff, plus checks on new elements. Checks whose verdict or numbers changed are reported as "changed".

## 5 · Screens → components → API

| Artboard | Components (C1 names) | API |
|---|---|---|
| P1 Idle | PanelHead, pack chips, scope segment | `GET /model`, `GET /rules` (pack split 64 / 20 / 12 from a dry run) |
| P2 Running | progress per pack | `POST /analyse` (streams nothing yet; returns in < 3 s) |
| P3 Results | summary strip, finding rows grouped by discipline | `POST /analyse {rev, scope, packs}` → `{counts, checks, findings, by_pack, duration_s}` |
| P4 Evidence | Evidence card, formula, required vs measured, unit toggle | `GET /findings/{id}` |
| P5 Chat (not tonight) | edit preview, ping card, fix cards | MCP `apply_edit`, `recheck`, `propose_fixes`, `explain` |
| P6 Accept with reason | modal | `POST /findings/{id}/accept` (review state; verdict stays Fail) |
| P7 Send to review | BCF row | `POST /export/bcf` → `sonariq_rev-b.bcfzip` |
| E2 Cannot verify | dashed card | `finding.missing[]` |
| W1/W2/W3 | project cards, inbox, thread | `GET /findings?discipline=`, decisions log |
| W4 / W4-RCRV | viewer + pins | `GET /model/ifc/{rev}` (IFC file), findings with `evidence.bbox` |
| W5 Mapping review | mapping rows | `GET /rcrv/mapping` (from `data/rcrv/mapping_review.csv`) |
| W8 Revision impact | ping card, mini plans | `POST /impact {from: A, to: B}` |

MCP tools: `analyse(scope, packs)`, `get_finding(id)`, `explain(id)`, `propose_fixes(id)`, `apply_edit(edit)`, `recheck()`, `export_bcf()`. `apply_edit` only accepts `add_cabin_block`, `move_wall`, `set_door_width` and `set_door_fire_class`. The guard is code. `explain` rejects any model text containing a number that is not in the finding.

## 6 · Test deck (contract numbers)

`scripts/make_deck.py` writes `data/deck5_revA.ifc` and `data/deck5_revB.ifc`. The deck covers Fr 120–215, with MVZ 4 from Fr 120–165, MVZ 5 from Fr 165–215, and the A-60 bulkhead at Fr 165. Cabins are 2,000 × 6,000 mm with 2 berths. Corridors are 1,300 mm, except the 900 mm starboard corridor at Fr 150–155. Stair 3B (Fr 160–164) is 1,350 mm clear and serves Decks 4–7. The check plan below is designed so the handoff counts follow from the model, not from the UI:

| Pack | Checks | Made of |
|---|---|---|
| Fire & life safety | 64 | 14 fire doors × 2 rules · 12 corridors × 2 rules · 2 MVZ lengths · 1 MVZ bulkhead · 2 stairs × 3 rules · 3 glazed windows |
| Accessibility | 20 | 12 corridors · 8 doors on the accessible route |
| Class · DNV | 12 | 12 deck plates |

Expected results. Rev A: F-01 (FD-5-165P is A-0 in A-60), W-01 (900 < 915 mm), U-01 (D-5-171-S has no FireRating), 4 Dormant (2 galley fire doors in the concept zone at Fr 205–212, × 2 rules), 89 Pass. Rev B (OR-117) adds 4 cabins at Fr 140–147.5. The cross corridor at Fr 146–150 P becomes a 4.2 × 1.2 m dead end, Fr 152 S narrows to 850 mm, and D5 on Stair 3B becomes 68. This gives F-07, F-08 and F-09, for counts 4 · 1 · 1 · 86 · 4. With fix 2 (four 1-berth cabins), Stair 3B is 1,340 ≤ 1,350 and counts are 3 · 1 · 1 · 87 · 4.

## 7 · Test plan

1. **Per rule** (`tests/test_rules.py`): one violation, one compliant control and one exact-threshold case for every implemented rule. Examples: corridor exactly 900 mm passes R-FLS-04, MVZ exactly 40.0 m passes, and a 32 in door passes.
2. **Stair formula by hand**: 1,300 mm (Rev A), 1,380 mm (Rev B), 1,340 mm (Rev B + fix 2), 1,320 mm (fix 3), and still 1,380 with the block moved 10 frames forward.
3. **Contract** (`tests/test_contract.py`): counts per revision equal handoff.md, IDs F-01 / W-01 / U-01 / F-07 / F-08 / F-09 / H-01, every finding resolves to Deck · Fr · Side, and the pack split is 64 / 20 / 12.
4. **Impact**: the A→B diff re-runs only checks touching the change, and the changed set is exactly {F-07, F-08, F-09}.
5. **Guards**: `apply_edit` refuses anything outside the four edits. The explanation checker rejects invented numbers.
6. **Bench** (`make bench`): Analyse on the test deck in under 3 s, and the ping in under 2 s.
7. **RCRV**: the 10-door table in `docs/rcrv_report.md` is checked by hand against the FreeCAD measure tool (±5 mm, human gate).
