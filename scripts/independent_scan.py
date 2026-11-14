"""Independent scan (spec B5): count what each rule should find, WITHOUT the engine or the pipeline.

Deliberately separate code: it reads the IFC with ifcopenshell and the raw Navisworks property export itself,
with its own (simpler) logic. The ground-truth test compares the engine's counts with these.

    python scripts/independent_scan.py [deck5_revA|deck5_revB|rcrv_structure] -> JSON {rule: {status: count}}

Covered: deck5 R-FLS-01 (door vs host wall fire class); RCRV R-STR-01, R-SYS-01, R-DQ-01, R-DQ-02, R-DQ-03.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RANK = {"A": 3, "B": 2, "C": 1}


def _rank(s):
    m = re.match(r"^\s*([ABC])\s*-?\s*(\d+)?\s*$", str(s or ""), re.I)
    return (RANK[m.group(1).upper()], int(m.group(2) or 0)) if m else None


def scan_deck5(path: Path) -> dict:
    import ifcopenshell
    f = ifcopenshell.open(str(path))

    def rating(ent, pset):
        for rel in getattr(ent, "IsDefinedBy", []) or []:
            d = getattr(rel, "RelatingPropertyDefinition", None)
            if d is not None and d.is_a("IfcPropertySet") and d.Name == pset:
                for p in d.HasProperties:
                    if p.Name == "FireRating" and p.NominalValue is not None:
                        return p.NominalValue.wrappedValue
        return None

    out = defaultdict(Counter)
    for door in f.by_type("IfcDoor"):
        for fill in door.FillsVoids or []:
            for void in fill.RelatingOpeningElement.VoidsElements or []:
                wall = void.RelatingBuildingElement
                hr = _rank(rating(wall, "Pset_WallCommon"))
                if not hr or hr[0] != 3:
                    continue
                dr = _rank(rating(door, "Pset_DoorCommon"))
                out["R-FLS-01"]["unk" if dr is None else "pass" if dr >= hr else "fail"] += 1
    return {k: dict(v) for k, v in out.items()}


# --- RCRV: properties.sqlite (objects, from scripts/rcrv_to_ifc.py) + raw properties.jsonl
STEEL = re.compile(r"A106|A105|A234|A53\b|A312|A182|A403|A216|A351|CARBON STEEL|STAINLESS|^STEEL|GR-A STEEL|316|304", re.I)
MAT_WORDS = re.compile(r"ASTM|UNS|COPPER|STEEL|STAINLESS|BRONZE|BRASS|PVC|RUBBER|ALUMIN|IRON|CUNI|HDPE|NYLON|PTFE|EPDM|FRP|GRP|TITANIUM", re.I)
W11 = {"A", "B", "D", "E"} | {f"{g}H{n}" for g in "ADEF" for n in (32, 36, 40)}
NOT_MATERIAL = re.compile(r"^AIR\b|ASTM E-?84|FABREEKA|DIM PAD", re.I)


def scan_rcrv() -> dict:
    rc = ROOT / "data" / "rcrv"
    db = sqlite3.connect(rc / "properties.sqlite")
    objs = {dbid: cls for dbid, cls in db.execute("select dbid, ifc_class from objects")}
    parent, sc, attrs, errs = {}, {}, {}, defaultdict(set)
    with open(rc / "gltf" / "properties.jsonl") as fh:
        for line in fh:
            o = json.loads(line)
            parent[o["dbid"]] = o["parent"] or 0
            if "ShipConstructor" not in line and '"Attributes"' not in line:
                continue
            for cat, k, v in o["props"]:
                if k == "ShipConstructor:StockMaterialName[0]":
                    sc.setdefault(o["dbid"], {})["mat"] = v
                elif k == "ShipConstructor:StockThickness[0]":
                    sc.setdefault(o["dbid"], {})["thk"] = v
                if cat == "ShipConstructor" and str(v).strip() in ("Error", "---"):
                    errs[o["dbid"]].add(str(v).strip())
            a = [str(v) for c, _, v in o["props"] if c == "Attributes"]
            if a:
                attrs[o["dbid"]] = a

    def near(d, table, up):
        for _ in range(up):
            if d in table:
                return table[d]
            d = parent.get(d, 0)
            if not d:
                return None
        return None

    out = defaultdict(Counter)
    hits = defaultdict(list)                       # non-pass findings: (rule, status, dbid, value)
    for dbid, cls in objs.items():
        s = near(dbid, sc, 2) or {}
        mat = s.get("mat")
        if cls == "IfcPlate":
            out["R-DQ-01"]["pass" if mat and s.get("thk") else "warn"] += 1
            if mat:
                out["R-DQ-02"]["warn" if NOT_MATERIAL.search(mat) else "pass"] += 1
                if NOT_MATERIAL.search(mat):
                    hits["R-DQ-02"].append(("warn", dbid, mat))
        if cls in ("IfcPlate", "IfcMember"):
            if mat is None:
                out["R-STR-01"]["unk"] += 1
            elif mat.upper().startswith(("CS ", "ASTM A", "STEEL", "GR-A")):
                g = mat[7:].strip() if mat.upper().startswith("CS ABS ") else None
                out["R-STR-01"]["pass" if g in W11 else "warn"] += 1
                if g not in W11:
                    hits["R-STR-01"].append(("warn", dbid, mat))
        if cls == "IfcPipeSegment":
            a = near(dbid, attrs, 5)
            if a and re.search(r"FUEL OIL|FO OVERFLOW", a[0], re.I):
                m = next((v for v in a[3:] if MAT_WORDS.search(v) and "F683" not in v.upper()
                          and "INSULATION" not in v.upper() and len(v) < 40), None)
                st = "unk" if m is None else "pass" if STEEL.search(m) else "warn"
                out["R-SYS-01"][st] += 1
                if st == "warn":
                    hits["R-SYS-01"].append(("warn", dbid, f"{a[0]} | {m}"))
        e = near(dbid, errs, 2)
        if e:
            out["R-DQ-03"]["warn"] += 1
            hits["R-DQ-03"].append(("warn", dbid, ", ".join(sorted(e))))
    scan_rcrv.hits = hits                          # for writing the ground-truth list once (see tests/ground_truth)
    return {k: dict(v) for k, v in out.items()}


def scan(scenario: str) -> dict:
    if scenario.startswith("deck5_rev"):
        return scan_deck5(ROOT / "data" / f"{scenario}.ifc")
    if scenario == "rcrv_structure":
        return scan_rcrv()
    raise ValueError(scenario)


if __name__ == "__main__":
    print(json.dumps({s: scan(s) for s in (sys.argv[1:] or ["deck5_revA", "deck5_revB", "rcrv_structure"])}, indent=1))
