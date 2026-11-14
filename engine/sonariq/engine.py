"""Analyse a model with rule packs; diff revisions; work out the re-run set (the ping)."""
from __future__ import annotations

import re
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from .checks import CHECKS, CheckResult, evidence_bbox
from .model import Model
from .rules import DISCIPLINES, PACK_GROUPS, SOURCES, Rule, expand_packs, load_rules

STATUS_ORDER = ["fail", "warn", "unk", "pass", "dor"]
STATUS_WORD = {"fail": "Fail", "warn": "Warning", "unk": "Cannot verify", "pass": "Pass", "dor": "Dormant",
               "na": "Not applicable", "acc": "Accepted with reason"}
STATUS_GLYPH = {"fail": "✕", "warn": "!", "unk": "?", "pass": "✓", "dor": "○", "na": "—", "acc": "⚑"}


@dataclass
class Run:
    revision: str
    results: list[CheckResult]
    na: list[dict]
    duration_s: float
    groups: list[str]
    scope: str
    ids: dict[str, str] = field(default_factory=dict)   # check key -> finding id
    not_run: list[dict] = field(default_factory=list)   # rules that could not run: draft, or the model lacks the data
    readiness: dict | None = None

    def counts(self) -> dict[str, int]:
        c = {s: 0 for s in STATUS_ORDER}
        for r in self.results:
            c[r.status] = c.get(r.status, 0) + 1
        c["na"] = len(self.na)
        return c

    def by_key(self) -> dict[str, CheckResult]:
        return {r.key: r for r in self.results}


def applicable(rule: Rule, model: Model) -> tuple[bool, str]:
    a = rule.applicability or {}
    if "passengers_gt" in a:
        n = model.ship.get("passengers")
        if n is None:
            n = model.ship.get("persons_on_board")
        if n is not None and int(n) <= int(a["passengers_gt"]):
            return False, (f"Written for ships carrying more than {a['passengers_gt']} passengers; "
                           f"this vessel carries {n} persons ({model.ship.get('vessel_type', 'vessel')}).")
    if a.get("accessibility") and model.ship.get("accessibility") is False:
        return False, "Accessibility switched off in the vessel profile."
    return True, ""


def expand_selection(model: Model, selection: set[str] | None) -> set[str] | None:
    """Selection scope by module: a selected deck (storey) means everything on it, an MVZ (IfcZone) its spaces and
    what lies inside them, a space what touches it, the ship/site/project the whole model. Elements stay as they are."""
    if not selection:
        return selection
    out = set(selection)
    areas = []
    for g in selection:
        c = model.containers.get(g)
        if c is not None:
            if c["class"] == "IfcBuildingStorey":
                # contained elements, plus spaces/zones (aggregated, not contained) by their deck number
                num = next(iter(re.findall(r"\d+", c["name"])), None)
                out |= {e.guid for e in model.elements.values()
                        if e.storey == c["name"] or (num is not None and str(e.sq.get("deck")) == num)}
            else:   # project, site, building
                return {e.guid for e in model.elements.values()}
            continue
        e = model.elements.get(g)
        if e is None:
            continue
        if e.ifc_class == "IfcZone":
            out |= set(e.members)
            areas += [model.elements[m] for m in e.members if m in model.elements]
        elif e.ifc_class == "IfcSpace":
            areas.append(e)
    for a in areas:
        if a.poly is None:
            continue
        zone = a.poly.buffer(0.15)   # doors and walls on the boundary belong to the module too
        for e in model.elements.values():
            if e.poly is not None and (a.storey is None or e.storey in (None, a.storey)) and e.poly.intersects(zone):
                out.add(e.guid)
    return out


def in_scope(r: CheckResult, scope: str, selection: set[str] | None) -> bool:
    if scope in ("whole", "Whole model", None, ""):
        return True
    if scope == "selection":
        return bool(selection) and (r.element is not None and r.element.guid in selection)
    deck = scope.split(":")[-1].replace("Deck", "").strip() if scope.lower().startswith(("deck", "d")) else None
    if deck is None:
        return True
    loc = r.location or {}
    return loc.get("deck") in (None, deck) or str(loc.get("deck")) == deck


