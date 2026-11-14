"""Pre-convert every bundled model to web tiles (deploy step), so no visitor waits for a conversion.

    PYTHONPATH=engine:. python scripts/preconvert.py

Cached by content hash (data/models/<sha16>/); a model whose status is already "ready" is skipped. The RCRV whole
ship has the fixed id "rcrv" and is converted only when data/rcrv exists. Exits 1 if any model fails.
"""
from __future__ import annotations

import sys
import time

from sonariq import models_api as m
from sonariq.pipeline.build import converter
from sonariq.session import REVISIONS

node = converter()
print(f"converter: {node['state']} {node.get('version') or node.get('message')}")
if node["state"] != "ok":
    sys.exit(1)
jobs = [(m._store(p.read_bytes(), p.name), p.name) for p in REVISIONS.values() if p.exists()]
if (m.RCRV / "gltf").exists() and (m.RCRV / "properties.sqlite").exists():
    jobs.append(("rcrv", "RCRV whole ship"))
bad = 0
for mid, name in jobs:
    if m.status(mid).get("state") == "ready":
        print(f"  {name:28} {mid}  cached")
        continue
    t0 = time.time()
    m._run(mid, "rcrv" if mid == "rcrv" else str(m.MODELS / mid / "original.ifc"))
    st = m.status(mid)
    print(f"  {name:28} {mid}  {st['state']} in {time.time() - t0:.0f} s {'' if st['state'] == 'ready' else st.get('message')}")
    bad += st["state"] != "ready"
sys.exit(1 if bad else 0)
