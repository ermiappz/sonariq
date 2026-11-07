"""One evacuation run of the Deck 5 sub-model (JuPedSim CollisionFreeSpeedModel) and the seeded Monte Carlo.

Stairs are capacity-limited exits: Deck 5 people queue on the stair landing (a JuPedSim queue stage) and are
released at the stair's flow capacity (specific flow x clear width), which they share with the timed inflows
from Decks 4, 6 and 7 (persons_by_deck). Everything here computes; nothing is typed.
"""
from __future__ import annotations

import math
import multiprocessing as mp
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml
from shapely.geometry import LineString, Point, box

from .geometry import DeckGeometry, build, route_length

PARAMS = yaml.safe_load((Path(__file__).with_name("params.yaml")).read_text())


# ---------------------------------------------------------------- scenario
@dataclass
class Scenario:
    case: str = "night"                       # night | day
    route: str = "primary"                    # primary | secondary
    closed_stair: str | None = None           # secondary: which stair is out of use
    closed_door: str | None = None            # secondary: which door (e.g. MVZ fire door) is out of use
    fire_origin: str | None = None            # fire what-if: origin space name
    smoke_hop_s: float | None = None          # override params smoke.hop_delay_s
    stair_width_override: dict = field(default_factory=dict)   # what-if: {"3B": 1.40}

    def key(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, {}, "")}

    def label(self) -> str:
        s = f"{self.case.title()} · {self.route}"
        if self.closed_stair:
            s += f" (Stair {self.closed_stair} out of use)"
        if self.closed_door:
            s += f" ({self.closed_door} out of use)"
        if self.fire_origin:
            s += f" · fire what-if in {self.fire_origin}"
        return s


# ---------------------------------------------------------------- deterministic prep (shared by all runs)
@dataclass
class Prep:
    geom: DeckGeometry
    open_stairs: list[str]
    spawn: list[dict]                 # candidate positions: {space, x, y, kind}
    target: dict[str, tuple[str, int]]   # space -> (stair, landing index), nearest by route length
    route_len: dict[str, float]
    route_path: dict[str, list]
    inflow: dict[str, int]            # stair -> persons from other decks
    capacity: dict[str, float]        # stair -> p/s
    scenario: dict
    smoke: list = field(default_factory=list)      # [{t, spaces}] illustrative smoke spread


def _berth_points(poly, n):
    x0, y0, x1, y1 = poly.bounds
    pts = []
    long_x = (x1 - x0) >= (y1 - y0)
    for i in range(n):
        f = (i + 1) / (n + 1)
        p = (x0 + f * (x1 - x0), (y0 + y1) / 2) if long_x else ((x0 + x1) / 2, y0 + f * (y1 - y0))
        pts.append(p)
    return pts


def _grid_points(poly, n, walk):
    if n <= 0:
        return []
    x0, y0, x1, y1 = poly.bounds
    step = math.sqrt(poly.area / n)
    pts = []
    yy = y0 + step / 2
    while yy < y1 and len(pts) < n:
        xx = x0 + step / 2
        while xx < x1 and len(pts) < n:
            p = Point(xx, yy)
            if walk.buffer(-0.3).contains(p):
                pts.append((round(xx, 3), round(yy, 3)))
            xx += step
        yy += step
    return pts


