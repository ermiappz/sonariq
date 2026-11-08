"""Review endpoints used by the portal and the panel: incorrect findings, reports, the run's own IFC, upload checks."""
import pytest
from fastapi.testclient import TestClient

import sonariq.api as api
from sonariq.session import DATA


@pytest.fixture
def c(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(api, "REPORTS", tmp_path / "reports.json")
    monkeypatch.setattr(api, "TASKS", tmp_path / "tasks.json")
    monkeypatch.setattr(api, "INCORRECT", tmp_path / "incorrect.json")
    monkeypatch.setenv("SONARIQ_RATE_LIMIT", "0")
    return TestClient(api.app)


def _run_b(c):
    j = c.post("/analyse", json={"revision": "B", "scope": "deck:5", "packs": ["fls", "acc", "dnv"]}).json()
    return j, {f["id"]: f for f in j["findings"]}


def test_incorrect_is_left_out_of_bcf_and_report_and_undo_restores(c):
    j, f = _run_b(c)
    u01 = f["U-01"]
    assert c.post("/incorrect", json={"check_key": u01["check_key"], "finding": "U-01", "reason": " "}).status_code == 422
    r = c.post("/incorrect", json={"check_key": u01["check_key"], "finding": "U-01", "reason": "B-class lining"})
    assert r.status_code == 200
    assert u01["check_key"] in c.get("/incorrect").json()["incorrect"]
    b = c.post("/export/bcf").json()
    assert b["excluded"] == 1 and b["topics"] == len(j["findings"]) - 1
    rep = c.post("/reports", json={"run_id": j["run_meta"]["id"]}).json()
    assert rep["id"] == "R-001" and rep["open_findings"] == len(j["findings"]) - 1
    assert [x["finding"] for x in rep["excluded"]] == ["U-01"]
    assert any(e["event"] == "incorrect" and e["finding"] == "U-01" for e in c.get("/history").json()["history"])
    assert c.delete("/incorrect/" + u01["check_key"]).status_code == 200
    assert c.post("/export/bcf").json()["excluded"] == 0
    # the verdict itself never changes
    assert {x["id"] for x in c.post("/analyse", json={"revision": "B"}).json()["findings"]} == set(f)


def test_report_once_per_run(c):
    j, _ = _run_b(c)
    a = c.post("/reports", json={"run_id": j["run_meta"]["id"]}).json()
    b = c.post("/reports", json={"run_id": j["run_meta"]["id"]}).json()
    assert a["id"] == b["id"] and b.get("existing")


def test_run_ifc_is_the_analysed_file(c):
    j, _ = _run_b(c)
    r = c.get(f"/runs/{j['run_meta']['id']}/ifc")
    assert r.status_code == 200 and r.content == (DATA / "deck5_revB.ifc").read_bytes()
    assert "path" not in c.get(f"/runs/{j['run_meta']['id']}").json()


def test_run_ifc_refused_after_chat_edit(c):
    c.post("/analyse", json={"revision": "A"})
    c.post("/edit", json={"edit": {"kind": "set_door_fire_class", "door": "FD-5-165P", "fire_class": "A-60"}, "confirm": True})
    j = c.post("/analyse", json={"scope": "deck:5"}).json()
    assert c.get(f"/runs/{j['run_meta']['id']}/ifc").status_code == 409


def test_upload_rejects_ifc2x3_and_oversize(c, monkeypatch):
    body = (DATA / "deck5_revA.ifc").read_bytes().replace(b"FILE_SCHEMA(('IFC4'))", b"FILE_SCHEMA(('IFC2X3'))")
    r = c.post("/upload?name=old.ifc", content=body)
    assert r.status_code == 422 and "IFC2X3" in r.json()["detail"]
    monkeypatch.setenv("SONARIQ_UPLOAD_MB", "0")
    assert c.post("/upload?name=a.ifc", content=(DATA / "deck5_revA.ifc").read_bytes()).status_code == 413


def test_tasks_validate_column(c):
    assert c.put("/tasks/k1", json={"column": "doing", "assignee": "ms"}).json()["column"] == "doing"
    assert c.put("/tasks/k1", json={"column": "nowhere"}).status_code == 400


def test_reset_all_data_archives_and_starts_empty(c, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DATA", tmp_path)
    j, f = _run_b(c)
    c.post("/incorrect", json={"check_key": f["U-01"]["check_key"], "finding": "U-01", "reason": "lining"})
    c.post("/reports", json={"run_id": j["run_meta"]["id"]})
    c.put("/tasks/k1", json={"column": "doing", "assignee": "ms"})
    r = c.post("/admin/reset").json()
    assert r["ok"] and r["runs"] == 1
    arch = tmp_path / "archive" / r["archived"]
    assert (arch / "runs").is_dir() and (arch / "reports.json").exists() and (arch / "history.json").exists()
    assert c.get("/runs").json()["runs"] == [] and c.get("/incorrect").json()["incorrect"] == {}
    assert c.get("/tasks").json()["tasks"] == {} and c.get("/history").json()["history"] == []
    # the panel keeps working: analyse again, report numbering restarts
    j2, _ = _run_b(c)
    assert c.post("/reports", json={"run_id": j2["run_meta"]["id"]}).json()["id"] == "R-001"


def test_model_file_serves_only_owned_models(c):
    assert c.get("/model-file?revision=B").content == (DATA / "deck5_revB.ifc").read_bytes()
    assert c.get("/model-file?path=/etc/passwd").status_code == 404
    assert c.get("/model-file?revision=Z").status_code == 404
