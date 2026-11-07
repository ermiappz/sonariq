"""Words -> scenario JSON. A code parser handles the demo phrases; the AI (JSON mode) is only a fallback.
The result is always validated against the model (stair and space names must exist) and shown to the
engineer as a preview to confirm. The AI never runs a simulation by itself.
"""
from __future__ import annotations

import re

SCHEMA = {
    "type": "object",
    "properties": {
        "case": {"type": "string", "enum": ["night", "day"]},
        "route": {"type": "string", "enum": ["primary", "secondary"]},
        "closed_stair": {"type": ["string", "null"], "description": "stair name such as 3A, or null"},
        "closed_door": {"type": ["string", "null"], "description": "door name such as FD-5-165P, or null"},
        "fire_origin": {"type": ["string", "null"], "description": "space name from the list, or null"},
        "revision": {"type": ["string", "null"], "enum": ["A", "B", "Bfix2", None]},
    },
    "required": ["case", "route", "closed_stair", "closed_door", "fire_origin", "revision"],
}

SYSTEM = ("You turn an engineer's request into an evacuation scenario JSON for a ship deck. Use only stair and "
          "space names from the lists given. Night = cabins full, day = public spaces busy. 'Secondary' means one "
          "stair is out of use. Never invent names; use null when unsure.")


def parse(text: str, stairs: list[str], spaces: list[str], doors: list[str] | None = None) -> dict | None:
    """Deterministic parser for common phrasings. Returns None when it cannot read the request."""
    t = text.lower().strip()
    if not t:
        return None
    out = {"case": None, "route": "primary", "closed_stair": None, "closed_door": None, "fire_origin": None,
           "revision": None}
    for d in doors or []:
        if d.lower() in t and re.search(r"\b(out|closed|blocked|jammed|unavailable|lost|lose|without|no)\b", t):
            out["closed_door"], out["route"] = d, "secondary"
            break
    if re.search(r"\bnight|nighttime|asleep|sleeping|cabins? full\b", t):
        out["case"] = "night"
    elif re.search(r"\bday|daytime|afternoon|lunch|public spaces? (busy|full)\b", t):
        out["case"] = "day"
    m = re.search(r"stair(?:way|case)?\s*([0-9][a-z])\b[^.]*?\b(out|closed|blocked|unavailable|lost|not available|"
                  r"out of use|out of service)", t) or \
        re.search(r"\b(without|lose|lost|close|closing|block|no)\s+(?:the\s+)?stair(?:way|case)?\s*([0-9][a-z])\b", t)
    if m:
        g = [x for x in m.groups() if x and re.fullmatch(r"[0-9][a-z]", x)]
        if g and g[0].upper() in stairs:
            out["closed_stair"] = g[0].upper()
            out["route"] = "secondary"
    if re.search(r"\bsecondary\b", t):
        out["route"] = "secondary"
    m = re.search(r"\bfire\b", t)
    if m:
        name = next((s for s in spaces if s.lower() in t), None)
        if not name:
            near = re.search(r"(?:near|by|next to|at|blocks?(?: the)? (?:approach|way) to)\s+(?:the\s+)?stair\s*([0-9][a-z])", t)
            if near:
                out["fire_origin"] = f"@near:{near.group(1).upper()}"   # resolved against the geometry later
        else:
            out["fire_origin"] = name
    if re.search(r"\bfix ?2\b", t):
        out["revision"] = "Bfix2"
    elif re.search(r"\brev(?:ision)?\.? ?b\b|or-?117", t):
        out["revision"] = "B"
    elif re.search(r"\brev(?:ision)?\.? ?a\b", t):
        out["revision"] = "A"
    if out["case"] is None:
        if not (out["closed_stair"] or out["fire_origin"] or "simulat" in t or "evacuat" in t):
            return None
        out["case"] = "night"      # Circ.1533 night cases usually govern; shown in the preview to confirm
    return out


def validate(sc: dict, stairs: list[str], spaces: list[str], doors: list[str] | None = None) -> list[str]:
    errs = []
    if sc.get("case") not in ("night", "day"):
        errs.append("case must be night or day")
    if sc.get("closed_stair") and sc["closed_stair"] not in stairs:
        errs.append(f"no stair {sc['closed_stair']} on this deck")
    fo = sc.get("fire_origin")
    if fo and not fo.startswith("@near:") and fo not in spaces:
        errs.append(f"no space {fo} on this deck")
    if sc.get("closed_door") and doors is not None and sc["closed_door"] not in doors:
        errs.append(f"no door {sc['closed_door']} on this deck")
    if sc.get("route") == "secondary" and not (sc.get("closed_stair") or sc.get("closed_door")):
        errs.append("secondary case needs a stair or door out of use")
    return errs


def from_words(text: str, stairs: list[str], spaces: list[str], llm=None, doors: list[str] | None = None) -> dict:
    sc = parse(text, stairs, spaces, doors)
    source = "parser"
    if sc is None and llm is not None:
        import json
        js, src = llm.ask_json(SYSTEM, json.dumps({"request": text, "stairs": stairs, "spaces": spaces,
                                                   "doors": [d for d in (doors or []) if d.startswith("FD-")]}), SCHEMA)
        if js:
            sc, source = js, f"ai ({src})"
    if sc is None:
        return {"ok": False, "source": source, "errors": ["Could not read a scenario from that. Try: "
                                                          "'simulate night', 'day with stair 3A out of use'."]}
    errs = validate(sc, stairs, spaces, doors)
    return {"ok": not errs, "scenario": sc, "source": source, "errors": errs, "confirm_required": True}
