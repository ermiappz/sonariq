"""Local HTTP API for the FreeCAD panel and the portal (port 8765). Same Session as the MCP server."""
from __future__ import annotations

import csv
import os as _os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import hashlib
import json
import re
from typing import Literal

from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .edits import EditRefused
from .rules import PACK_GROUPS, load_rules
from .session import DATA, REVISIONS, Session

app = FastAPI(title="SonarIQ engine", version="0.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ rate limits (public demo: chat / analyse / upload)
import time as _time  # noqa: E402
from collections import defaultdict, deque  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

_LIMITS = {"/chat": 20, "/chat/confirm": 20, "/analyse": 30, "/upload": 10, "/simulate": 10, "/models": 10,
           "/models/prepare": 30}   # requests per minute per IP
_HITS: dict = defaultdict(deque)


@app.middleware("http")
async def _rate_limit(request: Request, call_next):
    lim = _LIMITS.get(request.url.path) if request.method == "POST" else None
    if lim and _os.getenv("SONARIQ_RATE_LIMIT", "1") != "0":
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
        q, now = _HITS[(ip, request.url.path)], _time.time()
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= lim:
            return JSONResponse({"detail": f"Too many requests: {lim} per minute on {request.url.path}. Try again shortly."},
                                status_code=429, headers={"Retry-After": "30"})
        q.append(now)
    return await call_next(request)
from .models_api import router as _models_router  # noqa: E402
app.include_router(_models_router)
S = Session("A")
# Hosted on the VM (behind Caddy + basic auth): clients may only open files inside data/ (uploads included).
HOSTED = _os.getenv("SONARIQ_HOSTED", "0").lower() in ("1", "true", "on", "yes")
UPLOADS = DATA / "uploads"
_LAST_BCF: dict = {}


def _check_path(path: str | None) -> str | None:
    if not path:
        return path
    p = Path(path)
    if not p.is_absolute():
        p = (DATA.parent / p)
    p = p.resolve()
    if HOSTED and DATA.resolve() not in p.parents:
        raise HTTPException(403, "On the hosted engine only files inside data/ can be opened; upload the IFC instead.")
    return str(p)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


_REV_SHA: dict[str, tuple[float, str]] = {}


def _revision_for(sha: str) -> str | None:
    for rev, p in REVISIONS.items():
        if p.exists():
            m = p.stat().st_mtime
            if _REV_SHA.get(rev, (None,))[0] != m:
                _REV_SHA[rev] = (m, _sha(p))
            if _REV_SHA[rev][1] == sha:
                return rev
    return None


class AnalyseReq(BaseModel):
    revision: str | None = None
    path: str | None = None
    scope: str = "deck:5"
    packs: list[str] | None = None
    selection: list[str] | None = None


class EditReq(BaseModel):
    edit: dict
    confirm: bool = False


class AcceptReq(BaseModel):
    reason: str
    by: str = "Designer"


@app.get("/health")
def health():
    return {"ok": True, "engine": "ready", "ai": S.llm.status(), "revision": S.model.revision,
            "simulate": _os.getenv("SIMULATE_ENABLED", "0").lower() in ("1", "true", "on", "yes")}


@app.get("/model")
def model():
    return S.model_info()


@app.get("/rules")
def rules():
    return {"groups": PACK_GROUPS, "rules": [r.model_dump() | {"ref": r.ref, "group": r.group} for r in load_rules()]}


@app.post("/upload")
async def upload(request: Request, name: str = "model.ifc"):
    """Remote clients (the FreeCAD panel on a Mac) send the IFC bytes. A byte-identical demo file maps to its
    revision (A / B / Bfix2), so edits and simulations keep working; anything else is stored under data/uploads."""
    body = await request.body()
    if not body.startswith(b"ISO-10303-21"):
        raise HTTPException(422, "Not an IFC (STEP) file.")
    limit_mb = int(_os.getenv("SONARIQ_UPLOAD_MB", "400"))
    if len(body) > limit_mb * 1024 * 1024:
        raise HTTPException(413, f"IFC larger than {limit_mb} MB.")
    head = body[:4096].upper()
    m = re.search(rb"FILE_SCHEMA\s*\(\s*\(\s*'([A-Z0-9_]+)'", head)
    if m and not m.group(1).startswith(b"IFC4"):
        raise HTTPException(422, f"This file is {m.group(1).decode()}; SonarIQ reads IFC4. Export the model as IFC4 and try again.")
    sha = hashlib.sha256(body).hexdigest()
    rev = _revision_for(sha)
    if rev:
        return {"revision": rev, "path": None, "sha": sha[:12], "known": True}
    UPLOADS.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name)[:80] or "model.ifc"
    out = UPLOADS / f"{sha[:12]}_{safe}"
    if not out.exists():
        out.write_bytes(body)
    return {"revision": None, "path": str(out), "sha": sha[:12], "known": False}


@app.post("/open")
def open_(req: AnalyseReq):
    req.path = _check_path(req.path)
    try:
        return S.open(req.revision or "A", req.path)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


