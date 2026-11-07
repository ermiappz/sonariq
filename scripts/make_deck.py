"""Write the SonarIQ test deck: data/deck5_revA.ifc and data/deck5_revB.ifc (IFC4, IfcOpenShell).

Layout (see docs/SPEC.md §6). x = frame x 0.8 m (Fr 0 at x = 0), +y = port, Deck 5 at z = 14.5 m.
  Fr 120-215, MVZ 4 Fr 120-165, MVZ 5 Fr 165-215, A-60 MVZ bulkhead at Fr 165.
  Outboard cabins 2,000 x 6,000 mm, 2 berths. Corridors 1,300 mm; starboard Fr 150-155 900 mm.
  Stair 3B Fr 160-164, clear width 1,350 mm, serves D4-D7, persons_by_deck D4 40, D6 44, D7 24
  (D5 is counted from the cabins' berths; the pset carries D5 60 for cross-checking only).
Rev B = owner request OR-117: 4 cabins (8 berths) inboard at Fr 140-147.5; the cross corridor at
  Fr 146-150 P is cut to 4.2 m (dead end); the Fr 150-155 S corridor narrows to 850 mm.

Usage: python scripts/make_deck.py [--out data] [--fix2]
"""
from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import numpy as np

FR = 0.8          # frame spacing, m
Z5 = 14.5         # Deck 5 elevation, m
H = 2.8           # clear height
NS = uuid.UUID("5a4b1d2e-0000-4000-8000-534f4e415249")  # SonarIQ namespace for stable GlobalIds


def x(fr: float) -> float:
    return round(fr * FR, 4)


def gid(name: str) -> str:
    """Stable GlobalId from the element name, so Rev A and Rev B share IDs (diff by GlobalId)."""
    return ifcopenshell.guid.compress(uuid.uuid5(NS, name).hex)


# ----------------------------------------------------------------------------------------------
# Plain description of the deck (also used by tests to know what was planted)
# ----------------------------------------------------------------------------------------------
@dataclass
class Box:
    name: str
    x0: float
    y0: float
    x1: float
    y1: float
    z0: float = Z5
    h: float = H
    props: dict = field(default_factory=dict)


def side_of(y0: float, y1: float) -> str:
    c = (y0 + y1) / 2
    return "P" if c > 0.3 else "S" if c < -0.3 else "C"


def frames(x0: float, x1: float) -> str:
    a, b = x0 / FR, x1 / FR
    fa, fb = int(round(a)), int(round(b))
    return str(fa) if fa == fb else f"{fa}-{fb}"


Y_PC = (6.2, 7.5)      # port corridor
Y_SC = (-7.5, -6.2)    # starboard corridor
Y_PCAB = (7.5, 13.5)
Y_SCAB = (-13.5, -7.5)
Y_IN = (-6.2, 6.2)


