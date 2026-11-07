"""Local HTTP API for the FreeCAD panel and the portal (port 8765). Same Session as the MCP server."""
from __future__ import annotations

import csv
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json

from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .edits import EditRefused
from .rules import PACK_GROUPS, load_rules
from .session import DATA, REVISIONS, Session

app = FastAPI(title="SonarIQ engine", version="0.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
S = Session("A")


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
    return {"ok": True, "engine": "ready", "ai": S.llm.status(), "revision": S.model.revision}


@app.get("/model")
def model():
    return S.model_info()


@app.get("/rules")
def rules():
    return {"groups": PACK_GROUPS, "rules": [r.model_dump() | {"ref": r.ref, "group": r.group} for r in load_rules()]}


@app.post("/open")
def open_(req: AnalyseReq):
    try:
        return S.open(req.revision or "A", req.path)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/analyse")
def analyse(req: AnalyseReq):
    if req.revision and req.revision != S.model.revision or req.path:
        S.open(req.revision or S.model.revision, req.path)
    return S.analyse(req.scope, req.packs, req.selection)


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


@app.post("/export/bcf")
def bcf():
    return S.export_bcf()


@app.get("/history")
def history():
    return {"history": S.history, "decisions": S.decisions}


@app.get("/model/ifc/{rev}")
def ifc(rev: str):
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
