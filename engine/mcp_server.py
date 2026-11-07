"""SonarIQ MCP server (stdio). Any AI client or CAD adapter calls the same deterministic checks.

Tools: analyse, get_finding, explain, propose_fixes, apply_edit, recheck, export_bcf, sources (+ open_revision),
and when SIMULATE_ENABLED=1: simulate (preview -> confirm), simulation_status, simulation_results.
apply_edit only accepts add_cabin_block, move_wall, set_door_width, set_door_fire_class, and only applies
with confirm=true after a preview. Verdicts come from the rule engine; explain() rejects invented numbers.

Run:  .venv/bin/python engine/mcp_server.py
Claude Code / Desktop config: {"command": "<repo>/.venv/bin/python", "args": ["<repo>/engine/mcp_server.py"]}
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as FastMCP  # noqa: E402
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP  # noqa: E402

from sonariq.edits import EditRefused  # noqa: E402
from sonariq.session import Session  # noqa: E402

mcp = FastMCP("sonariq")
S = Session("A")


def _slim_run(d: dict) -> dict:
    return {k: d[k] for k in ("revision", "scope", "groups", "duration_s", "total_checks", "counts", "by_group",
                              "not_applicable")} | {
        "findings": [{k: f[k] for k in ("id", "status_word", "title", "ref", "location", "summary", "rule_status")}
                     for f in d["findings"]]}


@mcp.tool()
def open_revision(revision: str = "A", path: str | None = None) -> dict:
    """Open a model revision ("A", "B", "Bfix2") or an IFC4 file path. Resets the session."""
    return S.open(revision, path)


@mcp.tool()
def analyse(scope: str = "deck:5", packs: list[str] | None = None) -> dict:
    """Run the rule packs. scope: "deck:5", "whole". packs: fls (fire & life safety), acc (accessibility),
    dnv (class, to verify), hvac. Returns counts per status and the open findings."""
    return _slim_run(S.analyse(scope, packs))


@mcp.tool()
def get_finding(id: str) -> dict:
    """Full evidence for a finding (e.g. F-07): rule, clause, required vs measured, formula inputs, method,
    location (Deck · Fr · Side) and the IFC GlobalIds involved."""
    return S.finding(id)


@mcp.tool()
def explain(id: str, question: str | None = None) -> dict:
    """Plain-language explanation of a finding. Uses only the engine's numbers; any text with a number not in
    the finding is rejected and replaced by the engine's own wording."""
    return S.explain(id, question)


@mcp.tool()
def propose_fixes(id: str) -> list[dict]:
    """Fix options for a finding. The engine re-checks every option on a copy of the model before it is shown."""
    return S.propose_fixes(id)


@mcp.tool()
def apply_edit(edit: dict, confirm: bool = False) -> dict:
    """Apply one of the four allowed edits. Without confirm=true it only returns a preview.
    edit kinds: add_cabin_block{frame_from,count,berths_per_cabin,y_from}, move_wall{space,width_mm},
    set_door_width{door,width_mm}, set_door_fire_class{door,fire_class}. Anything else is refused."""
    try:
        return S.apply_edit(edit, confirm)
    except EditRefused as e:
        return {"refused": True, "reason": str(e),
                "allowed": ["add_cabin_block", "move_wall", "set_door_width", "set_door_fire_class"]}


@mcp.tool()
def recheck(revision: str | None = None) -> dict:
    """Re-check after a change (the ping). With revision, loads it and compares with the current model.
    Returns how many checks re-ran, which verdicts changed, and which values changed."""
    return S.switch_revision(revision) if revision else S.recheck()


@mcp.tool()
def export_bcf(path: str | None = None) -> dict:
    """Write open findings and decisions as a BCF 2.1 file for other design tools."""
    return S.export_bcf(path)


@mcp.tool()
def sources(id: str) -> dict:
    """Source text with citations for a finding (public sources + SonarIQ's reading). Never sets a verdict."""
    from sonariq.sources import finding_sources
    return finding_sources(S.finding(id))


import os  # noqa: E402

if os.getenv("SIMULATE_ENABLED", "0").lower() in ("1", "true", "on", "yes"):
    from sim.service import SimService  # noqa: E402

    _SIM = SimService()

    @mcp.tool()
    def simulate(text: str | None = None, scenario: dict | None = None, revision: str | None = None,
                 runs: int = 500, confirm: bool = False) -> dict:
        """Evacuation simulation of the Deck 5 sub-model (design insight, not a full-ship Circ.1533 analysis).
        Give words (e.g. 'night, stair 3B out') or a scenario {case, route, closed_stair, closed_door, fire_origin}.
        Without confirm=true it only returns the scenario preview; nothing runs until the engineer confirms."""
        from sim.geometry import build
        from sim.runner import Scenario
        from sim.smoke import resolve_origin
        from sim.words import from_words
        model = S.load(revision) if revision else S.model
        g = build(model)
        sc = dict(scenario or {})
        if text and not scenario:
            r = from_words(text, list(g.stairs), list(g.spaces), S.llm, list(g.doors), g.space_meta)
            if not r["ok"]:
                return {"error": r["errors"]}
            sc = r["scenario"]
            if sc.pop("revision", None):
                pass
        if (sc.get("fire_origin") or "").startswith("@"):
            sc["fire_origin"] = resolve_origin(g, sc["fire_origin"])
        scen = Scenario(**{k: v for k, v in sc.items() if k in Scenario.__dataclass_fields__})
        if not confirm:
            return {"preview": scen.label(), "scenario": scen.key(), "runs": runs, "confirm_required": True}
        return _SIM.start(model, scen, runs, revision=revision or model.revision)

    @mcp.tool()
    def simulation_status(id: str) -> dict:
        """Live run count and state of a simulation."""
        return _SIM.status(id)

    @mcp.tool()
    def simulation_results(id: str) -> dict:
        """Summary of a finished simulation: p95, per-stair and per-landing results, congestion, longest route."""
        r = dict(_SIM.results(id))
        r.get("longest_route", {}).pop("path", None)
        r.pop("target_stair", None)
        return r


if __name__ == "__main__":
    mcp.run()
