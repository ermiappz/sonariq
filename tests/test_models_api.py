"""POST /models, /models/prepare, status, cached re-upload, file serving with cache headers."""
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from sonariq import api, models_api
    monkeypatch.setattr(models_api, "MODELS", tmp_path / "models")
    monkeypatch.setenv("SONARIQ_RATE_LIMIT", "0")
    return TestClient(api.app)


def _wait(c, mid, timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        st = c.get(f"/models/{mid}").json()
        if st["state"] in ("ready", "error"):
            return st
        time.sleep(0.2)
    raise AssertionError(f"conversion did not finish: {st}")


def test_upload_convert_serve_and_cache(client):
    body = (ROOT / "data" / "deck5_revA.ifc").read_bytes()
    r = client.post("/models?name=deck5_revA.ifc", content=body)
    assert r.status_code == 200
    mid = r.json()["id"]
    st = _wait(client, mid)
    assert st["state"] == "ready" and st["summary"]["elements"] > 200
    assert st["summary"]["integrity"] == {"vertex_mismatch": 0, "triangle_mismatch": 0}
    ix = client.get(f"/models/{mid}/files/index.json")
    assert ix.status_code == 200 and "immutable" in ix.headers["cache-control"]
    tile = ix.json()["files"][0]["f"]
    g = client.get(f"/models/{mid}/files/tiles/{tile}")
    assert g.status_code == 200 and g.content[:4] == b"glTF"
    t = time.perf_counter()                       # same bytes again: cached, no new conversion
    r2 = client.post("/models?name=again.ifc", content=body).json()
    assert r2["id"] == mid and r2["state"] == "ready" and time.perf_counter() - t < 0.5


def test_prepare_demo_revision(client):
    st = client.post("/models/prepare", json={"revision": "B"}).json()
    assert _wait(client, st["id"])["state"] == "ready"


def test_rejects_bad_input_and_paths(client):
    assert client.post("/models", content=b"hello").status_code == 422
    assert client.get("/models/0123456789abcdef/files/../../etc/passwd").status_code == 404
    assert client.get("/models/nothexnothexnoth").status_code == 404
    head = b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('CIS2'));\n"
    assert client.post("/models", content=head).status_code == 422
