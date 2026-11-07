import subprocess
import sys
from pathlib import Path

import os

import pytest

os.environ.setdefault("SONARIQ_AI", "off")

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