def analyse(model: Model, groups: list[str] | None = None, scope: str = "deck:5",
            selection: set[str] | None = None, rules: tuple[Rule, ...] | None = None) -> Run:
    t0 = time.perf_counter()
    if scope == "selection":
        selection = expand_selection(model, selection)
    rules = rules or load_rules()
    packs = expand_packs(groups)
    ctx: dict[str, Any] = {}
    results: list[CheckResult] = []
    na: list[dict] = []
    from .readiness import readiness
    rd = readiness(model)
    not_run: list[dict] = []
    for rule in rules:
        if rule.pack not in packs:
            continue
        ok, why = applicable(rule, model)
        pk = rd["packs"].get(rule.pack, {})
        if ok and (not rule.runs or pk.get("state") == "not_possible"):
            # shown as Cannot verify with the reason; never a verdict on an element
            not_run.append({"rule": rule.id, "title": rule.title, "ref": rule.ref, "status": "unk", "pack": rule.pack,
                            "group": rule.group, "reason": rule.not_run_reason if not rule.runs else pk["reason"],
                            "kind": "draft" if not rule.runs else "no_data"})
            continue
        if not ok:
            na.append({"rule": rule.id, "title": rule.title, "ref": rule.ref, "reason": why, "status": "na"})
            continue
        fn = CHECKS.get(rule.check)
        if fn is None:
            continue
        for r in fn(rule, model, ctx):
            if r.element is not None and r.element.sq.get("maturity") == "concept":
                r.extra["verdict_if_reported"] = r.status
                r.status = "dor"
            if in_scope(r, scope, selection):
                results.append(r)
    results.sort(key=lambda r: (r.rule.id, r.element.name if r.element else ""))
    run = Run(revision=model.revision, results=results, na=na, duration_s=time.perf_counter() - t0,
              groups=list(groups or ["fls", "acc", "dnv"]), scope=scope, not_run=not_run, readiness=rd)
    assign_ids(run)
    return run


def finding_prefix(r: CheckResult) -> str:
    if r.rule.pack == "hvac":
        return "H"
    return {"fail": "F", "warn": "W", "unk": "U"}[r.status]


def assign_ids(run: Run) -> None:
    seen: dict[str, int] = {}
    for r in run.results:
        if r.status not in ("fail", "warn", "unk"):
            continue
        base = f"{finding_prefix(r)}-{r.rule.finding_no:02d}"
        n = seen.get(base, 0) + 1
        seen[base] = n
        run.ids[r.key] = base if n == 1 else f"{base}.{n}"


# ---------------------------------------------------------------- serialisation
# check function -> (measured, required) provenance: kind + what is read. "derived" = SonarIQ computes it from the
# named inputs; "model" = a property as the file states it; "public" = the rule's threshold from its source.
PROV = {
    "door_fire_class": (("model", "Pset_DoorCommon.FireRating"), ("model", "host wall Pset_WallCommon.FireRating")),
    "window_fire_class": (("model", "Pset_WindowCommon.FireRating"), ("model", "host wall Pset_WallCommon.FireRating")),
    "door_self_closing": (("model", "Pset_DoorCommon.SelfClosing"), ("public", None)),
    "mvz_bulkhead_class": (("model", "Pset_WallCommon.FireRating"), ("public", None)),
    "stair_enclosure_class": (("model", "Pset_WallCommon.FireRating"), ("public", None)),
    "mvz_length": (("derived", "extent of the zone's space footprints"), ("public", None)),
    "stair_width_formula": (("model", "IfcStairFlight clear width (geometry)"), ("derived", "FSS formula from persons per deck")),
    "stair_min_width": (("model", "IfcStairFlight clear width (geometry)"), ("public", None)),
    "dead_end": (("derived", "corridor depth from the space footprint and the corridor graph"), ("derived", "corridor clear width")),
    "corridor_width": (("derived", "short side of the corridor space footprint"), ("public", None)),
    "door_clear_width": (("model", "IfcDoor.OverallWidth"), ("public", None)),
    "duct_damper": (("model", "IfcDamper near the crossing"), ("public", None)),
    "plate_thickness": (("derived", "vertical extent of the IfcPlate solid"), ("derived", "t0 formula with ship length")),
}


def _with_prov(v: dict | None, kind_prop, r: CheckResult, model: Model | None, which: str) -> dict | None:
    if not v or v.get("provenance") or not kind_prop:
        return v
    kind, prop = kind_prop
    if kind == "public":
        p = {"kind": "public", "source": r.rule.ref, "verified_against_official_text": r.rule.verified_against_official_text}
    else:
        p = {"kind": kind, "file": Path(model.path).name if model and model.path else None,
             "element": r.element.guid if r.element else None, "prop": prop}
        if kind == "derived":
            p["inputs"] = sorted(r.depends_on)[:12]
    return {**v, "provenance": p}


