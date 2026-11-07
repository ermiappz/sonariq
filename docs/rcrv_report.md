# RCRV conversion report

Source `12100-RCRV-199_07-08-2021.nwd` (model units: inches) → Autodesk Model Derivative (SVF) → svf-utils glTF + property database → `scripts/rcrv_to_ifc.py` → IFC4. Generated 07 Nov 2026 03:48 UTC.

**90,331 objects** from 303,504 geometry nodes. **86,308 classified** into IFC; **4,023 unmapped** (listed in `data/rcrv/mapping_review.csv` for portal screen W5, left out of the IFC, never guessed). Overall length of geometry 66.71 m. 7 decks found from horizontal plate area at z = 1.80, 3.70, 5.80, 8.50, 11.30, 13.90, 16.50 m.

## Object counts per class

| IFC class | Label | Objects |
|---|---|---|
| IfcPipeSegment | pipe | 43,678 |
| IfcMember | stiffener | 11,771 |
| IfcPlate | plate | 9,716 |
| IfcDuctSegment | duct | 7,364 |
| IfcBuildingElementProxy | equipment | 4,894 |
| — | unmapped | 4,023 |
| IfcCableCarrierSegment | cable tray | 3,861 |
| IfcCovering | insulation | 1,398 |
| IfcRailing | railing | 1,367 |
| IfcFurnishingElement | furniture | 1,179 |
| IfcWall | bulkhead | 610 |
| IfcDoor | door | 149 |
| IfcDoor | hatch | 128 |
| IfcStair | stair | 114 |
| IfcWindow | window | 79 |

## Output files

| File | Objects | With real triangles |
|---|---|---|
| rcrv_full.ifc | 86,308 | 1,071 |
| rcrv_deck_1.ifc | 20,558 | 234 |
| rcrv_deck_2.ifc | 22,873 | 39 |
| rcrv_deck_3.ifc | 16,784 | 255 |
| rcrv_deck_4.ifc | 11,898 | 194 |
| rcrv_deck_5.ifc | 7,017 | 228 |
| rcrv_deck_6.ifc | 4,225 | 121 |
| rcrv_deck_7.ifc | 2,953 | 0 |

## 10 doors: clear width

Clear width = long horizontal side of the oriented bounding box of the door's leaf (tallest thin part of the block). Block width includes the frame. ADA 2010 §404.2.3 needs 32 in (813 mm). Check each against the FreeCAD measure tool (gate: within ±5 mm).

| # | Door (source name) | Deck | Source ID | Clear width (in) | Clear width (mm) | Block width (mm) | Leaf height (mm) | 32 in? |
|---|---|---|---|---|---|---|---|---|
| 1 | A-CLASS DOOR MA60CX (LO-RI)-108,115 | Deck 1 | 7212 | 37.1 | 943 | 943 | 2055 | ✓ Pass |
| 2 | A-CLASS DOOR MA60CX (RI)-118 | Deck 1 | 51599 | 37.5 | 952 | 1028 | 2130 | ✓ Pass |
| 3 | A-CLASS DOOR MA60CX (RO)-117 | Deck 1 | 51603 | 37.1 | 943 | 943 | 2128 | ✓ Pass |
| 4 | A-CLASS DOOR MA60CX (RO-LI)-121,314 | Deck 1 | 51390 | 37.1 | 942 | 946 | 2082 | ✓ Pass |
| 5 | A-CLASS SINGLE LEAF DOOR (LI)-116 | Deck 1 | 51606 | 37.4 | 949 | 949 | 2117 | ✓ Pass |
| 6 | A-CLASS DOOR MA60CX (LI)-504 | Deck 3 | 45757 | 37.1 | 943 | 943 | 2056 | ✓ Pass |
| 7 | A-CLASS DOOR MA60CX (LO)-506 | Deck 3 | 45764 | 33.0 | 838 | 1048 | 2027 | ✓ Pass |
| 8 | A-CLASS DOOR MA60CX (RI)-505 | Deck 3 | 45768 | 37.1 | 943 | 943 | 2056 | ✓ Pass |
| 9 | A-CLASS DOOR MA60CX (RO)-120,539 | Deck 3 | 45846 | 37.1 | 943 | 943 | 2056 | ✓ Pass |
| 10 | A-CLASS DOOR MA60CX (RO-LI)-502 | Deck 3 | 45774 | 37.6 | 954 | 1043 | 2011 | ✓ Pass |

149 door objects in total; 50 have no leaf found by this method (sliding, watertight or hatch-like doors, or a block whose parts are not separated). They stay in mapping_review.csv as Needs review; no width is reported for them.


## Caveats

- Where clear width = block width, the door block's parts are not separated, so the figure includes the frame and the true clear opening is smaller; treat it as an upper bound until measured.
- Mesh, not solids: the IFC carries triangles. Flat faces (door leaves, bulkheads) are exact; curved hull surfaces are display-only and no check uses them.
- Fire class, accessible route, berths and room names are not in the Navisworks model. Doors are listed as *Needs review* in mapping_review.csv; checks that need these report Cannot verify until they are set (from the GA PDF or by an engineer in W5).
- Classification rules are in `RULES` at the top of `scripts/rcrv_to_ifc.py` (name, layer, source file, ShipConstructor class).
