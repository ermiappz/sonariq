# SonarIQ · Meyer Q&A 1 · rule readings and test-deck results

Sat 7 Nov 2026, 09:00 · printed from the engine run of 07 Nov 03:11 · every number below comes from `scripts/make_qa.py` running the rule engine on the generated test deck.

**What we ask:** tick or correct each reading. Paragraph numbers marked *verify* are the ones we are least sure of. Also: which DNV rule would you most like to see?

## 1 · Rule readings

| ✓/✗ | Rule | Source and paragraph | Our reading | Threshold | Status |
|---|---|---|---|---|---|
| ☐ | R-FLS-01 · Fire door class below bulkhead class | SOLAS II-2 II-2/9.2.2.1.1 | A door in a fire-rated division has at least the division's fire class (A-60 > A-30 > A-15 > A-0 > B-15 > B-0). | door class ≥ division class | verified |
| ☐ | R-FLS-02 · Dead-end corridor deeper than wide | SOLAS II-2 II-2/13.3.1.2 | A corridor with escape in one direction only (leaf of the corridor graph, no stair, no continuation) fails when its depth exceeds its clear width. | dead end: depth ≤ width | verify |
| ☐ | R-FLS-03 · Stair narrower than the people it serves need | FSS Code Ch.13 §2.1.2 | W = (N1 + N2 + 0.5 N3 + 0.25 N4) x 10 mm, N1..N4 = persons per deck served, largest first. Deck 5 persons = berths of the cabins in the stair's MVZ on Deck 5 (from the model); other decks from SonarIQ_Ship.persons_by_deck. | W = (N1 + N2 + 0.5 N3 + 0.25 N4) × 10 mm | verified |
| ☐ | R-FLS-04 · Escape corridor narrower than 900 mm | FSS Code Ch.13 §2.1.2 | Clear width of each corridor space (short side of its footprint) >= 900 mm. | ≥ 900 mm | verify |
| ☐ | R-FLS-05 · Duct through A-class division without fire damper | SOLAS II-2 II-2/9.7 | Each duct segment whose axis crosses an A-class wall needs an IfcDamper within 1 m of the crossing. | damper within 1.0 m of crossing | verify |
| ☐ | R-FLS-06 · MVZ bulkhead below A-60 | SOLAS II-2 II-2/9.2.2.1.1 | Every wall with SonarIQ_Ship.mvz_boundary = true is A-60. | A-60 | verified |
| ☐ | R-FLS-07 · Main vertical zone longer than 40 m | SOLAS II-2 II-2/9.2.2.1.1 | Length of each MVZ on the deck (extent along the ship of its spaces) <= 40 m. The 48 m extension in 9.2.2.1.2 is not applied. | ≤ 40 m | verified |
| ☐ | R-FLS-08 · Stair enclosure below A-0 | SOLAS II-2 II-2/9.2.2.3 / 9.2.2.4 | Every wall listed as the stair's enclosure is at least A-0. | ≥ A-0 | verify |
| ☐ | R-FLS-09 · Stair narrower than 900 mm | FSS Code Ch.13 §2.1.1 | Stair flight clear width >= 900 mm, independent of persons served. | ≥ 900 mm | verify |
| ☐ | R-FLS-10 · Fire door not self-closing | SOLAS II-2 II-2/9.4.1.1.4 | Doors hosted in A-class divisions have Pset_DoorCommon.SelfClosing = true. | SelfClosing = true | verify |
| ☐ | R-FLS-11 · Glazing below the division's fire class | SOLAS II-2 II-2/9.4.1.3 | IfcWindow hosted in an A-class wall has a FireRating at least the wall's. | glazing class ≥ division class | verify |
| ☐ | R-ACC-01 · Corridor below width guideline | PVAG 2013 draft | Corridor clear width >= 915 mm. Draft source, so a violation is a Warning, never a Fail. | ≥ 915 mm (36 in) · Warning | verified |
| ☐ | R-ACC-02 · Door narrower than 32 in clear | ADA 2010 §404.2.3 | Clear width of each door on an accessible route >= 32 in (812.8 mm). | ≥ 32 in (813 mm) | verified |
| ☐ | R-DNV-01 · Deck plate thinner than class minimum | DNV [to confirm] DNV-RU-SHIP Pt.3 (minimum plate thickness) | Deck plate thickness (from geometry) >= 4.5 + 0.02 x min(L, 300) mm, L from SonarIQ_Ship.length_m on the ship. | t ≥ 4.5 + 0.02·min(L,300) mm | verify |
| ☐ | R-DNV-02 · Class rule placeholder (OCX stiffeners) | DNV [to confirm] | No elements on Deck 5 IFC; reported as 0 checks. | — | verify |

Applicability: rules for ships carrying more than 36 passengers are **Not applicable** on a vessel profile below that (the RCRV: 28 on board, 16 scientists and 12 crew). Missing model data gives **Cannot verify**, never Pass. Elements in a *concept* maturity zone are checked but stay **Dormant** (not reported).

## 2 · Test deck

