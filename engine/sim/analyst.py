"""Results analyst: explains a simulation result in plain words. Every number must be in the results JSON."""
from __future__ import annotations

SYSTEM = (
    "You explain a ship evacuation simulation result to a design engineer. Use only the results JSON. Do not compute "
    "new numbers: every number you write must appear in the JSON. Say where people queue, which stair clears last, "
    "and what the engineer could look at. Write times as mm:ss using times_mm_ss. It is a Deck 5 sub-model with inflows from Decks 4, 6 and 7, a design "
    "insight, not a full-ship analysis. Two to four short sentences. No product, vendor or model names."
)


def facts(res: dict) -> dict:
    keep = ("runs", "scenario_label", "revision", "tA_p50_s", "tA_p95_s", "deck5_last_p95_s", "peak_density_p95",
            "congestion_significant_share", "stairs", "landings", "people_deck5", "capacity_p_s", "inflow")
    f = {k: res.get(k) for k in keep}
    f["percentile"] = res.get("percentile", 95)
    f["model_scope"] = "Deck 5 sub-model with inflows from Decks 4, 6, 7"
    f["times_mm_ss"] = {k: _mmss(res.get(k)) for k in ("tA_p50_s", "tA_p95_s", "deck5_last_p95_s")}
    f["congestion"] = [{k: c.get(k) for k in ("label", "peak_p_m2", "finding")} for c in res.get("congestion", [])[:4]]
    f["events"] = [{"label": e["label"], "t_mm_ss": _mmss(e["t_s"])} for e in res.get("events", [])]
    lr = res.get("longest_route") or {}
    f["longest_route"] = {k: lr.get(k) for k in ("space", "length_m", "stair")}
    return f


def _mmss(s):
    if s is None:
        return None
    m = int(s // 60)
    return f"{m:02d}:{int(round(s - 60 * m)):02d}"


def template(res: dict) -> str:
    f = facts(res)
    worst = max(f["landings"].items(), key=lambda kv: kv[1]["queue_max_p95"]) if f["landings"] else None
    last = max(f["stairs"].items(), key=lambda kv: kv[1]["last_p95_s"]) if f["stairs"] else None
    s = f"{f['scenario_label']}, {f['runs']} runs: p{f['percentile']} assembly time {_mmss(f['tA_p95_s'])} ({f['tA_p95_s']} s)."
    if last:
        s += f" Stair {last[0]} clears last ({_mmss(last[1]['last_p95_s'])} at p{f['percentile']})."
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


HOT_SYSTEM = (
    "You explain one congested place in an evacuation replay to a ship designer. Use only the facts. Every number "
    "must be in the facts. Say what is happening there and one thing the designer could check. Two short sentences. "
    "No product or vendor names."
)


def hotspot(llm, res: dict, rep: dict, x: float, y: float, t: float) -> dict:
    """Facts at a clicked place: peak density and time above 4 p/m2 in that cell, the space, the nearest landing
    queue at time t (all computed); the AI explains them, numbers checked."""
    import math
    d = rep["density"]
    i, j = int((x - d["origin"][0]) // d["cell_m"]), int((y - d["origin"][1]) // d["cell_m"])
    if not (0 <= i < d["nx"] and 0 <= j < d["ny"]):
        return {"error": "outside the deck"}
    g = rep.get("geometry") or {}
    space = None
    for s in g.get("spaces", []):
        xs = [p[0] for p in s["poly"]["outer"]]
        ys = [p[1] for p in s["poly"]["outer"]]
        if min(xs) <= x <= max(xs) and min(ys) <= y <= max(ys):
            space = s["name"]
            break
    best = None
    for st in g.get("stairs", []):
        for li, h in enumerate(st["landings"]):
            dist = math.hypot(h[0] - x, h[1] - y)
            if best is None or dist < best[0]:
                best = (dist, st["name"] + ("PS"[li] if len(st["landings"]) > 1 else ""))
    k = max(0, int(t - rep["series_t0_s"]))
    q = rep["queue_series"].get(best[1], []) if best else []
    facts = {"place": {"space": space, "frame": round(x / 0.8), "side": "P" if y > 0.3 else "S" if y < -0.3 else "CL"},
             "peak_density_p_m2": d["peak"][j][i], "seconds_above_4_p_m2": d["over4_s"][j][i],
             "viewed_at_mm_ss": _mmss(t), "nearest_landing": best[1] if best else None,
             "distance_to_landing_m": round(best[0], 1) if best else None,
             "queue_at_landing_now": q[min(k, len(q) - 1)] if q else None,
             "queue_at_landing_max": max(q) if q else None, "congestion_level_p_m2": 4,
             "run": {"seed": rep["seed"], "tA_mm_ss": _mmss(rep["tA_s"])}}
    fb = (f"{facts['place']['space'] or 'Here'} (Fr {facts['place']['frame']} · {facts['place']['side']}): peak "
          f"{facts['peak_density_p_m2']} p/m², {facts['seconds_above_4_p_m2']} s above 4 p/m²."
          + (f" Landing {best[1]} queue {facts['queue_at_landing_now']} now, {facts['queue_at_landing_max']} at most."
             if q else ""))
    out = llm.guarded(HOT_SYSTEM, facts, "What happens at this place?", fb)
    out["facts"] = facts
    out["badge"] = "AI explanation · numbers checked" if out["source"] == "ai" else "Simulation facts"
    return out