# ------------------------------------------------------------------ run store (every Analyse is kept as a run)
RUNS = Path(_os.getenv("SONARIQ_RUNS", str(DATA / "runs")))


def _save_run(d: dict, req: "AnalyseReq", source: str) -> dict:
    """Write the result as runs/<seq>_<time>.json. Exclusive create, so a run is never overwritten."""
    import datetime as _dt
    RUNS.mkdir(parents=True, exist_ok=True)
    now = _dt.datetime.now()
    seq = 1 + max([int(p.name.split("_")[0]) for p in RUNS.glob("[0-9]*_*.json")] or [0])
    path = Path(S.model.path or "")
    whole_ship = d.get("revision") == "RCRV"
    meta = {"id": f"{seq:04d}_{now:%Y%m%d-%H%M%S}", "seq": seq, "time": now.isoformat(timespec="seconds"),
            "file": "RCRV whole ship" if whole_ship else re.sub(r"^[0-9a-f]{12}_", "", path.name), "revision": d.get("revision"),
            "scope": d.get("scope"), "packs": d.get("groups"), "counts": d.get("counts"),
            "total_checks": d.get("total_checks"), "source": source, "scope_note": d.get("scope_note"),
            # for the web viewer: which file this run read, its bounds, and whether chat edits changed it in memory
            "path": str(path) if S.model.path and not whole_ship else None, "bounds": S.model_info().get("bounds"),
            "edited": S.model is not S.base_model}
    while True:
        try:
            with open(RUNS / f"{meta['id']}.json", "x", encoding="utf-8") as fh:
                json.dump({**meta, "run": d}, fh, ensure_ascii=False, default=str)
            break
        except FileExistsError:
            seq += 1
            meta["seq"], meta["id"] = seq, f"{seq:04d}_{now:%Y%m%d-%H%M%S}"
    return meta


def _load_run(rid: str) -> dict:
    if not re.fullmatch(r"[0-9]{4,}_[0-9]{8}-[0-9]{6}", rid) or not (RUNS / f"{rid}.json").exists():
        raise HTTPException(404, "no such run")
    return json.loads((RUNS / f"{rid}.json").read_text(encoding="utf-8"))


