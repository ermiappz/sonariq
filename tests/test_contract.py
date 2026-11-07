"""The sample-data table in design/handoff.md is the contract: the engine must produce these numbers."""
import pytest

from sonariq.edits import EditRefused, apply_edit, propose_fixes
from sonariq.engine import analyse, impact, run_dict


def counts(run):
    c = run.counts()
    return (c["fail"], c["warn"], c["unk"], c["pass"], c["dor"])


def ids(run):
    return sorted(run.ids.values())


def test_rev_a_counts_and_split(models):
    run = analyse(models["A"])
    assert len(run.results) == 96
    assert counts(run) == (1, 1, 1, 89, 4)
    d = run_dict(run)
    assert [d["by_group"][g]["checks"] for g in ("fls", "acc", "dnv")] == [64, 20, 12]
    assert ids(run) == ["F-01", "U-01", "W-01"]


def test_rev_a_findings_match_handoff(models):
    run = analyse(models["A"])
    f = {run.ids[r.key]: r for r in run.results if r.key in run.ids}
    assert f["F-01"].element.name == "FD-5-165P" and f["F-01"].location["label"] == "Deck 5 · Fr 165 · P"
    assert f["F-01"].summary == "MVZ 4/5 bulkhead · fitted A-0, required A-60"
    assert f["W-01"].location["label"] == "Deck 5 · Fr 152 · S" and f["W-01"].measured["value"] == 900
    assert f["U-01"].element.name == "D-5-171-S"


def test_rev_b_counts_and_findings(models):
    run = analyse(models["B"])
    assert counts(run) == (4, 1, 1, 86, 4)
    assert ids(run) == ["F-01", "F-07", "F-08", "F-09", "U-01", "W-01"]
    f = {run.ids[r.key]: r for r in run.results if r.key in run.ids}
    assert f["F-07"].location["label"] == "Stair 3B · Decks 4–7"
    assert f["F-08"].location["label"] == "Deck 5 · Fr 146–150 · P"
    assert f["F-09"].location["label"] == "Deck 5 · Fr 152 · S"
    assert (f["F-09"].measured["value"], f["F-09"].required["value"]) == (850, 900)


def test_rev_b_fix2_counts(models):
    assert counts(analyse(models["Bfix2"])) == (3, 1, 1, 87, 4)


def test_every_finding_has_deck_frame_side(models):
    for rev in ("A", "B"):
        run = analyse(models[rev], ["fls", "acc", "dnv", "hvac"])
        for r in run.results:
            loc = r.location
            if r.rule.check in ("mvz_length",):
                assert loc["deck"] and loc["frame"]
                continue
            assert loc["deck"] and loc["frame"] and loc["side"] in ("P", "S", "C"), (r.key, loc)


def test_impact_a_to_b(models):
    A, B = models["A"], models["B"]
    ra, rb = analyse(A), analyse(B)
    im = impact(A, ra, B, rb)
    assert sorted(c["id"] for c in im["changed"]) == ["F-07", "F-08", "F-09"]
    assert im["stale"] == []          # nothing outside the re-run set changed: dependency index is complete
    # 11 checks touch the change on this deck (design says 14; see docs/DECISIONS.md #17)
    assert im["rerun"] == 11
    assert any(v["id"] == "W-01" for v in im["value_changed"])   # W-01: value changed, status unchanged


def test_hvac_h01(models):
    run = analyse(models["A"], ["hvac"])
    f = {run.ids[r.key]: r for r in run.results if r.key in run.ids}
    assert list(f) == ["H-01"] and f["H-01"].element.name == "VD-5-03"


# ---------------------------------------------------------------- edits and fixes
def test_edit_guard_refuses_anything_else(models):
    for bad in ({"kind": "delete_wall", "wall": "BHD-5-165"}, {"kind": "set_berths"}, "rm -rf", {}):
        with pytest.raises(EditRefused):
            apply_edit(models["A"], bad)


def test_add_cabin_block_on_rev_a_reproduces_the_ripple(models):
    A = models["A"]
    m, _, preview = apply_edit(A, {"kind": "add_cabin_block", "frame_from": 140, "count": 4})
    assert "8 berths" in preview
    run = analyse(m)
    by = {(r.rule.id, r.element.name): r for r in run.results}
    assert by[("R-FLS-03", "Stair 3B")].required["value"] == 1380
    assert by[("R-FLS-02", "COR-5-148-P")].status == "fail"
    assert A.by_name("CAB-5-OR117-1") is None     # original untouched


def test_set_door_fire_class_clears_f01_only(models):
    A = models["A"]
    ra = analyse(A)
    m, _, _ = apply_edit(A, {"kind": "set_door_fire_class", "door": "FD-5-165P", "fire_class": "A-60"})
    rm = analyse(m)
    assert counts(rm) == (0, 1, 1, 90, 4)
    im = impact(A, ra, m, rm)
    assert [c["id"] for c in im["changed"]] == ["F-01"]


def test_move_wall_900_keeps_pvag_warning(models):
    m, _, _ = apply_edit(models["B"], {"kind": "move_wall", "space": "COR-5-152-S", "width_mm": 900})
    run = analyse(m)
    by = {(r.rule.id, r.element.name): r.status for r in run.results}
    assert by[("R-FLS-04", "COR-5-152-S")] == "pass" and by[("R-ACC-01", "COR-5-152-S")] == "warn"


def test_fixes_for_f07(models):
    B = models["B"]
    rb = analyse(B)
    key = [k for k, v in rb.ids.items() if v == "F-07"][0]
    fixes = propose_fixes(B, rb, key)
    got = [(f["label"], f["verdict"], f["required"]["value"], f.get("rejected", False)) for f in fixes]
    assert got[0][1] == "pass" and "1,400" in got[0][0] and fixes[0]["needs"] == "Structure"
    assert got[1][1:] == ("pass", 1340, False)
    assert got[2][1:] == ("pass", 1320, False)
    assert got[3][1:] == ("fail", 1380, True)
