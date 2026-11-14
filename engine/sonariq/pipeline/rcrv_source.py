"""RCRV glTF (Navisworks -> APS -> svf-utils) as a tile source, without the IFC hop (DECISIONS M1, M4).

Objects and their GlobalIds are exactly those of scripts/rcrv_to_ifc.py (same owner walk, same uuid5), so engine
findings on rcrv_*.ifc map onto the tiles 1:1. One pass over properties.jsonl also collects what rules can read
(DECISIONS M10): ShipConstructor stock thickness / material / SWBS-like code / part GUID, and pipe block attributes.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from pathlib import Path

import ifcopenshell.guid
import numpy as np

from scripts.rcrv_to_ifc import CONTAINER_CLS, GEOM_CLS, IN2M, NS, node_xform

from .disciplines import classify

SC = "ShipConstructor:"
WANT = {SC + "StockThickness[0]": "thickness", SC + "StockMaterialName[0]": "material", SC + "V1[0]": "swbs_raw",
        SC + "PartGUID[0]": "part_guid", SC + "StockDescription[0]": "stock"}
CLS_KEY = "LcOaNode:LcOaSceneBaseClassUserName"
PLATE_CLS = {"Plate", "Standard Plate", "Stiffener"}
# a value that names a pipe material (block attributes have no names after the SVF export; see DECISIONS M10)
MATERIAL = re.compile(r"ASTM|ASME SB|UNS|COPPER|STEEL|STAINLESS|BRONZE|BRASS|CUNI|CU-NI|PVC|CPVC|RUBBER|HDPE|"
                      r"ALUMIN|TITANIUM|FRP|GRP|NYLON|PTFE|EPDM|IRON", re.I)
INSULATION = re.compile(r"F683|INSULATION", re.I)      # ASTM F683 is a pipe insulation spec, not the pipe material
ERROR_VALUES = {"Error", "---", "<None>", "TBD"}


def guid_of(dbid: int) -> str:
    return ifcopenshell.guid.compress(uuid.uuid5(NS, str(dbid)).hex)


def inch_fraction_mm(s: str | None) -> float | None:
    """'5/16"' -> 7.9375, '1 1/2"' -> 38.1. None when it is not an inch value."""
    if not s:
        return None
    m = re.fullmatch(r'\s*(?:(\d+)\s+)?(?:(\d+)/(\d+)|(\d+(?:\.\d+)?))\s*"?\s*', s)
    if not m:
        return None
    whole, num, den, dec = m.groups()
    v = float(dec) if dec else (int(whole or 0) + int(num) / int(den))
    return round(v * 25.4, 4)


def read_properties(path: Path) -> tuple[np.ndarray, list[str | None], np.ndarray, dict, dict]:
    """parents[dbid], class names, class code per dbid, ShipConstructor props per dbid, block attributes per dbid."""
    parents, codes, names = [0], [0], {None: 0}
    sc: dict[int, dict] = {}
    attrs: dict[int, list[str]] = {}
    with open(path) as f:
        for line in f:
            o = json.loads(line)
            i = o["dbid"]
            while len(parents) <= i:
                parents.append(0)
                codes.append(0)
            parents[i] = o["parent"] or 0
            c = None
            d, a = {}, []
            for cat, k, v in o["props"]:
                if k == CLS_KEY:
                    c = v
                elif k in WANT:
                    d[WANT[k]] = v
                elif cat == "Attributes":
                    a.append(str(v))
            codes[i] = names.setdefault(c, len(names))
            if d:
                sc[i] = d
            if a:
                attrs[i] = a
    cls_names = [None] * len(names)
    for k, v in names.items():
        cls_names[v] = k
    return np.array(parents, np.int32), cls_names, np.array(codes, np.int16), sc, attrs


def _up(dbid: int, table: dict, parents: np.ndarray, levels: int):
    for _ in range(levels):
        if dbid in table:
            return table[dbid]
        dbid = int(parents[dbid])
        if not dbid:
            return None
    return None


def element_meta(e: dict, sc: dict | None, attrs: list[str] | None) -> dict:
    m = {"deck": e["deck"], "bbox": [round(v, 4) for v in e["bbox"]], "source_file": e.get("file"),
         "layer": e.get("layer"), "unit_source": "inch"}
    if sc:
        m["part_guid"] = sc.get("part_guid")
        if sc.get("thickness"):
            m["thickness_raw"] = sc["thickness"]
            m["thickness_mm"] = inch_fraction_mm(sc["thickness"])
        if sc.get("material"):
            m["material"] = sc["material"]
            g = re.fullmatch(r"CS ABS (\w+)", sc["material"])
            if g:
                m["grade"] = g.group(1)
        if sc.get("stock"):
            m["stock"] = sc["stock"]
        if sc.get("swbs_raw") and re.fullmatch(r"\d{3,4}", sc["swbs_raw"]):
            m["swbs"] = sc["swbs_raw"]
        bad = sorted({str(v).strip() for v in sc.values() if str(v).strip() in ERROR_VALUES})
        if bad:
            m["error_values"] = bad
    if attrs:
        m["system"] = attrs[0]
        mat = next((v for v in attrs[3:] if MATERIAL.search(v) and not INSULATION.search(v) and len(v) < 40), None)
        if mat:
            m["material"] = mat
        m["attributes"] = attrs[:20]
    return m


class RcrvSource:
    def __init__(self, gltf_dir: Path, sqlite_path: Path, progress=None):
        gp = next(Path(gltf_dir).glob("*/output.gltf"))
        g = json.loads(gp.read_text())
        self.bufs = [np.memmap(gp.parent / b["uri"], dtype=np.uint8, mode="r") for b in g["buffers"]]
        bv, acc = g["bufferViews"], g["accessors"]
        self.acc = [(bv[a["bufferView"]]["buffer"], bv[a["bufferView"]].get("byteOffset", 0) + a.get("byteOffset", 0),
                     a["count"]) for a in acc]
        self.mesh = [(m["primitives"][0]["attributes"]["POSITION"], m["primitives"][0]["indices"],
                      m["primitives"][0].get("material", 0)) for m in g["meshes"]]   # all: 1 primitive, u16 indices
        colors = [m.get("pbrMetallicRoughness", {}).get("baseColorFactor", [0.7, 0.7, 0.7, 1]) for m in g["materials"]]
        if progress:
            progress(0.02)
        parents, cls_names, codes, sc, attrs = read_properties(Path(gltf_dir) / "properties.jsonl")
        if progress:
            progress(0.15)
        geom = np.array([n in GEOM_CLS for n in cls_names])
        cont = np.array([n in CONTAINER_CLS for n in cls_names])
        plate = np.array([n in PLATE_CLS for n in cls_names])
        self.nodes, owners = [], {}
        for n in g["nodes"]:
            if "mesh" not in n:
                continue
            dbid = int(n["name"])
            owner, j = dbid, dbid
            while j:                                   # same walk as scripts/rcrv_to_ifc.py step 1
                c = codes[j]
                if cont[c]:
                    break
                owner = j
                if not geom[c] and (j != dbid or plate[c]):
                    break
                j = int(parents[j])
            A, t = node_xform(n)
            owners.setdefault(owner, []).append(len(self.nodes))
            self.nodes.append((n["mesh"], (A * IN2M).astype(np.float32), (t * IN2M).astype(np.float32)))
        del g
        db = sqlite3.connect(sqlite_path)
        self.elements = []
        for dbid, name, layer, file, ifc, deck, *bb in db.execute(
                "select dbid,name,layer,file,ifc_class,deck,x0,y0,z0,x1,y1,z1 from objects order by dbid"):
            e = {"id": guid_of(dbid), "src": str(dbid), "cls": ifc or "IfcBuildingElementProxy", "name": name,
                 "deck": int(deck.split()[-1]), "bbox": bb, "nodes": owners.get(dbid, []), "layer": layer, "file": file}
            e["tris"] = sum(self.acc[self.mesh[self.nodes[k][0]][1]][2] // 3 for k in e["nodes"])
            meta = element_meta(e, _up(dbid, sc, parents, 2), _up(dbid, attrs, parents, 5) if ifc in
                                ("IfcPipeSegment", None) else None)
            meta["mapped"] = ifc is not None
            e["group"] = classify(ifc, name=name, layer=layer, system=meta.get("system"), swbs=meta.get("swbs"))
            meta["discipline"] = e["group"]
            e["meta"] = meta
            c = colors[self.mesh[self.nodes[e["nodes"][0]][0]][2]] if e["nodes"] else [0.7, 0.7, 0.7]
            e["color"] = [round(v * 255) for v in c[:3]]
            self.elements.append(e)

    def meshes(self, e):
        for ni in e["nodes"]:
            mi, A, t = self.nodes[ni]
            pa, ia, _ = self.mesh[mi]
            b, off, cnt = self.acc[pa]
            V = np.frombuffer(self.bufs[b], dtype="<f4", count=cnt * 3, offset=off).reshape(cnt, 3) @ A.T + t
            b, off, cnt = self.acc[ia]
            F = np.frombuffer(self.bufs[b], dtype="<u2", count=cnt, offset=off).reshape(-1, 3)
            yield V, F
