"""The AI never sets a verdict and never invents a number (gate 'Honest explanations')."""
import pytest

from sonariq.llm import check_numbers, template_explanation
from sonariq.session import Session


@pytest.fixture(scope="module")
def sess():
    s = Session("B")
    s.analyse()
    return s


def test_honest_text_passes(sess):
    f = sess.finding("F-07")
    ok = "Stair 3B needs 1,380 mm and has 1,350 mm: 68 people on Deck 5, 44 on Deck 6, 40 on Deck 4 and 24 on Deck 7."
    assert check_numbers(ok, f) == []


def test_invented_number_is_rejected(sess):
    f = sess.finding("F-07")
    assert check_numbers("Stair 3B needs 1,400 mm.", f) == ["1,400"]
    assert check_numbers("About 72 people use it.", f) == ["72"]


def test_template_uses_only_engine_numbers(sess):
    for fid in ("F-01", "F-07", "F-08", "F-09", "W-01", "U-01"):
        f = sess.finding(fid)
        assert check_numbers(template_explanation(f), f) == [], fid


def test_explain_without_endpoint_is_engine_text(sess, monkeypatch):
    sess.llm.enabled = False
    out = sess.explain("F-07")
    assert out["source"] == "template" and "1,380" in out["text"]


def test_session_preview_then_confirm_then_ping():
    s = Session("A")
    s.analyse()
    p = s.apply_edit({"kind": "set_door_fire_class", "door": "FD-5-165P", "fire_class": "A-60"})
    assert p["confirm_required"] and s.run.counts()["fail"] == 1      # preview changes nothing
    r = s.apply_edit({"kind": "set_door_fire_class", "door": "FD-5-165P", "fire_class": "A-60"}, confirm=True)
    assert [c["id"] for c in r["ping"]["changed"]] == ["F-01"] and r["ping"]["counts_after"]["fail"] == 0


def test_revision_switch_ping_and_bcf(tmp_path):
    s = Session("A")
    s.analyse()
    im = s.switch_revision("B")
    assert sorted(c["id"] for c in im["changed"]) == ["F-07", "F-08", "F-09"]
    s.accept("F-08", "Agreed with class: recess kept as service access")
    out = s.export_bcf(str(tmp_path / "sonariq_rev-b.bcfzip"))
    assert out["topics"] == 6 and out["decisions"] == 1
