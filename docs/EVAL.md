# SonarIQ eval log

Appended by `make eval` (scripts/eval.py). Numbers come from the run; nothing here is typed by hand.

## Sat 07 Nov 10:42 · git d24b165

- **Rules benchmark**: 12 planted violations · caught 12 · missed 0 · false alarms 0 · contract revisions A ok, B ok, Bfix2 ok
- **Simulation sanity**: free walk ok (errors 0.3 %, 0.1 %, 0.9 %) · wider stair ok (3B queue+wait mean 51.38 → 27.50) · same seed ok · smoke door True · one run 3.8 s
- **Golden path v3**: 13/13 steps (20 runs per simulation)
  - ✓ Analyse Rev A · `{"counts": {"fail": 1, "warn": 1, "unk": 1, "pass": 89, "dor": 4, "na": 0}}`
  - ✓ Typed change OR-117 -> edit preview · `{"text": "Add 4 cabins \u00d7 2 berths (8 berths) on Deck 5, Fr 140\u2013147.5, MVZ 4 \u00b7 OR-117"}`
  - ✓ Confirm -> Stair 3B fails (F-07) · `{"changed": ["F-08", "F-07"], "rerun": 7}`
  - ✓ Simulate night -> scenario preview · `{"text": "Night \u00b7 primary"}`
  - ✓ Night runs complete · `{"runs": 20, "id": "472ac80d4402_261260b6027e_20"}`
  - ✓ Replay shows the 3B queue · `{"replay_queue_3B_max": 7, "frames": 663}`
  - ✓ Fix 2 -> edit preview · `{"text": "Add 4 cabins \u00d7 1 berths (4 berths) on Deck 5, Fr 140\u2013147.5, MVZ 4 \u00b7 OR-117"}`
  - ✓ Confirm fix 2 -> F-07 clears · `{"changed": [{"id": "F-07", "status": null, "title": "Stair narrower than the people it serves need"}]}`
  - ✓ Re-run after fix 2 -> compare · `{"tA_p95": {"tA_p95_s": 4.2, "deck5_last_p95_s": 8.4}, "landings_3B": {"3BS": {"before": 11.0, "after": 11.0, "delta": 0.0}, "3BP": {"before": 11.0, "after": 11.0, "delta": 0.0}}}`
  - ✓ Fire what-if from words -> preview · `{"text": "Night \u00b7 primary \u00b7 fire what-if in LOUNGE-5-180"}`
  - ✓ Fire what-if runs · `{"error": null, "id": "cfeb85dceedf_ad9d142d25c6_20"}`
  - ✓ Pin to review
  - ✓ Portal review and approve -> BCF · `{"bcf": {"path": "/home/ermias/sonariq/data/out/sonariq_rev-a.bcfzip", "topics": 4, "decisions": 1, "open": 3}}`
- **ai**: error AttributeError: 'list' object has no attribute 'get'

## Sat 07 Nov 10:43 · git d24b165

- **AI**: phrasings 19/20 · number guard 4/6 cached explanations pass · latency cold 2753 ms, cached 1 ms (gemini-3.5-flash@eu) · RAG 14/15 (local sqlite + text-embedding-005 (europe-west4))
  - phrasing missed: “upgrade door FD-5-165P to an A-60 fire door” → {"type": "scenario_preview", "scenario": {"case": "night", "route": "primary", "closed_door": "FD-5-165P"}}
  - RAG missed: “How many simulations are needed for each benchmark case in an advanced evacuation analysis?” want circ1533 §5.2, top MSC.1/Circ.1533 Annex 3 App.1 §3.1.1

## Sat 07 Nov 12:53 · git da730f0

- **Rules benchmark**: 12 planted violations · caught 12 · missed 0 · false alarms 0 · contract revisions A ok, B ok, Bfix2 ok
- **AI**: phrasings 24/24 · number guard 13/18 cached AI outputs pass (the other 5 were caught at answer time and replaced by engine text) · latency cold 4230 ms, cached 1 ms (gemini-3.5-flash@eu) · RAG 14/15 (local sqlite + text-embedding-005 (europe-west4))
  - RAG missed: “How many simulations are needed for each benchmark case in an advanced evacuation analysis?” want circ1533 §5.2, top MSC.1/Circ.1533 Annex 3 App.1 §3.1.1
