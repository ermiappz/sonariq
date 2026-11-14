"""Named views (cut + camera + display mode) and the per-model frame grid behind the section blade (spec A3, M6)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
CAM = {"position": [120.0, -30.0, 40.0], "target": [130.0, 0.0, 15.0], "projection": "orthographic", "zoom": 1.5}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from sonariq import api, models_api
    monkeypatch.setattr(api, "VIEWS", tmp_path / "views.json")
    monkeypatch.setattr(models_api, "MODELS", tmp_path / "models")
    monkeypatch.setenv("SONARIQ_RATE_LIMIT", "0")
    return TestClient(api.app)


def test_save_list_delete_view(client):
    body = {"name": "Fr 152 looking aft", "model": "46d37922f4f9a5b6", "mode": "lines",
            "cuts": [{"kind": "cross", "pos": 121.6, "flip": True}, {"kind": "deck", "pos": 16.0}], "camera": CAM}
    v = client.post("/views", json=body).json()
    assert v["id"] == "V-001" and v["cuts"][1] == {"kind": "deck", "pos": 16.0, "flip": False}
    assert v["camera"]["projection"] == "orthographic" and v["mode"] == "lines"
    v2 = client.post("/views", json={**body, "name": "other model", "model": "rcrv", "cuts": []}).json()
    assert v2["id"] == "V-002"
    assert [x["id"] for x in client.get("/views", params={"model": "46d37922f4f9a5b6"}).json()["views"]] == ["V-001"]
    assert len(client.get("/views").json()["views"]) == 2
    assert client.delete("/views/V-001").status_code == 200
    assert client.delete("/views/V-001").status_code == 404
    assert [x["id"] for x in client.get("/views").json()["views"]] == ["V-002"]
    assert client.post("/views", json={**body, "name": "next"}).json()["id"] == "V-003"   # ids are never reused


@pytest.mark.parametrize("patch, why", [
    ({"name": "  "}, "name"), ({"name": "x" * 81}, "name"), ({"model": "../etc"}, "model"),
    ({"cuts": [{"kind": "cross", "pos": 1}] * 4}, "3 cuts"), ({"cuts": [{"kind": "diagonal", "pos": 1}]}, "kind"),
    ({"cuts": [{"kind": "cross", "pos": 1e9}]}, "range"), ({"mode": "toon"}, "mode"),
    ({"camera": {**CAM, "position": [0, 0]}}, "camera"), ({"camera": {**CAM, "target": [0, "x", 0]}}, "camera"),
    ({"camera": {**CAM, "projection": "fisheye"}}, "projection"), ({"camera": {**CAM, "zoom": 0}}, "zoom"),
])
def test_view_validation(client, patch, why):
    body = {"name": "ok", "model": "rcrv", "cuts": [], "camera": CAM, **patch}
    assert client.post("/views", json=body).status_code == 422, why


def _fake_model(models: Path, mid: str, box, ifc_text: str | None = None):
    web = models / mid / "web"
    web.mkdir(parents=True)
    (web / "index.json").write_text(json.dumps({"box": box}))
    if ifc_text is not None:
        (models / mid / "original.ifc").write_text(ifc_text)


def test_grid_defaults_and_user_override(client, tmp_path):
    from sonariq import models_api
    m = models_api.MODELS
    deck5 = (ROOT / "data" / "deck5_revB.ifc").read_text()
    _fake_model(m, "0123456789abcdef", [[96, -13.5, 14.5], [172, 13.5, 17.3]], deck5)
    _fake_model(m, "fedcba9876543210", [[0, -5, 0], [40, 5, 9]], "ISO-10303-21;\nDATA;\nENDSEC;\n")
    _fake_model(m, "rcrv", [[-62.416, -10.7, -1.36], [4.29, 8.65, 27.0]])
    g = client.get("/models/0123456789abcdef/grid").json()
    assert g["frame0_x"] == 0.0 and g["spacing_m"] == 0.8 and g["source"].startswith("model")   # Fr 120 at x = 96
    assert client.get("/models/fedcba9876543210/grid").json()["spacing_m"] == 0.8               # engine default
    r = client.get("/models/rcrv/grid").json()
    assert r["frame0_x"] == -62.416 and r["spacing_m"] == 1.0                                     # metres from aft
    u = client.put("/models/rcrv/grid", json={"frame0_x": -60.0, "spacing_m": 0.6}).json()
    assert u == {"frame0_x": -60.0, "spacing_m": 0.6, "source": "user"}
    assert client.get("/models/rcrv/grid").json()["source"] == "user"
    assert client.put("/models/rcrv/grid", json={"frame0_x": 0, "spacing_m": 0}).status_code == 422
    assert client.get("/models/0000000000000000/grid").status_code == 404
    assert client.get("/models/..%2Fx/grid").status_code == 404
