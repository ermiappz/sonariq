"""Model pipeline API (spec A1, DECISIONS M1-M4): store the original untouched, convert once in the background to web
tiles, cache by content hash, serve tiles with long cache headers. The engine's analysis never reads tiles.

  POST /models?name=<file>      body = IFC (IFC2x3 / IFC4 / IFC4x3) bytes -> {id, state}
  POST /models/prepare          {revision | path | run | source: "rcrv"}  -> {id, state}  (a file the engine already has)
  GET  /models/{id}             -> status: state queued|running|ready|error, progress 0-1, message, summary
  GET  /models/{id}/files/<p>   index.json | elements.json | meta.json | colors.bin | tiles/<name>.glb
  GET|PUT /models/{id}/grid     frame grid for the section blade (DECISIONS M6): frame zero x and spacing
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .session import DATA

MODELS = DATA / "models"
RCRV = DATA / "rcrv"
router = APIRouter()
_POOL = ThreadPoolExecutor(max_workers=1)        # one conversion at a time: RCRV peaks at several GB
_LOCK = threading.Lock()
_ACTIVE: set[str] = set()                        # ids queued or converting in this process
_FILE = re.compile(r"^(index\.json|elements\.json|meta\.json|colors\.bin|tiles/[A-Za-z0-9_.-]+\.glb)$")
_ID = re.compile(r"^(rcrv|[0-9a-f]{16})$")


def _status_path(mid: str) -> Path:
    return MODELS / mid / "status.json"


def status(mid: str) -> dict:
    p = _status_path(mid)
    return json.loads(p.read_text()) if p.exists() else {"id": mid, "state": "missing"}


def _write_status(mid: str, **kw) -> None:
    d = status(mid) if _status_path(mid).exists() else {"id": mid}
    d.update(kw)
    p = _status_path(mid)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d))
    tmp.replace(p)


def _run(mid: str, source: str) -> None:
    from .pipeline.build import build
    out = MODELS / mid / "web"
    try:
        _write_status(mid, state="running", progress=0.0, message="Preparing a fast web version")
        shutil.rmtree(out, ignore_errors=True)
        ix = build(source, out, progress=lambda f, m="": _write_status(mid, progress=round(f, 3),
                                                                      message=f"Preparing a fast web version · {m}"))
        summary = {k: ix[k] for k in ("elements", "tris", "bytes", "kind", "schema", "disciplines", "other", "unmapped",
                                      "integrity", "seconds", "max_quantization_dev_mm", "box")}
        _write_status(mid, state="ready", progress=1.0, message="Ready", summary=summary)
    except Exception as e:  # noqa: BLE001  (shown to the user; the original file stays untouched)
        from .pipeline.build import MISSING, PACKAGES
        _write_status(mid, state="error", message=str(e) if str(e) in (MISSING, PACKAGES) else f"Could not prepare the 3D version of this model: {str(e)[:300]}")
    finally:
        _ACTIVE.discard(mid)


def ensure(mid: str, source: str, convert: bool = True) -> dict:
    """Start a conversion unless it is ready or already queued. Cache = the content hash in the id.
    convert=False (the demo) never starts one: a model that is not ready reports state "not-prepared"."""
    with _LOCK:
        st = status(mid)
        if st["state"] == "ready" or mid in _ACTIVE:   # a "running" left by a restarted engine is started again
            return st
        if not convert:
            return {"id": mid, "state": "not-prepared", "message": "This model's 3D version is not prepared on the server yet."}
        _ACTIVE.add(mid)
        _write_status(mid, state="queued", progress=0.0, message="Preparing a fast web version")
        _POOL.submit(_run, mid, source)
        return status(mid)


def _store(data: bytes, name: str) -> str:
    mid = hashlib.sha256(data).hexdigest()[:16]
    d = MODELS / mid
    d.mkdir(parents=True, exist_ok=True)
    orig = d / ("original" + (Path(name).suffix.lower() or ".ifc"))
    if not orig.exists():
        tmp = orig.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(orig)            # the original is written once and never changed
        (d / "name.txt").write_text(Path(name).name[:120])
    return mid


def prepare_file(p: Path, convert: bool = True) -> dict:
    mid = _store(p.read_bytes(), p.name)
    return ensure(mid, str(MODELS / mid / ("original" + p.suffix.lower())), convert)


@router.post("/models")
async def upload_model(request: Request, name: str = "model.ifc"):
    body = await request.body()
    import os
    limit_mb = int(os.getenv("SONARIQ_UPLOAD_MB", "400"))
    if len(body) > limit_mb * 1024 * 1024:
        raise HTTPException(413, f"File larger than {limit_mb} MB.")
    if not body.startswith(b"ISO-10303-21"):
        raise HTTPException(422, "Not an IFC (STEP) file. glTF/GLB upload is not supported yet (docs/PROGRESS.md).")
    m = re.search(rb"FILE_SCHEMA\s*\(\s*\(\s*'([A-Za-z0-9_]+)'", body[:4096])
    if m and not m.group(1).upper().startswith((b"IFC2X3", b"IFC4")):
        raise HTTPException(422, f"Schema {m.group(1).decode()} is not supported; IFC2x3, IFC4 and IFC4x3 are.")
    mid = _store(body, name)
    return {**ensure(mid, str(MODELS / mid / "original.ifc")), "id": mid}


class PrepareReq(BaseModel):
    revision: str | None = None
    path: str | None = None
    run: str | None = None
    source: str | None = None
    convert: bool = True          # False: only report the cached version, never start a conversion (demo)


@router.post("/models/prepare")
def prepare(req: PrepareReq):
    from . import api
    if req.source == "rcrv":
        if not (RCRV / "gltf").exists() or not (RCRV / "properties.sqlite").exists():
            raise HTTPException(404, "The RCRV model is not on this engine (data/rcrv is not in git; see README).")
        return {**ensure("rcrv", "rcrv", req.convert), "id": "rcrv"}
    if req.run:
        d = api._load_run(req.run)
        if d.get("revision") == "RCRV":
            return prepare(PrepareReq(source="rcrv", convert=req.convert))
        p = api._run_file(d)
    elif req.revision:
        p = api.REVISIONS.get(req.revision)
    else:
        p = Path(api._check_path(req.path)) if req.path else None
    if p is None or not api._owned(p):
        raise HTTPException(404, "no such model on the engine")
    return prepare_file(p, req.convert)


@router.get("/models/{mid}")
def model_status(mid: str):
    if not _ID.match(mid):
        raise HTTPException(404, "no such model")
    st = status(mid)
    if st["state"] == "missing":
        raise HTTPException(404, "no such model")
    return st


_META: dict[str, list] = {}


def _meta(mid: str) -> list:
    if mid not in _META:
        p = MODELS / mid / "web" / "meta.json"
        if not p.exists():
            raise HTTPException(404, "no such model")
        if len(_META) > 4:
            _META.pop(next(iter(_META)))
        _META[mid] = json.loads(p.read_text())
    return _META[mid]


@router.get("/models/{mid}/elements/{index}")
def model_element(mid: str, index: int):
    """Properties card: one element's metadata (meta.json is tens of MB on a whole ship, so it stays on the server)."""
    if not _ID.match(mid):
        raise HTTPException(404, "no such model")
    meta = _meta(mid)
    if not 0 <= index < len(meta):
        raise HTTPException(404, "no such element")
    return meta[index]


