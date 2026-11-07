"""Per rule: one violation, one compliant control, one exact-threshold case (Build plan gate 'Rule correctness')."""
from shapely.geometry import box

from sonariq.engine import analyse

ALL = ["fls", "acc", "dnv", "hvac"]


def res(model, rule_id, name, groups=ALL):
    run = analyse(model, groups, scope="whole")
    hits = [r for r in run.results if r.rule.id == rule_id and r.element is not None and r.element.name == name]
    assert len(hits) == 1, f"{rule_id} on {name}: {len(hits)} results"
    return hits[0]


def door(m, name):
    return m.by_name(name)


# ---------------------------------------------------------------- R-FLS-01 door fire class
def test_fls01_violation_A0_door_in_A60_bulkhead(A):
    r = res(A, "R-FLS-01", "FD-5-165P")
    assert r.status == "fail" and r.measured["value"] == "A-0" and r.required["value"] == "A-60"


def test_fls01_control_A60_door(A):
    assert res(A, "R-FLS-01", "FD-5-165S").status == "pass"


def test_fls01_exact_threshold_equal_class_passes(A):
    door(A, "FD-5-165P").psets["Pset_DoorCommon"]["FireRating"] = "A-60"
    assert res(A, "R-FLS-01", "FD-5-165P").status == "pass"
    door(A, "FD-5-165P").psets["Pset_DoorCommon"]["FireRating"] = "A-30"
    assert res(A, "R-FLS-01", "FD-5-165P").status == "fail"


def test_fls01_missing_rating_is_cannot_verify(A):
    r = res(A, "R-FLS-01", "D-5-171-S")
    assert r.status == "unk" and "Pset_DoorCommon.FireRating" in r.missing


def test_fls01_b_class_door_in_A0_fails(A):
    door(A, "D-5-161-P").psets["Pset_DoorCommon"]["FireRating"] = "B-15"
    assert res(A, "R-FLS-01", "D-5-161-P").status == "fail"


# ---------------------------------------------------------------- R-FLS-02 dead end
def test_fls02_violation_rev_b(B):
    r = res(B, "R-FLS-02", "COR-5-148-P")
    assert r.status == "fail"
    assert r.measured["value"] == 4.2 and r.required["value"] == 1.2


def test_fls02_control_rev_a_not_dead_end(A):
    r = res(A, "R-FLS-02", "COR-5-148-P")
    assert r.status == "pass" and r.extra["dead_end"] is False


def test_fls02_exact_threshold_depth_equals_width(B):
    c = B.by_name("COR-5-148-P")
    x0, y0, x1, y1 = c.poly.bounds
    c.poly = box(x0, y1 - 1.2, x1, y1)   # 1.2 x 1.2 recess
    assert res(B, "R-FLS-02", "COR-5-148-P").status == "pass"
    c.poly = box(x0, y1 - 1.21, x1, y1)
    assert res(B, "R-FLS-02", "COR-5-148-P").status == "fail"


# ---------------------------------------------------------------- R-FLS-03 stair formula
def test_fls03_rev_a_1300(A):
    r = res(A, "R-FLS-03", "Stair 3B")
    assert r.status == "pass" and r.required["value"] == 1300 and r.measured["value"] == 1350


def test_fls03_rev_b_1380_fails(B):
    r = res(B, "R-FLS-03", "Stair 3B")
    assert r.status == "fail" and r.required["value"] == 1380 and r.measured["value"] == 1350
    n = {i["name"]: (i["deck"], i["value"]) for i in r.formula["inputs"]}
    assert n == {"N1": ("5", 68), "N2": ("6", 44), "N3": ("4", 40), "N4": ("7", 24)}
    assert r.formula["worked"] == "(68 + 44 + 20 + 6) × 10 = 138 × 10 = 1,380 mm"


def test_fls03_fix2_1340_passes(models):
    r = res(models["Bfix2"], "R-FLS-03", "Stair 3B")
    assert r.status == "pass" and r.required["value"] == 1340


