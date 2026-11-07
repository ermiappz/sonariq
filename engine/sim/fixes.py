"""Fix explorer: allowed edits only. Each candidate is re-checked by the rule engine, then re-simulated with
100 runs on the same scenario. Ideas the engine rejects are shown, not simulated. The AI may add one idea;
it goes through the same gate (parse_edit -> rule re-check -> simulation)."""
from __future__ import annotations

import json

from sonariq.chat import EDIT_SCHEMA, EDIT_SYSTEM
from sonariq.edits import ALLOWED, EditRefused, apply_edit, parse_edit, propose_fixes
from sonariq.engine import analyse

from .runner import Scenario

FIX_RUNS = 100


def explore(svc, base_model, run, finding_id: str, check_key: str, scenario: dict, revision: str, llm=None,
            groups=("fls", "acc", "dnv")) -> dict:
    cands = propose_fixes(base_model, run, check_key, list(groups))
    if llm is not None:
        names = {"doors": sorted(e.name for e in base_model.by_class("IfcDoor")),
                 "corridors": sorted(e.name for e in base_model.spaces("corridor"))}
        f = next((r for r in run.results if r.key == check_key), None)
        js, _ = llm.ask_json(EDIT_SYSTEM + " Propose one edit that could fix the finding.",
                             json.dumps({"finding": {"title": f.rule.title if f else "", "summary": f.summary if f else ""},
                                         **names}), EDIT_SCHEMA)
        if js and js.get("kind") in ALLOWED:
            e = {k: v for k, v in js.items() if v is not None}
            try:
                parse_edit(e)
                m, _, preview = apply_edit(base_model.copy(), e)
                r = analyse(m, list(groups)).by_key().get(check_key)
                cands.append({"label": f"AI idea: {preview}", "edit": e, "preview": preview, "needs": None,
                              "verdict": r.status if r else "na", "required": r.required if r else None,
                              "measured": r.measured if r else None, "summary": r.summary if r else "",
                              "verified_by": "Rule engine", "ai": True})
            except (EditRefused, Exception) as ex:  # noqa: BLE001
                cands.append({"label": f"AI idea refused: {e.get('kind')}", "edit": e, "verdict": "refused",
                              "rejected": True, "reason": str(ex), "ai": True})
    out = []
    for i, c in enumerate(cands, 1):
        row = {"n": i, **{k: c.get(k) for k in ("label", "edit", "needs", "verdict", "required", "measured",
                                                "summary", "verified_by", "ai", "reason")}}
        if c.get("rejected") or c.get("verdict") not in ("pass",):
            row["rejected"] = True
            row["simulated"] = False
            out.append(row)
            continue
        sc = Scenario(**{k: v for k, v in scenario.items() if k in Scenario.__dataclass_fields__})
        m = base_model.copy()
        if c.get("edit"):
            m, _, _ = apply_edit(m, c["edit"])
            tag = f"{revision} + fix {i}"
        else:   # widen the stair: structural, modelled as a flight width override
            stair = (c.get("label") or "").split("Stair ")[-1].split(" ")[0]
            w = (c.get("required") or {}).get("value")
            mm = int("".join(ch for ch in c["label"].split(" to ")[-1] if ch.isdigit()) or 0) if " to " in c["label"] else w
            sc.stair_width_override = {stair: mm / 1000}
            tag = f"{revision} + fix {i}"
        st = svc.start(m, sc, FIX_RUNS, revision=tag, label=f"{sc.label()} · fix {i}: {c['label']}")
        row.update({"simulated": True, "sim_id": st["id"], "state": st["state"]})
        out.append(row)
    return {"finding": finding_id, "scenario": scenario, "runs_each": FIX_RUNS, "candidates": out,
            "rejected": sum(1 for r in out if r.get("rejected"))}
