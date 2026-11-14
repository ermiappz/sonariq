"""One-off: what is in the RCRV glTF (counts, instancing, triangles). Prints JSON."""
import collections, json, sys, time
from pathlib import Path
t = time.time()
p = next(Path("data/rcrv/gltf").glob("*/output.gltf"))
g = json.loads(p.read_text())
acc, nodes, meshes = g["accessors"], g["nodes"], g["meshes"]
out = {k: len(v) for k, v in g.items() if isinstance(v, list)}
out["scene_roots"] = len(g["scenes"][0]["nodes"])
out["nodes_with_children"] = sum("children" in n for n in nodes)
out["node_keys"] = collections.Counter(k for n in nodes for k in n)
out["prim_modes"] = collections.Counter(pr.get("mode", 4) for m in meshes for pr in m["primitives"])
out["prim_attrs"] = collections.Counter(a for m in meshes for pr in m["primitives"] for a in pr["attributes"])
out["prims_per_mesh"] = collections.Counter(len(m["primitives"]) for m in meshes)
out["idx_types"] = collections.Counter(acc[pr["indices"]]["componentType"] for m in meshes for pr in m["primitives"] if "indices" in pr)
out["pos_types"] = collections.Counter(acc[pr["attributes"]["POSITION"]]["componentType"] for m in meshes for pr in m["primitives"])
tri = [sum(acc[pr["indices"]]["count"] // 3 for pr in m["primitives"] if pr.get("mode", 4) == 4 and "indices" in pr) for m in meshes]
vtx = [sum(acc[pr["attributes"]["POSITION"]]["count"] for pr in m["primitives"]) for m in meshes]
use = collections.Counter(n["mesh"] for n in nodes if "mesh" in n)
out["unique_mesh_tris"] = sum(tri); out["unique_mesh_verts"] = sum(vtx)
out["instanced_tris"] = sum(tri[m] * c for m, c in use.items())
out["instanced_verts"] = sum(vtx[m] * c for m, c in use.items())
out["meshes_used"] = len(use); out["max_instances"] = max(use.values())
out["tris_in_meshes_used_once"] = sum(tri[m] for m, c in use.items() if c == 1)
out["materials_sample"] = g["materials"][:3]
out["node_sample"] = [n for n in nodes if "mesh" in n][:2]
out["root_sample"] = nodes[g["scenes"][0]["nodes"][0]] if len(str(nodes[g["scenes"][0]["nodes"][0]])) < 500 else "big"
out["bufferView_sample"] = g["bufferViews"][:3]; out["accessor_sample"] = acc[:3]
out["load_s"] = round(time.time() - t, 1)
import resource; out["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
print(json.dumps(out, indent=1, default=str))
