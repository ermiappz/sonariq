"""Accuracy banner (spec B5): engine findings against hand-checked ground truth and the independent scan.

Computed, never typed: every number in the banner comes from comparing three things — the engine's run, the
hand-checked file tests/ground_truth/<scenario>.yaml, and scripts/independent_scan.py.
"""
from __future__ import annotations

import collections
import importlib.util
import json
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GT = ROOT / "tests" / "ground_truth"


def scenarios() -> list[str]:
    return sorted(p.stem for p in GT.glob("*.yaml"))


def truth(scenario: str) -> dict:
    return yaml.safe_load((GT / f"{scenario}.yaml").read_text())


@lru_cache(maxsize=8)
def _scan(scenario: str, stamp: float) -> dict:
    spec = importlib.util.spec_from_file_location("independent_scan", ROOT / "scripts" / "independent_scan.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.scan(scenario)


def scan(scenario: str) -> dict:
    src = ROOT / ("data/rcrv/gltf/properties.jsonl" if scenario.startswith("rcrv") else f"data/{scenario}.ifc")
    return _scan(scenario, src.stat().st_mtime if src.exists() else 0.0)


def compare(scenario: str, run: dict) -> dict:
    """run = run_dict output (compact or not). Returns the banner numbers and the lists behind them."""
    gt = truth(scenario)
    got = {(c["rule"], (c.get("element") or {}).get("guid")): c["status"] for c in run["checks"]}
    for rule, guid, *_ in run.get("passes") or []:
        got[(rule, guid)] = "pass"
    exp = gt.get("expected_findings") or []
    found = [f for f in exp if got.get((f["rule"], f["element"])) == f["status"]]
    missed = [f for f in exp if got.get((f["rule"], f["element"])) != f["status"]]
    exp_keys = {(f["rule"], f["element"]) for f in exp}
    false_alarms = [{"rule": c["rule"], "element": (c.get("element") or {}).get("guid"), "status": c["status"]}
                    for c in run["checks"] if c["status"] in ("fail", "warn")
                    and (c["rule"], (c.get("element") or {}).get("guid")) not in exp_keys]
    passes = gt.get("expected_passes") or []
    pass_ok = [p for p in passes if got.get((p["rule"], p["element"])) == "pass"]
    counts = collections.defaultdict(collections.Counter)
    for c in run["checks"]:   # Dormant (concept zones) counts as the verdict it holds back, as the scan sees it
        counts[c["rule"]][(c.get("extra") or {}).get("verdict_if_reported", c["status"]) if c["status"] == "dor" else c["status"]] += 1
    for rule, *_ in run.get("passes") or []:
        counts[rule]["pass"] += 1
    sc = scan(scenario)
    mism = {r: {"engine": dict(counts[r]), "scan": want} for r, want in sc.items()
            if {k: v for k, v in counts[r].items() if v} != {k: v for k, v in want.items() if v}}
    ec = gt.get("expected_counts") or {}
    count_mism = {r: {"engine": dict(counts[r]), "expected": want} for r, want in ec.items()
                  if {k: v for k, v in counts[r].items() if v} != want}
    return {"scenario": scenario, "found": len(found), "expected": len(exp), "missed": missed,
            "false_alarms": false_alarms, "passes_ok": len(pass_ok), "passes_expected": len(passes),
            "scan_rules": sorted(sc), "scan_match": not mism, "scan_mismatch": mism,
            "counts_match": not count_mism, "count_mismatch": count_mism,
            "ok": not missed and not false_alarms and len(pass_ok) == len(passes) and not mism and not count_mism}
