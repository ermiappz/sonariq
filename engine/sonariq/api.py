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

from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .edits import EditRefused
from .rules import PACK_GROUPS, load_rules
from .session import DATA, REVISIONS, Session

app = FastAPI(title="SonarIQ engine", version="0.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
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
    if len(body) > 400 * 1024 * 1024:
        raise HTTPException(413, "IFC larger than 400 MB.")
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


@app.post("/analyse")
def analyse(req: AnalyseReq):
    req.path = _check_path(req.path)
    # Reopen on a new path, a new revision, or a revision whose demo file is not the open model
    # (after a file opened by path, e.g. an RCRV deck, which also carries revision "A").
    # Same revision + same file keeps the model, including confirmed edits.
    other_file = (req.revision in REVISIONS and
                  str(Path(S.model.path).resolve()) != str(REVISIONS[req.revision].resolve()))
    if req.path or (req.revision and (req.revision != S.model.revision or other_file)):
        # a file opened by path is labelled by its name (uploads: without the hash prefix), not the last revision
        label = req.revision or (re.sub(r"^[0-9a-f]{12}_", "", Path(req.path).stem) if req.path else S.model.revision)
        S.open(label, req.path)
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
    r = S.export_bcf()
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
