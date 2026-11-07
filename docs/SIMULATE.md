# Simulate · model documentation

Design insight, not a full-ship MSC.1/Circ.1533 analysis: a **Deck 5 sub-model with inflows from Decks 4, 6, 7**.
This page follows what Circ.1533 Annex 3 App.1 §6 asks a simulation tool to document. Every parameter value lives
in `engine/sim/params.yaml` with its paragraph reference and status (*verify* until Meyer or class confirms).

## Geometry (from the IFC)

- Walkable area = `IfcSpace` footprints on the deck, minus `IfcWall` footprints, plus an opening through the host
  wall for every `IfcDoor` (`engine/sim/geometry.py`). Spaces with no walkable route to a stair are listed in the
  W9 model reader and left out.
- Stairs = `IfcStair` + `IfcStairFlight`; the flight's short side is the clear width. The flight is the exit; the
  landing between the stair door and the flight holds the queue.
- Smoke what-if reads `Pset_DoorCommon.SelfClosing`: TRUE holds smoke; FALSE or unknown = open (worst case).

## Population and timing (Annex 3 App.1 §3.2, §4)

- Night: every berth occupied (`SonarIQ_Ship.berths`), one crew member per service space. Day: public spaces at
  75 % of an assumed 2 m²/person capacity (SonarIQ assumption, the model has no capacity), one crew per service space.
  Counterflow crew (§4.1.3) is not modelled.
- Groups and speeds: Table 3.1 shares, Table 3.4 flat speeds (uniform between min and max).
- Response duration: truncated log-normal, night 400–700 s, day 0–300 s (§3.2.2). People appear in their space at
  their response time.

## Movement and update (§6.2.1–6.2.3)

- JuPedSim 1.4 CollisionFreeSpeedModel (velocity-based, parallel update), dt 0.05 s, radius 0.2 m, time gap 1 s.
- Route choice: the stair landing with the shortest walking route; in a fire what-if the route with the least
  smoke on the way (smoke metres × 5 + route metres) is chosen at spawn and at every smoke step.

## Stairs and inflows (§6.2.4)

- Each stair releases people at specific flow × clear width (0.88 p/m/s, stairs up, Annex 2 Table 1.2), shared
  between the two landing queues on Deck 5 and the people arriving from Decks 4, 6, 7 (`persons_by_deck`, arrival =
  their response time + 15–60 s), in proportion to who is waiting.
- A stair or door out of use (secondary case) is closed in the geometry; the closed stair's other-deck people move
  to the open stairs of the same main vertical zone.

## Outputs

Per run: assembly time (last person into a stair, including inflows), Deck 5 clear time, people per stair, queue
maximum per landing, people waiting from other decks, peak local density (1.5 m window on a 0.5 m grid),
time above 4 p/m² (§3.1), and in a fire what-if the people who walked through smoke. Over the runs: p50, p95
(§5.5), histogram, the run nearest p95 replayed at 2 Hz with its density grid and queue series, the longest route
from the farthest cabin, and congested places sorted by peak density.

## Checks (`make eval`)

Free walk: one person's time = route length / speed within 5 %. A wider stair gives a shorter queue. The same seed
gives the same result. A closed self-closing door keeps smoke out of the stair.

## Not modelled

Stair descent/ascent on other decks, ship motion (§3.3), embarkation, counterflow crew, smoke physics (the spread
is illustrative: one space per step through open boundaries and doors that are not self-closing).
