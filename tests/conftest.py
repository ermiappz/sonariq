import subprocess
import sys
from pathlib import Path

import os

import pytest

os.environ.setdefault("SONARIQ_AI", "off")
# tests must never add runs to the demo's run store (data/runs)
import tempfile
os.environ.setdefault("SONARIQ_RUNS", tempfile.mkdtemp(prefix="sonariq-test-runs-"))
# … nor to its revisions, tasks, marks, views or reports
_T = tempfile.mkdtemp(prefix="sonariq-test-stores-")
for _k, _f in (("SONARIQ_REVISIONS", "revisions.sqlite"), ("SONARIQ_TASKS", "tasks.json"), ("SONARIQ_INCORRECT", "incorrect.json"),
               ("SONARIQ_VIEWS", "views.json"), ("SONARIQ_REPORTS", "reports.json")):
    os.environ.setdefault(_k, os.path.join(_T, _f))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
DATA = ROOT / "data"


def _ensure_decks():
    need = [DATA / f for f in ("deck5_revA.ifc", "deck5_revB.ifc", "deck5_revB_fix2.ifc")]
    src = ROOT / "scripts" / "make_deck.py"
    if not all(p.exists() and p.stat().st_mtime >= src.stat().st_mtime for p in need):
        subprocess.run([sys.executable, str(src)], check=True, capture_output=True)


@pytest.fixture(scope="session")
def models():
    _ensure_decks()
    from sonariq.model import load_ifc
    return {"A": load_ifc(DATA / "deck5_revA.ifc", "A"), "B": load_ifc(DATA / "deck5_revB.ifc", "B"),
            "Bfix2": load_ifc(DATA / "deck5_revB_fix2.ifc", "B")}


@pytest.fixture
def A(models):
    return models["A"].copy()


@pytest.fixture
def B(models):
    return models["B"].copy()
