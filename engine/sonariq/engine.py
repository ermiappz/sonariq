"""Analyse a model with rule packs; diff revisions; work out the re-run set (the ping)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .checks import CHECKS, CheckResult, evidence_bbox
from .model import Model
from .rules import DISCIPLINES, PACK_GROUPS, Rule, expand_packs, load_rules

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
    rules = rules or load_rules()
    packs = expand_packs(groups)
    ctx: dict[str, Any] = {}
    results: list[CheckResult] = []
    na: list[dict] = []
    for rule in rules:
        if rule.pack not in packs:
            continue
        ok, why = applicable(rule, model)
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
              groups=list(groups or ["fls", "acc", "dnv"]), scope=scope)
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
        "required": r.required,
        "measured": r.measured,
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


def run_dict(run: Run, model: Model | None = None, include_pass: bool = True) -> dict:
    checks = [check_dict(r, run, model) for r in run.results]
    findings = [c for c in checks if c["status"] in ("fail", "warn", "unk")]
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
        "not_applicable": run.na,
    }


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
