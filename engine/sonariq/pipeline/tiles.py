"""Element meshes -> web tiles (DECISIONS M3, M4). From spikes/b1/to_tiles.py, made source-independent.

Writes into `out`:
  raw/<L>_<group>_d<deck>_s<slice>.glb  uint16-quantised positions (KHR_mesh_quantization) + element index per vertex
  index.json     tiles with level, group, deck, element range, triangles, box; whole-model box
  elements.json  index -> [stable_id, source_id, ifc_class, name]   (the ID map the viewer picks into)
  colors.bin     rgba per element (a = 255 shown, 0 hidden by default)
  meta.json      per element (same order): deck, discipline, SWBS, material, thickness, grade, fire rating, bbox ...
`scripts/node/pack_tiles.mjs` then Meshopt-compresses raw/ into tiles/ and checks every tile decodes back exactly.
Coordinates: the engine's frame (metres, Z up), so evidence boxes from findings draw without a transform.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

SLICE_M = 8.0
OVERVIEW_TRIS = 4_000_000
MAX_PER_TILE = 65_535          # element index is uint16 inside a tile

Mesh = tuple[np.ndarray, np.ndarray]   # V (n,3) float32 metres, F (m,3) int


def _glb(V: np.ndarray, F: np.ndarray, B: np.ndarray) -> tuple[bytes, list, list, float]:
    lo, hi = V.min(0), V.max(0)
    step = np.maximum(hi - lo, 1e-6) / 65535
    Q = np.rint((V - lo) / step).astype(np.uint16)
    dev = float(np.abs(Q * step + lo - V).max())
    vb = np.zeros((len(V), 4), np.uint16)
    vb[:, :3] = Q
    vb[:, 3] = B
    binb = vb.tobytes() + F.astype(np.uint32).tobytes()
    js = {"asset": {"version": "2.0", "generator": "sonariq tiles"},
          "extensionsUsed": ["KHR_mesh_quantization"], "extensionsRequired": ["KHR_mesh_quantization"],
          "scene": 0, "scenes": [{"nodes": [0]}],
          "nodes": [{"mesh": 0, "translation": lo.astype(float).tolist(), "scale": step.astype(float).tolist()}],
          "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "_BATCHID": 1}, "indices": 2, "mode": 4}]}],
          "buffers": [{"byteLength": len(binb)}],
          "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(V) * 8, "byteStride": 8, "target": 34962},
                          {"buffer": 0, "byteOffset": len(V) * 8, "byteLength": F.size * 4, "target": 34963}],
          "accessors": [{"bufferView": 0, "byteOffset": 0, "componentType": 5123, "count": len(V), "type": "VEC3",
                         "min": [0, 0, 0], "max": Q.max(0).astype(int).tolist()},
                        {"bufferView": 0, "byteOffset": 6, "componentType": 5123, "count": len(V), "type": "SCALAR"},
                        {"bufferView": 1, "componentType": 5125, "count": int(F.size), "type": "SCALAR"}]}
    jb = json.dumps(js, separators=(",", ":")).encode()
    jb += b" " * (-len(jb) % 4)
    head = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(binb))
    return (head + struct.pack("<I4s", len(jb), b"JSON") + jb + struct.pack("<I4s", len(binb), b"BIN\0") + binb,
            lo.round(3).tolist(), hi.round(3).tolist(), dev)


def write_tiles(elements: list[dict], meshes: Callable[[dict], Iterable[Mesh]], out: Path,
                groups: list[str], overview_tris: int = OVERVIEW_TRIS, progress: Callable[[float], None] | None = None) -> dict:
    """elements: dicts with id, src, cls, name, deck (int), group (in `groups`), color (r,g,b 0-255), hidden (bool),
    bbox [x0,y0,z0,x1,y1,z1], tris (int). meshes(e) yields that element's world-space triangles."""
    out = Path(out)
    (out / "raw").mkdir(parents=True, exist_ok=True)
    els = [e for e in elements if e["tris"] > 0]
    if not els:
        raise ValueError("no element has geometry")
    for e in els:
        b = e["bbox"]
        e["_diag"] = float(np.linalg.norm(np.subtract(b[3:], b[:3])))
    x_min = min(e["bbox"][0] for e in els)
    budget = overview_tris
    # biggest visible size per triangle first; small parts (< 1 m) go to detail unless the whole model fits
    small_model = sum(e["tris"] for e in els) <= overview_tris
    for e in sorted(els, key=lambda e: -e["_diag"] ** 2 / max(e["tris"], 1)):
        e["_lod"] = 0 if small_model or (budget > 0 and e["_diag"] >= 1.0) else 1
        budget -= e["tris"] if e["_lod"] == 0 else 0
    for e in els:
        e["_key"] = (e["_lod"], groups.index(e["group"]), int(e["deck"]),
                     int(((e["bbox"][0] + e["bbox"][3]) / 2 - x_min) // SLICE_M))
    els.sort(key=lambda e: (e["_key"], str(e["id"])))
    files, max_dev, i = [], 0.0, 0
    while i < len(els):
        j = i
        while j < len(els) and els[j]["_key"] == els[i]["_key"] and j - i < MAX_PER_TILE:
            j += 1
        Vs, Fs, Bs, base = [], [], [], 0
        for local, e in enumerate(els[i:j]):
            for V, F in meshes(e):
                if not len(F):
                    continue
                Vs.append(np.asarray(V, np.float32))
                Fs.append(np.asarray(F, np.uint32) + base)
                Bs.append(np.full(len(V), local, np.uint16))
                base += len(V)
        lod, grp, deck, sl = els[i]["_key"]
        if Vs:
            V, F, B = np.vstack(Vs), np.vstack(Fs), np.concatenate(Bs)
            data, lo, hi, dev = _glb(V, F, B)
            max_dev = max(max_dev, dev)
            name = f"L{lod}_{groups[grp]}_d{deck}_s{sl}_{i}.glb"
            (out / "raw" / name).write_bytes(data)
            files.append({"f": name, "lod": lod, "group": groups[grp], "deck": deck, "base": i, "n": j - i,
                          "tris": int(len(F)), "verts": int(len(V)), "min": lo, "max": hi})
        if progress:
            progress(j / len(els))
        i = j
    col = np.array([[*e["color"][:3], 0 if e.get("hidden") else 255] for e in els], np.uint8)
    (out / "colors.bin").write_bytes(col.tobytes())
    lo = np.min([f["min"] for f in files], 0).tolist()
    hi = np.max([f["max"] for f in files], 0).tolist()
    index = {"version": 1, "groups": groups, "elements": len(els), "box": [lo, hi],
             "max_quantization_dev_mm": round(max_dev * 1000, 4), "files": files,
             "tris": sum(f["tris"] for f in files), "overview_tris": sum(f["tris"] for f in files if f["lod"] == 0)}
    (out / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    (out / "meta.json").write_text(json.dumps([e.get("meta", {}) for e in els], separators=(",", ":")))
    (out / "elements.json").write_text(json.dumps([[e["id"], e.get("src"), e["cls"], e["name"]] for e in els],
                                                  separators=(",", ":")))
    return index
