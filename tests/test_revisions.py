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
    monkeypatch.setattr(api, "_SNAPS", {})
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
    assert a["draft"]["state"] == "draft" and a["draft"]["label"] == "Rev A"   # the seeded Rev A takes the run
    ra = export(client, a["id"], "bcf")
    b = analyse(client, "B")
    assert b["draft"]["label"] == "Rev B"
    rb = export(client, b["id"], "report")
    f = analyse(client, "Bfix2")
    rc = export(client, f["id"], "csv")
    assert [ra["counts"]["fail"], rb["counts"]["fail"], rc["counts"]["fail"]] == [1, 4, 3]
    models = client.get("/revisions").json()["models"]
    assert models[0]["name"] == "Deck 5"
    assert [(r["label"], r["state"]) for r in models[0]["revisions"]] == [("Rev A", "saved"), ("Rev B", "saved"), ("Fix 2", "saved")]

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
    r1 = analyse(client, "B")
    r2 = analyse(client, "B")
    assert r1["draft"]["id"] == r2["draft"]["id"] and r2["draft"]["run_id"] == r2["id"]   # same file: same draft
    assert analyse(client, "A")["draft"]["id"] != r2["draft"]["id"]                         # another file: its own revision
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
    assert client.post("/incorrect", json={"check_key": "R-FLS-04|2y9ZtcBKjQFBti02X9WcIg", "finding": "F-09", "reason": "door is A-60 in the schedule"}).status_code == 200
    s = export(client, run["id"], "bcf")
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/revisions/{s['id']}/bundle").content))
    assert sorted(z.namelist()) == ["checks.csv", "export.bcfzip", "report.json", "revision.json", "snapshot.json"]
    snap = json.loads(z.read("snapshot.json"))
    assert len(snap["model_file_sha256"]) == 64 and {"fire", "escape", "accessibility"} <= set(snap["rule_packs"])
    assert len(snap["run"]["checks"]) == 96 and snap["readiness"] and snap["accuracy"]
    assert list(snap["marks"]["incorrect"]) == ["R-FLS-04|2y9ZtcBKjQFBti02X9WcIg"]
    assert json.loads(z.read("report.json"))["open_findings"] == 5          # 6 findings, one marked incorrect
    # a saved revision is read-only: marks cannot change it
    assert client.delete("/incorrect/R-FLS-04|2y9ZtcBKjQFBti02X9WcIg").status_code == 409
    again = client.get(f"/revisions/{s['id']}").json()["data"]["snapshot"]["marks"]["incorrect"]
    assert list(again) == ["R-FLS-04|2y9ZtcBKjQFBti02X9WcIg"]


def test_upload_choice_new_model_or_revision_of(client):
    demo = analyse(client, "A")["draft"]["model_id"]
    other = analyse(client, "B", new_model="Fire zone 3")["draft"]
    assert other["model_id"] != demo and other["label"] == "Rev A"
    into = analyse(client, "Bfix2", model_id=other["model_id"])["draft"]
    assert into["model_id"] == other["model_id"] and into["label"] == "Rev B"   # same model, a new file: next revision
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
    ps = client.get("/projects").json()["projects"]          # re-seeded: Demo ship, nothing analysed
    assert [p["name"] for p in ps] == ["Demo ship"] and all(r["run_id"] is None for m in ps[0]["models"] for r in m["revisions"])


def _tree(c):
    p = c.get("/projects").json()["projects"][0]
    return p, {m["name"]: m for m in p["models"]}


def test_seed_demo_ship_and_scoped_tasks_and_marks(client):
    p, ms = _tree(client)
    assert p["name"] == "Demo ship" and [r["label"] for r in ms["Deck 5"]["revisions"]] == ["Rev A", "Rev B", "Fix 2"]
    rev_b = ms["Deck 5"]["revisions"][1]
    assert client.get(f"/revisions/{rev_b['id']}").json()["data"] is None          # opened, not analysed
    run = analyse(client, None, revision_id=rev_b["id"])
    assert run["draft"]["id"] == rev_b["id"]
    key = "R-FLS-04|2y9ZtcBKjQFBti02X9WcIg"
    q = {"revision_id": rev_b["id"]}
    assert client.put(f"/tasks/{key}", params=q, json={"column": "doing"}).status_code == 200
    assert client.post("/incorrect", json={"check_key": key, "reason": "lining", "revision_id": rev_b["id"]}).status_code == 200
    rev_a = ms["Deck 5"]["revisions"][0]["id"]
    assert client.get("/tasks", params={"revision_id": rev_a}).json()["tasks"] == {}          # nothing leaks to Rev A
    assert client.get("/incorrect", params={"revision_id": rev_a}).json()["incorrect"] == {}
    assert key in client.get("/tasks", params=q).json()["tasks"] and key in client.get("/incorrect", params=q).json()["incorrect"]
    # save (Export): frozen with its marks and tasks; analysing it again opens a new draft that starts with them
    s = export(client, run["id"], "report")
    snap = client.get(f"/revisions/{s['id']}").json()["data"]["snapshot"]
    assert key in snap["marks"]["incorrect"]
    assert client.put(f"/tasks/{key}", params=q, json={"column": "done"}).status_code == 409
    nxt = analyse(client, None, revision_id=rev_b["id"])["draft"]
    assert nxt["id"] != rev_b["id"] and nxt["label"] == "Rev D" and nxt["file"] == "deck5_revB.ifc"
    assert client.get("/tasks", params={"revision_id": nxt["id"]}).json()["tasks"][key]["column"] == "doing"


