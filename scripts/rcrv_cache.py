"""Build a compact cache of the RCRV property tree (names, parents, class, layer, key props) for rcrv_to_ifc.py."""
import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
G = ROOT / "data" / "rcrv" / "gltf"
KEEP = {"LcOaNode:LcOaSceneBaseClassUserName": "cls", "LcOaNode:LcOaNodeSourceFile": "src",
        "LcOaNode:LcOaNodeGuid": "nguid", "ShipConstructor:PartName[0]": "part",
        "ShipConstructor:StockName[0]": "stock", "ShipConstructor:StockDescription[0]": "stockdesc",
        "ShipConstructor:ProfileStandardTypeName[0]": "proftype", "ShipConstructor:AssemblyFullName[0]": "assy",
        "ShipConstructor:PartGUID[0]": "pguid", "ShipConstructor:Material[0]": "mat",
        "LcOaNode:LcOaNodeMaterial": "nmat"}


def build():
    names, parents, props = [None], [0], {}
    with open(G / "properties.jsonl") as f:
        for line in f:
            o = json.loads(line)
            i = o["dbid"]
            while len(names) <= i:
                names.append(None); parents.append(0)
            names[i] = o["name"]
            parents[i] = o["parent"] or 0
            kp = {}
            for c, k, v in o["props"]:
                if k in KEEP:
                    kp[KEEP[k]] = v
                elif c not in ("Item", "Entity Handle", "ShipConstructor", "Summary") and len(kp) < 40:
                    kp.setdefault("other", []).append((c, k, v))
            if kp:
                props[i] = kp
    with open(G / "props_cache.pkl", "wb") as f:
        pickle.dump({"names": names, "parents": parents, "props": props}, f, protocol=5)
    print("objects", len(names))


if __name__ == "__main__":
    build()
