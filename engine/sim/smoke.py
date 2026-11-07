"""Illustrative smoke spread, not a fire model.

Smoke starts in the origin space at t = 0 and moves one space per hop (params smoke.hop_delay_s) through
open boundaries (spaces touching with no wall) and through doors that are not self-closing. A door with
Pset_DoorCommon.SelfClosing = TRUE holds; FALSE or unknown = open (worst case). Stair enclosures behind
self-closing doors stay clear.
"""
from __future__ import annotations

from collections import defaultdict


def smoke_graph(g) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in g.open_edges:
        adj[a].add(b)
        adj[b].add(a)
    for d in g.doors.values():
        if d.self_closing is True or len(d.spaces) < 2:
            continue
        for i, a in enumerate(d.spaces):
            for b in d.spaces[i + 1:]:
                adj[a].add(b)
                adj[b].add(a)
    return adj


def smoke_schedule(g, origin: str, hop_s: float, until_s: float = 3600) -> list[dict]:
    """[{t, spaces (newly smoke-filled at t)}], origin first at t = 0."""
    adj = smoke_graph(g)
    seen = {origin}
    frontier = [origin]
    out = [{"t": 0.0, "spaces": [origin]}]
    t = 0.0
    while frontier and t + hop_s <= until_s:
        t += hop_s
        nxt = sorted({n for f in frontier for n in adj[f] if n not in seen})
        if not nxt:
            break
        seen |= set(nxt)
        out.append({"t": t, "spaces": nxt})
        frontier = nxt
    return out


def held_by(g, origin: str) -> list[str]:
    """Doors that stop smoke in this what-if (self-closing doors on the boundary of the smoke)."""
    smoked = {s for ev in smoke_schedule(g, origin, 1.0, 1e9) for s in ev["spaces"]}
    return sorted(d.name for d in g.doors.values()
                  if d.self_closing is True and len(d.spaces) >= 2
                  and any(x in smoked for x in d.spaces) and not all(x in smoked for x in d.spaces))


def origin_near_stair(g, stair: str) -> str:
    """A fire origin that blocks the approach to the stair: a non-corridor space with an open connection to a
    corridor that leads to one of the stair's doors (nearest such space). Falls back to the nearest space."""
    s = g.stairs[stair]
    door_corridors = {sp for dn in s.doors for sp in g.doors[dn].spaces
                      if g.space_meta.get(sp, {}).get("category") == "corridor"}
    adj = smoke_graph(g)
    pts = [g.doors[d].poly.centroid for d in s.doors]
    best, fallback = None, None
    for n, poly in g.spaces.items():
        cat = g.space_meta[n].get("category")
        if cat in ("stair", "corridor", "cabin"):
            continue
        d = min(poly.distance(p) for p in pts)
        if fallback is None or d < fallback[0]:
            fallback = (d, n)
        if adj[n] & door_corridors and (best is None or d < best[0]):
            best = (d, n)
    return (best or fallback)[1]
