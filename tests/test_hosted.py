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