def test_projects_create_rename_upload_and_demo_project_is_throwaway(client):
    from sonariq import revisions
    p = client.post("/projects", json={"name": "Hull 1384"}).json()
    assert client.patch(f"/projects/{p['id']}", json={"name": "Hull 1385"}).json()["name"] == "Hull 1385"
    assert client.post("/projects", json={"name": " "}).status_code == 422
    r = client.post(f"/projects/{p['id']}/models", json={"revision": "B", "name": "Zone 3"}).json()
    assert r["source"] == "demo:B" and r["run_id"] is None
    r2 = client.post(f"/projects/{p['id']}/models/{r['model_id']}/revisions", json={"revision": "Bfix2"}).json()
    assert r2["label"] == "Rev B" and r2["model_id"] == r["model_id"]
    assert client.delete(f"/projects/{p['id']}").status_code == 409            # a real project is never deleted
    d = client.post("/projects/demo").json()
    assert d["demo"] == 1 and [x["label"] for x in d["models"][0]["revisions"]] == ["Rev A", "Rev B"]
    assert all(x["id"] != d["id"] for x in client.get("/projects").json()["projects"])
    ra = d["models"][0]["revisions"][0]
    run = analyse(client, None, revision_id=ra["id"])
    export(client, run["id"])                                                   # a saved revision in the demo project …
    assert client.delete(f"/projects/{d['id']}").status_code == 200             # … still goes with it
    assert client.get(f"/projects/{d['id']}").status_code == 404
    assert client.get(f"/runs/{run['id']}").status_code == 404
    # expired demo projects are purged on the next listing
    d2 = client.post("/projects/demo").json()
    with sqlite3.connect(revisions.DB) as c:
        c.execute("UPDATE projects SET expires = '2000-01-01T00:00:00' WHERE id = ?", (d2["id"],))
    client.get("/projects")
    assert client.get(f"/projects/{d2['id']}").status_code == 404


def test_step7_store_is_migrated(tmp_path, client):
    from sonariq import revisions
    with sqlite3.connect(revisions.DB) as c:
        c.executescript("""
          CREATE TABLE models (id INTEGER PRIMARY KEY, name TEXT NOT NULL, created TEXT NOT NULL);
          CREATE TABLE revisions (id INTEGER PRIMARY KEY, model_id INTEGER NOT NULL, seq INTEGER NOT NULL, label TEXT NOT NULL,
            state TEXT NOT NULL, run_id TEXT NOT NULL, file TEXT, file_sha TEXT, counts TEXT, created TEXT NOT NULL, saved_at TEXT);
          INSERT INTO models VALUES (1, 'Deck 5 demo', 't'), (2, 'Fire zone 3', 't');
          INSERT INTO revisions VALUES (1, 1, 1, 'Rev A', 'saved', 'r1', 'deck5_revA.ifc', NULL, NULL, 't', 't'),
                                       (2, 2, 1, 'Rev A', 'draft', 'r2', 'zone3.ifc', NULL, NULL, 't', NULL);""")
    ps = {p["name"]: p for p in client.get("/projects").json()["projects"]}
    assert set(ps) == {"Demo ship", "Earlier uploads"}
    assert [r["run_id"] for m in ps["Demo ship"]["models"] for r in m["revisions"]] == [None] * len([r for m in ps["Demo ship"]["models"] for r in m["revisions"]])
    assert ps["Earlier uploads"]["models"][0]["revisions"][0]["run_id"] == "r2"
    assert list((tmp_path / "archive").glob("*-projects/revisions.sqlite"))
