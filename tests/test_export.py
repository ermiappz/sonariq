"""CSV export (spec B7): one row per check, values as the engine returned them."""
import csv
import io

from fastapi.testclient import TestClient


def test_csv_has_every_check(tmp_path, monkeypatch):
    from sonariq import api
    monkeypatch.setattr(api, "RUNS", tmp_path / "runs")
    monkeypatch.setenv("SONARIQ_RATE_LIMIT", "0")
    c = TestClient(api.app)
    d = c.post("/analyse", json={"revision": "B", "scope": "deck:5", "packs": ["fls", "acc", "dnv"]}).json()
    rid = d["run_meta"]["id"]
    r = c.get(f"/runs/{rid}/csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == d["total_checks"] == 96
    f07 = next(x for x in rows if x["finding"] == "F-07")
    assert (f07["measured"], f07["required"], f07["measured_source"], f07["required_source"]) == ("1350", "1380", "model", "derived")
