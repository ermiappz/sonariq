"""Spike step 3: what can rules read on the RCRV? Joins the 90,331 engine objects (properties.sqlite) with the raw
Navisworks properties (properties.jsonl): ShipConstructor part data on structure, DWG block attributes on pipes.
Output: data/rcrv/spike_b1/readiness_stats.json (not in git: real-ship data). Grounds B2/B3 in docs/DECISIONS.md."""
import collections, json, re, sqlite3, time
import numpy as np
from common import OUT, RC

T0 = time.time()
SC = "ShipConstructor:"
WANT = {SC + "StockThickness[0]": "thk", SC + "StockMaterialName[0]": "mat", SC + "V1[0]": "v1",
        SC + "PartGUID[0]": "pguid", SC + "Weight[0]": "weight", SC + "StockDescription[0]": "desc"}
MATERIAL = re.compile(r"ASTM|ASME SB|UNS|COPPER|STEEL|STAINLESS|BRONZE|BRASS|CUNI|CU-NI|PVC|CPVC|RUBBER|HDPE|"
                      r"ALUMIN|TITANIUM|FRP|GRP|NYLON|PTFE|EPDM|IRON", re.I)
sc, attrs = {}, {}
with open(RC / "gltf" / "properties.jsonl") as f:
    for line in f:
        if "ShipConstructor" not in line and '"Attributes"' not in line:
            continue
        o = json.loads(line)
        d = {WANT[k]: v for _, k, v in o["props"] if k in WANT}
        if d:
            sc[o["dbid"]] = d
        a = [v for c, _, v in o["props"] if c == "Attributes"]
        if a:
            attrs[o["dbid"]] = a
parents = np.load(OUT / "parents.npy")


def up(dbid, table, levels=5):
    """Nearest self-or-ancestor of dbid that has an entry in table."""
    for _ in range(levels):
        if dbid in table:
            return table[dbid]
        dbid = int(parents[dbid])
        if not dbid:
            break
    return None


db = sqlite3.connect(RC / "properties.sqlite")
out = {"objects": 0, "by_class": {}, "plate_grade": collections.Counter(), "plate_thickness": collections.Counter(),
       "plate_grade_x_thickness": collections.Counter(), "swbs_v1": collections.Counter(),
       "pipe_system": collections.Counter(), "pipe_material": collections.Counter(),
       "fuel_pipe_material": collections.Counter(), "attr_count": collections.Counter(),
       "door_names": collections.Counter(), "error_values": collections.Counter()}
for dbid, name, layer, ifc, label in db.execute("select dbid,name,layer,ifc_class,label from objects"):
    out["objects"] += 1
    c = out["by_class"].setdefault(f"{ifc}/{label}", collections.Counter())
    c["n"] += 1
    s = up(dbid, sc, 2)
    if s:
        c["shipconstructor"] += 1
        for k in ("thk", "mat", "v1", "pguid", "weight"):
            c[k] += k in s and s[k] not in ("", "<None>", "N/A")
        for v in s.values():
            if str(v).strip() in ("Error", "---", "<None>", "TBD"):
                out["error_values"][str(v).strip()] += 1
        if "v1" in s and re.fullmatch(r"\d{3,4}", s["v1"]):
            c["swbs"] += 1
            out["swbs_v1"][s["v1"]] += 1
    if ifc == "IfcPlate" and s:
        out["plate_grade"][s.get("mat", "(none)")] += 1
        out["plate_thickness"][s.get("thk", "(none)")] += 1
        out["plate_grade_x_thickness"][f"{s.get('mat')} | {s.get('thk')}"] += 1
    if ifc == "IfcPipeSegment":
        a = up(dbid, attrs)
        if a:
            c["attributes"] += 1
            out["attr_count"][len(a)] += 1
            out["pipe_system"][a[0]] += 1
            m = next((v for v in a[2:] if MATERIAL.search(v) and len(v) < 40), None)   # a[2] is the long description
            m = next((v for v in a[3:] if MATERIAL.search(v) and len(v) < 40), None) or "(no material value)"
            c["material"] += m != "(no material value)"
            out["pipe_material"][m] += 1
            if re.search(r"FUEL|\bF\.?O\b|DIESEL|LUBE|\bL\.?O\b|HYDRAULIC|OILY", a[0] + " " + (layer or ""), re.I):
                out["fuel_pipe_material"][f"{a[0]} | {m}"] += 1
        else:
            out["pipe_system"][f"(no attributes) layer={layer}"[:60]] += 1
    if ifc == "IfcDoor":
        out["door_names"][re.sub(r"[-(].*", "", name).strip()[:40]] += 1
res = {k: (dict(v.most_common(80)) if isinstance(v, collections.Counter) else v) for k, v in out.items()}
res["by_class"] = {k: dict(v) for k, v in out["by_class"].items()}
res["seconds"] = round(time.time() - T0, 1)
json.dump(res, open(OUT / "readiness_stats.json", "w"), indent=1)
print(json.dumps(res["by_class"], indent=0))