Demo ship, Deck 5, Fr 120–215 (800 mm frames), MVZ 4 Fr 120–165 and MVZ 5 Fr 165–215, A-60 MVZ bulkhead at Fr 165. Cabins 2,000 × 6,000 mm with 2 berths, corridors 1,300 mm, starboard corridor at Fr 152 900 mm, Stair 3B Fr 160–164 serving Decks 4–7, 1,350 mm clear. IFC4 written with IfcOpenShell; fire classes in Pset_WallCommon / Pset_DoorCommon.FireRating; ship words in a `SonarIQ_Ship` property set (deck, frame, side, mvz, berths …).

### Rev A

**96 checks** · ✕ 1 Fail · ! 1 Warning · ? 1 Cannot verify · ✓ 89 Pass · ○ 4 Dormant  (Fire & life safety 64, Accessibility 20, Class · DNV 12)

| ID | Status | Finding | Location | Rule | Required | Measured |
|---|---|---|---|---|---|---|
| F-01 | ✕ Fail | Fire door class below bulkhead class (FD-5-165P) | Deck 5 · Fr 165 · P | SOLAS II-2/9.2.2.1.1 | A-60 | A-0 |
| W-01 | ! Warning | Corridor below width guideline (COR-5-152-S) | Deck 5 · Fr 152 · S | PVAG 2013 draft | 915 mm | 900 mm |
| U-01 | ? Cannot verify | Door has no fire class in the model (D-5-171-S) | Deck 5 · Fr 171 · S | SOLAS II-2/9.2.2.1.1 | A-0 | — |

Stair 3B on Rev A: required 1,300 mm, measured 1,350 mm → Pass ((60 + 44 + 20 + 6) × 10 = 130 × 10 = 1,300 mm).

### Rev B · owner request OR-117 (+4 cabins, 8 berths, aft of Fr 150)

**96 checks** · ✕ 4 Fail · ! 1 Warning · ? 1 Cannot verify · ✓ 86 Pass · ○ 4 Dormant  (Fire & life safety 64, Accessibility 20, Class · DNV 12)

Ping: **11 checks re-ran**, verdicts changed: F-08 (pass → fail), F-07 (pass → fail), F-09 (pass → fail). Values changed with the same status: W-01 (900 → 850).

| ID | Status | Finding | Location | Rule | Required | Measured |
|---|---|---|---|---|---|---|
| F-01 | ✕ Fail | Fire door class below bulkhead class (FD-5-165P) | Deck 5 · Fr 165 · P | SOLAS II-2/9.2.2.1.1 | A-60 | A-0 |
| F-07 | ✕ Fail | Stair narrower than the people it serves need (Stair 3B) | Stair 3B · Decks 4–7 | FSS Code Ch.13 §2.1.2 | 1,380 mm | 1,350 mm |
| F-08 | ✕ Fail | Dead-end corridor deeper than wide (COR-5-148-P) | Deck 5 · Fr 146–150 · P | SOLAS II-2/13.3.1.2 | 1.2 m | 4.2 m |
| F-09 | ✕ Fail | Escape corridor narrower than 900 mm (COR-5-152-S) | Deck 5 · Fr 152 · S | FSS Code Ch.13 §2.1.2 | 900 mm | 850 mm |
| W-01 | ! Warning | Corridor below width guideline (COR-5-152-S) | Deck 5 · Fr 152 · S | PVAG 2013 draft | 915 mm | 850 mm |
| U-01 | ? Cannot verify | Door has no fire class in the model (D-5-171-S) | Deck 5 · Fr 171 · S | SOLAS II-2/9.2.2.1.1 | A-0 | — |

**Stair 3B, the indirect failure.** Nobody touched the stair. N1 = 68 (Deck 5, counted from cabins), N2 = 44 (Deck 6), N3 = 40 (Deck 4), N4 = 24 (Deck 7). W = (N₁ + N₂ + 0.5 N₃ + 0.25 N₄) × 10 mm = (68 + 44 + 20 + 6) × 10 = 138 × 10 = 1,380 mm vs 1,350 mm measured → Fail by 30 mm.

With fix 2 (the four cabins with one berth each): required 1,340 mm ≤ 1,350 mm → Pass. Counts: **96 checks** · ✕ 3 Fail · ! 1 Warning · ? 1 Cannot verify · ✓ 87 Pass · ○ 4 Dormant  (Fire & life safety 64, Accessibility 20, Class · DNV 12)

### HVAC model (separate pack)

| ID | Status | Finding | Location | Rule | Required | Measured |
|---|---|---|---|---|---|---|
| H-01 | ✕ Fail | Duct through A-class division without fire damper (VD-5-03) | Deck 5 · Fr 165 · P | SOLAS II-2/9.7 | fire damper | none |

## 3 · Questions

1. If you exported a deck from Cadmatic tomorrow, would it be IFC? Which version? Do element IDs stay the same between exports?
2. How do you name a location: deck + frame + side? Anything else?
3. Who should receive a fire-door finding, and who a duct-through-bulkhead finding?
4. How many findings per Analyse is useful before it becomes noise?
5. The RCRV is a research vessel with 28 aboard: are we right that the SOLAS rules for more than 36 passengers don't apply?
6. On demand, live, or both? When in the design spiral would you switch live on?
7. FSS Ch.13 stair width: do you order N1…N4 by size (as here) or by the deck nearest the stair first?
8. Dead ends: is "depth ≤ width" the reading you use, and which paragraph do you cite?

Notes:

&nbsp;

&nbsp;
