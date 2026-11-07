"""Chat router: words -> a preview card. Code parsers first, the AI (JSON mode) only as a fallback.

Nothing changes until the engineer confirms a card. Rules and simulation compute; the AI suggests and explains.
Cards: edit_preview, scenario_preview, explain, fixes, sim_progress, sim_result, ping, error.
"""
from __future__ import annotations

import json
import re

from .edits import ALLOWED, EditRefused, parse_edit

WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "a": 1, "an": 1,
           "single": 1, "double": 2}
FIRE = r"(A-60|A-30|A-15|A-0|B-15|B-0)"

EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(ALLOWED) + ["none"]},
        "frame_from": {"type": ["number", "null"]}, "count": {"type": ["integer", "null"]},
        "berths_per_cabin": {"type": ["integer", "null"]}, "change_request": {"type": ["string", "null"]},
        "space": {"type": ["string", "null"]}, "door": {"type": ["string", "null"]},
        "width_mm": {"type": ["number", "null"]}, "fire_class": {"type": ["string", "null"]},
    },
    "required": ["kind"],
}
EDIT_SYSTEM = ("You turn an engineer's requested design change into one edit JSON. Allowed kinds only: "
               "add_cabin_block (frame_from, count, berths_per_cabin, change_request), move_wall (space, width_mm), "
               "set_door_width (door, width_mm), set_door_fire_class (door, fire_class). Use names from the lists. "
               "If the request is not one of these, kind = none. Never invent names or numbers not in the request.")


def _num(tok: str | None) -> int | None:
    if tok is None:
        return None
    tok = tok.lower()
    return WORDNUM.get(tok) if tok in WORDNUM else int(tok) if tok.isdigit() else None


def parse_edit_words(t: str, names: dict) -> dict | None:
    """Deterministic edit parser for common phrasings. Returns an edit dict or None."""
    s = t.strip()
    low = s.lower()
    m = re.search(r"\b(add|insert|put|fit|place)\s+(?:a\s+block\s+of\s+)?(\d+|one|two|three|four|five|six|seven|eight|a|an)\s+"
                  r"(?:(single|double|one|two|\d)[- ]?berth\s+)?cabins?", low)
    if m:
        count = _num(m.group(2))
        bpc = _num(m.group(3)) if m.group(3) else None
        mb = re.search(r"(\d|one|two|three|four|single|double)[- ]?berths?\b(?! cabins? (?:for|instead))", low)
        if bpc is None and mb:
            bpc = _num(mb.group(1))
        mf = re.search(r"\bfr(?:ame)?s?\.?\s*(\d+(?:\.\d+)?)", low)
        cr = re.search(r"\b(or-?\d+)\b", low)
        e = {"kind": "add_cabin_block", "count": count, "berths_per_cabin": bpc or 2,
             "change_request": cr.group(1).upper().replace("OR", "OR-").replace("--", "-") if cr else "OR-117"}
        if mf:
            e["frame_from"] = float(mf.group(1))
        elif cr or "inboard" in low:
            e["frame_from"] = 140.0      # OR-117's block position on the GA (handoff.md); shown in the preview
        else:
            return {"kind": "add_cabin_block", "count": count, "berths_per_cabin": bpc or 2, "_missing": "frame_from"}
        return e
    door = next((d for d in names["doors"] if d.lower() in low), None)
    if door:
        mc = re.search(FIRE, s, re.I)
        if mc and re.search(r"\b(class|rating|fire|make|set|change|fit|upgrade)\b", low):
            return {"kind": "set_door_fire_class", "door": door, "fire_class": mc.group(1).upper()}
        mw = re.search(r"(\d{3,4})\s*mm", low)
        if mw and re.search(r"\b(widen|width|wide|wider|make|set|change)\b", low):
            return {"kind": "set_door_width", "door": door, "width_mm": float(mw.group(1))}
    space = next((n for n in names["spaces"] if n.lower() in low), None)
    if space and space.startswith("COR"):
        mw = re.search(r"(\d{3,4})\s*mm", low)
        if mw and re.search(r"\b(wall|widen|width|wide|wider|move)\b", low):
            return {"kind": "move_wall", "space": space, "width_mm": float(mw.group(1))}
    return None


SIM_WORDS = re.compile(r"\b(simulat\w*|evacuat\w*|what[- ]if|replay|run (?:a |the )?(?:night|day)|"
                       r"fire(?!\s*(?:door|class|rating|damper|division|integrity))|smoke|"
                       r"stair\s*[0-9][a-z]\s*(?:is\s+)?(?:out|closed|blocked|unavailable))\b", re.I)
