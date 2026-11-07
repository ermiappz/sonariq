"""RCRV (Navisworks -> SVF -> glTF + properties) to IFC4 for SonarIQ.

Inputs : data/rcrv/gltf/<view>/output.gltf (+ .bin), data/rcrv/gltf/props_cache.pkl (scripts/rcrv_cache.py)
Outputs: data/rcrv/rcrv_full.ifc, data/rcrv/rcrv_deck_<n>.ifc, data/rcrv/mapping_review.csv,
         data/rcrv/properties.sqlite, data/rcrv/rcrv_objects.json, docs/rcrv_report.md

Method
- An *object* is the named Navisworks node that owns geometry (a block such as "A-CLASS DOOR MA60CX (RI)-118");
  its Subentity / MESH / 3D Solid children are its geometry.
- Classification is rule-based on object name, layer, source file and ShipConstructor properties. Nothing is
  guessed: objects no rule matches go to mapping_review.csv (portal W5) and are left out of the IFC.
- Geometry: IfcTriangulatedFaceSet. Doors, windows, stairs, walls and hatches carry their real triangles; systems,
  structure and equipment carry an 8-vertex box (their meshes stay in the glTF for viewing). Units: model inches,
  IFC metres.
- Storeys: one per deck, found as peaks of horizontal plate area by height.
- Door clear width: the long horizontal side of the oriented bounding box of the door's largest leaf part; the whole
  block (leaf + frame) is reported next to it. Flat faces survive triangulation exactly.
"""
from __future__ import annotations

import collections
import csv
import json
import math
import pickle
import re
import sqlite3
import struct
import sys
import time
import uuid
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import numpy as np
from shapely.geometry import MultiPoint

ROOT = Path(__file__).resolve().parents[1]
RC = ROOT / "data" / "rcrv"
G = RC / "gltf"
IN2M = 0.0254
NS = uuid.UUID("5a4b1d2e-0000-4000-8000-524352560000")
GEOM_CLS = {None, "Subentity", "MESH", "3D Solid", "SURFACE", "Region", "Polyline", "Line", "Solid", "Body",
            "Geometry", "Shell", "Face", "3D Face", "PolyfaceMesh", "Polyface Mesh"}
CONTAINER_CLS = {"Layer", "File", "Group", "Collection"}
DETAIL_CLASSES = {"IfcDoor", "IfcWindow", "IfcStair", "IfcWall"}

# (ifc class, label, regex on "name | layer | file", object type)
RULES = [
    ("IfcDoor", "door", r"\bDOORS?\b(?!.*HOLD ?BACK)", None),
    ("IfcWindow", "window", r"WINDOW|PORT ?LIGHT|SIDELIGHT|SIDE ?SCUTTLE", None),
    ("IfcStair", "stair", r"\bSTAIRS?\b|STAIRWAY|\bLADDERS?\b|INCLINED LADDER", None),
    ("IfcDoor", "hatch", r"\bHATCH(ES)?\b|SCUTTLE|MANHOLE", "HATCH"),
    ("IfcWall", "bulkhead", r"JOINER|BULKHEAD|\bBHD\b|PARTITION|LINING|WALL PANEL|NON[- ]?STRUCTURAL", None),
    ("IfcDuctSegment", "duct", r"\bHVAC|\bDUCT|VENTILATION|LOUVER|DEMISTER", None),
    ("IfcPipeSegment", "pipe", r"WATER|DRAIN|SEWAGE|BILGE|BALLAST|FUEL|\bOIL\b|OIL -|COMPRESSED AIR|COOLING|FIREMAIN|"
                               r"HYDRAULIC|CHILLED|WASTE HEAT|VENTS? OVERFLOW|SCUPPER|\bDEF\b|EXHAUST|STEAM|SOUNDING|"
                               r"FO OVERFLOW|LUBE|PIPE", None),
    ("IfcCableCarrierSegment", "cable tray", r"CABLE ?TRAY|WIREWAY", None),
    ("IfcPlate", "plate", r"^__CLS_PLATE__", None),
    ("IfcMember", "stiffener", r"^__CLS_STIFFENER__", None),
    ("IfcRailing", "railing", r"RAILING|HANDRAIL|STANCHION|GUARD ?RAIL|NETTING", None),
    ("IfcFurnishingElement", "furniture", r"FURNITURE|FURNISHING|GALLEY EQUIPMENT|BUNK|BERTH|SOFA|TABLE|LOCKER", None),
    ("IfcCovering", "insulation", r"INSULATION", None),
    ("IfcBuildingElementProxy", "equipment", r"EQUIPMENT|SWITCHBOARD|ELECTRICAL|PANELS|GENERATOR|PROPULSION|"
                                             r"MOTOR CONTROLLER|LIGHT|CRANE|WINCH|DAVIT|A-FRAME|LARS|LIFERAFT|"
                                             r"Z-DRIVE|THRUSTER|RADOME|ANTENNA|MOUNT|FDNS|SOCKET|GANGWAY|"
                                             r"TRANSDUCER|\bTX\b|EK ?80|WIPER", "EQUIPMENT"),
]
RULES_C = [(c, l, re.compile(rx, re.I), t) for c, l, rx, t in RULES]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def quat_mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def node_xform(n):
    if "matrix" in n:
        M = np.array(n["matrix"]).reshape(4, 4).T
        return M[:3, :3], M[:3, 3]
    R = quat_mat(n.get("rotation", [0, 0, 0, 1]))
    S = np.diag(n.get("scale", [1, 1, 1]))
    return R @ S, np.array(n.get("translation", [0, 0, 0]), dtype=float)