def describe(rev: str, fix2: bool = False) -> dict:
    """Return plain dicts for every element of the deck for revision A or B."""
    D: dict = {"spaces": [], "walls": [], "doors": [], "windows": [], "stairs": [], "ducts": [],
               "dampers": [], "plates": [], "zones": {"MVZ 4": [], "MVZ 5": []}}

    def mvz_of(x0: float) -> str:
        return "MVZ 4" if x0 < x(165) - 1e-6 else "MVZ 5"

    def space(name, x0, y0, x1, y1, category, **kw):
        p = {"category": category, "deck": "5", "frame": kw.pop("frame", frames(x0, x1)),
             "side": kw.pop("side", side_of(y0, y1)), "mvz": mvz_of(x0)}
        p.update(kw)
        b = Box(name, x0, y0, x1, y1, props=p)
        D["spaces"].append(b)
        D["zones"][p["mvz"]].append(name)
        return b

    def wall(name, x0, y0, x1, y1, rating, **kw):
        p = {"deck": "5", "frame": kw.pop("frame", frames(x0, x1)), "side": kw.pop("side", side_of(y0, y1)),
             "FireRating": rating}
        p.update(kw)
        b = Box(name, x0, y0, x1, y1, props=p)
        D["walls"].append(b)
        return b

    def door(name, host, cx, cy, width, rating, along="x", self_closing=True, **kw):
        p = {"deck": "5", "frame": kw.pop("frame", frames(cx, cx)), "side": kw.pop("side", side_of(cy, cy)),
             "host": host, "width": width, "FireRating": rating, "SelfClosing": self_closing, "along": along}
        p.update(kw)
        D["doors"].append(Box(name, cx, cy, cx, cy, props=p))

    # ---- corridors (12) -------------------------------------------------------------------------
    s152_y0 = -7.05 if rev == "B" else -7.1
    space("COR-5-130-P", x(120), Y_PC[0], x(146), Y_PC[1], "corridor", escape_continues=True, accessible_route=True)
    space("COR-5-155-P", x(146), Y_PC[0], x(165), Y_PC[1], "corridor", accessible_route=True)
    space("COR-5-178-P", x(165), Y_PC[0], x(190), Y_PC[1], "corridor", accessible_route=True)
    space("COR-5-202-P", x(190), Y_PC[0], x(215), Y_PC[1], "corridor", escape_continues=True, accessible_route=True)
    space("COR-5-135-S", x(120), Y_SC[0], x(150), Y_SC[1], "corridor", escape_continues=True, accessible_route=True)
    space("COR-5-152-S", x(150), s152_y0, x(155), Y_SC[1], "corridor", frame="152", accessible_route=True)
    space("COR-5-160-S", x(155), Y_SC[0], x(165), Y_SC[1], "corridor", accessible_route=True)
    space("COR-5-178-S", x(165), Y_SC[0], x(190), Y_SC[1], "corridor", accessible_route=True)
    space("COR-5-202-S", x(190), Y_SC[0], x(215), Y_SC[1], "corridor", escape_continues=True, accessible_route=True)
    space("COR-5-134-X", x(134), Y_IN[0], x(135.5), Y_IN[1], "corridor", side="C", frame="134-135", accessible_route=True)
    if rev == "B":
        space("COR-5-148-P", x(146), 2.0, x(147.5), Y_IN[1], "corridor", side="P", frame="146-150", accessible_route=True)
    else:
        space("COR-5-148-P", x(146), Y_IN[0], x(147.5), Y_IN[1], "corridor", side="P", frame="146-150", accessible_route=True)
    space("COR-5-190-X", x(190), Y_IN[0], x(191.5), Y_IN[1], "corridor", side="C", frame="190-191", accessible_route=True)

    # ---- cabins: MVZ 4 15 per side Fr 120-157.5 (60 berths) -----------------------------------------
    for i in range(15):
        f0 = 120 + 2.5 * i
        for sd, ys in (("P", Y_PCAB), ("S", Y_SCAB)):
            n = f"CAB-5{int(f0):03d}-{sd}"
            space(n, x(f0), ys[0], x(f0 + 2.5), ys[1], "cabin", berths=2, solas_category="(6)")
            # cabin partitions B-0 (visual + hosting), corridor bulkhead B-15
            wall(f"WB0-{n}", x(f0) - 0.025, ys[0], x(f0) + 0.025, ys[1], "B-0")
            cy = Y_PC[1] if sd == "P" else Y_SC[0]
            door(f"D-{n}", f"WB15-5-{sd}", x(f0 + 1.25), cy, 0.70, "B-15", along="x", self_closing=False)
    # ---- service rooms, MVZ 4 Fr 157.5-165
    for sd, ys, nm in (("P", Y_PCAB, "PANTRY-5-160-P"), ("S", Y_SCAB, "STORE-5-160-S")):
        space(nm, x(157.5), ys[0], x(165), ys[1], "service", solas_category="(13)")
        cy = Y_PC[1] if sd == "P" else Y_SC[0]
        wall(f"WA0-{nm}", x(157.5), cy - 0.025, x(165), cy + 0.025, "A-0", side=sd)
        door(f"D-{nm}", f"WA0-{nm}", x(161), cy, 0.80, "A-0", frame="161", side=sd)

    # ---- MVZ 5: P side SWBD, 12 cabins, LINEN ; S side TRUNK, 12 cabins, LOCKER, 4 cabins --------
    def mvz5_side(sd, ys, first, last_name):
        cy = Y_PC[1] if sd == "P" else Y_SC[0]
        rating = "A-60" if first.startswith("SWBD") else "A-0"
        space(first, x(165), ys[0], x(170), ys[1], "service", solas_category="(10)" if rating == "A-60" else "(13)")
        wall(f"WA-{first}", x(165), cy - 0.025, x(170), cy + 0.025, rating, side=sd)
        door(f"D-{first}", f"WA-{first}", x(167.5), cy, 0.80, rating, frame="167", side=sd)
        for i in range(12):
            f0 = 170 + 2.5 * i
            n = f"CAB-5{int(f0):03d}-{sd}"
            acc = i == 4
            space(n, x(f0), ys[0], x(f0 + 2.5), ys[1], "cabin", berths=2, solas_category="(6)",
                  accessible_cabin=acc)
            wall(f"WB0-{n}", x(f0) - 0.025, ys[0], x(f0) + 0.025, ys[1], "B-0")
            if acc:
                door(f"D-{n}", f"WB15-5-{sd}", x(f0 + 1.25), cy, 0.915, "B-15", accessible_route=True, self_closing=False)
            else:
                door(f"D-{n}", f"WB15-5-{sd}", x(f0 + 1.25), cy, 0.70, "B-15", self_closing=False)
        space(last_name, x(200), ys[0], x(205), ys[1], "service", solas_category="(13)")
        wall(f"WA-{last_name}", x(200), cy - 0.025, x(205), cy + 0.025, "A-0", side=sd)
        door(f"D-{last_name}", f"WA-{last_name}", x(202.5), cy, 0.80, "A-0", frame="202", side=sd)

    mvz5_side("P", Y_PCAB, "SWBD-5-167-P", "LINEN-5-202-P")
    mvz5_side("S", Y_SCAB, "TRUNK-5-167-S", "LOCKER-5-202-S")
    for i in range(4):  # Fr 205-215 starboard cabins
        f0 = 205 + 2.5 * i
        n = f"CAB-5{int(f0):03d}-S"
        space(n, x(f0), Y_SCAB[0], x(f0 + 2.5), Y_SCAB[1], "cabin", berths=2, solas_category="(6)")
    space("LOUNGE-5-208-P", x(205), Y_PCAB[0], x(215), Y_PCAB[1], "public", solas_category="(8)")

    # ---- galley (concept zone): Fr 205-215 inboard, two A-0 doors -> Dormant ---------------------
    space("GALLEY-5-210", x(205), Y_IN[0], x(215), Y_IN[1], "galley", side="C", solas_category="(12)", maturity="concept")
    wall("WA0-GALLEY-P", x(205), Y_IN[1] - 0.05, x(215), Y_IN[1], "A-0", maturity="concept", side="P")
    wall("WA0-GALLEY-S", x(205), Y_IN[0], x(215), Y_IN[0] + 0.05, "A-0", maturity="concept", side="S")
    door("FD-5-208-P", "WA0-GALLEY-P", x(208), Y_IN[1], 0.80, "A-0", frame="208", side="P", maturity="concept")
    door("FD-5-208-S", "WA0-GALLEY-S", x(208), Y_IN[0], 0.80, "A-0", frame="208", side="S", maturity="concept")

    # ---- inboard public spaces (no checks)
    space("LOUNGE-5-125", x(120), Y_IN[0], x(134), Y_IN[1], "public", side="C", solas_category="(8)")
    if rev == "B":
        space("LOUNGE-5-140", x(135.5), Y_IN[0], x(140), Y_IN[1], "public", side="C", solas_category="(8)")
        space("LOUNGE-5-141-P", x(140), 2.0, x(146), Y_IN[1], "public", side="P", solas_category="(8)")
    else:
        space("LOUNGE-5-140", x(135.5), Y_IN[0], x(146), Y_IN[1], "public", side="C", solas_category="(8)")
    space("LOUNGE-5-153", x(147.5), Y_IN[0], x(160), Y_IN[1], "public", side="C", solas_category="(8)")
    space("LOUNGE-5-180", x(174), Y_IN[0], x(190), Y_IN[1], "public", side="C", solas_category="(8)")
    space("LOUNGE-5-198", x(191.5), Y_IN[0], x(205), Y_IN[1], "public", side="C", solas_category="(8)")

    # ---- OR-117 cabin block (Rev B): 4 cabins x 2 berths, inboard Fr 140-147.5, y -6..2 ---------
    if rev == "B":
        berths = 1 if fix2 else 2
        for i in range(4):
            y0 = -6.0 + 2.0 * i
            n = f"CAB-5-OR117-{i+1}"
            space(n, x(140), y0, x(147.5), y0 + 2.0, "cabin", berths=berths, side="C" if i < 3 else "P",
                  frame="140-147", solas_category="(6)", change_request="OR-117")
            wall(f"WB0-{n}", x(140), y0 - 0.025, x(147.5), y0 + 0.025, "B-0", change_request="OR-117")
        wall("WB15-5-OR117-END", x(146), 1.975, x(147.5), 2.025, "B-15", side="P", change_request="OR-117")

    # ---- corridor bulkheads B-15 (hosts for cabin doors)
    wall("WB15-5-P", x(120), Y_PC[1] - 0.025, x(157.5), Y_PC[1] + 0.025, "B-15", side="P")
    wall("WB15-5-S", x(120), Y_SC[0] - 0.025, x(157.5), Y_SC[0] + 0.025, "B-15", side="S")
    wall("WB15-5-P-5", x(170), Y_PC[1] - 0.025, x(200), Y_PC[1] + 0.025, "B-15", side="P")
    wall("WB15-5-S-5", x(170), Y_SC[0] - 0.025, x(200), Y_SC[0] + 0.025, "B-15", side="S")
    for d in D["doors"]:
        if d.props["host"] == "WB15-5-P" and d.x0 > x(170):
            d.props["host"] = "WB15-5-P-5"
        if d.props["host"] == "WB15-5-S" and d.x0 > x(170):
            d.props["host"] = "WB15-5-S-5"

    # ---- MVZ bulkhead Fr 165, A-60, with two fire doors in the corridors -----------------------
    wall("BHD-5-165", x(165) - 0.05, -13.5, x(165) + 0.05, 13.5, "A-60", mvz_boundary=True, side="C", frame="165", mvz="MVZ 4/5")
    door("FD-5-165P", "BHD-5-165", x(165), 6.85, 1.20, "A-0", along="y", frame="165", side="P", accessible_route=True)
    door("FD-5-165S", "BHD-5-165", x(165), -6.85, 1.20, "A-60", along="y", frame="165", side="S", accessible_route=True)

    # ---- stairs: 3B (Fr 160-164, MVZ 4) and 3C (Fr 170-174, MVZ 5), enclosures A-0 --------------
    def stair(name, f0, f1, width, persons, d5_check, doors_fr, window_names):
        x0, x1 = x(f0), x(f1)
        space(f"STAIR-{name}", x0, Y_IN[0], x1, Y_IN[1], "stair", side="C", frame=f"{f0}-{f1}", solas_category="(2)",
              stair=name)
        encl = []
        for sd, yy in (("P", Y_IN[1] - 0.05), ("S", Y_IN[0])):
            wn = f"WA0-STAIR{name}-{sd}"
            wall(wn, x0, yy, x1, yy + 0.05, "A-0", side=sd, frame=f"{f0}-{f1}")
            encl.append(wn)
        for end, xx in (("A", x0), ("F", x1 - 0.05)):
            wn = f"WA0-STAIR{name}-{end}"
            wall(wn, xx, Y_IN[0], xx + 0.05, Y_IN[1], "A-0", side="C", frame=str(f0 if end == "A" else f1))
            encl.append(wn)
        for sd, yy in (("P", Y_IN[1]), ("S", Y_IN[0])):
            rating = "A-0"
            if name == "3C" and sd == "S":
                rating = None   # U-01: D-5-171-S has no FireRating
            door(f"D-5-{doors_fr}-{sd}", f"WA0-STAIR{name}-{sd}", x(doors_fr), yy, 0.90, rating, frame=str(doors_fr),
                 side=sd, accessible_route=True)
        for wn, host, cx, cy in window_names:
            D["windows"].append(Box(wn, cx, cy, cx, cy, props={"host": host, "FireRating": "A-0", "deck": "5",
                                                               "frame": frames(cx, cx), "side": side_of(cy, cy)}))
        # flight: clear width along y, centred
        fl = Box(f"FLIGHT-{name}", x0 + 0.2, -width / 2, x1 - 0.2, width / 2, props={})
        D["stairs"].append({"name": f"Stair {name}", "flight": fl, "enclosure": encl,
                            "props": {"deck": "5", "frame": f"{f0}-{f1}", "side": "C", "mvz": mvz_of(x0),
                                      "decks_served": "4,5,6,7",
                                      "persons_by_deck": json.dumps(persons),
                                      "persons_deck5_declared": d5_check}})

    stair("3B", 160, 164, 1.35, {"4": 40, "6": 44, "7": 24}, 60, 161,
          [("GL-5-162-P", "WA0-STAIR3B-P", x(162.5), Y_IN[1]), ("GL-5-162-S", "WA0-STAIR3B-S", x(162.5), Y_IN[0])])
    stair("3C", 170, 174, 1.40, {"4": 40, "6": 40, "7": 20}, 56, 171,
          [("GL-5-172-P", "WA0-STAIR3C-P", x(172.5), Y_IN[1])])

    # ---- HVAC: VD-5-03 crosses the A-60 bulkhead with no damper (H-01); VD-5-01 has one ---------
    D["ducts"].append(Box("VD-5-03", 131.5, 2.9, 135.5, 3.3, z0=Z5 + 2.4, h=0.3,
                          props={"deck": "5", "frame": "165", "side": "P", "system": "supply"}))
    D["ducts"].append(Box("VD-5-01", 131.5, -3.3, 135.5, -2.9, z0=Z5 + 2.4, h=0.3,
                          props={"deck": "5", "frame": "165", "side": "S", "system": "supply"}))
    D["dampers"].append(Box("FDMP-5-165-01", x(165) + 0.1, -3.35, x(165) + 0.5, -2.85, z0=Z5 + 2.35, h=0.4,
                            props={"deck": "5", "frame": "165", "side": "S"}))

    # ---- deck plating: 12 panels, 12 mm
    w = (x(215) - x(120)) / 12
    for i in range(12):
        x0 = x(120) + i * w
        D["plates"].append(Box(f"PL-5-{i+1:02d}", round(x0, 4), -13.5, round(x0 + w, 4), 13.5, z0=Z5 - 0.012, h=0.012,
                               props={"category": "deck_plate", "deck": "5", "frame": frames(x0, x0 + w), "side": "C"}))
    return D


