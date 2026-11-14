"""Ground-truth harness (spec B5): any missed finding, false alarm, missed expected pass, or count that differs from
the independent scan fails CI."""
from pathlib import Path

import pytest

from sonariq.accuracy import compare, scenarios, truth
from sonariq.engine import analyse, run_dict
from sonariq.model import load_ifc

ROOT = Path(__file__).resolve().parents[1]
HAS_RCRV = (ROOT / "data/models/rcrv/web/meta.json").exists() and (ROOT / "data/rcrv/gltf/properties.jsonl").exists()


def _run(gt: dict) -> dict:
    if gt["revision"] == "RCRV":
        from sonariq.rcrv_model import load_rcrv
        m = load_rcrv()
    else:
        m = load_ifc(ROOT / "data" / f"{gt['scenario']}.ifc", gt["revision"])
    return run_dict(analyse(m, gt["packs"], gt["scope"]), m)


@pytest.mark.parametrize("scenario", scenarios())
def test_ground_truth(scenario):
    gt = truth(scenario)
    if gt["revision"] == "RCRV" and not HAS_RCRV:
        pytest.skip("RCRV data not on this machine (not in git)")
    r = compare(scenario, _run(gt))
    assert not r["missed"], r["missed"]
    assert not r["false_alarms"], r["false_alarms"][:10]
    assert r["passes_ok"] == r["passes_expected"]
    assert r["scan_match"], r["scan_mismatch"]
    assert r["counts_match"], r["count_mismatch"]
    assert r["found"] == r["expected"] > 0


def test_scenarios_present():
    assert {"deck5_revA", "deck5_revB", "rcrv_structure"} <= set(scenarios())
