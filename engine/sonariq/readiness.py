"""Data-readiness report (spec B2): what the model contains, and per rule pack whether it can run.

Ready = every input present; Partial = it runs, n elements lack data (they come out Cannot verify);
Not possible = an input the pack cannot do without is absent (e.g. no spaces), so its rules do not run and are listed
as Cannot verify with this reason. Computed from the engine Model only; no rule logic here.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .model import Model
from .rules import PACK_GROUPS


def _has(e, *keys) -> bool:
    s = e.psets.get("SonarIQ_Source", {})
    return all(s.get(k) is not None for k in keys)


def inventory(m: Model) -> dict:
    els = list(m.elements.values())
    by = Counter(e.ifc_class for e in els)
    spaces = [e for e in els if e.ifc_class == "IfcSpace"]
    doors = [e for e in els if e.ifc_class == "IfcDoor"]
    plates = [e for e in els if e.ifc_class == "IfcPlate"]
    pipes = [e for e in els if e.ifc_class == "IfcPipeSegment"]
    fr = lambda e: any(p.get("FireRating") not in (None, "") for n, p in e.psets.items() if n.endswith("Common"))  # noqa: E731
    src = lambda e, k: e.psets.get("SonarIQ_Source", {}).get(k)  # noqa: E731
    swbs = sum(1 for e in els if src(e, "swbs"))
    inv = {
        "elements": len(els),
        "spaces": len(spaces), "corridors": sum(1 for s in spaces if s.sq.get("category") == "corridor"),
        "cabins_with_berths": sum(1 for s in spaces if s.sq.get("berths") is not None),
        "doors": len(doors), "doors_with_fire_rating": sum(1 for d in doors if fr(d)),
        "stairs": by.get("IfcStair", 0),
        "plates": len(plates),
        "plates_with_thickness": sum(1 for p in plates if src(p, "thickness_mm") is not None or p.sq.get("category") == "deck_plate"),
        "plates_with_grade": sum(1 for p in plates if src(p, "grade")),
        "plates_with_material": sum(1 for p in plates if src(p, "material")),
        "stiffeners": by.get("IfcMember", 0),
        "pipes": len(pipes), "pipes_with_system": sum(1 for p in pipes if src(p, "system")),
        "pipes_with_material": sum(1 for p in pipes if src(p, "material")),
        "ducts": by.get("IfcDuctSegment", 0), "dampers": by.get("IfcDamper", 0),
        "swbs_coverage": round(swbs / len(els), 3) if els else 0.0,
        "units": m.ship.get("units_of_source") or "metres (IFC)",
        "classes": dict(by.most_common()),
    }
    inv["missing"] = {"door fire rating": inv["doors"] - inv["doors_with_fire_rating"],
                      "plate thickness": inv["plates"] - inv["plates_with_thickness"],
                      "plate material": inv["plates"] - inv["plates_with_material"],
                      "pipe material": inv["pipes"] - inv["pipes_with_material"]}
    return inv


def _pack(name: str, inv: dict, m: Model) -> dict:
    """One line per pack: state + reason. Thresholds of 'Partial' are counts of elements the rules will mark unknown."""
    if name in ("fire", "escape"):
        if inv["spaces"] == 0:
            return {"state": "not_possible", "reason": "No spaces or rooms in the model (IfcSpace): escape routes, "
                                                        "corridors and fire zones cannot be found."}
        n = inv["doors"] - inv["doors_with_fire_rating"]
        if name == "fire" and n:
            return {"state": "partial", "n": n, "reason": f"{n} door{'s' if n != 1 else ''} without a fire rating."}
        if name == "escape" and not inv["stairs"]:
            return {"state": "partial", "n": 0, "reason": "No stairs in the model."}
        return {"state": "ready", "reason": "Spaces, doors with fire ratings and stairs are present."}
    if name == "accessibility":
        if inv["corridors"] == 0:
            return {"state": "not_possible", "reason": "No corridor spaces in the model."}
        return {"state": "ready", "reason": "Corridor spaces and doors are present."}
    if name == "hvac":
        if inv["ducts"] == 0:
            return {"state": "not_possible", "reason": "No ducts in the model."}
        return {"state": "ready", "reason": f"{inv['ducts']} ducts, {inv['dampers']} dampers."}
    if name == "class_dnv":
        if not any(e.sq.get("category") == "deck_plate" for e in m.elements.values()):
            return {"state": "not_possible", "reason": "No plates marked as deck plates (SonarIQ_Ship.category)."}
        return {"state": "ready", "reason": "Deck plates with geometry are present."}
    if name == "structure_systems":
        if inv["plates_with_material"] == 0 and inv["pipes_with_material"] == 0:
            return {"state": "not_possible", "reason": "No plate or pipe material data in the model."}
        n = inv["missing"]["pipe material"] if inv["pipes_with_system"] else 0
        if n:
            return {"state": "partial", "n": n, "reason": f"{n:,} pipe parts without a material value."}
        return {"state": "ready", "reason": "Plate materials and pipe systems are present."}
    if name == "data_quality":
        if inv["plates"] == 0:
            return {"state": "not_possible", "reason": "No plates in the model."}
        if inv["plates_with_material"] == 0:
            return {"state": "not_possible", "reason": "The model carries no material data on its plates, so there is "
                                                        "nothing to check for completeness."}
        return {"state": "ready", "reason": "Runs on whatever plate data the model has."}
    return {"state": "ready", "reason": ""}


def readiness(m: Model) -> dict:
    inv = inventory(m)
    packs = {}
    for g, meta in PACK_GROUPS.items():
        for p in meta["packs"]:
            packs[p] = {"group": g, "group_label": meta["label"], **_pack(p, inv, m)}
    return {"revision": m.revision, "inventory": inv, "packs": packs}


def save(d: dict, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"readiness_{d['revision']}.json"
    p.write_text(json.dumps(d, indent=1))
    return p
