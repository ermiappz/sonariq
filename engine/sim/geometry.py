"""Walkable deck geometry from the SonarIQ model (read from IFC): spaces minus walls plus door openings.

Everything comes from the model: IfcSpace footprints (walkable), IfcWall footprints (blocked), IfcDoor leaves
(re-opened through their host wall), IfcStair/IfcStairFlight + the STAIR space (landing and exit).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

from sonariq.model import Model

WALL_PAD = 0.06      # walls grow by this on each side, so seams between spaces are cut cleanly
OPEN_DEPTH = 1.0     # a door opening reaches this far across its wall (bridges a moved corridor bulkhead)


@dataclass
class Door:
    name: str
    guid: str
    poly: Polygon          # opening through the wall
    width: float
    self_closing: bool | None
    fire_rating: str | None
    spaces: list[str] = field(default_factory=list)   # the 1-2 spaces it connects


@dataclass
class Stair:
    name: str              # "3B"
    guid: str
    width: float           # clear width of the flight, m
    flight: Polygon
    enclosure: Polygon     # STAIR space footprint
    persons_by_deck: dict[str, int]
    mvz: str
    landings: list[tuple[float, float]] = field(default_factory=list)   # queue head points (one per door side)
    doors: list[str] = field(default_factory=list)


@dataclass
class DeckGeometry:
    walkable: Polygon
    spaces: dict[str, Polygon]
    space_meta: dict[str, dict]
    doors: dict[str, Door]
    stairs: dict[str, Stair]
    walls: list[tuple[str, Polygon, str | None]]     # name, footprint, fire rating
    open_edges: list[tuple[str, str]]                 # spaces that touch with no wall between (smoke passes)
    dropped: list[str]                                # spaces not reachable from any stair

    def space_at(self, x: float, y: float) -> str | None:
        p = Point(x, y)
        for n, poly in self.spaces.items():
            if poly.buffer(0.05).contains(p):
                return n
        return None

    def to_json(self) -> dict:
        """Vector geometry for the replay (SVG)."""
        def ring(poly):
            if isinstance(poly, MultiPolygon):
                return [ring(g) for g in poly.geoms]
            return {"outer": [list(map(lambda v: round(v, 3), c)) for c in poly.exterior.coords],
                    "holes": [[list(map(lambda v: round(v, 3), c)) for c in h.coords] for h in poly.interiors]}
        return {
            "walkable": ring(self.walkable),
            "bounds": [round(v, 3) for v in self.walkable.bounds],
            "spaces": [{"name": n, "category": self.space_meta[n].get("category"), "poly": ring(p),
                        "label_xy": [round(p.centroid.x, 2), round(p.centroid.y, 2)]} for n, p in self.spaces.items()],
            "walls": [{"name": n, "rating": r, "poly": ring(p)} for n, p, r in self.walls],
            "doors": [{"name": d.name, "self_closing": d.self_closing, "rating": d.fire_rating, "width": d.width,
                       "poly": ring(d.poly)} for d in self.doors.values()],
            "stairs": [{"name": s.name, "width": s.width, "flight": ring(s.flight), "landings": s.landings,
                        "persons_by_deck": s.persons_by_deck} for s in self.stairs.values()],
        }


def _deck_of(e) -> str:
    return str(e.sq.get("deck", "5"))


def build(model: Model, deck: str = "5", closed_stairs: tuple[str, ...] = (),
          blocked_spaces: tuple[str, ...] = (), closed_doors: tuple[str, ...] = ()) -> DeckGeometry:
    spaces = {e.name: e.poly for e in model.spaces(deck=deck) if e.poly is not None}
    meta = {e.name: dict(e.sq) for e in model.spaces(deck=deck)}
    walls = [(w.name, w.poly, w.prop("Pset_WallCommon", "FireRating")) for w in model.by_class("IfcWall")
             if w.poly is not None and _deck_of(w) == deck]
    wall_u = unary_union([p.buffer(WALL_PAD, join_style=2) for _, p, _ in walls])

    doors: dict[str, Door] = {}
    for d in model.by_class("IfcDoor"):
        if d.poly is None or _deck_of(d) != deck:
            continue
        x0, y0, x1, y1 = d.poly.bounds
        w = d.overall_width or max(x1 - x0, y1 - y0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if (x1 - x0) >= (y1 - y0):   # leaf runs along x -> wall runs along x, opening crosses in y
            op = box(cx - w / 2, cy - OPEN_DEPTH / 2, cx + w / 2, cy + OPEN_DEPTH / 2)
        else:
            op = box(cx - OPEN_DEPTH / 2, cy - w / 2, cx + OPEN_DEPTH / 2, cy + w / 2)
        sc = d.prop("Pset_DoorCommon", "SelfClosing")
        doors[d.name] = Door(d.name, d.guid, op, w, None if sc is None else bool(sc),
                             d.prop("Pset_DoorCommon", "FireRating"))
        doors[d.name].spaces = [n for n, p in spaces.items() if p.buffer(0.01).intersects(op)]

    base = unary_union([p.buffer(0.01, join_style=2) for n, p in spaces.items() if n not in blocked_spaces])
    walk = base.difference(wall_u)
    openings = unary_union([d.poly for n, d in doors.items() if n not in closed_doors])
    walk = unary_union([walk, openings])
    # stairs
    stairs: dict[str, Stair] = {}
    for st in model.by_class("IfcStair"):
        if _deck_of(st) != deck:
            continue
        nm = st.name.replace("Stair ", "")
        fl = next((model.elements[g] for g in st.parts if g in model.elements), None)
        enc = spaces.get(f"STAIR-{nm}")
        if fl is None or enc is None:
            continue
        fx0, fy0, fx1, fy1 = fl.poly.bounds
        width = min(fx1 - fx0, fy1 - fy0)
        pbd = json.loads(st.sq.get("persons_by_deck") or "{}")
        s = Stair(nm, st.guid, round(width, 3), fl.poly, enc, {k: int(v) for k, v in pbd.items()},
                  str(st.sq.get("mvz", "")))
        for dn, d in doors.items():
            if enc.buffer(0.3).intersects(d.poly) and d.poly.centroid.within(enc.buffer(0.3)):
                s.doors.append(dn)
                # queue head: on the landing between the door and the flight, 0.6 m short of the flight edge
                dc = d.poly.centroid
                if abs(dc.y) > abs(fl.poly.centroid.y):
                    hy = fy1 + 0.6 if dc.y > fl.poly.centroid.y else fy0 - 0.6
                    s.landings.append((round(fl.poly.centroid.x, 3), round(hy, 3)))
                else:
                    hx = fx1 + 0.6 if dc.x > fl.poly.centroid.x else fx0 - 0.6
                    s.landings.append((round(hx, 3), round(fl.poly.centroid.y, 3)))
        stairs[nm] = s
    # the flight itself is not walkable (agents leave the deck there); keep landing area
    for s in stairs.values():
        walk = walk.difference(s.flight.buffer(0.05, join_style=2))
    for nm in closed_stairs:   # secondary case: stair out of use -> its enclosure is closed off
        if nm in stairs:
            walk = walk.difference(stairs[nm].enclosure.buffer(0.35, join_style=2))
    walk = walk.buffer(-0.02, join_style=2).buffer(0.02, join_style=2)
    parts = list(walk.geoms) if isinstance(walk, MultiPolygon) else [walk]
    live = [s for s in stairs.values() if s.name not in closed_stairs]
    keep = [p for p in parts if any(p.buffer(0.05).contains(Point(*h)) for s in live for h in s.landings)]
    walk_keep = unary_union(keep) if keep else max(parts, key=lambda p: p.area)
    dropped = [n for n, p in spaces.items() if walk_keep.intersection(p).area < 0.3 * p.area
               and not n.startswith("STAIR-") and n not in blocked_spaces]
    if isinstance(walk_keep, MultiPolygon):
        walk_keep = walk_keep  # several connected parts, each with a stair
    # open edges for smoke: spaces whose footprints touch where there is no wall
    open_edges = []
    names = list(spaces)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            seam = spaces[a].buffer(0.02).intersection(spaces[b].buffer(0.02))
            if seam.is_empty or seam.area < 1e-4:
                continue
            if seam.difference(wall_u).area > 0.02 * 0.3:    # at least ~0.3 m of seam with no wall
                open_edges.append((a, b))
    return DeckGeometry(walk_keep, spaces, meta, doors, stairs, walls, open_edges, dropped)


def route_length(routing, a: tuple[float, float], b: tuple[float, float]) -> float:
    pts = routing.compute_waypoints(a, b)
    return LineString(pts).length if len(pts) > 1 else 0.0