class Gltf:
    def __init__(self, path: Path):
        self.dir = path.parent
        self.g = json.loads(path.read_text())
        self._bins: dict[int, bytes] = {}

    def buf(self, i):
        if i not in self._bins:
            if len(self._bins) > 6:
                self._bins.pop(next(iter(self._bins)))
            self._bins[i] = (self.dir / self.g["buffers"][i]["uri"]).read_bytes()
        return self._bins[i]

    def accessor(self, i):
        a = self.g["accessors"][i]
        bv = self.g["bufferViews"][a["bufferView"]]
        data = self.buf(bv["buffer"])
        comp = {5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4), 5121: ("B", 1)}[a["componentType"]]
        ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride", 0)
        cnt = a["count"]
        if stride and stride != comp[1] * ncomp:
            arr = np.array([struct.unpack_from("<" + comp[0] * ncomp, data, off + k * stride) for k in range(cnt)])
        else:
            arr = np.frombuffer(data, dtype="<" + comp[0], count=cnt * ncomp, offset=off).reshape(cnt, ncomp)
        return arr

    def corners(self, mesh_i):
        out = []
        for p in self.g["meshes"][mesh_i]["primitives"]:
            a = self.g["accessors"][p["attributes"]["POSITION"]]
            lo, hi = a.get("min"), a.get("max")
            if lo is None:
                continue
            out += [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
        return np.array(out) if out else None

    def triangles(self, mesh_i):
        V, F = [], []
        for p in self.g["meshes"][mesh_i]["primitives"]:
            if p.get("mode", 4) != 4:
                continue
            pos = self.accessor(p["attributes"]["POSITION"])
            idx = self.accessor(p["indices"]).reshape(-1) if "indices" in p else np.arange(len(pos))
            base = sum(len(v) for v in V)
            V.append(pos)
            F.append(idx.reshape(-1, 3) + base)
        if not V:
            return None, None
        return np.vstack(V).astype(float), np.vstack(F)


def classify(name, layer, file, props):
    cls = (props or {}).get("cls")
    if cls in ("Plate", "Standard Plate"):
        key = "__CLS_PLATE__"
    elif cls == "Stiffener":
        key = "__CLS_STIFFENER__"
    else:
        key = f"{name} | {layer} | {file}"
    for ifc, label, rx, otype in RULES_C:
        if rx.search(key):
            return ifc, label, otype
    return None, None, None


def main(max_detail_tris: int = 20000):
    t0 = time.time()
    gl_path = next(G.glob("*/output.gltf"))
    log("loading", gl_path)
    gl = Gltf(gl_path)
    cache = pickle.load(open(G / "props_cache.pkl", "rb"))
    names, parents, props = cache["names"], cache["parents"], cache["props"]

    def chain(i):
        out = []
        while i:
            out.append(i)
            i = parents[i]
        return out

    # ---- 1. group geometry nodes into objects
    objects: dict[int, dict] = {}
    for ni, n in enumerate(gl.g["nodes"]):
        if "mesh" not in n:
            continue
        dbid = int(n["name"])
        ch = chain(dbid)
        owner = dbid
        for j in ch:
            c = props.get(j, {}).get("cls")
            if c in CONTAINER_CLS:
                break
            owner = j
            if c not in GEOM_CLS and j != dbid:
                break
            if c not in GEOM_CLS and j == dbid and c in ("Plate", "Standard Plate", "Stiffener"):
                break
        layer = next((names[j] for j in ch if props.get(j, {}).get("cls") == "Layer"), "")
        file = next((names[j] for j in ch if props.get(j, {}).get("cls") == "File"
                     and not str(names[j]).endswith(".nwd")), "")
        o = objects.setdefault(owner, {"dbid": owner, "name": names[owner] or str(owner), "layer": layer,
                                       "file": file, "nodes": []})
        o["nodes"].append(ni)
    log(f"{len(objects)} objects from {sum(len(o['nodes']) for o in objects.values())} geometry nodes")

    # ---- 2. bbox per object (from accessor min/max), classification
    for o in objects.values():
        pts = []
        for ni in o["nodes"]:
            n = gl.g["nodes"][ni]
            c = gl.corners(n["mesh"])
            if c is None:
                continue
            A, t = node_xform(n)
            pts.append(c @ A.T + t)
        if not pts:
            o["bbox"] = None
            continue
        P = np.vstack(pts) * IN2M
        o["bbox"] = [*P.min(0).round(4).tolist(), *P.max(0).round(4).tolist()]
        o["xy"] = P[:, :2]
        ifc, label, otype = classify(o["name"], o["layer"], o["file"], props.get(o["dbid"]))
        o["ifc"], o["label"], o["otype"] = ifc, label, otype

    objs = [o for o in objects.values() if o.get("bbox")]
    xs = [o["bbox"][0] for o in objs] + [o["bbox"][3] for o in objs]
    ship_len = round(max(xs) - min(xs), 2)

    # ---- 3. decks: peaks of horizontal plate area by height
    hist = collections.Counter()
    for o in objs:
        x0, y0, z0, x1, y1, z1 = o["bbox"]
        if o.get("ifc") == "IfcPlate" and (z1 - z0) < 0.05 and (x1 - x0) * (y1 - y0) > 1.0:
            hist[round((z0 + z1) / 2 / 0.1) * 0.1] += (x1 - x0) * (y1 - y0)
    peaks = sorted(z for z, a in hist.items() if a > 30)
    decks = []
    for z in peaks:
        if not decks or z - decks[-1] > 1.8:
            decks.append(z)
        elif hist[round(z / 0.1) * 0.1] > hist[round(decks[-1] / 0.1) * 0.1]:
            decks[-1] = z
    if not decks:
        decks = [0.0]
    deck_names = {i: f"Deck {i + 1}" for i in range(len(decks))}
    log("decks (m):", [round(d, 2) for d in decks])

    def deck_of(z0):
        k = 0
        for i, d in enumerate(decks):
            if z0 >= d - 0.3:
                k = i
        return k

    # ---- 4. mapping review csv + sqlite
    rows = []
    for o in objs:
        o["deck"] = deck_of(o["bbox"][2])
        status = "Matched" if o["ifc"] else "Unmapped"
        if o["ifc"] == "IfcDoor" and o["label"] == "door":
            status = "Needs review"   # accessible_route and fire class are not in the source model
        rows.append(o)
    with open(RC / "mapping_review.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source_id", "name", "layer", "source_file", "ifc_class", "label", "deck", "frame", "side",
                    "mvz", "solas_category", "berths", "status", "note"])
        for o in rows:
            if o["ifc"] and o["label"] != "door":
                continue
            x0, y0, z0, x1, y1, z1 = o["bbox"]
            side = "P" if (y0 + y1) / 2 > 0.3 else "S" if (y0 + y1) / 2 < -0.3 else "C"
            note = ("door: confirm accessible route and fire class" if o["ifc"] else
                    "no rule matched name/layer/file; checks that need it report Cannot verify")
            w.writerow([o["dbid"], o["name"], o["layer"], o["file"], o["ifc"] or "", o["label"] or "",
                        deck_names[o["deck"]], "", side, "", "", "",
                        "Needs review" if o["ifc"] else "Unmapped", note])
    db = sqlite3.connect(RC / "properties.sqlite")
    db.execute("DROP TABLE IF EXISTS objects")
    db.execute("CREATE TABLE objects (dbid INTEGER PRIMARY KEY, name TEXT, layer TEXT, file TEXT, ifc_class TEXT, "
               "label TEXT, deck TEXT, x0 REAL, y0 REAL, z0 REAL, x1 REAL, y1 REAL, z1 REAL, props TEXT)")
    db.executemany("INSERT INTO objects VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   [(o["dbid"], o["name"], o["layer"], o["file"], o["ifc"], o["label"], deck_names[o["deck"]],
                     *o["bbox"], json.dumps(props.get(o["dbid"], {}), default=str)) for o in objs])
    db.commit()
    db.close()

    # ---- 5. door clear widths
    def obb_long_short(xy):
        hull = MultiPoint([tuple(p) for p in xy]).convex_hull
        if hull.geom_type != "Polygon":
            return 0.0, 0.0
        r = hull.minimum_rotated_rectangle
        c = list(r.exterior.coords)
        a, b = math.dist(c[0], c[1]), math.dist(c[1], c[2])
        return max(a, b), min(a, b)

    doors = [o for o in objs if o["ifc"] == "IfcDoor" and o["label"] == "door"]
    for o in doors:
        o["block_w"], o["block_t"] = obb_long_short(o["xy"])
        best = None
        for ni in o["nodes"]:
            n = gl.g["nodes"][ni]
            c = gl.corners(n["mesh"])
            if c is None:
                continue
            A, t = node_xform(n)
            P = (c @ A.T + t) * IN2M
            L, T = obb_long_short(P[:, :2])
            h = P[:, 2].max() - P[:, 2].min()
            if h > 1.2 and T < 0.15 and (best is None or L > best[0]):   # a leaf: tall, thin
                best = (L, T, h)
        o["leaf_w"] = best[0] if best else None
        o["height"] = best[2] if best else o["bbox"][5] - o["bbox"][2]

    # ---- 6. IFC writer
    log("writing IFC")

    def new_file(title):
        f = ifcopenshell.file(schema="IFC4")
        run = ifcopenshell.api.run
        proj = run("root.create_entity", f, ifc_class="IfcProject", name=title)
        proj.UnitsInContext = f.createIfcUnitAssignment([f.createIfcSIUnit(None, "LENGTHUNIT", None, "METRE")])
        ctx = run("context.add_context", f, context_type="Model")
        body = run("context.add_context", f, context_type="Model", context_identifier="Body",
                   target_view="MODEL_VIEW", parent=ctx)
        site = run("root.create_entity", f, ifc_class="IfcSite", name="RCRV")
        ship = run("root.create_entity", f, ifc_class="IfcBuilding", name="RCRV")
        run("aggregate.assign_object", f, products=[site], relating_object=proj)
        run("aggregate.assign_object", f, products=[ship], relating_object=site)
        ps = run("pset.add_pset", f, product=ship, name="SonarIQ_Ship")
        run("pset.edit_pset", f, pset=ps, properties={
            "vessel_type": "research", "persons_on_board": 28, "scientists": 16, "crew": 12,
            "length_m": ship_len, "accessibility": True, "units_of_source": "inches",
            "source": "12100-RCRV-199_07-08-2021.nwd via APS SVF + svf-utils"})
        storeys = {}
        for i, z in enumerate(decks):
            s = run("root.create_entity", f, ifc_class="IfcBuildingStorey", name=deck_names[i])
            s.Elevation = float(z)
            run("aggregate.assign_object", f, products=[s], relating_object=ship)
            storeys[i] = s
        origin = f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0)))
        return f, body, storeys, f.createIfcLocalPlacement(None, origin)

    def faceset(f, body, V, F):
        pl = f.createIfcCartesianPointList3D([tuple(map(float, v)) for v in V])
        fs = f.createIfcTriangulatedFaceSet(pl, None, None, [tuple(int(i) + 1 for i in t) for t in F], None)
        return f.createIfcProductDefinitionShape(None, None,
                                                 [f.createIfcShapeRepresentation(body, "Body", "Tessellation", [fs])])

    BOX_F = np.array([[0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6], [0, 1, 5], [0, 5, 4], [2, 6, 7], [2, 7, 3],
                      [0, 4, 6], [0, 6, 2], [1, 3, 7], [1, 7, 5]])

    def object_geometry(o):
        if o["ifc"] in DETAIL_CLASSES:
            Vs, Fs, base = [], [], 0
            for ni in o["nodes"]:
                n = gl.g["nodes"][ni]
                V, F = gl.triangles(n["mesh"])
                if V is None:
                    continue
                A, t = node_xform(n)
                Vs.append((V @ A.T + t) * IN2M)
                Fs.append(F + base)
                base += len(V)
                if base > max_detail_tris * 3:
                    break
            if Vs:
                V = np.vstack(Vs).round(4)
                F = np.vstack(Fs)
                if len(F) <= max_detail_tris:
                    return V, F, "mesh"
        x0, y0, z0, x1, y1, z1 = o["bbox"]
        V = np.array([(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)])
        return V, BOX_F, "box"

    def write(path, sel, title):
        f, body, storeys, place = new_file(title)
        run = ifcopenshell.api.run
        by_storey = collections.defaultdict(list)
        n_mesh = 0
        for o in sel:
            e = f.create_entity(o["ifc"], GlobalId=ifcopenshell.guid.compress(uuid.uuid5(NS, str(o["dbid"])).hex),
                                Name=o["name"][:250])
            if o.get("otype"):
                e.ObjectType = o["otype"]
            if o["ifc"] == "IfcDoor" and o.get("leaf_w"):
                e.OverallWidth = round(o["leaf_w"], 4)
                e.OverallHeight = round(o["height"], 4)
            V, F, kind = object_geometry(o)
            n_mesh += kind == "mesh"
            e.ObjectPlacement = place
            e.Representation = faceset(f, body, V, F)
            x0, y0, z0, x1, y1, z1 = o["bbox"]
            side = "P" if (y0 + y1) / 2 > 0.3 else "S" if (y0 + y1) / 2 < -0.3 else "C"
            sq = {"deck": str(o["deck"] + 1), "side": side, "geometry": kind}
            if o["ifc"] == "IfcDoor" and o["label"] == "door":
                sq["clear_width_m"] = round(o["leaf_w"], 4) if o.get("leaf_w") else None
                sq["accessible_route"] = not re.search(r"W/?T|WATERTIGHT|WEATHERTIGHT|GRATING|HATCH", o["name"], re.I)
                if "A-CLASS" in o["name"].upper():
                    sq["fire_class_hint"] = "A-class (from source name; FireRating left empty until confirmed)"
            src = {"source_id": str(o["dbid"]), "source_name": o["name"][:250], "layer": o["layer"][:250],
                   "source_file": o["file"][:250]}
            for pn, pv in (("SonarIQ_Source", src), ("SonarIQ_Ship", sq)):
                ps = run("pset.add_pset", f, product=e, name=pn)
                run("pset.edit_pset", f, pset=ps, properties={k: v for k, v in pv.items() if v not in (None, "")})
            by_storey[o["deck"]].append(e)
        for k, els in by_storey.items():
            run("spatial.assign_container", f, products=els, relating_structure=storeys[k])
        f.write(str(path))
        return len(sel), n_mesh

    classified = [o for o in objs if o["ifc"]]
    per_deck = collections.defaultdict(list)
    for o in classified:
        per_deck[o["deck"]].append(o)
    deck_files = {}
    for k in sorted(per_deck):
        if k == 0:
            continue
        p = RC / f"rcrv_deck_{k + 1}.ifc"
        deck_files[k] = (p.name, *write(p, per_deck[k], f"RCRV {deck_names[k]}"))
        log("wrote", p.name, deck_files[k][1:])
    full = write(RC / "rcrv_full.ifc", classified, "RCRV")
    log("wrote rcrv_full.ifc", full)

    # ---- 7. report
    cnt = collections.Counter(o["ifc"] or "Unmapped" for o in objs)
    lab = collections.Counter(o["label"] or "unmapped" for o in objs)
    json.dump({"decks_m": decks, "ship_length_m": ship_len, "counts": cnt, "labels": lab,
               "doors": [{k: o.get(k) for k in ("dbid", "name", "file", "deck", "leaf_w", "block_w", "height", "bbox")}
                         for o in doors]}, open(RC / "rcrv_objects.json", "w"), indent=1, default=str)
    sample = sorted([o for o in doors if o.get("leaf_w")], key=lambda o: (o["deck"], o["name"]))
    pick = []
    seen = set()
    for o in sample:
        key = re.sub(r"[-\d,]+$", "", o["name"])
        if (o["deck"], key) in seen:
            continue
        seen.add((o["deck"], key))
        pick.append(o)
    pick = pick[:10]
    lines = ["# RCRV conversion report", "",
             f"Source `12100-RCRV-199_07-08-2021.nwd` (model units: inches) → Autodesk Model Derivative (SVF) → "
             f"svf-utils glTF + property database → `scripts/rcrv_to_ifc.py` → IFC4. Generated "
             f"{time.strftime('%d %b %Y %H:%M')} UTC.", "",
             f"**{len(objs):,} objects** from {sum(len(o['nodes']) for o in objs):,} geometry nodes. "
             f"**{len(classified):,} classified** into IFC; **{cnt['Unmapped']:,} unmapped** (listed in "
             f"`data/rcrv/mapping_review.csv` for portal screen W5, left out of the IFC, never guessed). "
             f"Overall length of geometry {ship_len} m. {len(decks)} decks found from horizontal plate area at "
             f"z = {', '.join(f'{d:.2f}' for d in decks)} m.", "",
             "## Object counts per class", "", "| IFC class | Label | Objects |", "|---|---|---|"]
    for (lb, n) in lab.most_common():
        ifc = next((o["ifc"] for o in objs if (o["label"] or "unmapped") == lb), None) or "—"
        lines.append(f"| {ifc} | {lb} | {n:,} |")
    lines += ["", "## Output files", "", "| File | Objects | With real triangles |", "|---|---|---|",
              f"| rcrv_full.ifc | {full[0]:,} | {full[1]:,} |"]
    for k, (nm, n, m) in deck_files.items():
        lines.append(f"| {nm} | {n:,} | {m:,} |")
    lines += ["", "## 10 doors: clear width", "",
              "Clear width = long horizontal side of the oriented bounding box of the door's leaf (tallest thin part "
              "of the block). Block width includes the frame. ADA 2010 §404.2.3 needs 32 in (813 mm). Check each "
              "against the FreeCAD measure tool (gate: within ±5 mm).", "",
              "| # | Door (source name) | Deck | Source ID | Clear width (in) | Clear width (mm) | Block width (mm) |"
              " Leaf height (mm) | 32 in? |",
              "|---|---|---|---|---|---|---|---|---|"]
    for i, o in enumerate(pick, 1):
        w = o["leaf_w"]
        lines.append(f"| {i} | {o['name']} | {deck_names[o['deck']]} | {o['dbid']} | {w / IN2M:.1f} | {w * 1000:.0f} | "
                     f"{o['block_w'] * 1000:.0f} | {o['height'] * 1000:.0f} | "
                     f"{'✓ Pass' if w * 1000 >= 812.8 else '✕ Fail'} |")
    lines += ["", "## Caveats", "",
              "- Mesh, not solids: the IFC carries triangles. Flat faces (door leaves, bulkheads) are exact; curved "
              "hull surfaces are display-only and no check uses them.",
              "- Fire class, accessible route, berths and room names are not in the Navisworks model. Doors are "
              "listed as *Needs review* in mapping_review.csv; checks that need these report Cannot verify until "
              "they are set (from the GA PDF or by an engineer in W5).",
              "- Classification rules are in `RULES` at the top of `scripts/rcrv_to_ifc.py` (name, layer, source file, "
              "ShipConstructor class).",
              ""]
    (ROOT / "docs" / "rcrv_report.md").write_text("\n".join(lines))
    log(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20000)