@app.get("/runs")
def runs_list():
    """All stored runs, newest first (without the full results)."""
    out = []
    for p in sorted(RUNS.glob("[0-9]*_*.json"), reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - half-written or foreign file
            continue
        d.pop("run", None)
        d.pop("path", None)
        out.append(d)
    return {"runs": out}


@app.get("/runs/diff")
def runs_diff(a: str, b: str):
    """What changed between two stored runs (a = before, b = after), by check: new findings, cleared, status changes."""
    ra, rb = _load_run(a), _load_run(b)
    ca = {c["check_key"]: c for c in ra["run"]["checks"]}
    cb = {c["check_key"]: c for c in rb["run"]["checks"]}
    bad = ("fail", "warn", "unk")
    row = lambda c: {"id": c.get("id"), "check_key": c["check_key"], "rule": c["rule"], "title": c["title"],
                     "status": c["status"], "location": c["location"]["label"],
                     "element": (c.get("element") or {}).get("name")}
    new, cleared, changed = [], [], []
    for k, c in cb.items():
        o = ca.get(k)
        if o is None:
            (new if c["status"] in bad else changed).append({**row(c), "before": None})
        elif o["status"] != c["status"]:
            if c["status"] in bad and o["status"] not in bad:
                new.append({**row(c), "before": o["status"]})
            elif o["status"] in bad and c["status"] not in bad:
                cleared.append({**row(c), "id": o.get("id"), "before": o["status"]})   # passing checks carry no finding id
            else:
                changed.append({**row(c), "before": o["status"]})
    for k, o in ca.items():
        if k not in cb and o["status"] in bad:
            cleared.append({**row(o), "before": o["status"], "status": "removed"})
    keys = ("fail", "warn", "unk", "pass", "dor", "na")
    return {"a": {k: ra[k] for k in ("id", "time", "file", "revision", "counts", "total_checks")},
            "b": {k: rb[k] for k in ("id", "time", "file", "revision", "counts", "total_checks")},
            "counts_delta": {k: (rb["counts"] or {}).get(k, 0) - (ra["counts"] or {}).get(k, 0) for k in keys},
            "new_findings": new, "cleared": cleared, "changed": changed,
            "added_checks": len(set(cb) - set(ca)), "removed_checks": len(set(ca) - set(cb))}


@app.get("/runs/{rid}")
def runs_get(rid: str):
    d = _load_run(rid)
    d.pop("path", None)
    return d


def _run_file(d: dict) -> Path | None:
    """The IFC a stored run read: its recorded path, else a demo file or the newest upload with that name."""
    p = Path(d["path"]) if d.get("path") else None
    if p is not None and not _owned(p):
        p = None   # e.g. written by another engine (staging) with its own data folder: find the file by name
    if p is None:
        name = d.get("file") or ""
        p = next((q for q in REVISIONS.values() if q.name == name), None)
        if p is None and UPLOADS.exists():
            hits = sorted(UPLOADS.glob(f"*_{name}"), key=lambda q: q.stat().st_mtime, reverse=True)
            p = hits[0] if hits else None
    return p if p is not None and _owned(p) else None


def _owned(p: Path) -> bool:
    """Only files this engine owns (demo models, uploads) are served."""
    if not p.exists():
        return False
    try:
        p.resolve().relative_to(DATA.resolve())
        return True
    except ValueError:
        return p.resolve() in [q.resolve() for q in REVISIONS.values()]


def _csv_val(v):
    return "" if not v else v.get("value")


@app.get("/runs/{rid}/csv")
def runs_csv(rid: str):
    """Every check of a stored run, one row each (spec B7). Values and verdicts exactly as the engine returned them."""
    import io
    d = _load_run(rid)
    run = d["run"]
    head = ["revision", "finding", "rule", "status", "element_guid", "element_name", "ifc_class", "deck", "location", "swbs",
            "measured", "measured_unit", "measured_source", "required", "required_unit", "required_source", "summary",
            "rule_ref", "verified_against_official_text"]
    by_rule = run.get("by_rule") or {}

    def rows():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(head)
        for c in run["checks"]:
            el, m, r = c.get("element") or {}, c.get("measured") or {}, c.get("required") or {}
            w.writerow([run.get("revision"), c.get("id") or "", c["rule"], c["status"], el.get("guid", ""), el.get("name", ""),
                        el.get("ifc_class", ""), c["location"].get("deck") or "", c["location"].get("label", ""), c["location"].get("swbs") or "",
                        _csv_val(m), m.get("unit", ""), (m.get("provenance") or {}).get("kind", ""), _csv_val(r), r.get("unit", ""),
                        (r.get("provenance") or {}).get("kind", ""), c.get("summary", ""), c.get("ref", ""),
                        c.get("verified_against_official_text", False)])
        yield buf.getvalue()
        buf.seek(0); buf.truncate()
        for i, (rule, guid, name, deck, summary, *rest) in enumerate(run.get("passes") or []):
            w.writerow([run.get("revision"), "", rule, "pass", guid or "", name or "", "", deck or "", f"Deck {deck}" if deck else "",
                        (rest[0] if rest else "") or "", "", "", "", "", "", "", summary, (by_rule.get(rule) or {}).get("ref", ""), ""])
            if i % 5000 == 4999:
                yield buf.getvalue()
                buf.seek(0); buf.truncate()
        yield buf.getvalue()
    name = f"sonariq_{d.get('revision', 'run')}_{rid}.csv"
    return StreamingResponse(rows(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/runs/{rid}/ifc")
def runs_ifc(rid: str):
    """Exactly the IFC this run analysed, so the web viewer never draws findings on other geometry."""
    d = _load_run(rid)
    if d.get("edited"):
        raise HTTPException(409, "This run includes edits made in chat; the file on disk is the version before them.")
    p = _run_file(d)
    if p is None:
        raise HTTPException(404, "The file of this run is not on the engine any more.")
    return FileResponse(p, media_type="application/x-step", filename=re.sub(r"^[0-9a-f]{12}_", "", p.name))



@app.get("/model-file")
def model_file(revision: str | None = None, path: str | None = None):
    """A model opened in the web Studio before Analyse: a demo revision or an uploaded file (only files this engine owns)."""
    p = REVISIONS.get(revision or "") if revision else (Path(path) if path else None)
    if p is None or not _owned(p):
        raise HTTPException(404, "no such model on the engine")
    return FileResponse(p, media_type="application/x-step", filename=re.sub(r"^[0-9a-f]{12}_", "", p.name))


# ------------------------------------------------------------------ reports (a run exported from FreeCAD, frozen) + task board
REPORTS = Path(_os.getenv("SONARIQ_REPORTS", str(DATA / "reports.json")))
TASKS = Path(_os.getenv("SONARIQ_TASKS", str(DATA / "tasks.json")))
VIEWS = Path(_os.getenv("SONARIQ_VIEWS", str(DATA / "views.json")))


def _jload(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing or half-written
        return default


def _jsave(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


class ReportReq(BaseModel):
    run_id: str


@app.get("/reports")
def reports_list():
    return {"reports": _jload(REPORTS, [])}


@app.post("/reports")
def reports_create(req: ReportReq):
    """Freeze a stored run as a report R-00n. One report per run: asking again returns the existing one."""
    r = _load_run(req.run_id)
    reps = _jload(REPORTS, [])
    for x in reps:
        if x["run_id"] == req.run_id:
            return {**x, "existing": True}
    import datetime as _dt
    rep = {"id": f"R-{len(reps) + 1:03d}", "run_id": req.run_id, "time": _dt.datetime.now().isoformat(timespec="seconds"),
           "file": r.get("file"), "revision": r.get("revision"), "counts": r.get("counts"),
           "total_checks": r.get("total_checks")}
    inc = incorrect_map()
    fs = r["run"].get("findings", [])
    rep["open_findings"] = sum(1 for f in fs if f["check_key"] not in inc)
    rep["excluded"] = [{"finding": f.get("id"), "check_key": f["check_key"], "reason": inc[f["check_key"]]["reason"]}
                       for f in fs if f["check_key"] in inc]
    reps.append(rep)
    _jsave(REPORTS, reps)
    return rep


class CutModel(BaseModel):
    kind: Literal["cross", "long", "deck"]
    pos: float                    # metres along x (cross), y (long) or z (deck), engine frame
    flip: bool = False


class ViewReq(BaseModel):
    name: str
    model: str                    # model id (GET /models/<id>)
    cuts: list[CutModel] = []
    camera: dict                  # {position: [x,y,z], target: [x,y,z], projection: perspective|orthographic, zoom}
    mode: str = "edges"


_MODES = {"shaded", "edges", "realistic", "xray", "lines", "wireframe"}


def _vec(v, n=3) -> list[float]:
    import math
    if not isinstance(v, list) or len(v) != n or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in v):
        raise HTTPException(422, "camera position and target must be three finite numbers")
    return [float(x) for x in v]


@app.get("/views")
def views_list(model: str | None = None):
    """Named views (spec A3): cuts + camera + display mode, per model."""
    vs = _jload(VIEWS, [])
    return {"views": [v for v in vs if model is None or v["model"] == model]}


@app.post("/views")
def views_create(req: ViewReq):
    import datetime as _dt
    import math
    name = req.name.strip()
    if not name or len(name) > 80:
        raise HTTPException(422, "name must be 1-80 characters")
    if not re.fullmatch(r"rcrv|[0-9a-f]{16}", req.model):
        raise HTTPException(422, "unknown model id")
    if len(req.cuts) > 3:
        raise HTTPException(422, "at most 3 cuts")
    if any(not math.isfinite(c.pos) or abs(c.pos) > 10000 for c in req.cuts):
        raise HTTPException(422, "cut position out of range")
    if req.mode not in _MODES:
        raise HTTPException(422, f"mode must be one of {sorted(_MODES)}")
    cam = req.camera
    proj = cam.get("projection", "perspective")
    if proj not in ("perspective", "orthographic"):
        raise HTTPException(422, "projection must be perspective or orthographic")
    zoom = cam.get("zoom", 1)
    if not isinstance(zoom, (int, float)) or not 0 < zoom < 1e4:
        raise HTTPException(422, "zoom out of range")
    vs = _jload(VIEWS, [])
    if len(vs) >= 500:
        raise HTTPException(409, "too many saved views; delete some first")
    n = max([int(v["id"][2:]) for v in vs] + [0]) + 1
    v = {"id": f"V-{n:03d}", "name": name, "model": req.model, "cuts": [c.model_dump() for c in req.cuts],
         "camera": {"position": _vec(cam.get("position")), "target": _vec(cam.get("target")), "projection": proj,
                    "zoom": float(zoom)},
         "mode": req.mode, "time": _dt.datetime.now().isoformat(timespec="seconds")}
    vs.append(v)
    _jsave(VIEWS, vs)
    return v


@app.delete("/views/{vid}")
def views_delete(vid: str):
    vs = _jload(VIEWS, [])
    keep = [v for v in vs if v["id"] != vid]
    if len(keep) == len(vs):
        raise HTTPException(404, "no such view")
    _jsave(VIEWS, keep)
    return {"deleted": vid}


class TaskReq(BaseModel):
    column: str | None = None     # backlog | doing | done
    assignee: str | None = None   # mock person id, "" clears


@app.get("/tasks")
def tasks_list():
    return {"tasks": _jload(TASKS, {})}


@app.put("/tasks/{key}")
def tasks_put(key: str, req: TaskReq):
    if len(key) > 200:
        raise HTTPException(400, "bad key")
    if req.column is not None and req.column not in ("backlog", "doing", "done"):
        raise HTTPException(400, "column must be backlog, doing or done")
    t = _jload(TASKS, {})
    cur = t.get(key, {"column": "backlog", "assignee": None})
    if req.column is not None:
        cur["column"] = req.column
    if req.assignee is not None:
        cur["assignee"] = req.assignee or None
    t[key] = cur
    _jsave(TASKS, t)
    return {"key": key, **cur}


@app.post("/analyse")
def analyse(req: AnalyseReq, request: Request):
    req.path = _check_path(req.path)
    # Reopen on a new path, a new revision, or a revision whose demo file is not the open model
    # (after a file opened by path, e.g. an RCRV deck, which also carries revision "A").
    # Same revision + same file keeps the model, including confirmed edits.
    other_file = (req.revision in REVISIONS and
                  str(Path(S.model.path).resolve()) != str(REVISIONS[req.revision].resolve()))
    if req.path or (req.revision and (req.revision != S.model.revision or other_file)):
        # a file opened by path is labelled by its name (uploads: without the hash prefix), not the last revision
        label = req.revision
        if not label and req.path:
            p = Path(req.path)
            # a byte-identical copy of a demo file keeps its revision name (A / B / Bfix2)
            known = _revision_for(_sha(p)) if p.exists() and p.stat().st_size < 100 * 1024 * 1024 else None
            label = known or re.sub(r"^[0-9a-f]{12}_", "", p.stem)
        label = label or S.model.revision
        S.open(label, req.path)
    d = S.analyse(req.scope, req.packs, req.selection)
    if d.get("readiness"):
        from .readiness import save as _save_rd
        _save_rd(d["readiness"], DATA / "readiness")      # readiness_<revision>.json, the latest per revision
    ua = request.headers.get("user-agent", "")
    d["run_meta"] = _save_run(d, req, "FreeCAD panel" if "Python-urllib" in ua else "portal" if "Mozilla" in ua else "API")
    return d


@app.get("/readiness")
def readiness_get(revision: str | None = None, path: str | None = None):
    """What the model can support before analysis (spec B2): inventory + per rule pack Ready / Partial / Not possible."""
    from .readiness import readiness
    try:
        m = S.load(revision or "A", _check_path(path)) if (revision or path) else S.model
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return readiness(m)


SCENARIO = {"A": "deck5_revA", "B": "deck5_revB", "RCRV": "rcrv_structure"}


@app.get("/accuracy")
def accuracy(revision: str):
    """Accuracy banner (spec B5), computed: a fresh engine run with the scenario's packs, compared with the hand-checked
    ground truth and the independent scan. Never typed."""
    from .accuracy import compare, truth
    from .engine import analyse as _an, run_dict as _rd
    sc = SCENARIO.get(revision)
    if sc is None:
        raise HTTPException(404, f"No hand-checked ground truth for revision {revision}.")
    gt = truth(sc)
    m = S.load(gt["revision"])
    try:
        r = compare(sc, _rd(_an(m, gt["packs"], gt["scope"]), m))
    except FileNotFoundError as e:
        raise HTTPException(404, f"The independent scan needs the source data: {e}")
    return r


@app.get("/findings/{fid}")
def finding(fid: str):
    try:
        return S.finding(fid)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/findings/{fid}/explain")
def explain(fid: str, q: str | None = None):
    return S.explain(fid, q)


@app.get("/findings/{fid}/explain/stream")
def explain_stream(fid: str, q: str | None = None):
    """SSE: delta events while the model writes, then a done event (or replace, if the number guard fails)."""
    from .llm import SYSTEM, template_explanation
    f = S.finding(fid)

    def gen():
        for ev in S.llm.stream_guarded(SYSTEM, S.llm.slim(f), q or "Why does this fail, in plain words?",
                                       template_explanation(f)):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/findings/{fid}/fixes")
def fixes(fid: str):
    return S.propose_fixes(fid)


@app.post("/findings/{fid}/accept")
def accept(fid: str, req: AcceptReq):
    try:
        return S.accept(fid, req.reason, req.by)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/edit")
def edit(req: EditReq):
    try:
        return S.apply_edit(req.edit, req.confirm)
    except EditRefused as e:
        raise HTTPException(422, {"refused": True, "reason": str(e)})


@app.post("/recheck")
def recheck(revision: str | None = None):
    return S.switch_revision(revision) if revision else S.recheck()


# ------------------------------------------------------------------ "Incorrect finding" (a reviewer says the engine is wrong here)
INCORRECT = Path(_os.getenv("SONARIQ_INCORRECT", str(DATA / "incorrect.json")))


def incorrect_map() -> dict:
    try:
        return json.loads(INCORRECT.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


class IncorrectReq(BaseModel):
    check_key: str
    reason: str
    finding: str | None = None
    by: str = "Designer"
    revision: str | None = None
    file: str | None = None


@app.get("/incorrect")
def incorrect_list():
    """Findings marked incorrect, by check key. They stay in every run (the verdict is the engine's) but are greyed
    and left out of BCF and reports."""
    return {"incorrect": incorrect_map()}


@app.post("/incorrect")
def incorrect_mark(req: IncorrectReq):
    reason = (req.reason or "").strip()
    if not reason:
        raise HTTPException(422, "Say why the finding is wrong.")
    if len(reason) > 200 or len(req.check_key) > 200:
        raise HTTPException(422, "Keep the reason short (200 characters).")
    import datetime as _dt
    m = incorrect_map()
    rec = {"finding": req.finding, "reason": reason, "by": req.by[:80], "revision": req.revision, "file": req.file,
           "time": _dt.datetime.now().isoformat(timespec="seconds")}
    m[req.check_key] = rec
    INCORRECT.parent.mkdir(parents=True, exist_ok=True)
    INCORRECT.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    S.history.append({"time": rec["time"][11:16], "event": "incorrect", "finding": req.finding, "check_key": req.check_key,
                      "reason": reason, "by": rec["by"]})
    return {"check_key": req.check_key, **rec}


@app.delete("/incorrect/{check_key:path}")
def incorrect_undo(check_key: str):
    m = incorrect_map()
    rec = m.pop(check_key, None)
    if rec is None:
        raise HTTPException(404, "Not marked incorrect.")
    INCORRECT.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    import datetime as _dt
    S.history.append({"time": _dt.datetime.now().strftime("%H:%M"), "event": "incorrect_undone",
                      "finding": rec.get("finding"), "check_key": check_key})
    return {"check_key": check_key, "undone": True}


@app.post("/export/bcf")
def bcf():
    r = S.export_bcf(exclude=set(incorrect_map()))
    _LAST_BCF["path"] = r.get("path")
    r["download"] = "/export/bcf/file"
    return r


@app.get("/export/bcf/file")
def bcf_file():
    """The last BCF written, for clients that are not on the engine's machine."""
    p = Path(_LAST_BCF.get("path") or "")
    if not _LAST_BCF.get("path") or not p.exists():
        raise HTTPException(404, "Export BCF first.")
    return FileResponse(p, media_type="application/zip", filename=p.name)


@app.get("/history")
def history():
    return {"history": S.history, "decisions": S.decisions}


@app.post("/admin/reset")
def admin_reset():
    """"Reset all data" (portal Settings): same as scripts/demo_reset.sh, without a restart. Runs, reports, tasks,
    incorrect marks, BCF exports and the in-memory history/decisions are moved to data/archive/<timestamp>/ (never
    deleted); report numbering restarts at R-001. Demo models, uploaded model files and the simulation cache stay, so
    the FreeCAD panel keeps working (its next Analyse starts a fresh session)."""
    global S, _LAST_BCF
    import datetime as _dt
    import shutil
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    arch = DATA / "archive" / ts
    arch.mkdir(parents=True, exist_ok=True)
    (arch / "history.json").write_text(json.dumps({"history": S.history, "decisions": S.decisions}, default=str), encoding="utf-8")
    moved = {"runs": 0}
    if RUNS.exists() and any(RUNS.iterdir()):
        moved["runs"] = len(list(RUNS.glob("*.json")))
        shutil.move(str(RUNS), str(arch / "runs"))
    RUNS.mkdir(parents=True, exist_ok=True)
    for f in (REPORTS, TASKS, INCORRECT):
        if f.exists():
            shutil.move(str(f), str(arch / f.name))
    out = DATA / "out"
    bcf = list(out.glob("*.bcfzip")) if out.exists() else []
    if bcf:
        (arch / "out").mkdir(exist_ok=True)
        for b in bcf:
            shutil.move(str(b), str(arch / "out" / b.name))
    (arch / "ARCHIVE.json").write_text(json.dumps({"archived": ts, "from": str(DATA), "by": "portal"}), encoding="utf-8")
    S = Session("A")
    _LAST_BCF = {}
    return {"ok": True, "archived": ts, **moved}


@app.get("/model/ifc/{rev}")
def ifc(rev: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", rev):
        raise HTTPException(404, "no such model")
    p = REVISIONS.get(rev) or (DATA / "rcrv" / f"{rev}.ifc")
    if not p.exists():
        raise HTTPException(404, "no such model")
    return FileResponse(p, media_type="application/x-step", filename=p.name)


@app.get("/rcrv/mapping")
def rcrv_mapping():
    p = DATA / "rcrv" / "mapping_review.csv"
    if not p.exists():
        return {"rows": []}
    with p.open() as f:
        return {"rows": list(csv.DictReader(f))[:2000]}


# ------------------------------------------------------------------ Simulate (behind SIMULATE_ENABLED)
import os as _os  # noqa: E402

SIM_ON = _os.getenv("SIMULATE_ENABLED", "0").lower() in ("1", "true", "on", "yes")
_SIM = None


def _sim():
    global _SIM
    if not SIM_ON:
        raise HTTPException(404, "Simulate is off (set SIMULATE_ENABLED=1)")
    if _SIM is None:
        from sim.service import SimService
        _SIM = SimService()
    return _SIM


class SimReq(BaseModel):
    text: str | None = None              # words -> scenario preview (confirm=False)
    scenario: dict | None = None         # explicit scenario JSON
    revision: str | None = None          # A | B | Bfix2; default = the open model (incl. confirmed edits)
    runs: int | None = None
    confirm: bool = False
    label: str | None = None


def _sim_model(revision: str | None):
    if not revision:
        return S.model, S.model.revision
    return S.load(revision, None), revision


def _names(model):
    from sim.geometry import build
    g = build(model)
    return list(g.stairs), list(g.spaces), g


def _scenario(sc: dict):
    from sim.runner import Scenario
    return Scenario(case=sc.get("case", "night"), route=sc.get("route", "primary"),
                    closed_stair=sc.get("closed_stair"), closed_door=sc.get("closed_door"),
                    fire_origin=sc.get("fire_origin"))


@app.get("/simulate/enabled")
def sim_enabled():
    return {"enabled": SIM_ON}


@app.post("/simulate")
def simulate(req: SimReq):
    from sim.runner import Scenario
    from sim.words import from_words, validate
    svc = _sim()
    sc = dict(req.scenario or {})
    parsed = None
    model, rev = _sim_model(req.revision or sc.get("revision"))
    stairs, spaces, g = _names(model)
    if req.text and not req.scenario:
        parsed = from_words(req.text, stairs, spaces, S.llm, list(g.doors), g.space_meta)
        if not parsed["ok"]:
            raise HTTPException(422, parsed)
        sc = parsed["scenario"]
        if sc.get("revision"):
            model, rev = _sim_model(sc["revision"])
    errs = validate({"case": sc.get("case", "night"), **sc}, stairs, spaces, list(g.doors))
    if errs:
        raise HTTPException(422, {"errors": errs})
    if (sc.get("fire_origin") or "").startswith("@"):
        from sim.smoke import resolve_origin
        sc["fire_origin"] = resolve_origin(g, sc["fire_origin"])
    scen = _scenario(sc)
    preview = {"scenario": scen.key(), "label": scen.label(), "revision": rev,
               "runs": req.runs or 500, "source": parsed["source"] if parsed else "explicit"}
    if not req.confirm:
        return {"preview": preview, "confirm_required": True}
    st = svc.start(model, scen, req.runs, revision=rev, label=req.label)
    return {"preview": preview, **st}


class SetupReq(BaseModel):
    scenario: dict = {}
    revision: str | None = None
    explain: bool = False


@app.post("/simulate/setup")
def sim_setup(req: SetupReq):
    """W9: what the simulation will read from the model (people, inflows, stairs, doors, gaps) before running."""
    from sim.reader import explain_gaps
    svc = _sim()
    model, rev = _sim_model(req.revision)
    sc = dict(req.scenario)
    if (sc.get("fire_origin") or "").startswith("@"):
        from sim.smoke import resolve_origin
        sc["fire_origin"] = resolve_origin(_names(model)[2], sc["fire_origin"])
    out = dict(svc.setup(model, _scenario(sc)))
    out["revision"] = rev
    if req.explain:
        out["reader"] = explain_gaps(S.llm, out)
    return out


@app.get("/simulate")
def sim_list():
    return {"results": _sim().list()}


@app.get("/simulate/compare")
def sim_compare(a: str, b: str):
    try:
        return _sim().compare(a, b)
    except KeyError as e:
        raise HTTPException(404, f"no results {e}")


@app.get("/simulate/{jid}")
def sim_status(jid: str):
    try:
        return _sim().status(jid)
    except KeyError:
        raise HTTPException(404, "no such simulation")


@app.post("/simulate/{jid}/cancel")
def sim_cancel(jid: str):
    try:
        return _sim().cancel(jid)
    except KeyError:
        raise HTTPException(404, "no running simulation")


@app.get("/simulate/{jid}/results")
def sim_results(jid: str):
    try:
        r = _sim().results(jid)
    except KeyError:
        raise HTTPException(404, "results not ready")
    # tag congested places with the open finding on the same element (e.g. the F-09 pinch)
    try:
        f_by_el = {f["element"]["name"]: f for f in S.analyse()["findings"] if f.get("element")}
        for c in r.get("congestion", []):
            f = f_by_el.get(c["place"])
            if f:
                c["finding"] = f["id"]
    except Exception:  # noqa: BLE001
        pass
    return r


class FixReq(BaseModel):
    finding: str = "F-07"
    ai: bool = True


@app.post("/simulate/{jid}/fixes")
def sim_fixes(jid: str, req: FixReq):
    """Fix explorer: rule re-check, then 100-run re-simulation per passing candidate; rejected ideas shown."""
    from sim.fixes import explore
    from .engine import analyse
    svc = _sim()
    try:
        base = svc.model_of(jid)
        res = svc.results(jid)
    except KeyError:
        raise HTTPException(404, "no model for that simulation")
    run = analyse(base, ["fls", "acc", "dnv"])
    key = next((k for k, i in run.ids.items() if i == req.finding), None)
    if key is None:
        raise HTTPException(404, f"{req.finding} is not open in that model")
    return explore(svc, base, run, req.finding, key, res["scenario"], res.get("revision", ""),
                   S.llm if req.ai else None)


@app.get("/simulate/{jid}/replay")
def sim_replay(jid: str):
    try:
        return _sim().replay(jid)
    except KeyError:
        raise HTTPException(404, "replay not ready")


@app.get("/simulate/{jid}/hotspot")
def sim_hotspot(jid: str, x: float, y: float, t: float):
    """Click on the replay: density, time and the analyst's checked text for that place."""
    from sim.analyst import hotspot
    svc = _sim()
    try:
        return hotspot(S.llm, svc.results(jid), svc.replay(jid), x, y, t)
    except KeyError:
        raise HTTPException(404, "replay not ready")


@app.get("/simulate/{jid}/explain")
def sim_explain(jid: str, q: str | None = None):
    """Results analyst: the AI explains the results JSON; every number must be in it (number guard)."""
    from sim.analyst import explain_results
    try:
        res = _sim().results(jid)
    except KeyError:
        raise HTTPException(404, "results not ready")
    return explain_results(S.llm, res, q)


class PinReq(BaseModel):
    t: float
    x: float
    y: float
    note: str
    by: str = "Designer"
    finding: str = "F-07"


@app.post("/simulate/{jid}/pin")
def sim_pin(jid: str, req: PinReq):
    """Pin to review: the replay moment becomes a BCF viewpoint + comment on the finding (W3)."""
    _sim()
    try:
        p = S.pin(req.finding, req.note, req.by, req.x, req.y, req.t, jid)
    except KeyError as e:
        raise HTTPException(404, str(e))
    return {"ok": True, "topic": req.finding, "pin": p}


# ------------------------------------------------------------------ Chat (panel P5 + portal): words -> preview card
_CHAT = None


def _chat():
    global _CHAT
    if _CHAT is None:
        from .chat import Chat
        rag = None
        try:
            from .rag import get_rag
            rag = get_rag()
        except Exception:  # noqa: BLE001
            rag = None
        _CHAT = Chat(S, _sim() if SIM_ON else None, rag)
    return _CHAT


class ChatReq(BaseModel):
    text: str
    finding: str | None = None


class ConfirmReq(BaseModel):
    action: dict


@app.post("/chat")
def chat(req: ChatReq):
    return _chat().ask(req.text, req.finding)


@app.post("/chat/confirm")
def chat_confirm(req: ConfirmReq):
    try:
        return _chat().confirm(req.action)
    except EditRefused as e:
        raise HTTPException(422, {"refused": True, "reason": str(e)})


@app.get("/simulate/{jid}/card")
def sim_card(jid: str):
    """Chat result card: the engine's numbers, the honest label and the analyst's checked text."""
    from sim.analyst import explain_results
    try:
        r = _sim().results(jid)
    except KeyError:
        raise HTTPException(404, "results not ready")
    worst = max(r["landings"].items(), key=lambda kv: kv[1]["queue_max_p95"]) if r["landings"] else (None, {})
    last = max(r["stairs"].items(), key=lambda kv: kv[1]["last_p95_s"]) if r["stairs"] else (None, {})
    ai = explain_results(S.llm, r)
    _chat().last_sim = {"id": jid}
    from sim.analyst import _mmss
    return {"type": "sim_result", "id": jid, "title": f"{r['scenario_label']} · {r['revision']}", "runs": r["runs"],
            "tA_p95_mmss": _mmss(r["tA_p95_s"]), "peak_density_p95": r.get("peak_density_p95"),
            "longest_route": {k: (r.get("longest_route") or {}).get(k) for k in ("space", "length_m", "stair")},
            "scenario": r.get("scenario"),
            "tA_p95_s": r["tA_p95_s"], "tA_p50_s": r["tA_p50_s"], "worst_landing": worst[0],
            "worst_queue_p95": worst[1].get("queue_max_p95"), "last_stair": last[0],
            "last_stair_p95_s": last[1].get("last_p95_s"), "label": r["label"], "analyst": ai["text"],
            "badge": ai["badge"], "replay_url": f"#simulate/{jid}"}


# ------------------------------------------------------------------ RAG: source text, cited why, draft rule
class DraftReq(BaseModel):
    query: str


class ApproveReq(BaseModel):
    draft: dict
    by: str = "Designer"


@app.get("/findings/{fid}/sources")
def finding_sources(fid: str):
    from .sources import finding_sources as fs
    try:
        return fs(S.finding(fid))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ImportError as e:
        raise HTTPException(503, str(e))


@app.get("/findings/{fid}/why")
def finding_why(fid: str, q: str | None = None):
    from .llm import template_explanation
    from .sources import why
    f = S.finding(fid)
    out = why(S.llm, f, q or "Why does this fail?", template_explanation(f))
    out["badge"] = "AI explanation · numbers checked · sources cited" if out["source"] == "ai" else "Rule engine text"
    return out


@app.post("/rules/draft")
def rules_draft(req: DraftReq):
    from .sources import draft_rule
    return draft_rule(S.llm, req.query)


@app.post("/rules/draft/approve")
def rules_draft_approve(req: ApproveReq):
    from .sources import approve_draft
    return approve_draft(req.draft, req.by)


class ReviewReq(BaseModel):
    action: str            # Approved | Requested a change | Declined
    reason: str = ""
    by: str = "Reviewer"


@app.post("/findings/{fid}/review")
def finding_review(fid: str, req: ReviewReq):
    """W3 sign-off: name, role, time and revision recorded by the engine (the verdict does not change)."""
    if req.action != "Approved" and not req.reason.strip():
        raise HTTPException(422, "A reason is required to decline or request a change.")
    try:
        f = S.finding(fid)
    except KeyError as e:
        raise HTTPException(404, str(e))
    import datetime as _dt
    row = {"finding": fid, "action": req.action, "reason": req.reason, "by": req.by,
           "time": _dt.datetime.now().strftime("%H:%M:%S"), "revision": f["revision"], "verdict": f["status_word"]}
    S.reviews.append(row)
    S.history.append({"time": row["time"], "event": "review", "finding": fid,
                      "text": f"{req.by}: {req.action}" + (f" · {req.reason}" if req.reason else "")})
    return row
