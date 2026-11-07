"""Simulation jobs: disk cache by model hash + scenario hash, live run count, summary, replay, compare.

Cache layout: data/cache/sim/<model hash>_<scenario hash>/{meta.json, runs.jsonl, summary.json, replay.json}
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

import numpy as np

from .runner import PARAMS, Prep, Scenario, monte_carlo, prepare, run_one

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path(os.getenv("SQ_SIM_CACHE", ROOT / "data" / "cache" / "sim"))
LABEL = "Deck 5 sub-model with inflows from Decks 4, 6, 7 · design insight, not a full-ship Circ.1533 analysis"
SIM_VERSION = "sim-0.4"


def model_hash(model) -> str:
    fp = sorted(e.fingerprint() for e in model.elements.values())
    return hashlib.sha256(json.dumps([SIM_VERSION, fp]).encode()).hexdigest()[:12]


def scenario_hash(sc: Scenario) -> str:
    return hashlib.sha256(json.dumps([sc.key(), PARAMS], sort_keys=True, default=str).encode()).hexdigest()[:12]


def pct(vals, q):
    return float(np.percentile(np.array(vals, float), q)) if vals else None


def summarize(runs: list[dict], prep_info: dict) -> dict:
    tA = [r["tA_s"] for r in runs]
    q = PARAMS["runs"]["percentile"]
    p95 = pct(tA, q)
    nearest = min(runs, key=lambda r: abs(r["tA_s"] - p95)) if runs else None
    stairs = {}
    for st in (runs[0]["stairs"] if runs else {}):
        stairs[st] = {"last_p95_s": round(pct([r["stairs"][st]["last_s"] for r in runs], q), 1),
                      "capacity_p_s": runs[0]["stairs"][st]["capacity_p_s"],
                      "deck5_mean": round(float(np.mean([r["stairs"][st]["deck5"] for r in runs])), 1),
                      "inflow": runs[0]["stairs"][st]["inflow"],
                      "inflow_wait_max_p95": round(pct([r["inflow_wait_max"][st] for r in runs], q), 1)}
    landings = {}
    for k in (runs[0]["queue_max"] if runs else {}):
        vals = [r["queue_max"][k] for r in runs]
        landings[k] = {"queue_max_p95": round(pct(vals, q), 1), "queue_max_mean": round(float(np.mean(vals)), 1),
                       "queue_max_max": int(max(vals))}
    hist_edges = np.linspace(min(tA), max(tA) + 1e-6, 21).tolist() if tA else []
    hist = np.histogram(tA, bins=hist_edges)[0].tolist() if tA else []
    return {
        "runs": len(runs), "target_runs": PARAMS["runs"]["target"],
        "tA_p50_s": round(pct(tA, 50), 1) if tA else None,
        "tA_p95_s": round(p95, 1) if tA else None,
        "tA_min_s": min(tA) if tA else None, "tA_max_s": max(tA) if tA else None,
        "tA_mean_s": round(float(np.mean(tA)), 1) if tA else None,
        "deck5_last_p95_s": round(pct([r["deck5_last_s"] for r in runs], q), 1) if runs else None,
        "peak_density_p95": round(pct([r["peak_density_p_m2"] for r in runs], q), 2) if runs else None,
        "congestion_significant_share": round(float(np.mean([r["congestion_significant"] for r in runs])), 3) if runs else None,
        "unfinished_runs": sum(1 for r in runs if r["unfinished"]),
        "stairs": stairs, "landings": landings,
        "histogram": {"edges": [round(e, 1) for e in hist_edges], "counts": hist},
        "p95_seed": nearest["seed"] if nearest else None,
        "people_deck5": runs[0]["people_deck5"] if runs else None,
        **prep_info,
        "label": LABEL,
        "percentile": q,
    }


def prep_info(prep: Prep) -> dict:
    far = max(prep.route_len.items(), key=lambda kv: kv[1]) if prep.route_len else (None, None)
    cabins = {k: v for k, v in prep.route_len.items() if prep.geom.space_meta.get(k, {}).get("category") == "cabin"}
    farc = max(cabins.items(), key=lambda kv: kv[1]) if cabins else far
    return {
        "longest_route": {"space": farc[0], "length_m": farc[1],
                          "stair": prep.target.get(farc[0], (None,))[0],
                          "path": prep.route_path.get(farc[0])},
        "open_stairs": prep.open_stairs,
        "capacity_p_s": prep.capacity,
        "inflow": prep.inflow,
        "target_stair": {k: v[0] for k, v in prep.target.items()},
        "dropped_spaces": prep.geom.dropped,
    }


def congestion(prep: Prep, rep: dict, top: int = 6) -> list[dict]:
    """Places sorted by peak density in the replay run (p95 run): spaces, stair landings and MVZ/stair doors."""
    from shapely.geometry import Point
    d = rep["density"]
    cs, (ox, oy) = d["cell_m"], d["origin"]
    peak, over = d["peak"], d["over4_s"]
    g = prep.geom
    places = []
    for n, poly in g.spaces.items():
        m = g.space_meta.get(n, {})
        if m.get("category") == "stair":
            label = f"Stair {m.get('stair') or n.split('-')[-1]} landing · Deck 5"
        elif m.get("category") == "corridor":
            label = f"Deck 5 · Fr {m.get('frame')} · {m.get('side')}"
        else:
            continue
        places.append((n, label, poly))
    for dn, door in g.doors.items():
        if dn.startswith("FD-") and not dn.startswith("FD-5-208"):
            places.append((dn, f"{dn} · MVZ door", door.poly.buffer(0.8)))
    out = []
    for n, label, poly in places:
        x0, y0, x1, y1 = poly.bounds
        best, o4 = 0.0, 0.0
        for j in range(max(0, int((y0 - oy) / cs)), min(d["ny"], int((y1 - oy) / cs) + 1)):
            for i in range(max(0, int((x0 - ox) / cs)), min(d["nx"], int((x1 - ox) / cs) + 1)):
                if poly.contains(Point(ox + (i + 0.5) * cs, oy + (j + 0.5) * cs)):
                    best = max(best, peak[j][i])
                    o4 = max(o4, over[j][i])
        if best > 0:
            out.append({"place": n, "label": label, "peak_p_m2": round(best, 2), "above4_s": round(o4, 1)})
    return sorted(out, key=lambda r: -r["peak_p_m2"])[:top]


def events(rep: dict) -> list[dict]:
    ev = []
    sm = (rep.get("smoke") or {}).get("corridor_reached_s")
    if sm is not None:
        ev.append({"kind": "smoke_corridor", "label": "Smoke reaches corridor", "t_s": sm})
    best = None
    for k, ser in (rep.get("queue_series") or {}).items():
        if ser:
            i = max(range(len(ser)), key=lambda x: ser[x])
            if best is None or ser[i] > best[1]:
                best = (k, ser[i], rep["series_t0_s"] + i)
    if best and best[1] > 0:
        ev.append({"kind": "queue_peak", "label": "Queue peak", "t_s": round(best[2], 1), "landing": best[0],
                   "people": best[1]})
    ev.append({"kind": "last_out", "label": "Last person out", "t_s": rep["tA_s"]})
    return sorted(ev, key=lambda e: e["t_s"])


class Job:
    def __init__(self, jid: str, model, sc: Scenario, n: int, revision: str, label: str | None = None):
        self.id, self.model, self.sc, self.n = jid, model, sc, n
        self.revision = revision
        self.dir = CACHE / jid
        self.state = "queued"
        self.count = 0
        self.error = None
        self.started = time.time()
        self.finished = None
        self.label = label or sc.label()
        self.lock = threading.Lock()
        self.partial: list[dict] = []
        self.prep_info: dict = {}

    def status(self) -> dict:
        s = {"id": self.id, "state": self.state, "runs_done": self.count, "runs_target": self.n,
             "elapsed_s": round((self.finished or time.time()) - self.started, 1), "scenario": self.sc.key(),
             "scenario_label": self.label, "revision": self.revision, "label": LABEL, "error": self.error}
        if self.partial and self.state == "running":
            tA = [r["tA_s"] for r in self.partial]
            s["live"] = {"tA_p95_s": round(pct(tA, 95), 1), "tA_p50_s": round(pct(tA, 50), 1)}
        return s

    def run(self):
        try:
            self.state = "preparing"
            prep = prepare(self.model, self.sc)
            self.prep_info = prep_info(prep)
            self.dir.mkdir(parents=True, exist_ok=True)
            import pickle
            (self.dir / "model.pkl").write_bytes(pickle.dumps(self.model))
            (self.dir / "meta.json").write_text(json.dumps({"scenario": self.sc.key(), "label": self.label,
                                                            "revision": self.revision, "n": self.n,
                                                            "geometry": prep.geom.to_json()}, default=str))
            self.state = "running"
            runs_f = (self.dir / "runs.jsonl").open("w")

            def on(r, k):
                with self.lock:
                    self.partial.append(r)
                    self.count = k
                runs_f.write(json.dumps(r) + "\n")
                runs_f.flush()
            runs = monte_carlo(prep, self.n, on_result=on, workers=int(os.getenv("SQ_SIM_WORKERS", "3")))
            runs_f.close()
            summ = summarize(runs, self.prep_info)
            summ |= {"scenario": self.sc.key(), "scenario_label": self.label, "revision": self.revision,
                     "elapsed_s": round(time.time() - self.started, 1)}
            self.state = "replay"
            rep = run_one(prep, summ["p95_seed"], record=True)
            summ["congestion"] = congestion(prep, rep)
            summ["events"] = events(rep)
            (self.dir / "replay.json").write_text(json.dumps(rep, separators=(",", ":")))
            summ["replay_run"] = {k: rep[k] for k in ("seed", "tA_s", "queue_max", "peak_density_p_m2",
                                                       "inflow_wait_max", "deck5_last_s")}
            (self.dir / "summary.json").write_text(json.dumps(summ, indent=1, default=str))
            self.state = "done"
        except Exception as e:  # noqa: BLE001
            import traceback
            self.error = f"{type(e).__name__}: {e}"
            traceback.print_exc()
            self.state = "error"
        finally:
            self.finished = time.time()


class SimService:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self._setup: dict[str, dict] = {}

    def setup(self, model, sc: Scenario) -> dict:
        """W9: initial people, routes, closed routes, fire origin, model reader gaps, scenario sentence."""
        from .reader import setup as _setup
        k = f"{model_hash(model)}_{scenario_hash(sc)}"
        if k not in self._setup:
            prep = prepare(model, sc)
            self._setup[k] = _setup(prep, model, sc) | {"scenario": sc.key(), "scenario_label": sc.label(),
                                                       "revision": model.revision, "label": LABEL,
                                                       "runs_default": PARAMS["runs"]["target"]}
        return self._setup[k]

    def job_id(self, model, sc: Scenario, n: int) -> str:
        return f"{model_hash(model)}_{scenario_hash(sc)}_{n}"

    def start(self, model, sc: Scenario, n: int | None = None, revision: str = "", label: str | None = None,
              wait: bool = False) -> dict:
        n = int(n or PARAMS["runs"]["target"])
        jid = self.job_id(model, sc, n)
        if (CACHE / jid / "summary.json").exists():
            return {"id": jid, "state": "done", "cached": True, "runs_done": n, "runs_target": n, "label": LABEL,
                    "scenario_label": label or sc.label(), "scenario": sc.key(), "revision": revision}
        if jid in self.jobs and self.jobs[jid].state not in ("error",):
            return self.jobs[jid].status()
        job = Job(jid, model.copy(), sc, n, revision, label)
        self.jobs[jid] = job
        if wait:
            job.run()
        else:
            threading.Thread(target=job.run, daemon=True).start()
        return job.status()

    def status(self, jid: str) -> dict:
        if jid in self.jobs:
            return self.jobs[jid].status()
        if (CACHE / jid / "summary.json").exists():
            s = json.loads((CACHE / jid / "summary.json").read_text())
            return {"id": jid, "state": "done", "cached": True, "runs_done": s["runs"], "runs_target": s["runs"],
                    "scenario": s.get("scenario"), "scenario_label": s.get("scenario_label"),
                    "revision": s.get("revision"), "label": LABEL}
        raise KeyError(jid)

    def model_of(self, jid: str):
        if jid in self.jobs:
            return self.jobs[jid].model
        import pickle
        p = CACHE / jid / "model.pkl"
        if not p.exists():
            raise KeyError(jid)
        return pickle.loads(p.read_bytes())

    def results(self, jid: str) -> dict:
        p = CACHE / jid / "summary.json"
        if not p.exists():
            raise KeyError(jid)
        return json.loads(p.read_text())

    def replay(self, jid: str) -> dict:
        p, m = CACHE / jid / "replay.json", CACHE / jid / "meta.json"
        if not p.exists():
            raise KeyError(jid)
        rep = json.loads(p.read_text())
        meta = json.loads(m.read_text())
        return {"id": jid, "label": LABEL, "scenario_label": meta.get("label"), "geometry": meta["geometry"],
                **rep, "smoke_label": PARAMS["smoke"]["label"] if meta["scenario"].get("fire_origin") else None}

    def compare(self, a: str, b: str) -> dict:
        ra, rb = self.results(a), self.results(b)

        def d(k):
            return None if ra.get(k) is None or rb.get(k) is None else round(rb[k] - ra[k], 1)
        landings = {}
        for k in set(ra["landings"]) | set(rb["landings"]):
            va = ra["landings"].get(k, {}).get("queue_max_p95")
            vb = rb["landings"].get(k, {}).get("queue_max_p95")
            landings[k] = {"before": va, "after": vb,
                           "delta": None if va is None or vb is None else round(vb - va, 1)}
        return {"before": {"id": a, "label": ra.get("scenario_label"), "revision": ra.get("revision"),
                           "tA_p95_s": ra["tA_p95_s"], "deck5_last_p95_s": ra["deck5_last_p95_s"]},
                "after": {"id": b, "label": rb.get("scenario_label"), "revision": rb.get("revision"),
                          "tA_p95_s": rb["tA_p95_s"], "deck5_last_p95_s": rb["deck5_last_p95_s"]},
                "delta": {"tA_p95_s": d("tA_p95_s"), "deck5_last_p95_s": d("deck5_last_p95_s")},
                "landings": landings, "label": LABEL}

    def list(self) -> list[dict]:
        out = []
        if CACHE.exists():
            for p in sorted(CACHE.glob("*/summary.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                s = json.loads(p.read_text())
                out.append({"id": p.parent.name, "scenario_label": s.get("scenario_label"),
                            "revision": s.get("revision"), "runs": s["runs"], "tA_p95_s": s["tA_p95_s"]})
        return out
