# RCRV conversion report

Source `12100-RCRV-199_07-08-2021.nwd` (model units: inches) → Autodesk Model Derivative (SVF) → svf-utils glTF + property database → `scripts/rcrv_to_ifc.py` → IFC4. Generated 07 Nov 2026 03:34 UTC.

**90,331 objects** from 303,504 geometry nodes. **86,593 classified** into IFC; **3,738 unmapped** (listed in `data/rcrv/mapping_review.csv` for portal screen W5, left out of the IFC, never guessed). Overall length of geometry 66.71 m. 7 decks found from horizontal plate area at z = 1.80, 3.70, 5.80, 8.50, 11.30, 13.90, 16.50 m.

## Object counts per class

| IFC class | Label | Objects |
|---|---|---|
| IfcPipeSegment | pipe | 43,678 |
| IfcMember | stiffener | 11,771 |
| IfcPlate | plate | 9,716 |
| IfcDuctSegment | duct | 7,364 |
| IfcBuildingElementProxy | equipment | 4,759 |
| IfcCableCarrierSegment | cable tray | 3,861 |
| — | unmapped | 3,738 |
| IfcCovering | insulation | 1,398 |
| IfcRailing | railing | 1,367 |
| IfcFurnishingElement | furniture | 1,167 |
| IfcWall | bulkhead | 600 |
| IfcDoor | door | 341 |
| IfcDoor | hatch | 251 |
| IfcWindow | window | 182 |
| IfcStair | stair | 138 |

## Output files

| File | Objects | With real triangles |
|---|---|---|
| rcrv_full.ifc | 86,593 | 1,503 |
| rcrv_deck_2.ifc | 22,892 | 58 |
| rcrv_deck_3.ifc | 16,935 | 517 |
| rcrv_deck_4.ifc | 11,931 | 249 |
| rcrv_deck_5.ifc | 7,058 | 283 |
| rcrv_deck_6.ifc | 4,226 | 122 |
| rcrv_deck_7.ifc | 2,954 | 1 |

## 10 doors: clear width

Clear width = long horizontal side of the oriented bounding box of the door's leaf (tallest thin part of the block). Block width includes the frame. ADA 2010 §404.2.3 needs 32 in (813 mm). Check each against the FreeCAD measure tool (gate: within ±5 mm).

| # | Door (source name) | Deck | Source ID | Clear width (in) | Clear width (mm) | Block width (mm) | Leaf height (mm) | 32 in? |
|---|---|---|---|---|---|---|---|---|
| 1 | 3D Solid | Deck 1 | 52022 | 18.5 | 471 | 798 | 1404 | ✕ Fail |
| 2 | A-CLASS DOOR MA60CX (LO-RI)-108,115 | Deck 1 | 7212 | 37.1 | 943 | 943 | 2055 | ✓ Pass |
| 3 | A-CLASS DOOR MA60CX (RI)-118 | Deck 1 | 51599 | 37.5 | 952 | 1028 | 2130 | ✓ Pass |
| 4 | A-CLASS DOOR MA60CX (RO)-117 | Deck 1 | 51603 | 37.1 | 943 | 943 | 2128 | ✓ Pass |
| 5 | A-CLASS DOOR MA60CX (RO-LI)-121,314 | Deck 1 | 51390 | 37.1 | 942 | 946 | 2082 | ✓ Pass |
| 6 | A-CLASS SINGLE LEAF DOOR (LI)-116 | Deck 1 | 51606 | 37.4 | 949 | 949 | 2117 | ✓ Pass |
| 7 | SLIDING W/T DOOR IWO GRATING L | Deck 1 | 7215 | 5.1 | 129 | 2304 | 2031 | ✕ Fail |
| 8 | A-CLASS DOOR MA60CX (LI)-504 | Deck 3 | 45757 | 37.1 | 943 | 943 | 2056 | ✓ Pass |
| 9 | A-CLASS DOOR MA60CX (LO)-506 | Deck 3 | 45764 | 33.0 | 838 | 1048 | 2027 | ✓ Pass |
| 10 | A-CLASS DOOR MA60CX (RI)-505 | Deck 3 | 45768 | 37.1 | 943 | 943 | 2056 | ✓ Pass |

## Caveats

- Mesh, not solids: the IFC carries triangles. Flat faces (door leaves, bulkheads) are exact; curved hull surfaces are display-only and no check uses them.
- Fire class, accessible route, berths and room names are not in the Navisworks model. Doors are listed as *Needs review* in mapping_review.csv; checks that need these report Cannot verify until they are set (from the GA PDF or by an engineer in W5).
- Classification rules are in `RULES` at the top of `scripts/rcrv_to_ifc.py` (name, layer, source file, ShipConstructor class).
