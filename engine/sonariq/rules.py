"""Rulebook: YAML rule packs. Thresholds and clause text live in YAML; measure functions in checks.py."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
RULES_FILE = ROOT / "rules" / "seed_rules.yaml"

# UI pack groups (P1 pack chips): YAML packs -> group
PACK_GROUPS: dict[str, dict[str, Any]] = {
    "fls": {"label": "Fire & life safety", "packs": ["fire", "escape"], "sources": "SOLAS II-2, FSS Code Ch.13",
            "discipline": "fire_life_safety", "short": "FS"},
    "acc": {"label": "Accessibility", "packs": ["accessibility"], "sources": "PVAG 2013 draft, ADA 2010",
            "discipline": "accessibility", "short": "AC"},
    "dnv": {"label": "Class · DNV", "packs": ["class_dnv"], "sources": "DNV (to confirm)",
            "discipline": "structure", "short": "CL"},
    "hvac": {"label": "HVAC", "packs": ["hvac"], "sources": "SOLAS II-2/9.7", "discipline": "hvac", "short": "HV"},
    "structure": {"label": "Structure · OCX", "packs": ["structure"], "sources": "stub", "discipline": "structure",
                  "short": "ST"},
}
DEFAULT_GROUPS = ["fls", "acc", "dnv"]

DISCIPLINES = {
    "fire_life_safety": "Fire & life safety",
    "accessibility": "Accessibility",
    "structure": "Class · DNV",
    "hvac": "HVAC",
    "architecture": "Architecture",
    "systems": "Systems",
}


class Rule(BaseModel):
    id: str
    finding_no: int
    pack: str
    discipline: str
    title: str
    unk_title: str | None = None
    source: str
    clause: str
    clause_text: str
    reading: str
    applies_to: str
    inputs: list[str] = []
    check: str
    params: dict[str, Any] = {}
    severity: str = "fail"
    cannot_verify_when: str | None = None
    applicability: dict[str, Any] = {}
    status: str = "verify"

    @property
    def ref(self) -> str:
        if self.source.startswith("SOLAS") and self.clause.startswith("II-2"):
            return f"SOLAS {self.clause}"
        return f"{self.source} {self.clause}"

    @property
    def group(self) -> str:
        for g, d in PACK_GROUPS.items():
            if self.pack in d["packs"]:
                return g
        return self.pack


@lru_cache(maxsize=4)
def load_rules(path: str | None = None) -> tuple[Rule, ...]:
    data = yaml.safe_load(Path(path or RULES_FILE).read_text())
    return tuple(Rule(**r) for r in data["rules"])


def expand_packs(groups_or_packs: list[str] | None) -> set[str]:
    """Accept UI groups (fls, acc, dnv, hvac) or raw YAML pack names."""
    if not groups_or_packs:
        groups_or_packs = DEFAULT_GROUPS
    out: set[str] = set()
    for g in groups_or_packs:
        if g in PACK_GROUPS:
            out.update(PACK_GROUPS[g]["packs"])
        else:
            out.add(g)
    return out