COLUMNS = {"fire_rating", "swbs", "deck", "discipline", "material", "grade", "system"}


@router.get("/models/{mid}/column/{field}")
def model_column(mid: str, field: str):
    """One metadata field for every element, in tile order (View pane: colour by fire class, SWBS ...)."""
    if not _ID.match(mid) or field not in COLUMNS:
        raise HTTPException(404, "no such column")
    return [m.get(field) for m in _meta(mid)]


_SPACING = re.compile(rb"IFCPROPERTYSINGLEVALUE\('frame_spacing_m',\$,IFCREAL\(([0-9.eE+-]+)\)")


def _default_grid(mid: str) -> dict:
    """Frames as the engine counts them (checks.py: frame = x / spacing): IFC -> frame 0 at x = 0, spacing from the
    SonarIQ_Ship pset (engine default 0.8 m); RCRV has no frame grid -> metres from the aft end (rcrv_model.py)."""
    ix = MODELS / mid / "web" / "index.json"
    if not ix.exists():
        raise HTTPException(404, "no such model")
    box = json.loads(ix.read_text())["box"]
    if mid == "rcrv":
        return {"frame0_x": box[0][0], "spacing_m": 1.0, "source": "no frame grid in the model: metres from the aft end"}
    orig = MODELS / mid / "original.ifc"
    m = None
    if orig.exists():
        with orig.open("rb") as f:          # the pset sits near the top; a 600 MB file is never read whole
            m = _SPACING.search(f.read(4 * 1024 * 1024))
    if m:
        return {"frame0_x": 0.0, "spacing_m": float(m.group(1)), "source": "model (SonarIQ_Ship.frame_spacing_m)"}
    return {"frame0_x": 0.0, "spacing_m": 0.8, "source": "engine default (no frame spacing in the model)"}


@router.get("/models/{mid}/grid")
def model_grid(mid: str):
    if not _ID.match(mid):
        raise HTTPException(404, "no such model")
    user = MODELS / mid / "grid.json"
    if user.exists():
        return {**json.loads(user.read_text()), "source": "user"}
    return _default_grid(mid)


class GridReq(BaseModel):
    frame0_x: float
    spacing_m: float


@router.put("/models/{mid}/grid")
def model_grid_set(mid: str, req: GridReq):
    """User-set frame zero and spacing for a model without a frame grid (stored next to the tiles, never in the IFC)."""
    if not _ID.match(mid) or not (MODELS / mid / "web" / "index.json").exists():
        raise HTTPException(404, "no such model")
    if not (0.1 <= req.spacing_m <= 5.0) or not (-10000 < req.frame0_x < 10000):
        raise HTTPException(422, "spacing must be 0.1-5 m and frame zero within 10 km of the origin")
    (MODELS / mid / "grid.json").write_text(json.dumps({"frame0_x": req.frame0_x, "spacing_m": req.spacing_m}))
    return model_grid(mid)


@router.get("/models/{mid}/files/{path:path}")
def model_file(mid: str, path: str):
    if not _ID.match(mid) or not _FILE.match(path):
        raise HTTPException(404, "no such file")
    p = MODELS / mid / "web" / path
    if not p.exists():
        raise HTTPException(404, "no such file")
    # content-hash ids never change; the rcrv id is rebuilt in place, so it revalidates
    cache = "public, max-age=31536000, immutable" if mid != "rcrv" else "public, max-age=300"
    media = "model/gltf-binary" if path.endswith(".glb") else ("application/json" if path.endswith(".json")
                                                               else "application/octet-stream")
    return FileResponse(p, media_type=media, headers={"Cache-Control": cache})