def check_dict(r: CheckResult, run: Run, model: Model | None = None) -> dict:
    e = r.element
    d = {
        "id": run.ids.get(r.key),
        "check_key": r.key,
        "rule": r.rule.id,
        "title": (r.rule.unk_title if r.status == "unk" and r.rule.unk_title else r.rule.title),
        "source": r.rule.source,
        "clause": r.rule.clause,
        "ref": r.rule.ref,
        "clause_text": r.rule.clause_text,
        "reading": r.rule.reading,
        "rule_status": r.rule.status,
        "verified_against_official_text": r.rule.verified_against_official_text,
        "source_group": SOURCES.get(r.rule.source, r.rule.source),
        "to_verify": r.rule.status != "verified",
        "pack": r.rule.pack,
        "group": r.rule.group,
        "discipline": r.rule.discipline,
        "discipline_label": DISCIPLINES.get(r.rule.discipline, r.rule.discipline),
        "status": r.status,
        "status_word": STATUS_WORD[r.status],
        "glyph": STATUS_GLYPH[r.status],
        "element": None if e is None else {"guid": e.guid, "name": e.name, "ifc_class": e.ifc_class},
        "location": r.location,
        "required": _with_prov(r.required, PROV.get(r.rule.check, (None, None))[1], r, model, "required"),
        "measured": _with_prov(r.measured, PROV.get(r.rule.check, (None, None))[0], r, model, "measured"),
        "margin": r.margin,
        "summary": r.summary,
        "formula": r.formula,
        "method": r.method,
        "missing": r.missing,
        "depends_on": sorted(r.depends_on),
        "revision": run.revision,
        "extra": r.extra,
        "engine": "Rule engine",
    }
    if model is not None:
        els = [model.elements.get(g) for g in r.depends_on if not g.startswith(("berths:", "members:"))]
        d["evidence"] = {"guids": [e.guid] if e else [], "related": [x.guid for x in els if x is not None],
                         "bbox": (evidence_bbox(e) or evidence_bbox(*[model.elements.get(g) for g in e.parts]))
                         if e is not None else None,
                         "z": None if e is None else (e.z0 if e.z0 is not None else
                                                      next((model.elements[g].z0 for g in e.parts
                                                            if g in model.elements), None))}
    return d


COMPACT_OVER = 2000   # whole-ship runs: passes as compact rows, findings in full (B6; a 36k-check run is 70 MB in full)


def run_dict(run: Run, model: Model | None = None, include_pass: bool = True) -> dict:
    compact = len(run.results) > COMPACT_OVER
    keep = [r for r in run.results if not compact or r.status != "pass"]
    checks = [check_dict(r, run, model) for r in keep]
    findings = [c for c in checks if c["status"] in ("fail", "warn", "unk")]
    passes = [[r.rule.id, r.element.guid if r.element else None, r.element.name if r.element else None,
               (r.location or {}).get("deck"), r.summary] for r in run.results if compact and r.status == "pass"]
    by_group: dict[str, dict] = {}
    for g in run.groups:
        meta = PACK_GROUPS.get(g, {"label": g, "packs": [g]})
        rs = [r for r in run.results if r.rule.group == g]
        rules_in = [r for r in load_rules() if r.pack in meta["packs"]]
        verified = all(r.status == "verified" for r in rules_in) if rules_in else False
        c = {s: 0 for s in STATUS_ORDER}
        for r in rs:
            c[r.status] += 1
        by_group[g] = {"label": meta["label"], "sources": meta.get("sources"), "checks": len(rs), "counts": c,
                       "pack_status": "Verified" if g in ("fls", "acc") else ("To verify" if g == "dnv" else
                                                                             ("Verified" if verified else "To verify")),
                       "short": meta.get("short")}
    return {
        "revision": run.revision,
        "scope": run.scope,
        "groups": run.groups,
        "duration_s": round(run.duration_s, 3),
        "total_checks": len(run.results),
        "counts": run.counts(),
        "by_group": by_group,
        "findings": findings,
        "checks": checks if include_pass else findings,
        "compact": compact,
        "passes": passes,              # compact: [rule, element guid, element name, deck, summary] per pass
        "by_rule": _by_rule(run),
        "not_applicable": run.na,
        "not_run": run.not_run,
        "readiness": run.readiness,
        "rules_verified_against_official_text": _verified_count(run),
    }


