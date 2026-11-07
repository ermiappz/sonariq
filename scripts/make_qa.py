"""Write docs/meyer_qa1.md (print for Meyer Q&A 1) from the rulebook and live engine runs. No number is typed."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from sonariq.engine import analyse, impact, run_dict  # noqa: E402
from sonariq.model import load_ifc  # noqa: E402
from sonariq.rules import load_rules  # noqa: E402

THRESH = {
    "R-FLS-01": "door class ≥ division class",
    "R-FLS-02": "dead end: depth ≤ width",
    "R-FLS-03": "W = (N1 + N2 + 0.5 N3 + 0.25 N4) × 10 mm",
    "R-FLS-04": "≥ 900 mm",
    "R-FLS-05": "damper within 1.0 m of crossing",
    "R-FLS-06": "A-60",
    "R-FLS-07": "≤ 40 m",
    "R-FLS-08": "≥ A-0",
    "R-FLS-09": "≥ 900 mm",
    "R-FLS-10": "SelfClosing = true",
    "R-FLS-11": "glazing class ≥ division class",
    "R-ACC-01": "≥ 915 mm (36 in) · Warning",
    "R-ACC-02": "≥ 32 in (813 mm)",
    "R-DNV-01": "t ≥ 4.5 + 0.02·min(L,300) mm",
    "R-DNV-02": "—",
}


def cell(s) -> str:
    return str(s).replace("|", "/").replace("\n", " ")


def val(d):
    if not d or d.get("value") is None:
        return "—"
    v = d["value"]
    if isinstance(v, (int,)) and d.get("unit") == "mm":
        return f"{v:,} mm"
    return f"{v} {d.get('unit', '') if d.get('unit') not in ('class', 'bool') else ''}".strip()


def findings_table(d: dict) -> list[str]:
    out = ["| ID | Status | Finding | Location | Rule | Required | Measured |", "|---|---|---|---|---|---|---|"]
    for f in sorted(d["findings"], key=lambda f: ("fwu".index(f["status"][0]), f["id"])):
        out.append(f"| {f['id']} | {f['glyph']} {f['status_word']} | {cell(f['title'])} "
                   f"({cell(f['element']['name'])}) | {cell(f['location']['label'])} | {cell(f['ref'])} | "
                   f"{cell(val(f['required']))} | {cell(val(f['measured']))} |")
    return out


def counts_line(d: dict) -> str:
    c = d["counts"]
    g = d["by_group"]
    return (f"**{d['total_checks']} checks** · ✕ {c['fail']} Fail · ! {c['warn']} Warning · ? {c['unk']} Cannot verify · "
            f"✓ {c['pass']} Pass · ○ {c['dor']} Dormant  (Fire & life safety {g['fls']['checks']}, Accessibility "
            f"{g['acc']['checks']}, Class · DNV {g['dnv']['checks']})")


def main():
    A = load_ifc(ROOT / "data" / "deck5_revA.ifc", "A")
    B = load_ifc(ROOT / "data" / "deck5_revB.ifc", "B")
    F = load_ifc(ROOT / "data" / "deck5_revB_fix2.ifc", "B")
    ra, rb, rf = analyse(A), analyse(B), analyse(F)
    da, db, dfx = run_dict(ra, A), run_dict(rb, B), run_dict(rf, F)
    im = impact(A, ra, B, rb)
    stair_a = next(r for r in ra.results if r.rule.id == "R-FLS-03" and r.element.name == "Stair 3B")
    stair_b = next(r for r in rb.results if r.rule.id == "R-FLS-03" and r.element.name == "Stair 3B")
    stair_f = next(r for r in rf.results if r.rule.id == "R-FLS-03" and r.element.name == "Stair 3B")
    hv = run_dict(analyse(A, ["hvac"]), A)
    changed_txt = ", ".join("{} ({} → {})".format(c["id"], c["from"], c["to"]) for c in im["changed"])
    value_txt = ", ".join("{} ({} → {})".format(v["id"] or v["title"], v["from"], v["to"]) for v in im["value_changed"])

    L = ["# SonarIQ · Meyer Q&A 1 · rule readings and test-deck results", "",
         f"Sat 7 Nov 2026, 09:00 · printed from the engine run of {dt.datetime.now():%d %b %H:%M} · "
         "every number below comes from `scripts/make_qa.py` running the rule engine on the generated test deck.", "",
         "**What we ask:** tick or correct each reading. Paragraph numbers marked *verify* are the ones we are least "
         "sure of. Also: which DNV rule would you most like to see?", "",
         "## 1 · Rule readings", "",
         "| ✓/✗ | Rule | Source and paragraph | Our reading | Threshold | Status |",
         "|---|---|---|---|---|---|"]
    for r in load_rules():
        L.append(f"| ☐ | {r.id} · {cell(r.title)} | {cell(r.source)} {cell(r.clause)} | {cell(r.reading)} | "
                 f"{cell(THRESH.get(r.id, ''))} | {r.status} |")
    L += ["", "Applicability: rules for ships carrying more than 36 passengers are **Not applicable** on a vessel "
              "profile below that (the RCRV: 28 on board, 16 scientists and 12 crew). Missing model data gives "
              "**Cannot verify**, never Pass. Elements in a *concept* maturity zone are checked but stay "
              "**Dormant** (not reported).", "",
          "## 2 · Test deck", "",
          "Demo ship, Deck 5, Fr 120–215 (800 mm frames), MVZ 4 Fr 120–165 and MVZ 5 Fr 165–215, A-60 MVZ bulkhead at "
          "Fr 165. Cabins 2,000 × 6,000 mm with 2 berths, corridors 1,300 mm, starboard corridor at Fr 152 900 mm, "
          "Stair 3B Fr 160–164 serving Decks 4–7, 1,350 mm clear. IFC4 written with IfcOpenShell; fire classes in "
          "Pset_WallCommon / Pset_DoorCommon.FireRating; ship words in a `SonarIQ_Ship` property set (deck, frame, "
          "side, mvz, berths …).", "",
          "### Rev A", "", counts_line(da), ""]
    L += findings_table(da)
    L += ["", f"Stair 3B on Rev A: required {stair_a.required['value']:,} mm, measured {stair_a.measured['value']:,} mm "
              f"→ {stair_a.status.capitalize()} ({stair_a.formula['worked']}).", "",
          "### Rev B · owner request OR-117 (+4 cabins, 8 berths, aft of Fr 150)", "", counts_line(db), "",
          f"Ping: **{im['rerun']} checks re-ran**, verdicts changed: " +
          changed_txt + ". Values changed with the same status: " + value_txt + ".",
          ""]
    L += findings_table(db)
    inp = ", ".join(f"{i['name']} = {i['value']} (Deck {i['deck']}{', counted from cabins' if i.get('source') == 'model' else ''})"
                    for i in stair_b.formula["inputs"])
    L += ["", "**Stair 3B, the indirect failure.** Nobody touched the stair. " + inp + ". "
          f"{stair_b.formula['text']} = {stair_b.formula['worked']} vs {stair_b.measured['value']:,} mm measured → "
          f"Fail by {abs(stair_b.margin['value'])} mm.", "",
          f"With fix 2 (the four cabins with one berth each): required {stair_f.required['value']:,} mm ≤ "
          f"{stair_f.measured['value']:,} mm → {stair_f.status.capitalize()}. Counts: " + counts_line(dfx), "",
          "### HVAC model (separate pack)", ""]
    L += findings_table(hv)
    L += ["", "## 3 · Questions", "",
          "1. If you exported a deck from Cadmatic tomorrow, would it be IFC? Which version? Do element IDs stay the "
          "same between exports?",
          "2. How do you name a location: deck + frame + side? Anything else?",
          "3. Who should receive a fire-door finding, and who a duct-through-bulkhead finding?",
          "4. How many findings per Analyse is useful before it becomes noise?",
          "5. The RCRV is a research vessel with 28 aboard: are we right that the SOLAS rules for more than 36 "
          "passengers don't apply?",
          "6. On demand, live, or both? When in the design spiral would you switch live on?",
          "7. FSS Ch.13 stair width: do you order N1…N4 by size (as here) or by the deck nearest the stair first?",
          "8. Dead ends: is \"depth ≤ width\" the reading you use, and which paragraph do you cite?",
          "", "Notes:", "", "&nbsp;", "", "&nbsp;", ""]
    (ROOT / "docs" / "meyer_qa1.md").write_text("\n".join(L))
    print("wrote docs/meyer_qa1.md")


if __name__ == "__main__":
    main()
