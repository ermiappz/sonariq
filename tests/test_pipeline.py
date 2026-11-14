"""Model pipeline (DECISIONS M1-M4): IFC -> web tiles, ID map, metadata index, disciplines; ID mapping proof."""
import json
import re
from pathlib import Path

import pytest

from sonariq.engine import analyse, run_dict
from sonariq.model import load_ifc
from sonariq.pipeline.build import build
from sonariq.pipeline.disciplines import classify
from sonariq.pipeline.rcrv_source import inch_fraction_mm

ROOT = Path(__file__).resolve().parents[1]
RCRV_WEB = ROOT / "data" / "models" / "rcrv" / "web"


@pytest.fixture(scope="module")
def revb(tmp_path_factory):
    out = tmp_path_factory.mktemp("revb")
    ix = build(ROOT / "data" / "deck5_revB.ifc", out)
    return out, ix


def test_tiles_pack_without_loss(revb):
    out, ix = revb
    assert ix["integrity"] == {"vertex_mismatch": 0, "triangle_mismatch": 0}
    assert ix["max_quantization_dev_mm"] < 1.0
    assert ix["elements"] == 258 and ix["tris"] > 4000
    tiles = list((out / "tiles").glob("*.glb"))
    assert len(tiles) == len(ix["files"]) and all(t.read_bytes()[:4] == b"glTF" for t in tiles)
    assert (out / "colors.bin").stat().st_size == 4 * ix["elements"]
    # every element sits in exactly one tile range
    covered = sorted(i for f in ix["files"] for i in range(f["base"], f["base"] + f["n"]))
    assert covered == list(range(ix["elements"]))


def test_meta_fields(revb):
    out, ix = revb
    meta = json.loads((out / "meta.json").read_text())
    els = json.loads((out / "elements.json").read_text())
    assert len(meta) == len(els) == ix["elements"]
    for (gid, _src, cls, _name), m in zip(els, meta):
        assert re.fullmatch(r"[0-9A-Za-z_$]{22}", gid)
        assert m["discipline"] and len(m["bbox"]) == 6 and "deck" in m
        if cls == "IfcDoor" and m.get("fire_rating"):
            assert m["fire_rating"].startswith(("A", "B", "C"))
    assert ix["other"] == 0 and ix["disciplines"]["spaces"] == 90


def test_finding_ids_resolve_in_viewer_deck5_revB(revb):
    """Spec A1: element IDs match between engine findings and viewer geometry."""
    out, ix = revb
    ids = {e[0] for e in json.loads((out / "elements.json").read_text())}
    m = load_ifc(ROOT / "data" / "deck5_revB.ifc", "B")
    d = run_dict(analyse(m, scope="deck:5"), m)
    assert d["findings"]
    for f in d["checks"]:
        g = f["element"]["guid"] if f["element"] else None
        if g is None:
            continue
        assert g in ids or all(p in ids for p in ix["aliases"].get(g, [None])), (f["id"], f["rule"], g)


@pytest.mark.skipif(not (RCRV_WEB / "elements.json").exists(), reason="RCRV tiles not built (data/rcrv is not in git)")
@pytest.mark.parametrize("deck", [1, 5, 7])
def test_rcrv_ifc_globalids_resolve_in_tiles(deck):
    """Every element the engine reads from rcrv_deck_<n>.ifc is pickable in the whole-ship tiles (same GlobalId)."""
    ids = {e[0] for e in json.loads((RCRV_WEB / "elements.json").read_text())}
    text = (ROOT / "data" / "rcrv" / f"rcrv_deck_{deck}.ifc").read_text(errors="replace")
    prod = re.findall(r"=IFC(?:PLATE|MEMBER|PIPESEGMENT|DUCTSEGMENT|DOOR|WINDOW|STAIR|WALL|RAILING|COVERING|"
                      r"FURNISHINGELEMENT|CABLECARRIERSEGMENT|BUILDINGELEMENTPROXY)\('([^']{22})'", text)
    assert len(prod) > 1000
    missing = [g for g in prod if g not in ids]
    assert not missing, f"{len(missing)} of {len(prod)} missing, e.g. {missing[:3]}"


def test_inch_fractions():
    assert inch_fraction_mm('5/16"') == 7.9375
    assert inch_fraction_mm('1 1/2"') == 38.1
    assert inch_fraction_mm('2"') == 50.8
    assert inch_fraction_mm("thick") is None and inch_fraction_mm(None) is None


def test_discipline_rules():
    assert classify("IfcPlate") == "structure"
    assert classify("IfcDamper") == "hvac"
    assert classify(None, name="FIRE EXTINGUISHER 10LB") == "fire"
    assert classify("IfcBuildingElementProxy", name="SWITCHBOARD MAIN") == "electrical"
    assert classify(None, name="xyz", swbs="512") == "hvac"
    assert classify(None, name="xyz") == "other"
