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
SIM_VERSION = "sim-0.3"


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