def _by_rule(run: Run) -> dict:
    out: dict[str, dict] = {}
    for r in run.results:
        d = out.setdefault(r.rule.id, {"title": r.rule.title, "source_group": SOURCES.get(r.rule.source, r.rule.source),
                                       "ref": r.rule.ref, "group": r.rule.group, "counts": {s: 0 for s in STATUS_ORDER}})
        d["counts"][r.status] += 1
    return out


def _verified_count(run: Run) -> dict:
    rs = [r for r in load_rules() if r.pack in expand_packs(run.groups)]
    return {"verified": sum(1 for r in rs if r.verified_against_official_text), "total": len(rs)}


# ---------------------------------------------------------------- impact analysis (the ping)
def touched_keys(model: Model, guids: set[str]) -> set[str]:
    """Derived dependency keys touched by a set of changed/added/removed elements."""
    keys = set()
    for g in guids:
        e = model.elements.get(g)
        if e is None or e.ifc_class != "IfcSpace":
            continue
        mvz = e.sq.get("mvz")
        keys.add(f"members:{mvz}")
        if e.sq.get("category") == "cabin":
            keys.add(f"berths:{e.sq.get('deck')}:{mvz}")
    return keys


def diff(a: Model, b: Model) -> dict[str, set[str]]:
    fa = {g: e.fingerprint() for g, e in a.elements.items()}
    fb = {g: e.fingerprint() for g, e in b.elements.items()}
    added = set(fb) - set(fa)
    removed = set(fa) - set(fb)
    changed = {g for g in set(fa) & set(fb) if fa[g] != fb[g]}
    keys = touched_keys(a, removed | changed) | touched_keys(b, added | changed)
    return {"added": added, "removed": removed, "changed": changed, "keys": keys}


def impact(model_a: Model, run_a: Run, model_b: Model, run_b: Run) -> dict:
    d = diff(model_a, model_b)
    touched = d["added"] | d["removed"] | d["changed"] | d["keys"]
    ka, kb = run_a.by_key(), run_b.by_key()
    rerun = []
    for k, r in kb.items():
        deps = set(r.depends_on)
        if k in ka:
            deps |= ka[k].depends_on
        if k not in ka or deps & touched:
            rerun.append(k)
    rerun_set = set(rerun)
    changed, value_changed = [], []
    for k in rerun:
        rb, ra = kb[k], ka.get(k)
        if ra is None or ra.status != rb.status:
            changed.append({"key": k, "id": run_b.ids.get(k) or run_a.ids.get(k), "from": ra.status if ra else None,
                            "to": rb.status, "title": rb.rule.title, "location": rb.location,
                            "summary": rb.summary})
        elif (rb.measured or {}).get("value") is not None and (
                (ra.measured or {}).get("value") != (rb.measured or {}).get("value") or
                (ra.required or {}).get("value") != (rb.required or {}).get("value")):
            value_changed.append({"key": k, "id": run_b.ids.get(k), "status": rb.status, "title": rb.rule.title,
                                  "from": (ra.measured or {}).get("value"), "to": (rb.measured or {}).get("value"),
                                  "location": rb.location})
    # dependency-index completeness: anything outside the re-run set must be unchanged
    stale = [k for k, r in kb.items() if k not in rerun_set and k in ka and
             (ka[k].status != r.status or (ka[k].measured or {}).get("value") != (r.measured or {}).get("value"))]
    removed_checks = [k for k in ka if k not in kb]
    names = lambda m, gs: sorted(m.elements[g].name for g in gs if g in m.elements)  # noqa: E731
    return {
        "from": run_a.revision, "to": run_b.revision,
        "added": names(model_b, d["added"]), "removed": names(model_a, d["removed"]),
        "changed_elements": names(model_b, d["changed"]), "derived_keys": sorted(d["keys"]),
        "rerun": len(rerun), "rerun_keys": sorted(rerun), "changed": changed, "value_changed": value_changed,
        "removed_checks": removed_checks, "stale": stale,
        "counts_before": run_a.counts(), "counts_after": run_b.counts(),
    }
