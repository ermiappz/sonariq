"""Convert one model to web tiles: source -> raw tiles + ID map + metadata index -> Meshopt pack with integrity check.

    python -m sonariq.pipeline.build <file.ifc | rcrv> <out dir>
"""
from __future__ import annotations

import collections
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .disciplines import disciplines
from .tiles import write_tiles

ROOT = Path(__file__).resolve().parents[3]
PACK = ROOT / "scripts" / "node" / "pack_tiles.mjs"
RCRV = ROOT / "data" / "rcrv"
MISSING = ("The 3D converter is not available on this server: Node.js was not found. The findings still work; "
           "an administrator can install Node.js 18 or newer, or set SONARIQ_NODE_BIN, and restart the engine.")
PACKAGES = ("The 3D converter is not ready on this server: its packages are not installed. The findings still work; an "
            "administrator can run `npm ci` in scripts/node and restart the engine.")
_NODE: dict = {}


def converter() -> dict:
    """Resolve the Node binary once: SONARIQ_NODE_BIN, else `node` on PATH. {state: ok|missing, bin, version, message}."""
    if not _NODE:
        b = os.getenv("SONARIQ_NODE_BIN") or shutil.which("node")
        v = None
        if b:
            try:
                v = subprocess.run([b, "--version"], capture_output=True, text=True, timeout=10).stdout.strip() or None
            except (OSError, subprocess.SubprocessError):
                v = None
        if not v:
            _NODE.update({"state": "missing", "bin": b, "message": MISSING})
        else:   # Node alone is not enough: the packer needs its npm packages (scripts/node, gitignored)
            try:
                ok = subprocess.run([b, "--input-type=module", "-e", "await import('meshoptimizer')"], cwd=PACK.parent,
                                    capture_output=True, timeout=20).returncode == 0
            except (OSError, subprocess.SubprocessError):
                ok = False
            _NODE.update({"state": "ok", "bin": b, "version": v} if ok else
                         {"state": "missing", "bin": b, "version": v, "message": PACKAGES})
        logging.getLogger("sonariq").warning("3D converter: %s", f"node {v} at {b}, {_NODE['state']}" if v else f"missing ({b or 'not on PATH'})")
    return dict(_NODE)


def build(source: str | Path, out: Path, progress=lambda f, msg="": None) -> dict:
    t0 = time.time()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    node = converter()
    if node["state"] != "ok":
        raise RuntimeError(node["message"])
    progress(0.01, "Reading the model")
    if str(source) == "rcrv":
        from .rcrv_source import RcrvSource
        src = RcrvSource(RCRV / "gltf", RCRV / "properties.sqlite", progress=lambda f: progress(f * 0.5, "Reading the model"))
        aliases, kind, schema = {}, "rcrv-gltf", "glTF 2.0 (Navisworks via APS)"
    else:
        from .ifc_source import IfcSource
        src = IfcSource(Path(source), progress=lambda f: progress(f * 0.5, "Reading the model"))
        aliases, kind, schema = src.aliases, "ifc", src.schema
    t_read = time.time() - t0
    progress(0.5, "Writing tiles")
    index = write_tiles(src.elements, src.meshes, out, disciplines(),
                        progress=lambda f: progress(0.5 + f * 0.35, "Writing tiles"))
    progress(0.85, "Compressing tiles")
    r = subprocess.run([node["bin"], str(PACK), str(out / "raw"), str(out / "tiles")], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"tile packing failed: {(r.stderr or r.stdout)[-400:]}")
    pack = json.loads(r.stdout.strip().splitlines()[-1])
    shutil.rmtree(out / "raw")
    meta = json.loads((out / "meta.json").read_text())
    disc = collections.Counter(m.get("discipline", "other") for m in meta)
    index.update({"kind": kind, "schema": schema, "aliases": aliases, "disciplines": dict(disc),
                  "other": disc.get("other", 0), "unmapped": sum(1 for m in meta if not m.get("mapped", True)),
                  "bytes": pack["packed"], "integrity": {"vertex_mismatch": pack["vertexMismatch"],
                                                         "triangle_mismatch": pack["triangleMismatch"]},
                  "seconds": {"read": round(t_read, 1), "total": round(time.time() - t0, 1)}})
    (out / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    progress(1.0, "Ready")
    return index


if __name__ == "__main__":
    ix = build(sys.argv[1], Path(sys.argv[2]), progress=lambda f, m="": print(f"{f:5.0%} {m}", flush=True))
    print(json.dumps({k: v for k, v in ix.items() if k not in ("files", "aliases")}, indent=1))