def prepare(model, sc: Scenario) -> Prep:
    import jupedsim as jps
    blocked = (sc.fire_origin,) if sc.fire_origin else ()
    closed = (sc.closed_stair,) if sc.closed_stair else ()
    g = build(model, closed_stairs=closed, blocked_spaces=blocked,
              closed_doors=(sc.closed_door,) if sc.closed_door else ())
    for nm, w in (sc.stair_width_override or {}).items():
        if nm in g.stairs:
            g.stairs[nm].width = float(w)
    open_stairs = [s for s in g.stairs if s not in closed]
    occ = PARAMS["occupancy"][sc.case]
    spawn = []
    for n, poly in g.spaces.items():
        m = g.space_meta[n]
        cat = m.get("category")
        if n in blocked or n in g.dropped:
            continue
        if cat == "cabin" and occ["cabins"] == "full_berths":
            for x, y in _berth_points(poly, int(m.get("berths") or 0)):
                spawn.append({"space": n, "x": x, "y": y, "kind": "passenger"})
        elif cat == "service":
            for x, y in _berth_points(poly, int(occ["crew_per_service_space"])):
                spawn.append({"space": n, "x": x, "y": y, "kind": "crew"})
        elif cat == "public" and occ.get("public_share"):
            npers = int(poly.area / occ["public_m2_per_person"] * occ["public_share"])
            for x, y in _grid_points(poly, npers, g.walkable):
                spawn.append({"space": n, "x": x, "y": y, "kind": "passenger"})
    spawn = [s for s in spawn if g.walkable.buffer(-0.21).contains(Point(s["x"], s["y"]))]
    routing = jps.RoutingEngine(g.walkable)
    target, rlen, rpath = {}, {}, {}
    for n in sorted({s["space"] for s in spawn}):
        first = next(s for s in spawn if s["space"] == n)
        best = None
        for st in open_stairs:
            for li, h in enumerate(g.stairs[st].landings):
                if not g.walkable.buffer(0.01).contains(Point(*h)):
                    continue
                d = route_length(routing, (first["x"], first["y"]), h)
                if d > 0 and (best is None or d < best[0]):
                    best = (d, st, li)
        if best:
            target[n] = (best[1], best[2])
            rlen[n] = round(best[0], 2)
            rpath[n] = [[round(a, 2), round(b, 2)] for a, b in
                        routing.compute_waypoints((first["x"], first["y"]), g.stairs[best[1]].landings[best[2]])]
    inflow = {st: sum(v for k, v in g.stairs[st].persons_by_deck.items() if k != "5") for st in open_stairs}
    if sc.closed_stair and sc.closed_stair in g.stairs:   # its other-deck people use the remaining stairs, same MVZ first
        moved = sum(v for k, v in g.stairs[sc.closed_stair].persons_by_deck.items() if k != "5")
        same = [s for s in open_stairs if g.stairs[s].mvz == g.stairs[sc.closed_stair].mvz] or open_stairs
        for i, s in enumerate(same):
            inflow[s] += moved // len(same) + (1 if i < moved % len(same) else 0)
    f = PARAMS["flow"]
    spec = f["stair_max_specific_flow_up"]["value"] if f["stair_direction"] == "up" else \
        f["stair_max_specific_flow_down"]["value"]
    cap = {st: round(spec * g.stairs[st].width, 4) for st in open_stairs}
    smoke = []
    if sc.fire_origin:
        from .smoke import smoke_schedule
        smoke = smoke_schedule(g, sc.fire_origin, float(sc.smoke_hop_s or PARAMS["smoke"]["hop_delay_s"]),
                               PARAMS["model"]["max_sim_s"] + 800)
    return Prep(g, open_stairs, spawn, target, rlen, rpath, inflow, cap, sc.key(), smoke)


_ROUTING: dict = {}
SMOKE_WEIGHT = 5.0   # one metre through smoke costs as much as five metres of clear route (SonarIQ assumption)


def _routing(prep: Prep):
    import jupedsim as jps
    k = id(prep)
    if k not in _ROUTING:
        _ROUTING[k] = jps.RoutingEngine(prep.geom.walkable)
    return _ROUTING[k]


def _smoke_aware_target(prep: Prep, smoked_union, pos) -> tuple[tuple[str, int], float] | None:
    """Landing with the least smoke on the way (smoke metres x SMOKE_WEIGHT + route metres)."""
    eng = _routing(prep)
    best = None
    for st in prep.open_stairs:
        for li, h in enumerate(prep.geom.stairs[st].landings):
            try:
                pts = eng.compute_waypoints(tuple(pos), h)
            except Exception:  # noqa: BLE001
                continue
            if len(pts) < 2:
                continue
            line = LineString(pts)
            smoke_m = line.intersection(smoked_union).length
            cost = line.length + SMOKE_WEIGHT * smoke_m
            if best is None or cost < best[1]:
                best = ((st, li), cost)
    return best


# ---------------------------------------------------------------- population sampling
def _groups(kind):
    tab = PARAMS["population"]["passengers" if kind == "passenger" else "crew"]
    names = list(tab)
    w = np.array([tab[n][0] for n in names], float)
    return names, w / w.sum(), tab


