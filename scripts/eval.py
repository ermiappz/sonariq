"""make eval: rules benchmark, simulation sanity, AI evals, golden path v3. Writes data/out/eval.json and appends
a delta to docs/EVAL.md. Every number in the report comes from this run.

Usage: python scripts/eval.py [--quick] [--only rules,sim,ai,golden] [--no-append]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT)]
os.environ.setdefault("SIMULATE_ENABLED", "1")
OUT = ROOT / "data" / "out"
DATA = ROOT / "data"


def load(rev):
    from sonariq.model import load_ifc
    p = {"A": DATA / "deck5_revA.ifc", "B": DATA / "deck5_revB.ifc", "Bfix2": DATA / "deck5_revB_fix2.ifc"}[rev]
    return load_ifc(p, rev)


# =============================================================================== A. rules benchmark
def _set_pset(m, name, pset, prop, value):
    e = m.by_name(name)
    if value is None:
        e.psets.get(pset, {}).pop(prop, None)
    else:
        e.psets.setdefault(pset, {})[prop] = value


def _plate_thin(m, name, t_m):
    e = m.by_name(name)
    e.z1 = e.z0 + t_m


PLANTS = [
    # (id, description, mutate(model), expected [(rule, element, status)], allowed side effects [(rule, element)])
    ("P01", "stair door B-15 in an A-0 enclosure",
     lambda m: _set_pset(m, "D-5-171-P", "Pset_DoorCommon", "FireRating", "B-15"),
     [("R-FLS-01", "D-5-171-P", "fail")], []),
    ("P02", "accessible stair door narrowed to 700 mm",
     lambda m: setattr(m.by_name("D-5-161-S"), "overall_width", 0.70),
     [("R-ACC-02", "D-5-161-S", "fail")], []),
    ("P03", "corridor COR-5-178-S narrowed to 850 mm", "edit:move_wall:COR-5-178-S:850",
     [("R-FLS-04", "COR-5-178-S", "fail")], [("R-ACC-01", "COR-5-178-S")]),
    ("P04", "MVZ fire door not self-closing",
     lambda m: _set_pset(m, "FD-5-165S", "Pset_DoorCommon", "SelfClosing", False),
     [("R-FLS-10", "FD-5-165S", "fail")], []),
    ("P05", "stair door self-closing not stated",
     lambda m: _set_pset(m, "D-5-161-P", "Pset_DoorCommon", "SelfClosing", None),
     [("R-FLS-10", "D-5-161-P", "unk")], []),
    ("P06", "MVZ bulkhead downgraded to A-30",
     lambda m: _set_pset(m, "BHD-5-165", "Pset_WallCommon", "FireRating", "A-30"),
     [("R-FLS-06", "BHD-5-165", "fail")], []),
    ("P07", "stair 3A enclosure wall B-15",
     lambda m: _set_pset(m, "WA0-STAIR3A-P", "Pset_WallCommon", "FireRating", "B-15"),
     [("R-FLS-08", "Stair 3A", "fail")], [("R-FLS-01", "D-5-171-P"), ("R-FLS-10", "D-5-171-P"),
                                         ("R-FLS-11", "GL-5-172-P")]),
    ("P08", "stair glazing B-0 in an A-0 enclosure",
     lambda m: _set_pset(m, "GL-5-162-P", "Pset_WindowCommon", "FireRating", "B-0"),
     [("R-FLS-11", "GL-5-162-P", "fail")], []),
    ("P09", "24 extra berths in MVZ 4 (6 cabins × 4)", "edit:add_cabin_block:148:6:4",
     [("R-FLS-03", "Stair 3B", "fail")], [("R-FLS-02", "*"), ("R-FLS-04", "*"), ("R-ACC-01", "*"), ("R-FLS-07", "*")]),
    ("P10", "fire damper removed from VD-5-01",
     lambda m: m.elements.pop(m.by_name("FDMP-5-165-01").guid),
     [("R-FLS-05", "VD-5-01", "fail")], []),
    ("P11", "deck plate PL-5-03 at 4 mm",
     lambda m: _plate_thin(m, "PL-5-03", 0.004),
     [("R-DNV-01", "PL-5-03", "fail")], []),
    ("P12", "stair door fire rating missing",
     lambda m: _set_pset(m, "D-5-161-S", "Pset_DoorCommon", "FireRating", None),
     [("R-FLS-01", "D-5-161-S", "unk")], []),
]


def _key(r):
    return (r.rule.id, r.element.name if r.element else "-")


def eval_rules() -> dict:
    from sonariq.edits import apply_edit
    from sonariq.engine import analyse
    groups = ["fls", "acc", "dnv", "hvac"]
    base_m = load("A")
    base = {_key(r): r.status for r in analyse(base_m, groups).results}
    rows, caught, missed, false_alarms = [], 0, 0, 0
    for pid, desc, mut, expected, allowed in PLANTS:
        m = base_m.copy()
        if isinstance(mut, str):
            _, kind, *a = mut.split(":")
            if kind == "move_wall":
                m, _, _ = apply_edit(m, {"kind": "move_wall", "space": a[0], "width_mm": float(a[1])})
            else:
                m, _, _ = apply_edit(m, {"kind": "add_cabin_block", "frame_from": float(a[0]), "count": int(a[1]),
                                         "berths_per_cabin": int(a[2]), "change_request": "PLANT"})
        else:
            mut(m)
        res = {_key(r): r.status for r in analyse(m, groups).results}
        got = []
        for rule, el, st in expected:
            ok = res.get((rule, el)) == st and base.get((rule, el)) != st
            got.append(ok)
        new_bad = [k for k, s in res.items() if s in ("fail", "warn", "unk") and base.get(k) != s
                   and not any(k[0] == r and k[1] == e for r, e, _ in expected)
                   and not any(k[0] == r and (e == "*" or k[1] == e) for r, e in allowed)]
        c = all(got)
        caught += c
        missed += not c
        false_alarms += len(new_bad)
        rows.append({"id": pid, "plant": desc, "caught": c, "false_alarms": [f"{a} {b}" for a, b in new_bad]})
    # contract: the shipped revisions give exactly the designed findings
    contract = {}
    for rev, want in (("A", {"F-01", "W-01", "U-01"}), ("B", {"F-01", "W-01", "U-01", "F-07", "F-08", "F-09"}),
                      ("Bfix2", {"F-01", "W-01", "U-01", "F-08", "F-09"})):
        run = analyse(load(rev), ["fls", "acc", "dnv"])
        got = set(run.ids[r.key] for r in run.results if r.key in run.ids and r.status in ("fail", "warn", "unk"))
        contract[rev] = {"expected": sorted(want), "got": sorted(got), "ok": got == want}
    return {"plants": len(PLANTS), "caught": caught, "missed": missed, "false_alarms": false_alarms, "rows": rows,
            "contract": contract}


# =============================================================================== B. simulation sanity
def eval_sim(quick=False) -> dict:
    from sim.geometry import route_length
    from sim.runner import Scenario, monte_carlo, prepare, run_one
    import jupedsim as jps
    out = {}
    m = load("A")
    prep = prepare(m, Scenario("night"))
    # 1. free walk: one person, known speed, empty deck -> time = route length / speed (within 5 %)
    rows = []
    routing = jps.RoutingEngine(prep.geom.walkable)
    for space, v in (("CAB-5212-S", 1.2), ("CAB-5120-P", 0.8), ("CAB-5150-S", 1.5)):
        sp = next(s for s in prep.spawn if s["space"] == space)
        st, li = prep.target[space]
        head = prep.geom.stairs[st].landings[li]
        L = route_length(routing, (sp["x"], sp["y"]), head)
        r = run_one(prep, 1, people=[{**sp, "group": "test", "v": v, "t0": 0.0}],
                    inflow_times={s: [] for s in prep.open_stairs})
        t_sim = r["deck5_last_s"]
        t_exp = L / v
        rows.append({"space": space, "route_m": round(L, 2), "speed": v, "expected_s": round(t_exp, 1),
                     "sim_s": t_sim, "err_pct": round(100 * (t_sim - t_exp) / t_exp, 1)})
    out["free_walk"] = {"rows": rows, "ok": all(abs(r["err_pct"]) <= 5 for r in rows)}
    # 2. wider stair -> shorter queue (day case, crowded)
    n = 6 if quick else 16
    q = {}
    for w in (1.35, 2.2):
        pr = prepare(load("B"), Scenario("day", stair_width_override={"3B": w}))
        runs = monte_carlo(pr, n, base_seed=100, workers=3)
        q[w] = {"queue_3B_mean": round(statistics.mean(r["queue_max"]["3BP"] + r["queue_max"]["3BS"] for r in runs), 2),
                "inflow_wait_3B_mean": round(statistics.mean(r["inflow_wait_max"]["3B"] for r in runs), 2),
                "stair_3B_last_mean_s": round(statistics.mean(r["stairs"]["3B"]["last_s"] for r in runs), 1)}
    out["wider_stair"] = {"runs_each": n, "w1.35": q[1.35], "w2.2": q[2.2],
                          "ok": (q[2.2]["queue_3B_mean"] + q[2.2]["inflow_wait_3B_mean"])
                          < (q[1.35]["queue_3B_mean"] + q[1.35]["inflow_wait_3B_mean"])}
    # 3. same seed -> same result
    a, b = run_one(prep, 7), run_one(prep, 7)
    out["same_seed"] = {"ok": json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True), "tA_s": a["tA_s"]}
    # 4. smoke: a closed self-closing door stops smoke entering
    try:
        from sim.smoke import smoke_schedule
        from sim.geometry import build
        g = build(m)
        stair_space = "STAIR-3B"
        sched = smoke_schedule(g, "LOUNGE-5-153", hop_s=60, until_s=3000)
        smoked = {s for ev in sched for s in ev["spaces"]}
        g2 = build(m)
        for dn in g2.stairs["3B"].doors:
            g2.doors[dn].self_closing = False
        sched2 = smoke_schedule(g2, "LOUNGE-5-153", hop_s=60, until_s=3000)
        smoked2 = {s for ev in sched2 for s in ev["spaces"]}
        out["smoke_door"] = {"ok": stair_space not in smoked and stair_space in smoked2,
                             "stair_smoked_with_self_closing": stair_space in smoked,
                             "stair_smoked_when_doors_open": stair_space in smoked2}
    except ImportError:
        out["smoke_door"] = {"ok": None, "note": "smoke not built yet"}
    except Exception as e:  # noqa: BLE001
        out["smoke_door"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    # timing
    t = time.time()
    run_one(prep, 3)
    out["run_s"] = round(time.time() - t, 2)
    out["ok"] = all(v.get("ok") is not False for v in out.values() if isinstance(v, dict))
    return out


# =============================================================================== C. AI
PHRASES = [  # (text, expected subset of the card)
    ("simulate night", {"type": "scenario_preview", "scenario": {"case": "night", "route": "primary"}}),
    ("Simulate the night case", {"type": "scenario_preview", "scenario": {"case": "night"}}),
    ("run a day evacuation", {"type": "scenario_preview", "scenario": {"case": "day"}}),
    ("what if stair 3A is out of use at night", {"type": "scenario_preview", "scenario": {"case": "night", "closed_stair": "3A"}}),
    ("evacuation during the day without stair 3B", {"type": "scenario_preview", "scenario": {"case": "day", "closed_stair": "3B"}}),
    ("secondary case, stair 3A blocked, daytime", {"type": "scenario_preview", "scenario": {"case": "day", "closed_stair": "3A"}}),
    ("fire near stair 3A at night", {"type": "scenario_preview", "scenario": {"case": "night", "fire_origin": "*"}}),
    ("fire in LOUNGE-5-153 during the day", {"type": "scenario_preview", "scenario": {"case": "day", "fire_origin": "LOUNGE-5-153"}}),
    ("how long does it take to evacuate at night if we lose stair 3B", {"type": "scenario_preview", "scenario": {"case": "night", "closed_stair": "3B"}}),
    ("replay the night case", {"type": "scenario_preview", "scenario": {"case": "night"}}),
    ("Add 4 cabins inboard at Fr 140 for OR-117", {"type": "edit_preview", "edit": {"kind": "add_cabin_block", "count": 4, "frame_from": 140.0, "berths_per_cabin": 2}}),
    ("add four 2-berth cabins at frame 140 (OR-117)", {"type": "edit_preview", "edit": {"kind": "add_cabin_block", "count": 4, "frame_from": 140.0}}),
    ("insert 4 single berth cabins at Fr 140", {"type": "edit_preview", "edit": {"kind": "add_cabin_block", "count": 4, "berths_per_cabin": 1}}),
    ("set FD-5-165P to A-60", {"type": "edit_preview", "edit": {"kind": "set_door_fire_class", "door": "FD-5-165P", "fire_class": "A-60"}}),
    ("upgrade door FD-5-165P to an A-60 fire door", {"type": "edit_preview", "edit": {"kind": "set_door_fire_class", "door": "FD-5-165P", "fire_class": "A-60"}}),
    ("make the corridor COR-5-152-S 900 mm wide", {"type": "edit_preview", "edit": {"kind": "move_wall", "space": "COR-5-152-S", "width_mm": 900.0}}),
    ("widen D-5-171-P to 950 mm", {"type": "edit_preview", "edit": {"kind": "set_door_width", "door": "D-5-171-P", "width_mm": 950.0}}),
    ("put a sauna in the lounge", {"type": "error", "refused": True}),
    ("delete the MVZ bulkhead", {"type": "error", "refused": True}),
    ("apply fix 2", {"type": "edit_preview", "edit": {"kind": "add_cabin_block", "berths_per_cabin": 1}}),
    ("what if a fire starts in the service space?", {"type": "scenario_preview", "scenario": {"fire_origin": "*"}}),
    ("what if Stair 3B is out?", {"type": "scenario_preview", "scenario": {"closed_stair": "3B"}}),
    ("night with FD-5-165P out", {"type": "scenario_preview", "scenario": {"case": "night", "closed_door": "FD-5-165P"}}),
]


def _match(card: dict, want: dict) -> bool:
    for k, v in want.items():
        if isinstance(v, dict):
            sub = card.get(k) or {}
            for kk, vv in v.items():
                if vv == "*":
                    if not sub.get(kk):
                        return False
                elif sub.get(kk) != vv:
                    return False
        elif card.get(k) != v:
            return False
    return True


def eval_ai() -> dict:
    from fastapi.testclient import TestClient
    import sonariq.api as api
    from sonariq.llm import CACHE, check_numbers
    c = TestClient(api.app)
    out = {}
    c.post("/analyse", json={"revision": "B"})
    rows = []
    for text, want in PHRASES:
        t = time.time()
        r = c.post("/chat", json={"text": text}).json()
        card = r["cards"][0]
        ok = _match(card, want)
        rows.append({"text": text, "ok": ok, "got": {k: card.get(k) for k in ("type", "scenario", "edit", "refused") if card.get(k) is not None},
                     "source": card.get("source"), "ms": round((time.time() - t) * 1000)})
    out["phrasings"] = {"n": len(rows), "correct": sum(r["ok"] for r in rows), "rows": rows}
    # number guard over all cached free-text explanations
    tot, ok, bad = 0, 0, []
    for p in CACHE.glob("*.json"):
        try:
            d = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(d, dict) or d.get("json") or "prompt" not in d:
            continue
        tot += 1
        b = check_numbers(d["text"], d["prompt"])
        if b:
            bad.append({"file": p.name, "numbers": b, "text": d["text"][:160]})
        else:
            ok += 1
    out["number_guard"] = {"cached_explanations": tot, "pass": ok,
                           "pass_rate": round(ok / tot, 3) if tot else None, "failures": bad[:10],
                           "note": "a failure here was caught at answer time and replaced by the engine's text"}
    # latency cold vs cached
    S = api.S
    f = S.finding("F-07")
    q = f"latency probe {time.time()}"
    t = time.time()
    S.llm.explain(f, q)
    cold = time.time() - t
    t = time.time()
    S.llm.explain(f, q)
    warm = time.time() - t
    out["latency"] = {"cold_ms": round(cold * 1000), "cached_ms": round(warm * 1000), "model": S.llm.gateway.name}
    # RAG
    try:
        from sonariq.rag import RAG_EVAL, get_rag
        rag = get_rag()
        rows = []
        for qq, src, para in RAG_EVAL:
            hits = rag.search(qq, k=3)
            top = hits[0] if hits else {}
            ok = bool(hits) and any(h.get("source") == src and (para is None or para in (h.get("citation") or ""))
                                    for h in hits[:3])
            rows.append({"q": qq, "want": f"{src} {para or ''}".strip(), "top": top.get("citation"), "ok": ok})
        out["rag"] = {"n": len(rows), "correct": sum(r["ok"] for r in rows), "backend": rag.backend, "rows": rows}
    except ImportError:
        out["rag"] = {"n": 0, "note": "RAG not built yet"}
    return out


# =============================================================================== D. golden path v3
def eval_golden(runs=20) -> dict:
    from fastapi.testclient import TestClient
    import importlib
    import sonariq.api as api
    importlib.reload(api)
    c = TestClient(api.app)
    steps = []

    def step(name, ok, **kw):
        steps.append({"step": name, "ok": bool(ok), **kw})
        return ok

    def wait(jid, limit=900):
        t = time.time()
        while time.time() - t < limit:
            s = c.get(f"/simulate/{jid}").json()
            if s["state"] in ("done", "error"):
                return s
            time.sleep(1)
        return {"state": "timeout"}
    try:
        r = c.post("/analyse", json={"revision": "A"}).json()
        step("Analyse Rev A", r["counts"]["fail"] >= 1, counts=r["counts"])
        card = c.post("/chat", json={"text": "Add 4 cabins inboard at Fr 140 for OR-117"}).json()["cards"][0]
        step("Typed change OR-117 -> edit preview", card["type"] == "edit_preview", text=card.get("text"))
        p = c.post("/chat/confirm", json={"action": card["confirm"]}).json()["cards"][0]
        changed = [x["id"] for x in p["changed"]]
        step("Confirm -> Stair 3B fails (F-07)", "F-07" in changed, changed=changed, rerun=p["rerun"])
        card = c.post("/chat", json={"text": "simulate night"}).json()["cards"][0]
        step("Simulate night -> scenario preview", card["type"] == "scenario_preview", text=card.get("text"))
        act = dict(card["confirm"], runs=runs)
        s = c.post("/chat/confirm", json={"action": act}).json()["cards"][0]
        st = wait(s["id"])
        step("Night runs complete", st["state"] == "done", runs=st.get("runs_done"), id=s["id"])
        before = s["id"]
        rep = c.get(f"/simulate/{before}/replay").json()
        q3b = max(max(rep["queue_series"].get("3BP", [0])), max(rep["queue_series"].get("3BS", [0])))
        step("Replay shows the 3B queue", "3BP" in rep["queue_series"] and len(rep["frames"]) > 10,
             replay_queue_3B_max=q3b, frames=len(rep["frames"]))
        card = c.post("/chat", json={"text": "apply fix 2", "finding": "F-07"}).json()["cards"][0]
        step("Fix 2 -> edit preview", card["type"] == "edit_preview", text=card.get("text"))
        p = c.post("/chat/confirm", json={"action": card["confirm"]}).json()["cards"][0]
        step("Confirm fix 2 -> F-07 clears", any(x["id"] == "F-07" and x.get("status") in (None, "pass") for x in p["changed"]),
             changed=p["changed"])
        card = c.post("/chat", json={"text": "simulate night"}).json()["cards"][0]
        s = c.post("/chat/confirm", json={"action": dict(card["confirm"], runs=runs)}).json()["cards"][0]
        st = wait(s["id"])
        after = s["id"]
        cmp = c.get(f"/simulate/compare?a={before}&b={after}").json()
        l3b = {k: v for k, v in cmp["landings"].items() if k.startswith("3B")}
        step("Re-run after fix 2 -> compare", st["state"] == "done", tA_p95=cmp["delta"], landings_3B=l3b)
        card = c.post("/chat", json={"text": "fire near stair 3A at night"}).json()["cards"][0]
        ok = card["type"] == "scenario_preview" and card["scenario"].get("fire_origin")
        step("Fire what-if from words -> preview", ok, text=card.get("text"))
        s = c.post("/chat/confirm", json={"action": dict(card["confirm"], runs=runs)}).json()["cards"][0]
        st = wait(s["id"])
        step("Fire what-if runs", st["state"] == "done", error=st.get("error"), id=s["id"])
        pin = c.post(f"/simulate/{before}/pin", json={"t": 500, "x": 129.6, "y": 1.3, "note": "3B queue",
                                                      "finding": "F-08", "by": "eval"}).json()
        step("Pin to review", pin.get("ok"))
        acc = c.post("/findings/F-08/accept", json={"reason": "Agreed: recess kept as service access", "by": "eval"})
        b = c.post("/export/bcf").json()
        step("Portal review and approve -> BCF", acc.status_code == 200 and b["decisions"] >= 1, bcf=b)
    except Exception as e:  # noqa: BLE001
        step("exception", False, error=f"{type(e).__name__}: {e}", tb=traceback.format_exc()[-800:])
    return {"steps": steps, "passed": sum(s["ok"] for s in steps), "n": len(steps),
            "ok": all(s["ok"] for s in steps), "runs_per_sim": runs}


# =============================================================================== report
def md(res: dict, when: str) -> str:
    L = [f"\n## {when}\n"]
    if "rules" in res:
        r = res["rules"]
        L.append(f"- **Rules benchmark**: {r['plants']} planted violations · caught {r['caught']} · missed {r['missed']} · "
                 f"false alarms {r['false_alarms']} · contract revisions "
                 + ", ".join(f"{k} {'ok' if v['ok'] else 'DIFF'}" for k, v in r["contract"].items()))
        miss = [x for x in r["rows"] if not x["caught"] or x["false_alarms"]]
        for x in miss:
            L.append(f"  - {x['id']} {x['plant']}: caught={x['caught']} false alarms={x['false_alarms']}")
    if "sim" in res:
        s = res["sim"]
        fw = s["free_walk"]
        L.append(f"- **Simulation sanity**: free walk {'ok' if fw['ok'] else 'FAIL'} (errors "
                 + ", ".join(f"{x['err_pct']} %" for x in fw["rows"]) + ")"
                 f" · wider stair {'ok' if s['wider_stair']['ok'] else 'FAIL'} (3B queue+wait mean "
                 f"{s['wider_stair']['w1.35']['queue_3B_mean'] + s['wider_stair']['w1.35']['inflow_wait_3B_mean']:.2f} → "
                 f"{s['wider_stair']['w2.2']['queue_3B_mean'] + s['wider_stair']['w2.2']['inflow_wait_3B_mean']:.2f})"
                 f" · same seed {'ok' if s['same_seed']['ok'] else 'FAIL'}"
                 f" · smoke door {s['smoke_door'].get('ok')} · one run {s['run_s']} s")
    if "ai" in res:
        a = res["ai"]
        L.append(f"- **AI**: phrasings {a['phrasings']['correct']}/{a['phrasings']['n']} · number guard "
                 f"{a['number_guard']['pass']}/{a['number_guard']['cached_explanations']} cached AI outputs pass "
                 f"(the other {a['number_guard']['cached_explanations'] - a['number_guard']['pass']} were caught at answer time and replaced by engine text) · "
                 f"latency cold {a['latency']['cold_ms']} ms, cached {a['latency']['cached_ms']} ms ({a['latency']['model']})"
                 + (f" · RAG {a['rag']['correct']}/{a['rag']['n']} ({a['rag'].get('backend')})" if a["rag"].get("n") else " · RAG not built"))
        for x in a["phrasings"]["rows"]:
            if not x["ok"]:
                L.append(f"  - phrasing missed: “{x['text']}” → {json.dumps(x['got'])[:160]}")
        for x in (a.get("rag") or {}).get("rows", []):
            if not x["ok"]:
                L.append(f"  - RAG missed: “{x['q']}” want {x['want']}, top {x['top']}")
    if "golden" in res:
        g = res["golden"]
        L.append(f"- **Golden path v3**: {g['passed']}/{g['n']} steps ({g['runs_per_sim']} runs per simulation)")
        for x in g["steps"]:
            extra = {k: v for k, v in x.items() if k not in ("step", "ok", "tb")}
            L.append(f"  - {'✓' if x['ok'] else '✕'} {x['step']}" + (f" · `{json.dumps(extra)[:220]}`" if extra else ""))
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", default="rules,sim,ai,golden")
    ap.add_argument("--no-append", action="store_true")
    ap.add_argument("--runs", type=int, default=20)
    a = ap.parse_args()
    parts = a.only.split(",")
    res = {}
    t0 = time.time()
    for p in parts:
        t = time.time()
        print(f"== {p}", flush=True)
        try:
            res[p] = {"rules": eval_rules, "sim": lambda: eval_sim(a.quick), "ai": eval_ai,
                      "golden": lambda: eval_golden(a.runs)}[p]()
        except Exception as e:  # noqa: BLE001
            res[p] = {"error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[-1500:]}
            print(res[p]["tb"])
        res[p]["_s"] = round(time.time() - t, 1)
        print(json.dumps(res[p], default=str)[:1500], flush=True)
    res["_total_s"] = round(time.time() - t0, 1)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "eval.json").write_text(json.dumps(res, indent=1, default=str))
    when = dt.datetime.now().strftime("%a %d %b %H:%M") + f" · git {os.popen('git rev-parse --short HEAD').read().strip()}"
    text = md({k: v for k, v in res.items() if isinstance(v, dict) and "error" not in v}, when)
    for k, v in res.items():
        if isinstance(v, dict) and "error" in v:
            text += f"- **{k}**: error {v['error']}\n"
    print(text)
    if not a.no_append:
        p = ROOT / "docs" / "EVAL.md"
        if not p.exists():
            p.write_text("# SonarIQ eval log\n\nAppended by `make eval` (scripts/eval.py). Numbers come from the run; "
                         "nothing here is typed by hand.\n")
        with p.open("a") as f:
            f.write(text)


if __name__ == "__main__":
    main()
