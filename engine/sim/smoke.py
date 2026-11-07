"""Illustrative smoke spread, not a fire model."""
from __future__ import annotations

from shapely.geometry import Point


def origin_near_stair(g, stair: str) -> str:
    """The non-corridor, non-stair space whose footprint is closest to the stair's doors (its approach)."""
    s = g.stairs[stair]
    pts = [g.doors[d].poly.centroid for d in s.doors]
    best = None
    for n, poly in g.spaces.items():
        cat = g.space_meta[n].get("category")
        if cat in ("stair", "corridor", "cabin"):
            continue
        d = min(poly.distance(p) for p in pts)
        if best is None or d < best[0]:
            best = (d, n)
    return best[1]
