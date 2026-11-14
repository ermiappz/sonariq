"""What changed between two runs (before → after), the one diff behind /runs/diff and /revisions/compare (spec B11).
Checks are matched by element ID (the check key: rule + GlobalId). A finding left over on each side with the same rule
and the same element name (or, without an element, the same location) is matched as a fallback, which a person
should confirm: the element got a new ID, or it is a different element with the same name."""
from __future__ import annotations

BAD = ("fail", "warn", "unk")


def _row(c: dict, before: str | None, match: str) -> dict:
    return {"id": c.get("id"), "check_key": c["check_key"], "rule": c["rule"], "title": c["title"], "status": c["status"],
            "location": c["location"]["label"], "element": (c.get("element") or {}).get("name"), "before": before, "match": match}


def _fallback_key(c: dict) -> tuple:
    return (c["rule"], (c.get("element") or {}).get("name") or c["location"]["label"])


def diff(a: dict, b: dict) -> dict:
    """a, b: run dicts with `checks`. Findings = fail / warn / cannot verify."""
    ca = {c["check_key"]: c for c in a["checks"]}
    cb = {c["check_key"]: c for c in b["checks"]}
    pairs = [(ca[k], cb[k], "id") for k in cb if k in ca]
    # fallback: unmatched on both sides, same rule + element name, only when that pairing is unambiguous
    la, lb = {}, {}
    for k in set(ca) - set(cb):
        la.setdefault(_fallback_key(ca[k]), []).append(ca[k])
    for k in set(cb) - set(ca):
        lb.setdefault(_fallback_key(cb[k]), []).append(cb[k])
    gone, added = [c for k, cs in la.items() for c in cs], [c for k, cs in lb.items() for c in cs]
    for key, cs in lb.items():
        if len(cs) == 1 and len(la.get(key, [])) == 1:
            pairs.append((la[key][0], cs[0], "fallback"))
            gone.remove(la[key][0])
            added.remove(cs[0])
    new, resolved, still, changed = [], [], [], []
    for o, c, how in pairs:
        if o["status"] in BAD and c["status"] in BAD:
            still.append(_row(c, o["status"], how))
            if o["status"] != c["status"]:
                changed.append(_row(c, o["status"], how))   # still a finding, with another verdict
        elif c["status"] in BAD:
            new.append(_row(c, o["status"], how))
        elif o["status"] in BAD:
            resolved.append({**_row(c, o["status"], how), "id": o.get("id")})   # passing checks carry no finding id
        elif o["status"] != c["status"]:
            changed.append(_row(c, o["status"], how))
    for c in added:
        (new if c["status"] in BAD else changed).append(_row(c, None, "new"))
    for o in gone:
        if o["status"] in BAD:
            resolved.append({**_row(o, o["status"], "removed"), "status": "removed"})
    keys = ("fail", "warn", "unk", "pass", "dor", "na")
    count = lambda r: {k: sum(1 for c in r["checks"] if c["status"] == k) for k in keys}
    na, nb = a.get("counts") or count(a), b.get("counts") or count(b)
    return {"new_findings": new, "cleared": resolved, "still_open": still, "changed": changed,
            "fallback_matches": sum(1 for _, _, h in pairs if h == "fallback"),
            "counts_delta": {k: nb.get(k, 0) - na.get(k, 0) for k in keys},
            "added_checks": len(added), "removed_checks": len(gone)}
