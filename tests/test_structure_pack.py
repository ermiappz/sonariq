"""Structure & systems pack, readiness, provenance and compact runs (spec B2-B4, DECISIONS M7, M10)."""
import time
from pathlib import Path

import pytest

from sonariq.engine import COMPACT_OVER, analyse, run_dict
from sonariq.model import load_ifc
from sonariq.readiness import readiness
from sonariq.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]
HAS_RCRV = (ROOT / "data/models/rcrv/web/meta.json").exists()
UI_DEFAULT = ["fls", "acc", "dnv", "sts"]       # the Studio's FIRE + HULL + INT chips


@pytest.mark.parametrize("rev,counts", [("A", (1, 1, 1, 89, 4)), ("B", (4, 1, 1, 86, 4))])
def test_golden_path_unchanged_with_the_new_pack(rev, counts):
    m = load_ifc(ROOT / f"data/deck5_rev{rev}.ifc", rev)
    d = run_dict(analyse(m, UI_DEFAULT, "deck:5"), m)
    assert tuple(d["counts"][s] for s in ("fail", "warn", "unk", "pass", "dor")) == counts
    assert {n["rule"] for n in d["not_run"]} == {r.id for r in load_rules() if r.pack in ("structure_systems", "data_quality")}


def test_every_finding_value_has_provenance():
    m = load_ifc(ROOT / "data/deck5_revB.ifc", "B")
    d = run_dict(analyse(m, UI_DEFAULT), m)
    for f in d["findings"]:
        if f["status"] in ("fail", "warn") and f["measured"]:
            assert f["measured"].get("provenance", {}).get("kind") in ("model", "derived"), f["id"]
            assert f["required"].get("provenance", {}).get("kind") in ("model", "derived", "public"), f["id"]


def test_new_rules_are_honest_about_official_text():
    new = [r for r in load_rules() if r.pack in ("structure_systems", "data_quality")]
    assert new and not any(r.verified_against_official_text for r in new)
    s6 = next(r for r in new if r.id == "R-STR-02")
    assert not s6.runs and "not in SonarIQ" in s6.not_run_reason


def test_readiness_deck5():
    rd = readiness(load_ifc(ROOT / "data/deck5_revB.ifc", "B"))
    assert rd["inventory"]["spaces"] == 90 and rd["inventory"]["doors_with_fire_rating"] == 67
    assert rd["packs"]["fire"]["state"] == "partial" and rd["packs"]["fire"]["n"] == 1
    assert rd["packs"]["structure_systems"]["state"] == "not_possible"


@pytest.mark.skipif(not HAS_RCRV, reason="RCRV tiles not built (data/rcrv is not in git)")
def test_rcrv_whole_ship_under_two_seconds_and_compact():
    from sonariq.rcrv_model import load_rcrv
    m = load_rcrv()
    rd = readiness(m)
    assert rd["packs"]["fire"]["state"] == "not_possible" and "No spaces" in rd["packs"]["fire"]["reason"]
    t = time.perf_counter()
    run = analyse(m, ["sts"], "whole")
    assert time.perf_counter() - t < 2.0
    d = run_dict(run, m)
    assert len(run.results) > COMPACT_OVER and d["compact"]
    assert all(c["status"] != "pass" for c in d["checks"]) and len(d["passes"]) == d["counts"]["pass"]
    sys = [c for c in d["checks"] if c["rule"] == "R-SYS-01" and c["status"] == "warn"]
    assert sys and all(c["measured"]["provenance"]["kind"] == "model" for c in sys)
    assert d["counts"]["fail"] == 0      # nothing in this pack is a Fail: missing approval evidence is a warning