FIX_WORDS = re.compile(r"\b(apply|use|take|do)\s+(?:the\s+)?fix\s*(\d)\b|\bfix\s*(\d)\b", re.I)
WHY_WORDS = re.compile(r"^\s*(why|what|how|explain|which|where|is|does|can)\b", re.I)
CHANGE_WORDS = re.compile(r"\b(add|put|insert|remove|delete|move|make|change|set|widen|narrow|replace|build|fit)\b", re.I)
FINDING = re.compile(r"\b([FWUH]-\d{2})\b", re.I)


class Chat:
    def __init__(self, session, sim_service=None, rag=None):
        self.S = session
        self.sim = sim_service
        self.rag = rag
        self.context_finding: str | None = None
        self.last_sim: dict = {}

    def names(self) -> dict:
        m = self.S.model
        return {"doors": sorted(e.name for e in m.by_class("IfcDoor")),
                "spaces": sorted(e.name for e in m.by_class("IfcSpace")),
                "stairs": sorted(e.name.replace("Stair ", "") for e in m.by_class("IfcStair"))}

    # ------------------------------------------------------------------ entry
    def ask(self, text: str, finding: str | None = None) -> dict:
        text = (text or "").strip()
        if finding:
            self.context_finding = finding
        names = self.names()
        mf = FINDING.search(text)
        if mf:
            self.context_finding = mf.group(1).upper()
        # 1. fix N -> the engine's Nth fix option for the finding (default: the stair finding)
        m = FIX_WORDS.search(text)
        if m and not SIM_WORDS.search(text):
            return self._fix_card(int(m.group(2) or m.group(3)))
        # 2. simulate
        if SIM_WORDS.search(text) and self.sim is not None:
            return self._scenario_card(text, names)
        # 3. edits
        e = parse_edit_words(text, names)
        src = "parser"
        if e is None and not WHY_WORDS.search(text):
            js, s = self.S.llm.ask_json(EDIT_SYSTEM, json.dumps({"request": text, "doors": names["doors"][:80],
                                                                 "corridors": [n for n in names["spaces"] if n.startswith("COR")]}),
                                        EDIT_SCHEMA)
            if js and js.get("kind") in ALLOWED:
                e = {k: v for k, v in js.items() if v is not None}
                src = f"ai ({s})"
        if e is not None:
            return self._edit_card(e, src)
        if CHANGE_WORDS.search(text) and not WHY_WORDS.search(text):
            return {"cards": [{"type": "error", "refused": True, "allowed": list(ALLOWED),
                               "text": "That is not one of the four allowed edits: add a cabin block, move a corridor "
                                       "wall, set a door width, set a door fire class. Nothing was changed."}]}
        # 4. questions -> explanation with sources
        return self._explain_card(text)

    # ------------------------------------------------------------------ cards
    def _edit_card(self, e: dict, src: str) -> dict:
        if e.get("_missing"):
            return {"cards": [{"type": "error", "text": f"Which frame should the block start at? Say for example "
                                                        f"'add {e['count']} cabins at Fr 140'."}]}
        try:
            parse_edit(e)
            pv = self.S.preview_edit(e)
        except (EditRefused, Exception) as ex:  # noqa: BLE001
            return {"cards": [{"type": "error", "refused": True, "text": f"Edit refused: {ex}",
                               "allowed": list(ALLOWED)}]}
        return {"cards": [{"type": "edit_preview", "text": pv["preview"], "edit": pv["edit"], "source": src,
                           "confirm": {"kind": "edit", "edit": pv["edit"]}}]}

    def _fix_card(self, n: int) -> dict:
        fid = self.context_finding if self.context_finding and self.context_finding.startswith("F") else "F-07"
        try:
            fixes = self.S.propose_fixes(fid)
        except KeyError:
            return {"cards": [{"type": "error", "text": f"{fid} is not open in this revision."}]}
        if not 1 <= n <= len(fixes):
            return {"cards": [{"type": "error", "text": f"{fid} has {len(fixes)} fix options."}]}
        f = fixes[n - 1]
        if f.get("rejected") or not f.get("edit"):
            return {"cards": [{"type": "fixes", "finding": fid, "fixes": fixes,
                               "text": f"Fix {n} cannot be applied as an edit here: {f['label']}"
                                       + (" (needs Structure)" if f.get("needs") else " (rejected by the rule engine)")}]}
        card = self._edit_card(f["edit"], f"fix {n} for {fid}")
        card["cards"][0]["fix"] = {"n": n, "finding": fid, "label": f["label"], "verdict": f.get("verdict"),
                                   "required": f.get("required"), "measured": f.get("measured"),
                                   "verified_by": f.get("verified_by")}
        return card

    def _scenario_card(self, text: str, names: dict) -> dict:
        from sim.words import from_words
        from sim.smoke import origin_near_stair
        from sim.geometry import build
        g = build(self.S.model)
        r = from_words(text, list(g.stairs), list(g.spaces), self.S.llm, list(g.doors))
        if not r["ok"]:
            return {"cards": [{"type": "error", "text": "; ".join(r["errors"])}]}
        sc = r["scenario"]
        if (sc.get("fire_origin") or "").startswith("@near:"):
            sc["fire_origin"] = origin_near_stair(g, sc["fire_origin"].split(":", 1)[1])
        rev = sc.pop("revision", None)
        from sim.runner import Scenario
        scen = Scenario(case=sc.get("case", "night"), route=sc.get("route", "primary"),
                        closed_stair=sc.get("closed_stair"), closed_door=sc.get("closed_door"),
                        fire_origin=sc.get("fire_origin"))
        model_label = rev or f"{self.S.model.revision} (open model{', with edits' if self._edited() else ''})"
        return {"cards": [{"type": "scenario_preview", "text": scen.label(), "scenario": scen.key(),
                           "model": model_label, "runs": 500, "source": r["source"],
                           "confirm": {"kind": "simulate", "scenario": scen.key(), "revision": rev, "runs": 500}}]}

    def _edited(self) -> bool:
        return any(h.get("event") == "edit" for h in self.S.history)

    def _explain_card(self, text: str) -> dict:
        fid = self.context_finding
        cards = []
        if self.last_sim.get("id") and re.search(r"\b(queue|replay|simulat|evacuat|stair clear|clears?|p95|density)\b", text, re.I):
            from sim.analyst import explain_results
            res = self.sim.results(self.last_sim["id"])
            out = explain_results(self.S.llm, res, text)
            cards.append({"type": "explain", "text": out["text"], "badge": out["badge"], "about": self.last_sim["id"]})
        elif fid:
            try:
                f = self.S.finding(fid)
            except KeyError:
                f = None
                cards.append({"type": "error", "text": f"{fid} is not open in Rev {self.S.model.revision}."})
            if f is not None and self.rag is not None:
                from .llm import template_explanation
                from .sources import why
                out = why(self.S.llm, f, text, template_explanation(f))
                badge = "AI explanation · numbers checked · sources cited" if out["source"] == "ai" else "Rule engine text"
                cards.append({"type": "explain", "text": out["text"], "badge": badge, "about": fid,
                              "citations": out["citations"]})
                src = out["sources"]["reading"] + out["sources"]["public"]
                if src:
                    cards.append({"type": "sources", "sources": src[:3], "note": out["sources"]["note"]})
            elif f is not None:
                out = self.S.explain(fid, text)
                cards.append({"type": "explain", "text": out["text"], "badge": out["badge"], "about": fid})
        elif self.rag is not None:
            src = self.rag.search(text, k=3)
            if src:
                cards.append({"type": "sources", "sources": src})
        if not cards:
            cards.append({"type": "error", "text": "Open a finding, or ask about one (for example 'why does F-07 fail?')."})
        return {"cards": cards}

    # ------------------------------------------------------------------ confirm
    def confirm(self, action: dict) -> dict:
        if action.get("kind") == "edit":
            r = self.S.apply_edit(action["edit"], confirm=True)
            p = r["ping"]
            return {"cards": [{"type": "ping", "text": r["applied"], "rerun": p["rerun"],
                               "changed": [{"id": c["id"], "status": c.get("status"), "title": c.get("title")}
                                           for c in p["changed"]],
                               "counts": p["counts_after"], "duration_s": p.get("duration_s")}]}
        if action.get("kind") == "simulate":
            from sim.runner import Scenario
            sc = action["scenario"]
            rev = action.get("revision")
            model = self.S.load(rev) if rev else self.S.model
            scen = Scenario(**{k: v for k, v in sc.items() if k in Scenario.__dataclass_fields__})
            st = self.sim.start(model, scen, action.get("runs") or 500, revision=rev or self._model_tag())
            self.last_sim = {"id": st["id"]}
            return {"cards": [{"type": "sim_progress", **st}]}
        return {"cards": [{"type": "error", "text": "Nothing to confirm."}]}

    def _model_tag(self) -> str:
        edits = [h["edit"] for h in self.S.history if h.get("event") == "edit"]
        if not edits:
            return self.S.model.revision
        last = edits[-1]
        tag = f"{self.S.model.revision} + edit"
        if last.get("kind") == "add_cabin_block":
            tag = f"{self.S.model.revision} + {last.get('count')}×{last.get('berths_per_cabin')} berth {last.get('change_request', '')}".strip()
        return tag
