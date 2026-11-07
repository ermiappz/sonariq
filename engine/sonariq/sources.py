"""RAG uses: evidence-card source text, cited 'why' answers, and draft-rule-from-clause. RAG never sets a verdict.

Drafts are written to rules/drafts/*.yaml with status 'draft'; the engine only loads rules/seed_rules.yaml, so a
draft never runs until a human moves it into the rulebook.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import yaml

from .rag import LINK_ONLY, get_rag

ROOT = Path(__file__).resolve().parents[2]
DRAFTS = ROOT / "rules" / "drafts"
CHECKS = ["door_fire_class", "window_fire_class", "door_self_closing", "mvz_bulkhead_class", "stair_enclosure_class",
          "mvz_length", "stair_width_formula", "stair_min_width", "dead_end", "corridor_width", "door_clear_width",
          "duct_damper", "plate_thickness", "placeholder"]

# public guidance to search per rule family (SOLAS/FSS full text is not public: we show our reading + related
# public text, and say so)
QUERY_HINT = {   # by rule id: the words the public text uses for the same requirement
    "R-ACC-01": "clear width of walking surfaces 36 inches minimum",
    "R-ACC-02": "door openings shall provide a clear width of 32 inches minimum",
    "R-FLS-03": "stairs specific flow clear width persons evacuation", "R-FLS-04": "corridor clear width specific flow",
    "R-FLS-10": "self-closing fire doors", "R-FLS-02": "dead end corridor",
}


def finding_sources(finding: dict, k: int = 3) -> dict:
    rag = get_rag()
    rule = finding.get("rule")
    q = f"{finding.get('title')}. {finding.get('clause_text')} {QUERY_HINT.get(rule or '', '')}"
    src_name = (finding.get("source") or "")
    pref = "pvag" if src_name.startswith("PVAG") else "ada2010" if src_name.startswith("ADA") else None
    first = rag.search(QUERY_HINT.get(rule or "") or f"{finding.get('clause_text')} {finding.get('title')}", 2,
                       source=pref) if pref else []
    hits = first + [h for h in rag.search(q, k + 2) if h["source"] != "meyer_qa" and h["citation"] not in
                    {f["citation"] for f in first}]
    own = [h for h in rag.search(f"{rule} {finding.get('title')}", 3, source="sonariq_rules") if h["para"] == rule]
    public = [h for h in hits if h["source"] not in ("sonariq_rules",)][:k]
    note = None
    if (finding.get("source") or "").startswith(("SOLAS", "FSS")):
        note = ("SOLAS and the FSS Code are not public, so the clause is shown as our reading; the public texts "
                "below are related guidance, not the clause itself.")
    if (finding.get("source") or "").startswith("DNV"):
        note = "DNV rules are linked, not copied."
    return {"finding": finding.get("id"), "reading": own[:1], "public": public, "note": note,
            "links": LINK_ONLY if (finding.get("source") or "").startswith("DNV") else [],
            "backend": rag.backend}


WHY_SYSTEM = (
    "You answer an engineer's 'why' question about a ship design compliance finding. Use only the finding JSON and "
    "the source excerpts given. The rule engine already decided the verdict; never change it. Every number you write "
    "must appear in the facts. Cite sources in square brackets with their citation, e.g. [ADA 2010 §404.2.3]. "
    "Two to four short sentences of plain text, no formula markup. No product or vendor names."
)


def why(llm, finding: dict, question: str, fallback: str) -> dict:
    src = finding_sources(finding)
    facts = {"finding": llm.slim(finding),
             "sources": [{"citation": h["citation"], "text": h["text"][:600]} for h in (src["reading"] + src["public"])]}
    out = llm.guarded(WHY_SYSTEM, facts, question, fallback)
    cites = re.findall(r"\[([^\]]+)\]", out["text"]) if out["source"] == "ai" else []
    known = {h["citation"] for h in src["reading"] + src["public"]}

    def ok(c):   # "SonarIQ R-FLS-03" matches "SonarIQ R-FLS-03 (reading of ...)"; the clause ref of a reading is ours
        return any(k == c or k.startswith(c) or c in k for k in known)
    out["citations"] = [c for c in cites if ok(c)]
    out["unknown_citations"] = [c for c in cites if not ok(c)]
    out["sources"] = src
    return out


DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"}, "source": {"type": "string"}, "clause": {"type": "string"},
        "clause_text": {"type": "string", "description": "quoted from the source excerpt"},
        "reading": {"type": "string", "description": "how a rule engine would test it on IFC data"},
        "applies_to": {"type": "string"}, "inputs": {"type": "array", "items": {"type": "string"}},
        "check": {"type": "string", "enum": CHECKS},
        "params": {"type": "object", "properties": {"min_mm": {"type": ["number", "null"]},
                                                    "min_in": {"type": ["number", "null"]},
                                                    "required": {"type": ["string", "null"]},
                                                    "max_m": {"type": ["number", "null"]}}},
        "pack": {"type": "string", "enum": ["fire", "escape", "accessibility", "hvac", "dnv"]},
    },
    "required": ["title", "source", "clause", "clause_text", "reading", "applies_to", "inputs", "check", "params", "pack"],
}
DRAFT_SYSTEM = ("You draft a rule for a ship design rule engine from a regulation excerpt. Quote the clause text from "
                "the excerpt. Pick the closest existing check function; use 'placeholder' if none fits. Every number "
                "must come from the excerpt. The draft is reviewed by an engineer before it can run.")


def draft_rule(llm, query: str) -> dict:
    rag = get_rag()
    hits = [h for h in rag.search(query, 3) if h["source"] not in ("sonariq_rules", "meyer_qa")]
    if not hits:
        return {"ok": False, "error": "No public source text found for that clause."}
    src = hits[0]
    js, how = llm.ask_json(DRAFT_SYSTEM, json.dumps({"request": query, "excerpt": {"citation": src["citation"],
                                                                                  "text": src["text"]}}), DRAFT_SCHEMA)
    if not js:
        return {"ok": False, "error": f"AI unavailable ({how}); the source text is shown so you can write the rule.",
                "source": src}
    from .llm import check_numbers
    bad = check_numbers(json.dumps({k: js.get(k) for k in ("clause_text", "reading", "params")}), src["text"] + " " + query)
    js["params"] = {k: v for k, v in (js.get("params") or {}).items() if v is not None}
    draft = {"id": "R-DRAFT-" + dt.datetime.now().strftime("%H%M%S"), "finding_no": 99, "discipline":
             {"accessibility": "accessibility", "dnv": "structure", "hvac": "hvac"}.get(js["pack"], "fire_life_safety"),
             **js, "status": "draft", "severity": "fail", "applicability": {},
             "drafted_from": src["citation"], "drafted_by": f"AI ({llm.gateway.name}) · needs human approval"}
    return {"ok": not bad, "draft": draft, "source": src, "numbers_not_in_source": bad, "alternatives": hits[1:]}


def approve_draft(draft: dict, by: str) -> dict:
    DRAFTS.mkdir(parents=True, exist_ok=True)
    d = dict(draft, approved_by=by, approved_at=dt.datetime.now().isoformat(timespec="seconds"), status="draft")
    p = DRAFTS / f"{d['id']}.yaml"
    p.write_text(yaml.safe_dump({"rules": [d]}, sort_keys=False, allow_unicode=True))
    return {"ok": True, "path": str(p.relative_to(ROOT)),
            "note": "Saved as a draft. It runs only after it is moved into rules/seed_rules.yaml and its status set."}
