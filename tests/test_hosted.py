"""Hosted engine (VM): the FreeCAD panel uploads the IFC; only files inside data/ can be opened."""
from fastapi.testclient import TestClient

import sonariq.api as api
from sonariq.session import DATA


def test_upload_demo_file_maps_to_revision():
    c = TestClient(api.app)
    r = c.post("/upload?name=deck5_revB.ifc", content=(DATA / "deck5_revB.ifc").read_bytes()).json()
    assert r["revision"] == "B" and r["known"]
    j = c.post("/analyse", json={"revision": r["revision"]}).json()
    assert (j["counts"]["fail"], j["total_checks"]) == (4, 96)


def test_upload_other_file_is_stored_and_analysed():
    c = TestClient(api.app)
    body = (DATA / "deck5_revA.ifc").read_bytes().replace(b"Demo ship", b"Demo shiq")
    r = c.post("/upload?name=../../evil name.ifc", content=body).json()
    assert r["revision"] is None and "/uploads/" in r["path"] and ".." not in r["path"].split("/uploads/")[1]
    j = c.post("/analyse", json={"path": r["path"]}).json()
    assert j["total_checks"] == 96


def test_upload_rejects_non_ifc():
    assert TestClient(api.app).post("/upload", content=b"hello").status_code == 422


def test_hosted_blocks_paths_outside_data(monkeypatch):
    monkeypatch.setattr(api, "HOSTED", True)
    c = TestClient(api.app)
    assert c.post("/analyse", json={"path": "/etc/passwd"}).status_code == 403
    assert c.post("/analyse", json={"path": "data/../pyproject.toml"}).status_code == 403
    assert c.post("/analyse", json={"path": "data/deck5_revA.ifc"}).status_code == 200


def test_model_ifc_rejects_odd_ids():
    c = TestClient(api.app)
    assert c.get("/model/ifc/..%2F..%2Fpyproject").status_code == 404
    assert c.get("/model/ifc/A").status_code == 200


def test_bcf_download():
    c = TestClient(api.app)
    c.post("/analyse", json={"revision": "A"})
    r = c.post("/export/bcf").json()
    f = c.get(r["download"])
    assert f.status_code == 200 and f.content[:2] == b"PK"


def test_smoke_summary_aggregates_runs():
    from sim.service import smoke_summary
    runs = [{"smoke": {"people_exposed": n, "exposure_s_total": 10 * n, "rerouted": 1, "corridor_reached_s": 90.0}}
            for n in range(1, 101)]
    s = smoke_summary(runs)
    assert s["runs"] == 100 and s["people_exposed_max"] == 100 and s["rerouted_mean"] == 1.0
    assert 94 <= s["people_exposed_p95"] <= 96 and s["corridor_reached_s"] == 90.0
    assert smoke_summary([{"smoke": None}, {}]) is None


def test_selection_by_module(models):
    """Selecting a deck = Deck scope; an MVZ or a space = the elements inside it."""
    from sonariq.engine import analyse
    m = models["B"]
    deck = {g for g, c in m.containers.items() if c["class"] == "IfcBuildingStorey"}
    assert analyse(m, ["fls", "acc", "dnv"], "selection", deck).counts() == analyse(m, ["fls", "acc", "dnv"], "deck:5").counts()
    mvz4 = {e.guid for e in m.by_class("IfcZone") if e.name == "MVZ 4"}
    r = analyse(m, ["fls", "acc", "dnv"], "selection", mvz4)
    assert 0 < len(r.results) < 96 and r.counts()["fail"] == 3   # F-07, F-08, F-09 are all in MVZ 4
    cor = {m.by_name("COR-5-152-S").guid}
    names = {x.element.name for x in analyse(m, ["fls", "acc", "dnv"], "selection", cor).results if x.element}
    assert "COR-5-152-S" in names and len(names) > 1
