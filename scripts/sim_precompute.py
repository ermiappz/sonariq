"""Precompute the demo simulations (500 runs each) into the disk cache, then write docs/DEMO_SCRIPT.md with the
numbers read from the cached results. Nothing in the demo script is typed by hand.

The golden-path models are rebuilt exactly as the chat builds them (Rev A + typed OR-117 edit, then fix 2), so their
model hashes match the live demo and Confirm returns the cached result at once.

Usage: python scripts/sim_precompute.py [--runs 500] [--only golden,files,fixes] [--doc-only]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT)]
os.environ.setdefault("SIMULATE_ENABLED", "1")

OR117 = {"kind": "add_cabin_block", "frame_from": 140.0, "count": 4, "berths_per_cabin": 2, "change_request": "OR-117"}
FIX2 = {"kind": "add_cabin_block", "frame_from": 140.0, "count": 4, "berths_per_cabin": 1, "change_request": "OR-117"}


def models():
    from sonariq.session import Session
    s = Session("A")
    s.analyse()
    s.apply_edit(OR117, confirm=True)
    m1 = s.model.copy()
    s.apply_edit(FIX2, confirm=True)
    m2 = s.model.copy()
    return s, m1, m2


def plan(runs: int):
    from sim.geometry import build
    from sim.runner import Scenario
    from sim.smoke import origin_near_stair
    s, m1, m2 = models()
    fire1 = origin_near_stair(build(m2), "3A")
    revB = s.load("B")
    fireB = origin_near_stair(build(revB), "3A")
    night = Scenario("night", "primary")
    return [
        ("golden_or117_night", m1, night, "A + 4×2 berth OR-117", "golden"),
        ("golden_fix2_night", m2, night, "A + 4×1 berth OR-117", "golden"),
        ("golden_fix2_fire_3A", m2, Scenario("night", "primary", fire_origin=fire1), "A + 4×1 berth OR-117", "golden"),
        ("revA_night", s.load("A"), night, "A", "files"),
        ("revB_night", revB, night, "B", "files"),
        ("revBfix2_night", s.load("Bfix2"), night, "Bfix2", "files"),
        ("revB_fire_3A", revB, Scenario("night", "primary", fire_origin=fireB), "B", "files"),
    ], m1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=500)
    ap.add_argument("--only", default="golden,files,fixes")
    ap.add_argument("--doc-only", action="store_true")
    a = ap.parse_args()
    from sim.service import SimService
    svc = SimService()
    jobs, m1 = plan(a.runs)
    index = {}
    for name, model, sc, tag, group in jobs:
        jid = svc.job_id(model, sc, a.runs)
        index[name] = {"id": jid, "revision": tag, "scenario": sc.key()}
        if a.doc_only or group not in a.only.split(","):
            continue
        t = time.time()
        st = svc.start(model, sc, a.runs, revision=tag, wait=True)
        print(f"{name}: {st.get('state')} {jid} {round(time.time() - t)} s", flush=True)
    if "fixes" in a.only.split(",") and not a.doc_only:
        from sim.fixes import explore
        from sonariq.engine import analyse
        from sonariq.llm import LLM
        run = analyse(m1, ["fls", "acc", "dnv"])
        key = next(k for k, i in run.ids.items() if i == "F-07")
        ex = explore(svc, m1, run, "F-07", key, {"case": "night", "route": "primary"}, "A + 4×2 berth OR-117", LLM())
        for c in ex["candidates"]:
            if c.get("sim_id"):
                while svc.status(c["sim_id"])["state"] not in ("done", "error", "cancelled"):
                    time.sleep(2)
        index["fixes_or117"] = ex
        print("fixes:", [(c["label"], c.get("verdict"), c.get("sim_id")) for c in ex["candidates"]], flush=True)
    out = ROOT / "data" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "precompute.json").write_text(json.dumps(index, indent=1, default=str))
    write_demo(svc, index)


def _resp():
    from sim.runner import PARAMS
    r = PARAMS["response"]["night"]
    return f"{r['min_s']}–{r['max_s']} s, MSC.1/Circ.1533 Annex 3 App.1 §3.2.2"


def _mmss(s):
    if s is None:
        return "—"
    m = int(s // 60)
    return f"{m:02d}:{int(round(s - 60 * m)):02d}"


def write_demo(svc, index):
    def R(name):
        try:
            return svc.results(index[name]["id"])
        except Exception:  # noqa: BLE001
            return None
    g1, g2, gf = R("golden_or117_night"), R("golden_fix2_night"), R("golden_fix2_fire_3A")
    rA, rB, rBf, rBfire = R("revA_night"), R("revB_night"), R("revBfix2_night"), R("revB_fire_3A")

    def line(r, label):
        if not r:
            return f"| {label} | not computed yet | | | |"
        worst = max(r["landings"].items(), key=lambda kv: kv[1]["queue_max_p95"])
        return (f"| {label} | {r['runs']} | {_mmss(r['tA_p95_s'])} ({r['tA_p95_s']} s) | "
                f"{worst[0]} · {worst[1]['queue_max_p95']} | {r['peak_density_p95']} |")

    def landing(r, k):
        return (r or {}).get("landings", {}).get(k, {}).get("queue_max_p95", "—")

    from sim.service import LABEL
    lines = [
        "# SonarIQ demo script (golden path v3)",
        "",
        f"Generated by `make sim-precompute` on {time.strftime('%a %d %b %H:%M')} from the cached simulation results. "
        "Every number below is read from the engine's results JSON; do not edit numbers by hand, re-run the script.",
        "",
        f"Every result screen carries: *{LABEL}*.",
        "",
        "## Before you start",
        "",
        "1. `make api-sim` (engine with Simulate on, port 8765) and `make portal` (http://localhost:5173).",
        "2. FreeCAD: open `data/deck5_revA.ifc`. The panel shows **Analyse** and **Simulate**.",
        "3. The simulations below are cached (500 runs each), so Confirm shows the result at once. "
        "If the cache is missing, set the runs stepper to 20 and say so.",
        "",
        "## Steps",
        "",
        "1. **Analyse** Rev A. Point at F-01 (MVZ door A-0 in A-60).",
        "2. Chat: *Add 4 cabins inboard at Fr 140 for OR-117* → preview → **Confirm**. The ping re-runs the "
        "affected checks; **F-07 Stair 3B fails** (and F-08 dead end).",
        "3. Chat: *Why does F-07 fail?* → cited answer (FSS reading + Circ.1533 text), numbers checked.",
        "4. **Simulate** → *Simulation preview* (people on Deck 5, inflow to 3B, model gaps) → **Confirm** → result card.",
    ]
    if g1:
        w = max(g1["landings"].items(), key=lambda kv: kv[1]["queue_max_p95"])
        lines += [f"   - Expect: p95 **{_mmss(g1['tA_p95_s'])}** over {g1['runs']} runs; longest landing queue "
                  f"**{w[0]} · {w[1]['queue_max_p95']} people** (p95); longest route {g1['longest_route']['length_m']} m "
                  f"from {g1['longest_route']['space']}."]
        ev = {e["kind"]: e for e in g1.get("events", [])}
        if "queue_peak" in ev:
            lines += [f"   - Replay (W10, **Open replay**): the 3B queue peaks at {ev['queue_peak']['people']} on "
                      f"{ev['queue_peak']['landing']} at {_mmss(ev['queue_peak']['t_s'])}; click the hotspot → "
                      "**Pin to review** (BCF viewpoint + comment on the finding)."]
    lines += ["5. Chat: *Apply fix 2* (four cabins, one berth each) → **Confirm** → F-07 clears (rule engine)."]
    if g1 and g2:
        lines += [f"6. **Simulate** again → compare: p95 {_mmss(g1['tA_p95_s'])} → {_mmss(g2['tA_p95_s'])} "
                  f"({round(g2['tA_p95_s'] - g1['tA_p95_s'], 1):+} s); 3B landing queue p95 "
                  f"3BP {landing(g1, '3BP')} → {landing(g2, '3BP')}, 3BS {landing(g1, '3BS')} → {landing(g2, '3BS')}.",
                  "   - Say it straight: fix 2 makes the **rule** pass; in the night case the evacuation time is driven by "
                  f"the response-time spread ({_resp()}), so read the change against that. That is the design insight."]
    lines += ["7. Chat: *Fire near stair 3A at night* → *Fire what-if · preview* (mini plan, hatched smoke) → **Confirm**."]
    if gf:
        sm = gf.get("replay_run", {})
        lines += [f"   - Expect: p95 **{_mmss(gf['tA_p95_s'])}**; label *Illustrative smoke spread, not a fire model*; "
                  "smoke stops at the self-closing stair and MVZ doors."]
        _ = sm
    lines += [
        "8. Portal W3 (F-07 thread): Source text, the pinned replay moment, **Approve** (signed row) → "
        "**Export BCF** from the panel (topics carry the pin viewpoint and the sign-off comment).",
        "9. Optional: W10 **Try fixes** → each fix re-checked by the rule engine and re-simulated with 100 runs; "
        "rejected ideas listed, not simulated.",
        "",
        "## Results table (500 runs each, night case, Deck 5 sub-model)",
        "",
        "| Model | Runs | p95 assembly | Longest landing queue (p95) | Peak density p95 (p/m²) |",
        "|---|---|---|---|---|",
        line(g1, "Rev A + OR-117 (typed edit)"), line(g2, "Rev A + OR-117 + fix 2"),
        line(gf, "… + fix 2, fire what-if near Stair 3A"),
        line(rA, "Rev A (IFC)"), line(rB, "Rev B (IFC)"), line(rBf, "Rev B + fix 2 (IFC)"),
        line(rBfire, "Rev B, fire what-if near Stair 3A"),
        "",
    ]
    fx = index.get("fixes_or117")
    if fx:
        lines += ["## Fix explorer (F-07, Rev A + OR-117, 100 runs each)", "",
                  "| # | Fix | Rule engine | p95 after |", "|---|---|---|---|"]
        for c in fx["candidates"]:
            r = None
            if c.get("sim_id"):
                try:
                    r = svc.results(c["sim_id"])
                except Exception:  # noqa: BLE001
                    r = None
            lines.append(f"| {c['n']} | {c['label']} | {c.get('verdict')}{' (rejected, not simulated)' if c.get('rejected') else ''} | "
                         f"{_mmss(r['tA_p95_s']) if r else '—'} |")
        lines.append("")
    lines += ["## If something breaks", "",
              "- AI offline or slow (> 8 s): explanations fall back to the rule engine's text (badge *Rule engine text*).",
              "- Simulation not cached: lower the runs (stepper) and say the number on screen.",
              "- Portal: `make portal`; replay needs the engine on 8765.", ""]
    (ROOT / "docs" / "DEMO_SCRIPT.md").write_text("\n".join(lines))
    print("wrote docs/DEMO_SCRIPT.md")


if __name__ == "__main__":
    main()
