"""IFC4 -> SonarIQ internal model.

The engine's checks run on this model, never on raw IFC, so edits (apply_edit) and what-if fixes can
change the model in memory and re-check in milliseconds.
"""
from __future__ import annotations

import copy
import hashlib
import json
import multiprocessing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element as uel
from shapely.geometry import MultiPoint, Polygon, box

GEOM_CLASSES = ("IfcSpace", "IfcWall", "IfcDoor", "IfcWindow", "IfcStairFlight", "IfcDuctSegment",
                "IfcDamper", "IfcPlate", "IfcSlab", "IfcPipeSegment", "IfcCovering", "IfcBuildingElementProxy",
                "IfcFurnishingElement", "IfcMember", "IfcBeam", "IfcColumn", "IfcRailing", "IfcStair")


@dataclass
class Element:
    guid: str
    ifc_class: str
    name: str
    psets: dict[str, dict[str, Any]] = field(default_factory=dict)
    poly: Polygon | None = None          # footprint, world XY, metres
    z0: float | None = None
    z1: float | None = None
    host: str | None = None              # GlobalId of the hosting wall (doors, windows)
    overall_width: float | None = None   # IfcDoor/IfcWindow.OverallWidth, metres
    parts: list[str] = field(default_factory=list)    # IfcStair -> flights
    members: list[str] = field(default_factory=list)  # IfcZone -> spaces
    storey: str | None = None

    @property
    def sq(self) -> dict[str, Any]:
        return self.psets.get("SonarIQ_Ship", {})

    def prop(self, pset: str, name: str) -> Any:
        v = self.psets.get(pset, {}).get(name)
        return None if v in ("", None) else v

    def fingerprint(self) -> str:
        geo = None
        if self.poly is not None:
            geo = [round(c, 3) for c in self.poly.bounds]
        payload = {"c": self.ifc_class, "n": self.name, "p": self.psets, "g": geo,
                   "z": [None if v is None else round(v, 3) for v in (self.z0, self.z1)],
                   "h": self.host, "w": None if self.overall_width is None else round(self.overall_width, 4),
                   "parts": sorted(self.parts), "m": sorted(self.members)}
        return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class Model:
    path: str | None
    revision: str
    ship: dict[str, Any]
    elements: dict[str, Element]
    frame_spacing_m: float = 0.8

    def copy(self) -> "Model":
        return copy.deepcopy(self)

    def by_class(self, *classes: str) -> list[Element]:
        return [e for e in self.elements.values() if e.ifc_class in classes]

    def by_name(self, name: str) -> Element | None:
        for e in self.elements.values():
            if e.name == name:
                return e
        return None

    def spaces(self, category: str | None = None, deck: str | None = None) -> list[Element]:
        out = []
        for e in self.elements.values():
            if e.ifc_class != "IfcSpace":
                continue
            if category and e.sq.get("category") != category:
                continue
            if deck and str(e.sq.get("deck")) != str(deck):
                continue
            out.append(e)
        return out


def _clean(v: Any) -> Any:
    if isinstance(v, float):
        return round(v, 6)
    return v


def _psets(ent) -> dict[str, dict[str, Any]]:
    out = {}
    for name, props in uel.get_psets(ent).items():
        out[name] = {k: _clean(v) for k, v in props.items() if k != "id"}
    return out


def _settings():
    s = ifcopenshell.geom.settings()
    try:
        s.set("use-world-coords", True)
    except Exception:  # noqa: BLE001  (older API)
        s.set(s.USE_WORLD_COORDS, True)
    return s


def load_ifc(path: str | Path, revision: str | None = None) -> Model:
    f = ifcopenshell.open(str(path))
    ship_ent = (f.by_type("IfcBuilding") or [None])[0]
    ship = _psets(ship_ent).get("SonarIQ_Ship", {}) if ship_ent else {}
    if ship_ent is not None:
        ship = dict(ship, name=ship_ent.Name)
    els: dict[str, Element] = {}
    for ent in f.by_type("IfcProduct"):
        if ent.is_a("IfcOpeningElement") or ent.is_a("IfcSpatialStructureElement") and not ent.is_a("IfcSpace"):
            continue
        e = Element(guid=ent.GlobalId, ifc_class=ent.is_a(), name=ent.Name or ent.GlobalId, psets=_psets(ent))
        if ent.is_a("IfcDoor") or ent.is_a("IfcWindow"):
            e.overall_width = ent.OverallWidth
            for rel in getattr(ent, "FillsVoids", []) or []:
                op = rel.RelatingOpeningElement
                for v in getattr(op, "VoidsElements", []) or []:
                    e.host = v.RelatingBuildingElement.GlobalId
        if ent.is_a("IfcStair"):
            for rel in getattr(ent, "IsDecomposedBy", []) or []:
                e.parts += [p.GlobalId for p in rel.RelatedObjects]
        c = uel.get_container(ent)
        if c is not None:
            e.storey = c.Name
        els[e.guid] = e
    for z in f.by_type("IfcZone"):
        e = Element(guid=z.GlobalId, ifc_class="IfcZone", name=z.Name, psets=_psets(z))
        for rel in getattr(z, "IsGroupedBy", []) or []:
            e.members += [o.GlobalId for o in rel.RelatedObjects]
        els[e.guid] = e

    # geometry: footprint = convex hull of world XY vertices; z range
    it = ifcopenshell.geom.iterator(_settings(), f, max(1, min(4, multiprocessing.cpu_count())),
                                    include=[x for c in GEOM_CLASSES for x in f.by_type(c)])
    if it.initialize():
        while True:
            sh = it.get()
            g = els.get(sh.guid)
            if g is not None:
                v = sh.geometry.verts
                pts = [(v[i], v[i + 1]) for i in range(0, len(v), 3)]
                zs = v[2::3]
                if pts:
                    hull = MultiPoint(pts).convex_hull
                    if hull.geom_type != "Polygon":
                        hull = hull.buffer(0.005)
                    g.poly = hull
                    g.z0, g.z1 = min(zs), max(zs)
            if not it.next():
                break
    rev = revision or str(ship.get("revision") or Path(str(path)).stem.split("rev")[-1][:1] or "?")
    return Model(path=str(path), revision=rev, ship=ship, elements=els,
                 frame_spacing_m=float(ship.get("frame_spacing_m") or 0.8))


def rect(poly: Polygon) -> tuple[float, float]:
    """(short side, long side) of the minimum rotated rectangle, metres."""
    r = poly.minimum_rotated_rectangle
    xs = list(r.exterior.coords)
    import math
    a = math.dist(xs[0], xs[1])
    b = math.dist(xs[1], xs[2])
    return (min(a, b), max(a, b))


def set_rect(e: Element, x0: float, y0: float, x1: float, y1: float) -> None:
    e.poly = box(x0, y0, x1, y1)
