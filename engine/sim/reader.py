"""Model reader (W9 right column): what the simulation reads from the model, and the gaps it found.

Code finds the gaps (unknown = worst case); the AI only ranks and explains them, numbers checked.
"""
from __future__ import annotations

from collections import Counter

from .runner import Prep

SYSTEM = ("You help a ship designer prepare an evacuation simulation. You get the gaps a code scan found in the "
          "model. In at most two short sentences, no lists: say which gap could change the simulation most and what "
          "to fix first. Use only the facts; every number must be in them. No product or vendor names.")


def gap_scan(prep: Prep, model) -> list[dict]:
    g = prep.geom
    gaps = []
    no_sc = sorted(d.name for d in g.doors.values() if d.self_closing is None)
    no_fr = sorted(d.name for d in g.doors.values() if not d.fire_rating and
                   any(g.space_meta.get(s, {}).get("category") in ("stair", "corridor") for s in d.spaces))
    if no_sc:
        gaps.append({"kind": "door_self_closing_unknown", "severity": 2, "count": len(no_sc), "items": no_sc[:6],
                     "text": f"{len(no_sc)} doors do not state SelfClosing · treated as open (smoke passes)"})
    if no_fr:
        gaps.append({"kind": "door_fire_rating_missing", "severity": 2, "count": len(no_fr), "items": no_fr[:6],
                     "text": f"{len(no_fr)} doors on escape routes have no fire rating · smoke rule reads SelfClosing"})
    if g.dropped:
        gaps.append({"kind": "unreachable_spaces", "severity": 3, "count": len(g.dropped), "items": g.dropped[:6],
                     "text": f"{len(g.dropped)} spaces have no walkable route to a stair · left out"})
    for st in model.by_class("IfcStair"):
        nm = st.name.replace("Stair ", "")
        decl = st.sq.get("persons_deck5_declared")
        counted = sum(1 for s in prep.spawn if prep.target.get(s["space"], ("",))[0] == nm and s["kind"] == "passenger")
        if decl is not None and prep.scenario.get("case") == "night" and abs(int(decl) - counted) > 0:
            gaps.append({"kind": "persons_declared_vs_counted", "severity": 1, "count": abs(int(decl) - counted),
                         "items": [st.name],
                         "text": f"{st.name}: pset says {decl} on Deck 5, the model's berths routed to it count {counted}"})
    cab_no_door = sorted(n for n, m in g.space_meta.items() if m.get("category") == "cabin"
                         and not any(n in d.spaces for d in g.doors.values()))
    if cab_no_door:
        gaps.append({"kind": "cabins_without_door", "severity": 1, "count": len(cab_no_door), "items": cab_no_door[:6],
                     "text": f"{len(cab_no_door)} cabins have no IfcDoor · reached through open boundaries"})
    return sorted(gaps, key=lambda x: -x["severity"])


def setup(prep: Prep, model, sc) -> dict:
    g = prep.geom
    people = [s for s in prep.spawn if s["space"] in prep.target]
    by_stair = Counter(prep.target[s["space"]][0] for s in people)
    kind = Counter(s["kind"] for s in people)
    routes = {}
    for sp, path in prep.route_path.items():
        routes[sp] = path
    closed = []
    if sc.closed_stair and sc.closed_stair in g.stairs:
        c = g.stairs[sc.closed_stair].flight.centroid
        closed.append({"name": f"Stair {sc.closed_stair}", "xy": [round(c.x, 2), round(c.y, 2)]})
    if sc.closed_door and sc.closed_door in g.doors:
        c = g.doors[sc.closed_door].poly.centroid
        closed.append({"name": sc.closed_door, "xy": [round(c.x, 2), round(c.y, 2)]})
    origin = None
    if sc.fire_origin and sc.fire_origin in g.spaces:
        c = g.spaces[sc.fire_origin].centroid
        m = g.space_meta[sc.fire_origin]
        origin = {"space": sc.fire_origin, "xy": [round(c.x, 2), round(c.y, 2)],
                  "label": f"{(m.get('category') or '').title()} · Deck 5 · Fr {m.get('frame')} · {m.get('side')}"}
    stairs = [{"name": s, "width_mm": int(round(g.stairs[s].width * 1000)), "open": s in prep.open_stairs,
               "deck5": by_stair.get(s, 0), "inflow": prep.inflow.get(s, 0),
               "persons_by_deck": g.stairs[s].persons_by_deck, "capacity_p_s": prep.capacity.get(s)} for s in g.stairs]
    gaps = gap_scan(prep, model)
    n = len(people)
    infl = sum(prep.inflow.values())
    where = "in their Deck 5 cabins" if sc.case == "night" else "in Deck 5 public spaces and service rooms"
    sent = (f"{sc.case.title()} on Deck 5, Rev {model.revision}: {n} people head for "
            + " and ".join(f"Stair {s['name']}" for s in stairs if s["open"])
            + f" while {infl} more arrive from Decks 4, 6 and 7")
    if sc.closed_stair:
        sent += f", with Stair {sc.closed_stair} out of use"
    if sc.closed_door:
        sent += f", with {sc.closed_door} out of use"
    if origin:
        sent += f", and a fire starting in {origin['space']}"
    sent += "."
    return {
        "people": {"deck5": n, "passengers": kind.get("passenger", 0), "crew": kind.get("crew", 0), "where": where,
                   "source": "berths in IfcSpace (SonarIQ_Ship.berths)" if sc.case == "night"
                   else "public space area at 2 m²/person × 75 %, 1 crew per service space",
                   "positions": [[round(s["x"], 2), round(s["y"], 2)] for s in people]},
        "stairs": stairs, "routes": routes, "closed": closed, "fire_origin": origin, "smoke": prep.smoke,
        "doors_out_options": sorted(d for d in g.doors if d.startswith("FD-")),
        "gaps": gaps, "sentence": sent, "label": "Smoke spread is illustrative, not a fire model" if origin else None,
        "geometry": g.to_json(),
    }


def explain_gaps(llm, s: dict) -> dict:
    facts = {"gaps": [{k: v for k, v in x.items() if k in ("kind", "count", "text")} for x in s["gaps"]],
             "people_deck5": s["people"]["deck5"]}
    fb = ("Fix first: " + s["gaps"][0]["text"] + ".") if s["gaps"] else "No gaps found that change the simulation."
    return llm.guarded(SYSTEM, facts, "Which gap matters most for the simulation?", fb)
