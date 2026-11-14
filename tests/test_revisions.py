"""Model revisions (spec B11): export saves Rev A, B, C…; saved revisions are frozen; compare by element ID."""
import io
import json
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient

PACKS = ["fls", "acc", "dnv"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from sonariq import api, revisions
    for name, f in (("RUNS", "runs"), ("REPORTS", "reports.json"), ("VIEWS", "views.json"), ("INCORRECT", "incorrect.json"),
                    ("TASKS", "tasks.json")):
        monkeypatch.setattr(api, name, tmp_path / f)
    monkeypatch.setattr(revisions, "DB", tmp_path / "revisions.sqlite")
    monkeypatch.setattr(api, "DATA", tmp_path)   # reset archives into tmp, never the real data/
    monkeypatch.setattr(api, "_LAST_RUN", {})
    monkeypatch.setenv("SONARIQ_RATE_LIMIT", "0")
    return TestClient(api.app)


def analyse(c, rev, **kw):
    r = c.post("/analyse", json={"revision": rev, "scope": "deck:5", "packs": PACKS, **kw})
    assert r.status_code == 200, r.text
    return r.json()["run_meta"]


def export(c, run_id, fmt="bcf"):
    r = c.post("/revisions/export", json={"run_id": run_id, "format": fmt})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_b_fix2_timeline_and_diff_counts(client):
    a = analyse(client, "A")
    assert a["draft"]["state"] == "draft" and a["draft"]["label"] == "Rev A"
    ra = export(client, a["id"], "bcf")
    b = analyse(client, "B")
    assert b["draft"]["label"] == "Rev B"                     # new work after an export opens the next draft
    rb = export(client, b["id"], "report")
    f = analyse(client, "Bfix2")
    rc = export(client, f["id"], "csv")
    assert [ra["counts"]["fail"], rb["counts"]["fail"], rc["counts"]["fail"]] == [1, 4, 3]
    models = client.get("/revisions").json()["models"]
    assert [m["name"] for m in models] == ["Deck 5 demo"]
    assert [(r["label"], r["state"]) for r in models[0]["revisions"]] == [("Rev A", "saved"), ("Rev B", "saved"), ("Rev C", "saved")]

    ab = client.get("/revisions/compare", params={"a": ra["id"], "b": rb["id"]}).json()
    assert sorted(x["id"] for x in ab["new_findings"]) == ["F-07", "F-08", "F-09"]   # OR-117: three new fails
    assert ab["cleared"] == [] and len(ab["still_open"]) == 3                     # F-01 fail + one warning + one cannot verify
    bc = client.get("/revisions/compare", params={"a": rb["id"], "b": rc["id"]}).json()
    assert [x["id"] for x in bc["cleared"]] == ["F-07"] and bc["new_findings"] == [] and len(bc["still_open"]) == 5
    assert all(x["match"] == "id" for x in ab["still_open"] + bc["still_open"]) and bc["fallback_matches"] == 0
    ac = client.get("/revisions/compare", params={"a": ra["id"], "b": rc["id"]}).json()
    assert sorted(x["id"] for x in ac["new_findings"]) == ["F-08", "F-09"] and ac["counts_delta"]["fail"] == 2
    # /runs/diff (Revisions screen) is the same function
    rd = client.get("/runs/diff", params={"a": a["id"], "b": b["id"]}).json()
    assert [x["check_key"] for x in rd["new_findings"]] == [x["check_key"] for x in ab["new_findings"]]


def test_draft_is_replaced_until_export_and_export_is_idempotent(client):
    r1 = analyse(client, "A")
    r2 = analyse(client, "B")
    assert r1["draft"]["id"] == r2["draft"]["id"] and r2["draft"]["run_id"] == r2["id"]
    s1 = export(client, r2["id"], "csv")
    s2 = export(client, r2["id"], "bcf")                     # a second export of the same run: the same revision
    assert s1["id"] == s2["id"] and s1["saved_at"] == s2["saved_at"] and s2["download"].endswith("/files/bcf")
    rep = client.post("/reports", json={"run_id": r2["id"]}).json()
    assert rep["saved_revision"]["id"] == s1["id"]
    assert client.get(f"/revisions/{s1['id']}/files/csv").text.count("\n") == 97   # header + 96 checks


def test_saved_revision_is_frozen_but_label_is_editable(client):
    from sonariq import revisions
    s = export(client, analyse(client, "B")["id"])
    with sqlite3.connect(revisions.DB) as c, pytest.raises(sqlite3.IntegrityError, match="cannot be changed"):
        c.execute("UPDATE revisions SET run_id = 'x' WHERE id = ?", (s["id"],))
    with sqlite3.connect(revisions.DB) as c, pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
        c.execute("DELETE FROM revisions WHERE id = ?", (s["id"],))
    r = client.patch(f"/revisions/{s['id']}", json={"label": "Rev B · OR-117 issued"})
    assert r.status_code == 200 and r.json()["label"] == "Rev B · OR-117 issued"
    assert client.patch(f"/revisions/{s['id']}", json={"label": " "}).status_code == 422
    folder = revisions.folder(s)
    assert all(not (p.stat().st_mode & 0o222) for p in folder.iterdir())   # files are read-only on disk too


def test_bundle_holds_everything(client):
    run = analyse(client, "B")
    client.post("/incorrect", json={"check_key": "R-FLS-04|2y9ZtcBKjQFBti02X9WcIg", "finding": "F-09", "reason": "door is A-60 in the schedule"})
    s = export(client, run["id"], "bcf")
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/revisions/{s['id']}/bundle").content))
    assert sorted(z.namelist()) == ["checks.csv", "export.bcfzip", "report.json", "revision.json", "snapshot.json"]
    snap = json.loads(z.read("snapshot.json"))
    assert len(snap["model_file_sha256"]) == 64 and {"fire", "escape", "accessibility"} <= set(snap["rule_packs"])
    assert len(snap["run"]["checks"]) == 96 and snap["readiness"] and snap["accuracy"]
    assert list(snap["marks"]["incorrect"]) == ["R-FLS-04|2y9ZtcBKjQFBti02X9WcIg"]
    assert json.loads(z.read("report.json"))["open_findings"] == 5          # 6 findings, one marked incorrect
    # marks made after the save do not change it
    client.delete("/incorrect/R-FLS-04|2y9ZtcBKjQFBti02X9WcIg")
    again = client.get(f"/revisions/{s['id']}").json()["data"]["snapshot"]["marks"]["incorrect"]
    assert list(again) == ["R-FLS-04|2y9ZtcBKjQFBti02X9WcIg"]


def test_upload_choice_new_model_or_revision_of(client):
    demo = analyse(client, "A")["draft"]["model_id"]
    other = analyse(client, "B", new_model="Fire zone 3")["draft"]
    assert other["model_id"] != demo and other["label"] == "Rev A"
    into = analyse(client, "Bfix2", model_id=other["model_id"])["draft"]
    assert into["id"] == other["id"]                          # same model, its open draft
    assert client.post("/analyse", json={"revision": "A", "packs": PACKS, "model_id": 999}).status_code == 404


def test_fallback_match_needs_confirmation():
    from sonariq.revdiff import diff
    el = lambda g: {"guid": g, "name": "Door D-5-14", "ifc_class": "IfcDoor"}
    chk = lambda key, st, g: {"check_key": key, "id": "F-1", "rule": "R-FLS-04", "title": "t", "status": st,
                              "location": {"label": "Fr 140"}, "element": el(g)}
    d = diff({"checks": [chk("R-FLS-04|old", "fail", "old")]}, {"checks": [chk("R-FLS-04|new", "fail", "new")]})
    assert d["fallback_matches"] == 1 and d["still_open"][0]["match"] == "fallback" and d["new_findings"] == d["cleared"] == []


def test_reset_clears_revisions(client):
    export(client, analyse(client, "A")["id"])
    assert client.post("/admin/reset").status_code == 200
    assert client.get("/revisions").json()["models"] == []
