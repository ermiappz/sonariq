"""Speed gate (Build plan): Analyse on the test deck < 3 s; ping after a change < 2 s."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from sonariq.session import Session  # noqa: E402

t0 = time.perf_counter()
s = Session("A")
t_load = time.perf_counter() - t0
t0 = time.perf_counter()
d = s.analyse()
t_an = time.perf_counter() - t0
t0 = time.perf_counter()
p = s.apply_edit({"kind": "add_cabin_block", "frame_from": 140, "count": 4}, confirm=True)["ping"]
t_ping = time.perf_counter() - t0
t0 = time.perf_counter()
im = s.switch_revision("B")
t_rev = time.perf_counter() - t0
c = d["counts"]
print(f"load IFC (Rev A)        {t_load:6.2f} s")
print(f"Analyse Rev A           {t_an:6.2f} s  ({d['total_checks']} checks: {c['fail']}·{c['warn']}·{c['unk']}·{c['pass']}·{c['dor']})"
      f"  gate < 3 s: {'PASS' if t_load + t_an < 3 else 'FAIL'} (incl. load)")
print(f"Ping after add_cabin_block {t_ping:6.2f} s  ({p['rerun']} re-run, changed {[x['id'] for x in p['changed']]})"
      f"  gate < 2 s: {'PASS' if t_ping < 2 else 'FAIL'}")
print(f"Switch to Rev B + ping  {t_rev:6.2f} s  ({im['rerun']} re-run, changed {[x['id'] for x in im['changed']]})")