def test_fls03_exact_threshold(B):
    st = B.by_name("Stair 3B")
    fl = B.elements[st.parts[0]]
    x0, y0, x1, y1 = fl.poly.bounds
    fl.poly = box(x0, -0.69, x1, 0.69)   # 1,380 mm
    assert res(B, "R-FLS-03", "Stair 3B").status == "pass"
    fl.poly = box(x0, -0.6895, x1, 0.6895)  # 1,379 mm
    assert res(B, "R-FLS-03", "Stair 3B").status == "fail"


def test_fls03_missing_berths_is_cannot_verify(A):
    cab = A.by_name("CAB-5120-P")
    del cab.psets["SonarIQ_Ship"]["berths"]
    r = res(A, "R-FLS-03", "Stair 3B")
    assert r.status == "unk" and any("berths" in m for m in r.missing)


# ---------------------------------------------------------------- R-FLS-04 corridor 900
def test_fls04_violation_850(B):
    r = res(B, "R-FLS-04", "COR-5-152-S")
    assert r.status == "fail" and r.measured["value"] == 850


def test_fls04_control_1300(A):
    assert res(A, "R-FLS-04", "COR-5-130-P").measured["value"] == 1300


def test_fls04_exact_900_passes(A):
    r = res(A, "R-FLS-04", "COR-5-152-S")
    assert r.status == "pass" and r.measured["value"] == 900


# ---------------------------------------------------------------- R-FLS-05 duct damper (hvac)
def test_fls05_violation_and_control(A):
    assert res(A, "R-FLS-05", "VD-5-03").status == "fail"
    assert res(A, "R-FLS-05", "VD-5-01").status == "pass"


def test_fls05_exact_radius(A):
    d = A.by_name("FDMP-5-165-01")
    _, y0, _, y1 = d.poly.bounds
    # bulkhead face at x = 132.05; damper exactly 1.0 m away passes, 1.05 m fails
    d.poly = box(133.05, y0, 133.45, y1)
    assert res(A, "R-FLS-05", "VD-5-01").status == "pass"
    d.poly = box(133.1, y0, 133.5, y1)
    assert res(A, "R-FLS-05", "VD-5-01").status == "fail"


# ---------------------------------------------------------------- R-FLS-06 MVZ bulkhead A-60
def test_fls06(A):
    assert res(A, "R-FLS-06", "BHD-5-165").status == "pass"          # exact: A-60 required, A-60 fitted
    A.by_name("BHD-5-165").psets["Pset_WallCommon"]["FireRating"] = "A-30"
    assert res(A, "R-FLS-06", "BHD-5-165").status == "fail"
    A.by_name("BHD-5-165").psets["Pset_WallCommon"]["FireRating"] = None
    assert res(A, "R-FLS-06", "BHD-5-165").status == "unk"


# ---------------------------------------------------------------- R-FLS-07 MVZ length 40 m
def test_fls07_exact_40m_passes_and_control(A):
    assert res(A, "R-FLS-07", "MVZ 5").measured["value"] == 40.0
    assert res(A, "R-FLS-07", "MVZ 5").status == "pass"
    assert res(A, "R-FLS-07", "MVZ 4").measured["value"] == 36.0


def test_fls07_violation(A):
    c = A.by_name("COR-5-202-P")
    x0, y0, x1, y1 = c.poly.bounds
    c.poly = box(x0, y0, x1 + 0.01, y1)
    assert res(A, "R-FLS-07", "MVZ 5").status == "fail"


# ---------------------------------------------------------------- R-FLS-08 stair enclosure A-0
def test_fls08(A):
    assert res(A, "R-FLS-08", "Stair 3B").status == "pass"   # exact: A-0 vs A-0
    A.by_name("WA0-STAIR3B-P").psets["Pset_WallCommon"]["FireRating"] = "B-15"
    assert res(A, "R-FLS-08", "Stair 3B").status == "fail"