def sample_response(rng, case, n):
    p = PARAMS["response"][case]
    out = np.empty(n)
    for i in range(n):
        while True:
            v = p["shift_s"] + math.exp(rng.normal(p["mu"], p["sigma"]))
            if p["min_s"] < v < p["max_s"]:
                out[i] = v
                break
    return out


def sample_people(rng, prep: Prep, case: str):
    ppl = []
    for s in prep.spawn:
        if s["space"] not in prep.target:
            continue
        names, w, tab = _groups(s["kind"])
        gi = rng.choice(len(names), p=w)
        row = tab[names[gi]]
        ppl.append({**s, "group": names[gi], "v": float(rng.uniform(row[1], row[2]))})
    resp = sample_response(rng, case, len(ppl))
    for p, r in zip(ppl, resp):
        p["t0"] = float(r)
    inflow_t = {}
    lo, hi = PARAMS["inflow"]["travel_to_stair_s"]
    for st, n in prep.inflow.items():
        inflow_t[st] = np.sort(sample_response(rng, case, n) + rng.uniform(lo, hi, n)).tolist()
    return ppl, inflow_t


# ---------------------------------------------------------------- one run
def run_one(prep: Prep, seed: int, record: bool = False, people: list[dict] | None = None,
            inflow_times: dict | None = None) -> dict:
    import jupedsim as jps
    m = PARAMS["model"]
    dt = float(m["dt_s"])
    rng = np.random.default_rng(seed)
    case = prep.scenario.get("case", "night")
    ppl, inflow_t = sample_people(rng, prep, case)
    if people is not None:          # evals: fixed people (position, speed, start time)
        ppl = people
    if inflow_times is not None:
        inflow_t = inflow_times
    g = prep.geom
    sim = jps.Simulation(model=jps.CollisionFreeSpeedModel(), geometry=g.walkable, dt=dt)
    queues, journeys = {}, {}
    for st in prep.open_stairs:
        s = g.stairs[st]
        for li, h in enumerate(s.landings):
            # queue positions run from the head on the landing back towards the stair door
            dn = min(s.doors, key=lambda d: g.doors[d].poly.centroid.distance(Point(*h)))
            dc = g.doors[dn].poly.centroid
            line = LineString([h, (dc.x, dc.y)])
            nq = max(2, int(line.length / 0.45))
            pos = [line.interpolate(i * 0.45).coords[0] for i in range(nq)]
            pos = [p for p in pos if g.walkable.buffer(-0.2).contains(Point(p))] or [h]
            qid = sim.add_queue_stage(pos)
            ex = sim.add_exit_stage(box(h[0] - 0.3, h[1] - 0.3, h[0] + 0.3, h[1] + 0.3).intersection(g.walkable))
            jd = jps.JourneyDescription([qid, ex])
            jd.set_transition_for_stage(qid, jps.Transition.create_fixed_transition(ex))
            journeys[(st, li)] = (sim.add_journey(jd), qid)
            queues[(st, li)] = sim.get_stage(qid)
    t_start = max(0.0, min([p["t0"] for p in ppl] + [t for v in inflow_t.values() for t in v[:1]] + [1e9]) - 1.0)
    pending = sorted(ppl, key=lambda p: p["t0"])
    pi = 0
    tokens = {st: 0.0 for st in prep.open_stairs}
    inflow_wait = {st: 0 for st in prep.open_stairs}
    inflow_idx = {st: 0 for st in prep.open_stairs}
    out_time = {st: 0.0 for st in prep.open_stairs}
    served = {st: {"deck5": 0, "inflow": 0} for st in prep.open_stairs}
    qlen = {f"{st}{'PS'[li] if len(g.stairs[st].landings) > 1 else ''}": [] for st, li in queues}
    qmax = {k: 0 for k in qlen}
    stair_wait = {st: [] for st in prep.open_stairs}
    agent_meta = {}
    nx = ny = 0
    bx0, by0, bx1, by1 = g.walkable.bounds
    cell = float(m["density_cell_m"])
    nx, ny = int(math.ceil((bx1 - bx0) / cell)), int(math.ceil((by1 - by0) / cell))
    peak = np.zeros((ny, nx), np.float32)
    over4 = np.zeros((ny, nx), np.float32)
    frames = []
    rec_every = int(round(1.0 / (m["record_hz"] * dt)))
    sec_every = int(round(1.0 / dt))
    smoke_ev = list(prep.smoke)
    smoked: set[str] = set()
    smoked_poly = None
    smoked_union = None
    exposed: dict[int, float] = {}
    rerouted = 0
    target_of: dict[int, tuple[str, int]] = {}
    t = t_start
    step = 0
    removed_total = 0
    last_d5 = 0.0
    n_total = len(ppl)
    while True:
        # spawn people whose response time has passed
        while pi < len(pending) and pending[pi]["t0"] <= t:
            p = pending[pi]
            st, li = prep.target[p["space"]]
            jid, qid = journeys[(st, li)]
            if smoked:
                bt = _smoke_aware_target(prep, smoked_union, (p["x"], p["y"]))
                if bt:
                    st, li = bt[0]
                    jid, qid = journeys[(st, li)]
            try:
                aid = sim.add_agent(jps.CollisionFreeSpeedModelAgentParameters(
                    position=(p["x"], p["y"]), journey_id=jid, stage_id=qid, desired_speed=p["v"],
                    radius=float(m["radius_m"]), time_gap=float(m["time_gap_s"])))
                agent_meta[aid] = p
                target_of[aid] = (st, li)
                pi += 1
            except Exception:  # noqa: BLE001  overlapping: try again next step
                p["t0"] = t + dt
                pending.sort(key=lambda q: q["t0"])
                break
        # smoke events: spaces fill; people re-route to a smoke-free landing where one exists
        while smoke_ev and smoke_ev[0]["t"] <= t:
            ev = smoke_ev.pop(0)
            smoked |= set(ev["spaces"])
            from shapely.ops import unary_union
            from shapely.prepared import prep as _prep
            smoked_union = unary_union([g.spaces[x] for x in smoked])
            smoked_poly = _prep(smoked_union)
            for a in list(sim.agents()):
                bt = _smoke_aware_target(prep, smoked_union, a.position)
                nt = bt[0] if bt else None
                if nt and nt != target_of.get(a.id):
                    jid, qid = journeys[nt]
                    try:
                        sim.switch_agent_journey(a.id, jid, qid)
                        target_of[a.id] = nt
                        rerouted += 1
                    except Exception:  # noqa: BLE001
                        pass
        # inflows arrive at their stair
        for st in prep.open_stairs:
            arr = inflow_t[st]
            while inflow_idx[st] < len(arr) and arr[inflow_idx[st]] <= t:
                inflow_idx[st] += 1
                inflow_wait[st] += 1
        # stair service: tokens at capacity, shared by the landing queues and the inflow (proportional to waiting)
        for st in prep.open_stairs:
            tokens[st] = min(tokens[st] + prep.capacity[st] * dt, 1.0 + prep.capacity[st] * dt)
            while tokens[st] >= 1.0:
                ql = [(li, queues[(st, li)]) for li in range(len(g.stairs[st].landings)) if (st, li) in queues]
                heads = [(li, q) for li, q in ql if q.count_enqueued() > 0 and _head_ready(sim, q)]
                w5 = sum(q.count_enqueued() for _, q in heads)
                wi = inflow_wait[st]
                if w5 + wi == 0:
                    tokens[st] = min(tokens[st], 1.0)
                    break
                if rng.random() < wi / (w5 + wi):
                    inflow_wait[st] -= 1
                    served[st]["inflow"] += 1
                else:
                    li, q = max(heads, key=lambda h: h[1].count_enqueued())
                    q.pop(1)
                    served[st]["deck5"] += 1
                tokens[st] -= 1.0
                out_time[st] = t
        sim.iterate()
        step += 1
        t += dt
        for aid in sim.removed_agents():     # left the deck at the queue head = entered the stair
            last_d5 = t
            p = agent_meta.get(aid)
            if p is not None:
                st = prep.target[p["space"]][0]
                out_time[st] = max(out_time[st], t)
        if step % sec_every == 0:
            for (st, li), q in queues.items():
                k = f"{st}{'PS'[li] if len(g.stairs[st].landings) > 1 else ''}"
                n = q.count_enqueued()
                qlen[k].append(n)
                qmax[k] = max(qmax[k], n)
            for st in prep.open_stairs:
                stair_wait[st].append(inflow_wait[st])
            if smoked_poly is not None:
                for a in sim.agents():
                    if smoked_poly.contains(Point(a.position)):
                        exposed[a.id] = exposed.get(a.id, 0.0) + 1.0
        if step % rec_every == 0:
            pos = [(a.id, a.position[0], a.position[1]) for a in sim.agents()]
            if pos:
                xs = np.array([p[1] for p in pos])
                ys = np.array([p[2] for p in pos])
                h, _, _ = np.histogram2d(ys, xs, bins=[ny, nx], range=[[by0, by0 + ny * cell], [bx0, bx0 + nx * cell]])
                # 1 m^2 window (2 x 2 cells of 0.5 m) -> p/m2
                from numpy.lib.stride_tricks import sliding_window_view
                hp = np.pad(h, ((0, 1), (0, 1)))
                d = sliding_window_view(hp, (2, 2)).sum(axis=(2, 3)) / (4 * cell * cell)
                np.maximum(peak, d, out=peak)
                over4 += (d > PARAMS["congestion"]["density_p_m2"]["value"]) * (1.0 / m["record_hz"])
            if record:
                frames.append([round(t, 2), [[a, round(x, 2), round(y, 2)] for a, x, y in pos]])
        done_spawn = pi >= len(pending)
        done_inflow = all(inflow_idx[s] >= len(inflow_t[s]) and inflow_wait[s] == 0 for s in prep.open_stairs)
        if done_spawn and done_inflow and sim.agent_count() == 0:
            break
        if t - t_start > m["max_sim_s"]:
            break
    tA = max(out_time.values()) if out_time else 0.0
    congested_s = float(over4.max()) if over4.size else 0.0
    res = {
        "seed": seed, "tA_s": round(tA, 1), "deck5_last_s": round(last_d5, 1),
        "people_deck5": n_total, "inflow": dict(prep.inflow),
        "stairs": {st: {"last_s": round(out_time[st], 1), **served[st], "capacity_p_s": prep.capacity[st]}
                   for st in prep.open_stairs},
        "queue_max": qmax, "inflow_wait_max": {st: max(v) if v else 0 for st, v in stair_wait.items()}, "peak_density_p_m2": round(float(peak.max()), 2),
        "congestion_s": round(congested_s, 1),
        "congestion_significant": bool(tA > 0 and congested_s > PARAMS["congestion"]["significant_share_of_tA"]["value"] * tA),
        "unfinished": sim.agent_count() + (len(pending) - pi),
        "t_start_s": round(t_start, 1),
    }
    if prep.smoke:
        res["smoke"] = {"people_exposed": len(exposed), "exposure_s_total": round(sum(exposed.values()), 1),
                        "rerouted": rerouted,
                        "corridor_reached_s": next((ev["t"] for ev in prep.smoke if any(
                            g.space_meta.get(x, {}).get("category") == "corridor" for x in ev["spaces"])), None)}
    if record:
        res["queue_series"] = {k: v for k, v in qlen.items()}
        res["inflow_wait_series"] = stair_wait
        res["series_t0_s"] = round(t_start + 1.0, 2)
        res["density"] = {"cell_m": cell, "origin": [bx0, by0], "nx": nx, "ny": ny,
                          "peak": np.round(peak, 2).tolist(), "over4_s": np.round(over4, 1).tolist()}
        res["frames"] = frames
        res["smoke_events"] = prep.smoke
        res["agents"] = {int(a): {"group": p["group"], "space": p["space"], "kind": p["kind"]}
                         for a, p in agent_meta.items()}
    return res


def _head_ready(sim, q) -> bool:
    return True


# ---------------------------------------------------------------- Monte Carlo
_PREP: Prep | None = None


def _init(prep):
    global _PREP
    _PREP = prep


def _work(seed):
    return run_one(_PREP, seed)


def monte_carlo(prep: Prep, n: int, base_seed: int = 1, workers: int | None = None, on_result=None) -> list[dict]:
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    seeds = [base_seed + i for i in range(n)]
    out = []
    ctx = mp.get_context("fork")
    with ctx.Pool(workers, initializer=_init, initargs=(prep,)) as pool:
        for r in pool.imap_unordered(_work, seeds):
            out.append(r)
            if on_result:
                on_result(r, len(out))
    return sorted(out, key=lambda r: r["seed"])
