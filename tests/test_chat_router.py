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