# ---------------------------------------------------------------- R-FLS-09 stair min 900
def test_fls09(A):
    assert res(A, "R-FLS-09", "Stair 3B").status == "pass"
    fl = A.elements[A.by_name("Stair 3B").parts[0]]
    x0, _, x1, _ = fl.poly.bounds
    fl.poly = box(x0, -0.45, x1, 0.45)
    assert res(A, "R-FLS-09", "Stair 3B").status == "pass"
    fl.poly = box(x0, -0.4495, x1, 0.4495)
    assert res(A, "R-FLS-09", "Stair 3B").status == "fail"


# ---------------------------------------------------------------- R-FLS-10 self-closing
def test_fls10(A):
    assert res(A, "R-FLS-10", "FD-5-165P").status == "pass"
    door(A, "FD-5-165P").psets["Pset_DoorCommon"]["SelfClosing"] = False
    assert res(A, "R-FLS-10", "FD-5-165P").status == "fail"
    del door(A, "FD-5-165P").psets["Pset_DoorCommon"]["SelfClosing"]
    assert res(A, "R-FLS-10", "FD-5-165P").status == "unk"


# ---------------------------------------------------------------- R-FLS-11 glazing
def test_fls11(A):
    assert res(A, "R-FLS-11", "GL-5-162-P").status == "pass"   # exact: A-0 in A-0
    A.by_name("GL-5-162-P").psets["Pset_WindowCommon"]["FireRating"] = "B-0"
    assert res(A, "R-FLS-11", "GL-5-162-P").status == "fail"


# ---------------------------------------------------------------- R-ACC-01 PVAG corridor 915 (warning)
def test_acc01_violation_is_warning_not_fail(A):
    r = res(A, "R-ACC-01", "COR-5-152-S")
    assert r.status == "warn" and r.required["value"] == 915 and r.required["alt"]["value"] == 36


def test_acc01_control_and_exact(A):
    assert res(A, "R-ACC-01", "COR-5-130-P").status == "pass"
    c = A.by_name("COR-5-152-S")
    x0, y0, x1, y1 = c.poly.bounds
    c.poly = box(x0, y1 - 0.915, x1, y1)
    assert res(A, "R-ACC-01", "COR-5-152-S").status == "pass"


# ---------------------------------------------------------------- R-ACC-02 ADA door 32 in
def test_acc02(A):
    d = door(A, "D-5-161-P")
    assert res(A, "R-ACC-02", "D-5-161-P").status == "pass"            # 900 mm
    d.overall_width = 0.762                                              # 30 in
    r = res(A, "R-ACC-02", "D-5-161-P")
    assert r.status == "fail" and r.measured["value"] == 30.0
    d.overall_width = 0.8128                                             # exactly 32 in
    assert res(A, "R-ACC-02", "D-5-161-P").status == "pass"


# ---------------------------------------------------------------- R-DNV-01 plate thickness
def test_dnv01(A):
    p = A.by_name("PL-5-01")
    assert res(A, "R-DNV-01", "PL-5-01").status == "pass"
    p.z1 = p.z0 + 0.0105                                                # exactly 10.5 mm
    assert res(A, "R-DNV-01", "PL-5-01").status == "pass"
    p.z1 = p.z0 + 0.0104
    assert res(A, "R-DNV-01", "PL-5-01").status == "fail"


# ---------------------------------------------------------------- applicability + maturity
def test_research_vessel_profile_makes_passenger_rules_not_applicable(A):
    A.ship["passengers"] = 28
    run = analyse(A, ALL)
    na = {n["rule"] for n in run.na}
    assert {"R-FLS-01", "R-FLS-02", "R-FLS-03", "R-FLS-06", "R-FLS-07"} <= na
    assert any(r.rule.id == "R-ACC-02" for r in run.results)   # accessibility still applies


def test_concept_zone_is_dormant(A):
    r = res(A, "R-FLS-01", "FD-5-208-P")
    assert r.status == "dor"
