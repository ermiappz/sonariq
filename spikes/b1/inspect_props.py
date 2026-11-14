"""Stream data/rcrv/gltf/properties.jsonl once: which property keys exist, with value samples (grounds B2/B3),
and compact parent / class arrays for prep.py. Output goes to data/rcrv/spike_b1/ (not in git: real-ship data)."""
import collections, json, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data/rcrv/gltf/properties.jsonl"
OUT = ROOT / "data/rcrv/spike_b1"
CLS_KEY = "LcOaNode:LcOaSceneBaseClassUserName"
MAXV = 400   # distinct values kept per key

t = time.time()
parents, cls_codes, cls_names = [0], [0], {None: 0}
keys = collections.Counter()                 # (category, key) -> records carrying it
vals = collections.defaultdict(collections.Counter)
by_cls = collections.defaultdict(collections.Counter)  # class -> (category,key) counts
names_by_cls = collections.defaultdict(list)
n = 0
with open(SRC) as f:
    for line in f:
        o = json.loads(line)
        i = o["dbid"]
        while len(parents) <= i:
            parents.append(0); cls_codes.append(0)
        parents[i] = o["parent"] or 0
        c = None
        for cat, k, v in o["props"]:
            ck = f"{cat}|{k}"
            keys[ck] += 1
            vc = vals[ck]
            v = str(v)[:120]
            if v in vc or len(vc) < MAXV:
                vc[v] += 1
            if k == CLS_KEY:
                c = v
        cls_codes[i] = cls_names.setdefault(c, len(cls_names))
        for cat, k, v in o["props"]:
            by_cls[c][f"{cat}|{k}"] += 1
        if len(names_by_cls[c]) < 8:
            names_by_cls[c].append(o["name"])
        n += 1
OUT.mkdir(parents=True, exist_ok=True)
np.save(OUT / "parents.npy", np.array(parents, dtype=np.int32))
np.save(OUT / "cls.npy", np.array(cls_codes, dtype=np.int16))
cls_count = collections.Counter(cls_codes)
json.dump({
    "records": n, "seconds": round(time.time() - t, 1),
    "classes": {str(c): {"code": k, "count": cls_count[k], "names": names_by_cls[c],
                         "keys": dict(by_cls[c].most_common(60))} for c, k in cls_names.items()},
    "keys": {k: {"count": c, "distinct_kept": len(vals[k]), "top": vals[k].most_common(25)}
             for k, c in keys.most_common()},
}, open(OUT / "props_stats.json", "w"), indent=1)
print("records", n, "keys", len(keys), "classes", len(cls_names), f"{time.time() - t:.0f}s")
