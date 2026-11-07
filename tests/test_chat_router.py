"""Chat router: words -> the right card, without the AI (SONARIQ_AI=off in conftest)."""
import pytest

from sonariq.chat import SIM_WORDS, Chat, parse_edit_words


@pytest.mark.parametrize("text", [
    "simulate night",
    "night with FD-5-165P out",
    "day without stair 3B",
    "FD-5-165P is closed at night",
    "D-5-171-S blocked",
    "what if stair 3A is out?",
])
def test_simulate_words(text):
    assert SIM_WORDS.search(text)


@pytest.mark.parametrize("text", [
    "set FD-5-165P to A-60",
    "upgrade door FD-5-165P to an A-60 fire door",
    "widen D-5-171-P to 950 mm",
    "why is F-07 failing?",
])
def test_not_simulate_words(text):
    assert not SIM_WORDS.search(text)


class _S:  # minimal session stand-in: the router only needs names and the model's classes here
    def __init__(self, model):
        self.model = model


def test_edit_words_fire_class(models):
    names = Chat(_S(models["A"])).names()
    e = parse_edit_words("upgrade door FD-5-165P to an A-60 fire door", names)
    assert e == {"kind": "set_door_fire_class", "door": "FD-5-165P", "fire_class": "A-60"}


def test_simulate_off_says_so(models):
    r = Chat(_S(models["A"]), sim_service=None).ask("simulate night")
    card = r["cards"][0]
    assert card["type"] == "error" and "make api-sim" in card["text"]


def test_deck_scope_falls_back_to_whole_model_and_back(tmp_path):
    """Opening a file with no Deck 5 (an RCRV deck) must not show 0 checks; going back to Rev A must reload it."""
    import shutil
    from fastapi.testclient import TestClient
    import sonariq.api as api
    from sonariq.session import DATA
    c = TestClient(api.app)
    # a copy of Rev A whose deck property says Deck 3 stands in for an RCRV deck file
    src = (DATA / "deck5_revA.ifc").read_text(encoding="utf-8")
    p = tmp_path / "deck3.ifc"
    p.write_text(src.replace("IFCLABEL('5')", "IFCLABEL('3')"), encoding="utf-8")
    if "IFCLABEL('3')" not in p.read_text(encoding="utf-8"):
        shutil.copy(DATA / "deck5_revA.ifc", p)   # deck stored differently: only check the reopen below
    else:
        j = c.post("/analyse", json={"path": str(p)}).json()
        assert j["total_checks"] > 0 and j["scope"] == "whole" and "scope_note" in j
    c.post("/analyse", json={"path": str(p)})
    j = c.post("/analyse", json={"revision": "A"}).json()
    assert j["total_checks"] == 96 and j["scope"] == "deck:5" and "scope_note" not in j
