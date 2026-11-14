"""Spike B1, option 2: RCRV glTF -> GLB tiles per (level, discipline group, deck, 8 m slice), straight from the
glTF (no IFC hop). Positions uint16 (KHR_mesh_quantization), element index per vertex (_BATCHID), no normals
(flat shading in the fragment shader). Level 0 = overview (elements >= 1 m with the most size per triangle, up to a triangle budget), level 1 =
detail (the rest). pack.mjs then Meshopt-compresses each tile and checks it decodes back bit-exact.
shortcut: overview = size-per-triangle ranking; the spec's exterior-visibility overview is a step-2 task (docs/PLAN.md)."""
import json, random, struct, sys, time
import numpy as np
from common import GROUP_OF, GROUPS, OUT, Ship

OVERVIEW_TRIS = int(sys.argv[1]) if len(sys.argv) > 1 else 4_000_000
SLICE_M = 8.0
T0 = time.time()
ship = Ship()
els = ship.elements
print(f"loaded {len(els)} elements, {len(ship.nodes)} mesh nodes in {time.time() - T0:.1f}s", flush=True)

for e in els:
    e["tris"] = sum(ship.node_tris(n) for n in e["nodes"])
    b = e["bbox"]
    e["diag"] = float(np.linalg.norm(np.subtract(b[3:], b[:3])))
x_min = min(e["bbox"][0] for e in els)
budget = OVERVIEW_TRIS
# most visible size per triangle first (big plates before dense fittings); nothing under 1 m in the overview
for e in sorted(els, key=lambda e: -e["diag"] ** 2 / max(e["tris"], 1)):
    e["lod"] = 0 if budget > 0 and e["diag"] >= 1.0 else 1
    budget -= e["tris"] if e["lod"] == 0 else 0
ov = [e for e in els if e["lod"] == 0]
print(f"overview: {len(ov)} elements, {sum(e['tris'] for e in ov):,} tris, smallest diagonal {min(e['diag'] for e in ov):.2f} m")
for e in els:
    e["key"] = (e["lod"], GROUP_OF[e["ifc"]], e["deck"], int(((e["bbox"][0] + e["bbox"][3]) / 2 - x_min) // SLICE_M))
els.sort(key=lambda e: (e["key"], e["dbid"]))

random.seed(1)
tests = {id(e) for e in random.sample(els, 60)}
tdir = OUT / "tiles_raw"
tdir.mkdir(parents=True, exist_ok=True)
files, test_out, max_dev, i = [], [], 0.0, 0
while i < len(els):
    j = i
    while j < len(els) and els[j]["key"] == els[i]["key"]:
        j += 1
    assert j - i < 65536, "more than 65,535 elements in one tile: split the cell"
    Vs, Fs, Bs, base = [], [], [], 0
    for local, e in enumerate(els[i:j]):
        ev = []
        for n in e["nodes"]:
            V, F = ship.node_mesh(n)
            Vs.append(V); Fs.append(F.astype(np.uint32) + base); Bs.append(np.full(len(V), local, np.uint16))
            base += len(V)
            ev.append((V, F))
        if id(e) in tests:                      # pick test: look at the largest triangle from close by, both sides
            best = None
            for V, F in ev:
                tri = V[F]
                cr = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
                a = np.linalg.norm(cr, axis=1)
                k = int(a.argmax())
                if a[k] > 0 and (best is None or a[k] > best[0]):
                    best = (float(a[k]), tri[k].mean(0), cr[k] / a[k])
            if best:
                test_out.append({"dbid": e["dbid"], "guid": e["guid"], "name": e["name"], "ifc": e["ifc"],
                                 "c": best[1].round(4).tolist(), "n": best[2].round(5).tolist(),
                                 # camera standoff scales with the triangle: 5 cm would sit inside the neighbour of a bolt
                                 "d": round(min(0.05, max(0.002, 0.3 * best[0] ** 0.5)), 4)})
    V = np.vstack(Vs); F = np.vstack(Fs); B = np.concatenate(Bs)
    lo, hi = V.min(0), V.max(0)
    step = np.maximum(hi - lo, 1e-6) / 65535
    Q = np.rint((V - lo) / step).astype(np.uint16)
    max_dev = max(max_dev, float(np.abs(Q * step + lo - V).max()))
    vb = np.zeros((len(V), 4), np.uint16); vb[:, :3] = Q; vb[:, 3] = B
    binb = vb.tobytes() + F.tobytes()
    lod, grp, deck, sl = els[i]["key"]
    name = f"L{lod}_{GROUPS[grp]}_d{deck}_s{sl}.glb"
    js = {"asset": {"version": "2.0", "generator": "sonariq spike b1"},
          "extensionsUsed": ["KHR_mesh_quantization"], "extensionsRequired": ["KHR_mesh_quantization"],
          "scene": 0, "scenes": [{"nodes": [0]}],
          "nodes": [{"mesh": 0, "translation": lo.astype(float).tolist(), "scale": step.astype(float).tolist()}],
          "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "_BATCHID": 1}, "indices": 2, "mode": 4}]}],
          "buffers": [{"byteLength": len(binb)}],
          "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(V) * 8, "byteStride": 8, "target": 34962},
                          {"buffer": 0, "byteOffset": len(V) * 8, "byteLength": F.size * 4, "target": 34963}],
          "accessors": [{"bufferView": 0, "byteOffset": 0, "componentType": 5123, "count": len(V), "type": "VEC3",
                         "min": [0, 0, 0], "max": Q.max(0).tolist()},
                        {"bufferView": 0, "byteOffset": 6, "componentType": 5123, "count": len(V), "type": "SCALAR"},
                        {"bufferView": 1, "componentType": 5125, "count": F.size, "type": "SCALAR"}]}
    jb = json.dumps(js, separators=(",", ":")).encode()
    jb += b" " * (-len(jb) % 4)
    with open(tdir / name, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(binb)))
        f.write(struct.pack("<I4s", len(jb), b"JSON") + jb + struct.pack("<I4s", len(binb), b"BIN\0") + binb)
    files.append({"f": name, "lod": lod, "group": GROUPS[grp], "deck": deck, "base": i, "n": j - i,
                  "tris": len(F), "verts": len(V), "min": lo.round(3).tolist(), "max": hi.round(3).tolist()})
    i = j

col = np.array([[*(round(c * 255) for c in ship.element_color(e)[:3]), 255] for e in els], np.uint8)
(OUT / "tiles").mkdir(exist_ok=True)
(OUT / "tiles" / "colors.bin").write_bytes(col.tobytes())
json.dump({"groups": GROUPS, "elements": len(els), "max_quantization_dev_mm": round(max_dev * 1000, 4),
           "files": files, "dbid": [e["dbid"] for e in els]}, open(OUT / "tiles" / "index.json", "w"),
          separators=(",", ":"))
json.dump([[e["dbid"], e["guid"], e["ifc"], e["name"]] for e in els], open(OUT / "tiles" / "elements.json", "w"),
          separators=(",", ":"))
json.dump(test_out, open(OUT / "tests.json", "w"), indent=0)
print(json.dumps({"seconds": round(time.time() - T0, 1), "files": len(files),
                  "tris": sum(f["tris"] for f in files), "verts": sum(f["verts"] for f in files),
                  "overview_tris": sum(f["tris"] for f in files if f["lod"] == 0),
                  "max_quantization_dev_mm": round(max_dev * 1000, 4), "tests": len(test_out)}))
