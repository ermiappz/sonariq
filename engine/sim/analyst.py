"""Results analyst: explains a simulation result in plain words. Every number must be in the results JSON."""
from __future__ import annotations

SYSTEM = (
    "You explain a ship evacuation simulation result to a design engineer. Use only the results JSON. Do not compute "
    "new numbers: every number you write must appear in the JSON. Say where people queue, which stair clears last, "
    "and what the engineer could look at. It is a Deck 5 sub-model with inflows from Decks 4, 6 and 7, a design "
    "insight, not a full-ship analysis. Two to four short sentences. No product, vendor or model names."
)


def facts(res: dict) -> dict:
    keep = ("runs", "scenario_label", "revision", "tA_p50_s", "tA_p95_s", "deck5_last_p95_s", "peak_density_p95",
            "congestion_significant_share", "stairs", "landings", "people_deck5", "capacity_p_s", "inflow")
    f = {k: res.get(k) for k in keep}
    lr = res.get("longest_route") or {}
    f["longest_route"] = {k: lr.get(k) for k in ("space", "length_m", "stair")}
    return f


def template(res: dict) -> str:
    f = facts(res)
    worst = max(f["landings"].items(), key=lambda kv: kv[1]["queue_max_p95"]) if f["landings"] else None
    last = max(f["stairs"].items(), key=lambda kv: kv[1]["last_p95_s"]) if f["stairs"] else None
    s = f"{f['scenario_label']}, {f['runs']} runs: 95th percentile assembly time {f['tA_p95_s']} s."
    if last:
        s += f" Stair {last[0]} clears last ({last[1]['last_p95_s']} s at p95)."
    if worst:
        s += f" Longest landing queue: {worst[0]}, {worst[1]['queue_max_p95']} people at p95."
    lr = f["longest_route"]
    if lr.get("space"):
        s += f" Longest walk: {lr['space']} to Stair {lr['stair']}, {lr['length_m']} m."
    return s


def explain_results(llm, res: dict, question: str | None = None) -> dict:
    out = llm.guarded(SYSTEM, facts(res), question or "What does this result show?", template(res))
    out["badge"] = "AI explanation · numbers checked" if out["source"] == "ai" else "Simulation summary"
    return out
