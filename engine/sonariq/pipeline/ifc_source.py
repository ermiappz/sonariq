"""IFC (IFC2x3 / IFC4 / IFC4x3, whatever ifcopenshell opens) as a tile source: world-space triangles per product."""
from __future__ import annotations

import multiprocessing
import re
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element as uel
import numpy as np

from .disciplines import classify

DEFAULT_RGB = {"structure": (150, 160, 172), "architecture": (205, 200, 190), "hvac": (63, 208, 230),
               "piping": (196, 227, 92), "electrical": (130, 221, 138), "fire": (226, 125, 255),
               "equipment": (163, 163, 255), "other": (170, 170, 170), "spaces": (120, 140, 170)}


def _fire_rating(psets: dict) -> str | None:
    for n, p in psets.items():
        if n.endswith("Common") and p.get("FireRating") not in (None, ""):
            return str(p["FireRating"])
    return None


def _material(ent) -> str | None:
    m = uel.get_material(ent)
    if m is None:
        return None
    if m.is_a("IfcMaterial"):
        return m.Name
    for attr in ("ForLayerSet", "ForProfileSet"):
        if getattr(m, attr, None) is not None:
            m = getattr(m, attr)
    names = [getattr(x, "Name", None) for x in uel.get_materials(ent) or []] if hasattr(uel, "get_materials") else []
    return ", ".join(n for n in names if n) or getattr(m, "Name", None)


class IfcSource:
    def __init__(self, path: Path, progress=None):
        f = ifcopenshell.open(str(path))
        self.schema = f.schema
        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", True)
        self.geo: dict[str, list] = {}
        products = [p for p in f.by_type("IfcProduct") if not p.is_a("IfcOpeningElement")
                    and not (p.is_a("IfcSpatialStructureElement") and not p.is_a("IfcSpace"))]
        it = ifcopenshell.geom.iterator(settings, f, max(1, min(4, multiprocessing.cpu_count())), include=products)
        rgb: dict[str, tuple] = {}
        if it.initialize():
            while True:
                sh = it.get()
                g = sh.geometry
                V = np.asarray(g.verts, np.float32).reshape(-1, 3)
                F = np.asarray(g.faces, np.uint32).reshape(-1, 3)
                if len(F):
                    self.geo.setdefault(sh.guid, []).append((V, F))
                    if g.materials:
                        d = g.materials[0].diffuse
                        rgb[sh.guid] = tuple(round(c * 255) for c in (d.r(), d.g(), d.b())) if hasattr(d, "r") else None
                if not it.next():
                    break
        if progress:
            progress(0.6)
        storey_deck = {}
        for s in f.by_type("IfcBuildingStorey"):
            num = re.findall(r"\d+", s.Name or "")
            storey_deck[s.GlobalId] = int(num[0]) if num else 0
        self.aliases: dict[str, list[str]] = {}
        for z in f.by_type("IfcZone"):            # MVZ findings point at the zone; the viewer shows its spaces
            self.aliases[z.GlobalId] = [o.GlobalId for r in getattr(z, "IsGroupedBy", []) or [] for o in r.RelatedObjects]
        self.elements = []
        for p in products:
            psets = uel.get_psets(p)
            sq = psets.get("SonarIQ_Ship", {})
            c = uel.get_container(p)
            deck = sq.get("deck")
            deck = int(deck) if str(deck or "").isdigit() else storey_deck.get(c.GlobalId if c else None, 0)
            parts = [o.GlobalId for r in getattr(p, "IsDecomposedBy", []) or [] for o in r.RelatedObjects]
            if parts:
                self.aliases[p.GlobalId] = parts
            V = [v for v, _ in self.geo.get(p.GlobalId, [])]
            if not V:
                continue
            allv = np.vstack(V)
            disc = classify(p.is_a(), name=p.Name, system=sq.get("system"))
            meta = {"deck": deck, "frame": sq.get("frame"), "side": sq.get("side"), "discipline": disc,
                    "fire_rating": _fire_rating(psets), "material": _material(p), "category": sq.get("category"),
                    "bbox": [round(float(x), 4) for x in (*allv.min(0), *allv.max(0))], "mapped": True,
                    "unit_source": "metre"}
            self.elements.append({
                "id": p.GlobalId, "src": getattr(p, "Tag", None), "cls": p.is_a(), "name": p.Name or p.GlobalId,
                "deck": deck, "group": disc, "bbox": meta["bbox"], "meta": {k: v for k, v in meta.items() if v is not None},
                "tris": sum(len(F) for _, F in self.geo[p.GlobalId]), "hidden": disc == "spaces",
                "color": rgb.get(p.GlobalId) or DEFAULT_RGB.get(disc, (170, 170, 170))})

    def meshes(self, e):
        return self.geo.get(e["id"], [])