# ----------------------------------------------------------------------------------------------
# IFC writer
# ----------------------------------------------------------------------------------------------
class Writer:
    def __init__(self, rev: str):
        f = ifcopenshell.file(schema="IFC4")
        self.f = f
        run = ifcopenshell.api.run
        self.run = run
        proj = run("root.create_entity", f, ifc_class="IfcProject", name="Demo ship")
        proj.GlobalId = gid("project")
        lu = f.createIfcSIUnit(None, "LENGTHUNIT", None, "METRE")
        au = f.createIfcSIUnit(None, "AREAUNIT", None, "SQUARE_METRE")
        vu = f.createIfcSIUnit(None, "VOLUMEUNIT", None, "CUBIC_METRE")
        proj.UnitsInContext = f.createIfcUnitAssignment([lu, au, vu])
        model = run("context.add_context", f, context_type="Model")
        self.body = run("context.add_context", f, context_type="Model", context_identifier="Body",
                        target_view="MODEL_VIEW", parent=model)
        site = run("root.create_entity", f, ifc_class="IfcSite", name="Yard")
        site.GlobalId = gid("site")
        ship = run("root.create_entity", f, ifc_class="IfcBuilding", name="Demo ship")
        ship.GlobalId = gid("ship")
        self.storey = run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Deck 5")
        self.storey.GlobalId = gid("deck5")
        self.storey.Elevation = Z5
        run("aggregate.assign_object", f, products=[site], relating_object=proj)
        run("aggregate.assign_object", f, products=[ship], relating_object=site)
        run("aggregate.assign_object", f, products=[self.storey], relating_object=ship)
        for e in (site, ship, self.storey):
            run("geometry.edit_object_placement", f, product=e)
        self.pset(ship, "SonarIQ_Ship", {"vessel_type": "passenger", "passengers": 2800, "persons_on_board": 3900,
                                          "length_m": 300.0, "accessibility": True, "revision": rev,
                                          "frame_spacing_m": FR})
        self.pset(self.storey, "SonarIQ_Ship", {"deck": "5"})
        self.by_name: dict[str, ifcopenshell.entity_instance] = {}

    def pset(self, e, name, props):
        props = {k: v for k, v in props.items() if v is not None}
        ps = self.run("pset.add_pset", self.f, product=e, name=name)
        self.run("pset.edit_pset", self.f, pset=ps, properties=props)

    def box_rep(self, dx, dy, dz):
        f = self.f
        prof = f.createIfcRectangleProfileDef("AREA", None,
                                              f.createIfcAxis2Placement2D(f.createIfcCartesianPoint((dx / 2, dy / 2))), dx, dy)
        solid = f.createIfcExtrudedAreaSolid(prof, f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0))),
                                             f.createIfcDirection((0.0, 0.0, 1.0)), dz)
        return f.createIfcShapeRepresentation(self.body, "Body", "SweptSolid", [solid])

    def place(self, e, x0, y0, z0, rel=None):
        m = np.eye(4)
        m[0:3, 3] = (x0, y0, z0)
        self.run("geometry.edit_object_placement", self.f, product=e, matrix=m, is_si=True)

    def product(self, ifc_class, b: Box, predefined=None, contain=True, h=None):
        e = self.run("root.create_entity", self.f, ifc_class=ifc_class, name=b.name, predefined_type=predefined)
        e.GlobalId = gid(b.name)
        dx, dy = max(b.x1 - b.x0, 0.01), max(b.y1 - b.y0, 0.01)
        self.place(e, b.x0, b.y0, b.z0)
        self.run("geometry.assign_representation", self.f, product=e, representation=self.box_rep(dx, dy, h or b.h))
        if contain:
            self.run("spatial.assign_container", self.f, products=[e], relating_structure=self.storey)
        self.by_name[b.name] = e
        return e


