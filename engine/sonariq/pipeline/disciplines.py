"""Discipline classification for the viewer and readiness (config/discipline_mapping.yaml): IFC class first, then rules."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[3] / "config" / "discipline_mapping.yaml"


@lru_cache(maxsize=2)
def _config(path: str = str(CONFIG)):
    d = yaml.safe_load(Path(path).read_text())
    by_class = {c: disc for disc, cs in d["by_class"].items() for c in cs}
    rules = [{k: (v if k == "discipline" else re.compile(v, re.I)) for k, v in r.items()} for r in d["rules"]]
    return d["disciplines"], by_class, rules


def disciplines() -> list[str]:
    return list(_config()[0])


def classify(ifc_class: str | None, name: str | None = None, layer: str | None = None, system: str | None = None,
             swbs: str | None = None) -> str:
    _, by_class, rules = _config()
    if ifc_class in by_class:
        return by_class[ifc_class]
    vals = {"name": name or "", "layer": layer or "", "system": system or "", "swbs": swbs or "", "cls": ifc_class or ""}
    for r in rules:
        if all(rx.search(vals[k]) for k, rx in r.items() if k != "discipline"):
            return r["discipline"]
    return "other"
