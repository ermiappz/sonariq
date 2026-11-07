"""One working session over a model: analyse, findings, edits with preview/confirm, recheck (ping), BCF.

Shared by the MCP server (engine/mcp_server.py) and the HTTP API (sonariq/api.py) used by FreeCAD and the portal.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from pathlib import Path
from typing import Any

from .bcf import export_bcf as _export_bcf
from .edits import EditRefused, apply_edit, parse_edit, propose_fixes
from .engine import Run, analyse, impact, run_dict
from .llm import LLM
from .model import Model, load_ifc

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv("SONARIQ_DATA", ROOT / "data"))
REVISIONS = {"A": DATA / "deck5_revA.ifc", "B": DATA / "deck5_revB.ifc", "Bfix2": DATA / "deck5_revB_fix2.ifc"}


class Session:
    def __init__(self, revision: str = "A", path: str | None = None):
        self.llm = LLM()
        self._cache: dict[str, Model] = {}
        self.decisions: list[dict] = []
        self.history: list[dict] = []
        self.pending: dict | None = None
        self.groups = ["fls", "acc", "dnv"]
        self.scope = "deck:5"
        self.open(revision, path)

    # ------------------------------------------------------------ model
    def load(self, revision: str, path: str | None = None) -> Model:
        p = Path(path) if path else REVISIONS.get(revision)
        if p is None or not p.exists():
            raise FileNotFoundError(f"No IFC for revision {revision} ({p})")
        key = f"{revision}|{p}|{p.stat().st_mtime}"
        if key not in self._cache:
            self._cache[key] = load_ifc(p, revision)
        return self._cache[key].copy()

    def open(self, revision: str = "A", path: str | None = None) -> dict:
        self.model = self.load(revision, path)
        self.base_model = self.model
        self.run: Run | None = None
        self.prev: tuple[Model, Run] | None = None
        return self.model_info()

    def model_info(self) -> dict:
        m = self.model
        counts: dict[str, int] = {}
        for e in m.elements.values():
            counts[e.ifc_class] = counts.get(e.ifc_class, 0) + 1
        geo = [e for e in m.elements.values() if e.poly is not None and e.z0 is not None]
        bounds = None
        if geo:
            bounds = [min(e.poly.bounds[0] for e in geo), min(e.poly.bounds[1] for e in geo), min(e.z0 for e in geo),
                      max(e.poly.bounds[2] for e in geo), max(e.poly.bounds[3] for e in geo), max(e.z1 for e in geo)]
        return {"name": m.ship.get("name", "Demo ship"), "revision": m.revision, "path": m.path,
                "schema": "IFC4", "ship": m.ship, "element_counts": counts, "bounds": bounds}

    # ------------------------------------------------------------ analyse
    def analyse(self, scope: str | None = None, packs: list[str] | None = None,
                selection: list[str] | None = None) -> dict:
        if packs:
            self.groups = packs
        if scope:
            self.scope = scope
        self.run = analyse(self.model, self.groups, self.scope, set(selection or []) or None)
        d = run_dict(self.run, self.model)
        self.apply_decisions(d)
        self.history.append({"time": _now(), "event": "analyse", "revision": self.model.revision,
                             "checks": d["total_checks"], "counts": d["counts"], "duration_s": d["duration_s"]})
        return d

    def ensure_run(self) -> Run:
        if self.run is None:
            self.analyse()
        return self.run

    def apply_decisions(self, d: dict) -> None:
        for f in d["checks"]:
            for dec in self.decisions:
                if dec["check_key"] == f["check_key"]:
                    f["decision"] = dec
                    f["review_state"] = "acc" if dec.get("approved") else "pending_acceptance"

    def finding(self, fid: str) -> dict:
        run = self.ensure_run()
        d = run_dict(run, self.model)
        self.apply_decisions(d)
        for f in d["checks"]:
            if f["id"] == fid or f["check_key"] == fid:
                return f
        raise KeyError(f"No finding {fid} in revision {run.revision}")

    def _key(self, fid: str) -> str:
        return self.finding(fid)["check_key"]

    # ------------------------------------------------------------ AI + fixes
    def explain(self, fid: str, question: str | None = None) -> dict:
        f = self.finding(fid)
        out = self.llm.explain(f, question)
        out["badge"] = "AI explanation · numbers checked" if out["source"] == "ai" else "Rule engine text"
        out["finding"] = f["id"]
        return out

    def propose_fixes(self, fid: str) -> list[dict]:
        run = self.ensure_run()
        return propose_fixes(self.model, run, self._key(fid), self.groups)

    # ------------------------------------------------------------ edits: preview -> confirm -> ping
    def preview_edit(self, edit: dict) -> dict:
        parse_edit(edit)  # raises EditRefused
        _, e, text = apply_edit(self.model, edit)
        self.pending = {"edit": e.model_dump(), "preview": text}
        return {"preview": text, "edit": e.model_dump(), "confirm_required": True}

    def apply_edit(self, edit: dict, confirm: bool = False) -> dict:
        if not confirm:
            return self.preview_edit(edit)
        before_model, before_run = self.model, self.ensure_run()
        new_model, e, text = apply_edit(self.model, edit)
        self.model = new_model
        self.pending = None
        self.history.append({"time": _now(), "event": "edit", "edit": e.model_dump(), "preview": text})
        ping = self._ping(before_model, before_run)
        return {"applied": text, "ping": ping}

    def _ping(self, before_model: Model, before_run: Run) -> dict:
        t0 = time.perf_counter()
        self.run = analyse(self.model, self.groups, self.scope)
        im = impact(before_model, before_run, self.model, self.run)
        im["duration_s"] = round(time.perf_counter() - t0, 3)
        self.prev = (before_model, before_run)
        self.history.append({"time": _now(), "event": "ping", "rerun": im["rerun"],
                             "changed": [c["id"] for c in im["changed"]]})
        return im

    def recheck(self) -> dict:
        """Re-check after a change made outside SonarIQ (e.g. the IFC was edited in FreeCAD and reloaded)."""
        before = self.prev or (self.model, self.ensure_run())
        return self._ping(*before)

    def switch_revision(self, revision: str, path: str | None = None) -> dict:
        """Load another revision and ping against the current one (Rev A -> Rev B = OR-117)."""
        before_model, before_run = self.model, self.ensure_run()
        self.model = self.load(revision, path)
        return self._ping(before_model, before_run)

    # ------------------------------------------------------------ review
    def accept(self, fid: str, reason: str, who: str = "Designer", to: str = "Fire & life safety lead") -> dict:
        if not reason or not reason.strip():
            raise ValueError("A reason is required.")
        f = self.finding(fid)
        dec = {"finding": f["id"], "check_key": f["check_key"], "kind": "accept_with_reason", "reason": reason.strip(),
               "by": who, "to": to, "time": _now(), "revision": self.model.revision, "approved": False,
               "engine_verdict": f["status"]}
        self.decisions.append(dec)
        self.history.append({"time": _now(), "event": "accept_requested", **dec})
        return dec

    def export_bcf(self, path: str | None = None) -> dict:
        run = self.ensure_run()
        d = run_dict(run, self.model)
        self.apply_decisions(d)
        topics = [f for f in d["findings"]]
        out = Path(path) if path else DATA / "out" / f"sonariq_rev-{self.model.revision.lower()}.bcfzip"
        res = _export_bcf(topics, out, project=self.model.ship.get("name", "Demo ship"))
        res["decisions"] = sum(1 for f in topics if f.get("decision"))
        res["open"] = len(topics) - res["decisions"]
        return res


def _now() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


__all__ = ["Session", "EditRefused"]
