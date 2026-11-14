"""Shared by to_tiles.py and to_ifc.py: load the RCRV glTF, group mesh nodes into elements exactly as
scripts/rcrv_to_ifc.py does (same owner rule, same GlobalId), and read mesh data from the .bin files."""
import json, sqlite3, sys, uuid
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from rcrv_to_ifc import CONTAINER_CLS, GEOM_CLS, IN2M, NS, node_xform  # noqa: E402  (reuse, do not copy)
import ifcopenshell.guid  # noqa: E402

RC = ROOT / "data" / "rcrv"
OUT = RC / "spike_b1"
GROUPS = ["structure", "architecture", "hvac", "piping", "electrical", "equipment", "other"]
GROUP_OF = {"IfcPlate": 0, "IfcMember": 0, "IfcWall": 1, "IfcDoor": 1, "IfcWindow": 1, "IfcStair": 1, "IfcRailing": 1,
            "IfcFurnishingElement": 1, "IfcCovering": 1, "IfcDuctSegment": 2, "IfcPipeSegment": 3,
            "IfcCableCarrierSegment": 4, "IfcBuildingElementProxy": 5, None: 6}


def guid_of(dbid):
    return ifcopenshell.guid.compress(uuid.uuid5(NS, str(dbid)).hex)


class Ship:
    def __init__(self):
        gp = next((RC / "gltf").glob("*/output.gltf"))
        g = json.loads(gp.read_text())
        self.dir = gp.parent
        self.bufs = [np.memmap(self.dir / b["uri"], dtype=np.uint8, mode="r") for b in g["buffers"]]
        bv = g["bufferViews"]
        acc = g["accessors"]
        self.acc = [(bv[a["bufferView"]]["buffer"], bv[a["bufferView"]].get("byteOffset", 0) + a.get("byteOffset", 0),
                     a["count"]) for a in acc]
        self.mesh = [(m["primitives"][0]["attributes"]["POSITION"], m["primitives"][0]["indices"],
                      m["primitives"][0].get("material", 0)) for m in g["meshes"]]   # all meshes: 1 primitive, u16 idx
        self.colors = [m["pbrMetallicRoughness"].get("baseColorFactor", [0.7, 0.7, 0.7, 1]) for m in g["materials"]]
        parents = np.load(OUT / "parents.npy")
        cls = np.load(OUT / "cls.npy")
        stats = json.load(open(OUT / "props_stats.json"))
        code_name = {v["code"]: (None if k == "None" else k) for k, v in stats["classes"].items()}
        geom = np.array([code_name[c] in GEOM_CLS for c in range(len(code_name))])
        cont = np.array([code_name[c] in CONTAINER_CLS for c in range(len(code_name))])
        plate = np.array([code_name[c] in ("Plate", "Standard Plate", "Stiffener") for c in range(len(code_name))])
        self.nodes = []          # (mesh, A 3x3, t 3, owner dbid)
        owners = {}
        for n in g["nodes"]:
            if "mesh" not in n:
                continue
            dbid = int(n["name"])
            owner, j = dbid, dbid
            while j:                                   # same walk as rcrv_to_ifc.main step 1
                c = cls[j]
                if cont[c]:
                    break
                owner = j
                if not geom[c] and (j != dbid or plate[c]):
                    break
                j = parents[j]
            A, t = node_xform(n)
            owners.setdefault(owner, []).append(len(self.nodes))
            self.nodes.append((n["mesh"], (A * IN2M).astype(np.float32), (t * IN2M).astype(np.float32)))
        db = sqlite3.connect(RC / "properties.sqlite")
        self.elements = []       # dict(dbid, guid, name, ifc, deck, bbox, nodes)
        for dbid, name, ifc, deck, *bb in db.execute(
                "select dbid,name,ifc_class,deck,x0,y0,z0,x1,y1,z1 from objects order by dbid"):
            self.elements.append({"dbid": dbid, "guid": guid_of(dbid), "name": name, "ifc": ifc,
                                  "deck": int(deck.split()[-1]), "bbox": bb, "nodes": owners[dbid]})
        del g

    def node_mesh(self, ni):
        """World-space (IFC frame: metres, Z up) vertices float32 (n,3) and triangle indices (m,3) of one node."""
        mi, A, t = self.nodes[ni]
        pa, ia, _ = self.mesh[mi]
        b, off, cnt = self.acc[pa]
        V = np.frombuffer(self.bufs[b], dtype="<f4", count=cnt * 3, offset=off).reshape(cnt, 3) @ A.T + t
        b, off, cnt = self.acc[ia]
        F = np.frombuffer(self.bufs[b], dtype="<u2", count=cnt, offset=off).reshape(-1, 3)
        return V, F

    def node_tris(self, ni):
        return self.acc[self.mesh[self.nodes[ni][0]][1]][2] // 3

    def element_color(self, e):
        return self.colors[self.mesh[self.nodes[e["nodes"][0]][0]][2]]