def write(rev: str, out: Path, fix2: bool = False) -> Path:
    D = describe(rev, fix2=fix2)
    W = Writer(rev)
    f, run = W.f, W.run
    spaces = {}
    for b in D["spaces"]:
        sp = run("root.create_entity", f, ifc_class="IfcSpace", name=b.name, predefined_type="INTERNAL")
        sp.GlobalId = gid(b.name)
        sp.LongName = b.props["category"]
        W.place(sp, b.x0, b.y0, b.z0)
        run("geometry.assign_representation", f, product=sp, representation=W.box_rep(b.x1 - b.x0, b.y1 - b.y0, b.h))
        run("aggregate.assign_object", f, products=[sp], relating_object=W.storey)
        W.pset(sp, "SonarIQ_Ship", b.props)
        spaces[b.name] = sp
        W.by_name[b.name] = sp
    for zname, members in D["zones"].items():
        z = run("root.create_entity", f, ifc_class="IfcZone", name=zname)
        z.GlobalId = gid(zname)
        W.pset(z, "SonarIQ_Ship", {"category": "mvz", "mvz": zname, "deck": "5"})
        run("group.assign_group", f, products=[spaces[m] for m in members], group=z)
    for b in D["walls"]:
        props = dict(b.props)
        rating = props.pop("FireRating")
        e = W.product("IfcWall", b)
        W.pset(e, "Pset_WallCommon", {"FireRating": rating, "IsExternal": False})
        W.pset(e, "SonarIQ_Ship", props)

    def fill(kind, b: Box):
        p = dict(b.props)
        host = W.by_name[p.pop("host")]
        width = p.pop("width", 0.9)
        along = p.pop("along", "x")
        rating = p.pop("FireRating")
        sc = p.pop("SelfClosing", None)
        hh = 2.1 if kind == "IfcDoor" else 1.2
        z0 = Z5 if kind == "IfcDoor" else Z5 + 1.0
        if along == "x":
            bb = Box(b.name, b.x0 - width / 2, b.y0 - 0.06, b.x0 + width / 2, b.y0 + 0.06, z0=z0, h=hh)
        else:
            bb = Box(b.name, b.x0 - 0.06, b.y0 - width / 2, b.x0 + 0.06, b.y0 + width / 2, z0=z0, h=hh)
        e = W.product(kind, bb, predefined="DOOR" if kind == "IfcDoor" else "WINDOW")
        e.OverallWidth, e.OverallHeight = width, hh
        op = run("root.create_entity", f, ifc_class="IfcOpeningElement", name=f"OP-{b.name}")
        op.GlobalId = gid("OP-" + b.name)
        W.place(op, bb.x0, bb.y0, bb.z0)
        run("geometry.assign_representation", f, product=op,
            representation=W.box_rep(bb.x1 - bb.x0, bb.y1 - bb.y0, hh))
        f.createIfcRelVoidsElement(ifcopenshell.guid.new(), None, None, None, host, op)
        f.createIfcRelFillsElement(ifcopenshell.guid.new(), None, None, None, op, e)
        common = {"FireRating": rating}
        if kind == "IfcDoor":
            common["SelfClosing"] = sc
            W.pset(e, "Pset_DoorCommon", common)
        else:
            W.pset(e, "Pset_WindowCommon", common)
        W.pset(e, "SonarIQ_Ship", p)

    # Windows are written first so door/window opening relations exist
    for b in D["windows"]:
        b.props.setdefault("width", 1.0)
        fill("IfcWindow", b)
    for b in D["doors"]:
        fill("IfcDoor", b)
    for s in D["stairs"]:
        fl: Box = s["flight"]
        st = run("root.create_entity", f, ifc_class="IfcStair", name=s["name"], predefined_type="STRAIGHT_RUN_STAIR")
        st.GlobalId = gid(s["name"])
        W.place(st, fl.x0, fl.y0, Z5)
        run("spatial.assign_container", f, products=[st], relating_structure=W.storey)
        flight = W.product("IfcStairFlight", fl, contain=False)
        run("aggregate.assign_object", f, products=[flight], relating_object=st)
        props = dict(s["props"])
        props["encloses"] = ",".join(s["enclosure"])
        W.pset(st, "SonarIQ_Ship", props)
        W.by_name[s["name"]] = st
    for b in D["ducts"]:
        e = W.product("IfcDuctSegment", b, predefined="RIGIDSEGMENT")
        W.pset(e, "SonarIQ_Ship", b.props)
    for b in D["dampers"]:
        e = W.product("IfcDamper", b, predefined="FIREDAMPER")
        W.pset(e, "SonarIQ_Ship", b.props)
    for b in D["plates"]:
        e = W.product("IfcPlate", b, predefined="SHEET")
        W.pset(e, "SonarIQ_Ship", b.props)

    out.mkdir(parents=True, exist_ok=True)
    name = f"deck5_rev{rev}{'_fix2' if fix2 else ''}.ifc"
    p = out / name
    f.write(str(p))
    return p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data"))
    ap.add_argument("--fix2", action="store_true", help="also write Rev B with fix 2 (4 cabins x 1 berth)")
    a = ap.parse_args()
    out = Path(a.out)
    for rev in ("A", "B"):
        print("wrote", write(rev, out))
    print("wrote", write("B", out, fix2=True))


if __name__ == "__main__":
    main()
