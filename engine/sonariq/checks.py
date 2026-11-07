"""Measure functions. Each takes (rule, model, ctx) and returns one CheckResult per element it applies to.

Rules decide nothing here beyond comparing a measured value to a YAML threshold. Missing input -> "unk"
(Cannot verify), never a pass and never a guess.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import networkx as nx
import pint
from shapely.geometry import Polygon

from .model import Element, Model, rect
from .rules import Rule

U = pint.UnitRegistry()
MM_PER_IN = 25.4


@dataclass
class CheckResult:
    rule: Rule
    element: Element | None
    status: str                       # fail | warn | unk | pass | dor | na
    required: dict | None = None      # {"value", "unit", "op", "alt"}
    measured: dict | None = None
    margin: dict | None = None
    method: str = ""
    summary: str = ""                 # one line of numbers (P3 row)
    formula: dict | None = None
    missing: list[str] = field(default_factory=list)
    depends_on: set[str] = field(default_factory=set)
    location: dict | None = None
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.rule.id}|{self.element.guid if self.element else '-'}"


# ---------------------------------------------------------------- helpers
_FIRE = re.compile(r"^\s*([ABC])\s*[- ]?\s*(\d+)?\s*$", re.I)


def fire_rank(rating: str | None) -> tuple[int, int] | None:
    """A-60 > A-30 > A-15 > A-0 > B-15 > B-0 > C. None if unknown/unparseable."""
    if not rating:
        return None
    m = _FIRE.match(str(rating))
    if not m:
        return None
    cls = {"A": 3, "B": 2, "C": 1}[m.group(1).upper()]
    return (cls, int(m.group(2) or 0))


def is_a_class(rating: str | None) -> bool:
    r = fire_rank(rating)
    return bool(r and r[0] == 3)


def fmt_int(v: float) -> str:
    return f"{int(round(v)):,}"


def mm(v_m: float) -> int:
    return int(round(v_m * 1000))


def location(model: Model, e: Element | None, label: str | None = None) -> dict:
    if e is None:
        return {"deck": None, "frame": None, "side": None, "label": label or "Whole model"}
    sq = e.sq
    deck = sq.get("deck")
    frame = sq.get("frame")
    side = sq.get("side")
    if (frame is None or side is None) and e.poly is not None:  # geometry fallback
        x0, y0, x1, y1 = e.poly.bounds
        fs = model.frame_spacing_m
        a, b = round(x0 / fs), round(x1 / fs)
        frame = frame or (str(a) if a == b else f"{a}-{b}")
        cy = (y0 + y1) / 2
        side = side or ("P" if cy > 0.3 else "S" if cy < -0.3 else "C")
    if deck is None and e.storey:
        m = re.search(r"(\d+)", e.storey)
        deck = m.group(1) if m else e.storey
    fr = str(frame).replace("-", "–") if frame is not None else "?"
    lab = label or f"Deck {deck if deck is not None else '?'} · Fr {fr} · {side or '?'}"
    return {"deck": None if deck is None else str(deck), "frame": None if frame is None else str(frame),
            "side": side, "label": lab}


def evidence_bbox(*els: Element | None) -> list[float] | None:
    polys = [e.poly for e in els if e is not None and e.poly is not None]
    if not polys:
        return None
    xs0, ys0, xs1, ys1 = zip(*(p.bounds for p in polys))
    return [round(min(xs0), 3), round(min(ys0), 3), round(max(xs1), 3), round(max(ys1), 3)]


def _res(rule: Rule, model: Model, e: Element | None, ok: bool | None, **kw) -> CheckResult:
    if ok is None:
        status = "unk"
    elif ok:
        status = "pass"
    else:
        status = "warn" if rule.severity == "warning" else "fail"
    r = CheckResult(rule=rule, element=e, status=status, **kw)
    if r.location is None:
        r.location = location(model, e)
    if e is not None:
        r.depends_on.add(e.guid)
    return r


def _host(model: Model, e: Element) -> Element | None:
    return model.elements.get(e.host) if e.host else None


# ---------------------------------------------------------------- fire divisions
def door_fire_class(rule: Rule, model: Model, ctx: dict) -> list[CheckResult]:
    return _opening_fire_class(rule, model, "IfcDoor", "Pset_DoorCommon")


def window_fire_class(rule: Rule, model: Model, ctx: dict) -> list[CheckResult]:
    return _opening_fire_class(rule, model, "IfcWindow", "Pset_WindowCommon")


def _opening_fire_class(rule: Rule, model: Model, cls: str, pset: str) -> list[CheckResult]:
    out = []
    for d in model.by_class(cls):
        host = _host(model, d)
        if host is None:
            continue
        h_rating = host.prop("Pset_WallCommon", "FireRating")
        if not is_a_class(h_rating):
            continue  # rule applies to openings in A-class divisions only
        d_rating = d.prop(pset, "FireRating")
        where = f"{host.sq.get('mvz', 'MVZ')} bulkhead" if host.sq.get("mvz_boundary") else ("stair enclosure" if "STAIR" in host.name.upper()
                                                                   else "A-class division")
        kw = dict(required={"value": h_rating, "unit": "class", "op": ">="},
                  method=f"Door FireRating ({pset}) compared with the FireRating of its host wall {host.name} "
                         "(Pset_WallCommon), found through IfcRelFillsElement / IfcRelVoidsElement. "
                         "Order A-60 > A-30 > A-15 > A-0 > B-15 > B-0.",
                  depends_on={host.guid}, extra={"host": host.name, "where": where})
        if d_rating is None or fire_rank(d_rating) is None:
            out.append(_res(rule, model, d, None, measured={"value": None, "unit": "class"},
                            missing=[f"{pset}.FireRating"],
                            summary=f"{where} {h_rating} · door fire class missing", **kw))
            continue
        ok = fire_rank(d_rating) >= fire_rank(h_rating)
        out.append(_res(rule, model, d, ok, measured={"value": d_rating, "unit": "class"},
                        summary=f"{where} · fitted {d_rating}, required {h_rating}", **kw))
    return out


def door_self_closing(rule: Rule, model: Model, ctx: dict) -> list[CheckResult]:
    out = []
    for d in model.by_class("IfcDoor"):
        host = _host(model, d)
        if host is None or not is_a_class(host.prop("Pset_WallCommon", "FireRating")):
            continue
        v = d.psets.get("Pset_DoorCommon", {}).get("SelfClosing")
        kw = dict(required={"value": True, "unit": "bool", "op": "=="},
                  method="Pset_DoorCommon.SelfClosing on a door hosted in an A-class division.",
                  depends_on={host.guid})
        if v is None:
            out.append(_res(rule, model, d, None, measured={"value": None, "unit": "bool"},
                            missing=["Pset_DoorCommon.SelfClosing"], summary="self-closing not stated", **kw))
        else:
            out.append(_res(rule, model, d, bool(v), measured={"value": bool(v), "unit": "bool"},
                            summary="self-closing" if v else "not self-closing", **kw))
    return out


def mvz_bulkhead_class(rule: Rule, model: Model, ctx: dict) -> list[CheckResult]:
    req = rule.params.get("required", "A-60")
    out = []
    for w in model.by_class("IfcWall"):
        if not w.sq.get("mvz_boundary"):
            continue
        r = w.prop("Pset_WallCommon", "FireRating")
        kw = dict(required={"value": req, "unit": "class", "op": ">="},
                  method="Pset_WallCommon.FireRating of each wall flagged SonarIQ_Ship.mvz_boundary.")
        if fire_rank(r) is None:
            out.append(_res(rule, model, w, None, measured={"value": None, "unit": "class"},
                            missing=["Pset_WallCommon.FireRating"], summary="bulkhead fire class missing", **kw))
        else:
            out.append(_res(rule, model, w, fire_rank(r) >= fire_rank(req), measured={"value": r, "unit": "class"},
                            summary=f"MVZ bulkhead {r}, required {req}", **kw))
    return out


def stair_enclosure_class(rule: Rule, model: Model, ctx: dict) -> list[CheckResult]:
    req = rule.params.get("required", "A-0")
    out = []
    for s in model.by_class("IfcStair"):
        names = [n for n in str(s.sq.get("encloses") or "").split(",") if n]
        walls = [model.by_name(n) for n in names]
        walls = [w for w in walls if w is not None]
        kw = dict(required={"value": req, "unit": "class", "op": ">="},
                  method="Lowest Pset_WallCommon.FireRating among the walls listed in SonarIQ_Ship.encloses.",
                  depends_on={w.guid for w in walls}, location=stair_location(model, s))
        if not walls:
            out.append(_res(rule, model, s, None, missing=["SonarIQ_Ship.encloses"], summary="enclosure not modelled",
                            measured={"value": None, "unit": "class"}, **kw))
            continue
        ratings = [w.prop("Pset_WallCommon", "FireRating") for w in walls]
        if any(fire_rank(r) is None for r in ratings):
            out.append(_res(rule, model, s, None, missing=["Pset_WallCommon.FireRating"],
                            measured={"value": None, "unit": "class"}, summary="enclosure wall class missing", **kw))
            continue
        low = min(ratings, key=fire_rank)
        out.append(_res(rule, model, s, fire_rank(low) >= fire_rank(req), measured={"value": low, "unit": "class"},
                        summary=f"{len(walls)} enclosure walls, lowest {low}", **kw))
    return out


def mvz_length(rule: Rule, model: Model, ctx: dict) -> list[CheckResult]:
    mx = float(rule.params.get("max_m", 40.0))
    out = []
    for z in model.by_class("IfcZone"):
        if z.sq.get("category") != "mvz":
            continue
        mem = [model.elements[g] for g in z.members if g in model.elements and model.elements[g].poly is not None]
        name = z.sq.get("mvz") or z.name
        kw = dict(required={"value": mx, "unit": "m", "op": "<="},
                  method="Extent along the ship (x) of the zone's member spaces on the deck.",
                  depends_on={m.guid for m in mem} | {f"members:{name}"},
                  location={"deck": z.sq.get("deck"), "frame": None, "side": None,
                            "label": f"{name} · Deck {z.sq.get('deck', '?')}"})
        if not mem:
            out.append(_res(rule, model, z, None, missing=["zone members"], summary="no spaces in zone", **kw))
            continue
        x0 = min(m.poly.bounds[0] for m in mem)
        x1 = max(m.poly.bounds[2] for m in mem)
        L = round(x1 - x0, 3)
        fs = model.frame_spacing_m
        kw["location"]["frame"] = f"{round(x0 / fs)}-{round(x1 / fs)}"
        out.append(_res(rule, model, z, L <= mx + 1e-6, measured={"value": L, "unit": "m"},
                        margin={"value": round(mx - L, 3), "unit": "m"},
                        summary=f"{name} {L:.1f} m, max {mx:.0f} m", **kw))
    return out


# ---------------------------------------------------------------- escape
def stair_location(model: Model, s: Element) -> dict:
    decks = [d for d in str(s.sq.get("decks_served") or "").split(",") if d]
    lab = s.name
    if decks:
        lab = f"{s.name} · Decks {min(decks, key=int)}–{max(decks, key=int)}"
    loc = location(model, s, label=lab)
    return loc


def flight_width(model: Model, s: Element) -> tuple[float | None, list[Element]]:
    flights = [model.elements[g] for g in s.parts if g in model.elements]
    widths = [rect(f.poly)[0] for f in flights if f.poly is not None]
    return (min(widths) if widths else None), flights


def stair_persons(model: Model, s: Element) -> tuple[list[dict], list[str], set[str]]:
    """Persons per served deck. The modelled deck(s) are counted from cabin berths in the stair's MVZ;
    other decks come from SonarIQ_Ship.persons_by_deck. Returns (inputs, missing, depends)."""
    decks = [d for d in str(s.sq.get("decks_served") or "").split(",") if d]
    declared = {}
    try:
        declared = json.loads(s.sq.get("persons_by_deck") or "{}")
    except Exception:  # noqa: BLE001
        pass
    mvz = s.sq.get("mvz")
    modelled_decks = {str(e.sq.get("deck")) for e in model.spaces("cabin")}
    inputs, missing, deps = [], [], set()
    for d in decks:
        if d in modelled_decks:
            cabins = [c for c in model.spaces("cabin", deck=d) if not mvz or c.sq.get("mvz") == mvz]
            no_berths = [c.name for c in cabins if c.sq.get("berths") is None]
            deps |= {c.guid for c in cabins} | {f"berths:{d}:{mvz}"}
            if no_berths:
                missing.append(f"SonarIQ_Ship.berths on {len(no_berths)} cabins (Deck {d})")
                continue
            n = sum(int(c.sq["berths"]) for c in cabins)
            inputs.append({"deck": d, "value": n, "source": "model", "source_guids": [c.guid for c in cabins],
                           "note": f"{len(cabins)} cabins in {mvz}, berths counted"})
        elif d in declared:
            inputs.append({"deck": d, "value": int(declared[d]), "source": "persons_by_deck"})
        else:
            missing.append(f"persons on Deck {d}")
    return inputs, missing, deps


def stair_width_formula(rule: Rule, model: Model, ctx: dict) -> list[CheckResult]:
    D = float(rule.params.get("D_mm", 10))
    weights = rule.params.get("weights", [1.0, 1.0, 0.5, 0.25])
    out = []
    for s in model.by_class("IfcStair"):
        if not s.sq.get("decks_served"):
            continue
        w, flights = flight_width(model, s)
        inputs, missing, deps = stair_persons(model, s)
        deps |= {f.guid for f in flights}
        loc = stair_location(model, s)
        method = ("Clear width = short side of the stair flight solid (IfcStairFlight), between handrails as "
                  "modelled. Persons: Deck 5 = berths of the cabins in the stair's MVZ, counted from the model; "
                  "other decks from SonarIQ_Ship.persons_by_deck. N1..N4 are taken largest first.")
        if w is None:
            missing.append("IfcStairFlight geometry")
        if missing:
            out.append(_res(rule, model, s, None, missing=missing, depends_on=deps, location=loc, method=method,
                            summary="inputs missing: " + "; ".join(missing)))
            continue
        ins = sorted(inputs, key=lambda i: -i["value"])[: len(weights)]
        terms, total = [], 0.0
        for k, (i, wt) in enumerate(zip(ins, weights)):
            i["name"] = f"N{k + 1}"
            i["weight"] = wt
            i["weighted"] = i["value"] * wt
            total += i["value"] * wt
            terms.append(i)
        req = round(total * D)
        meas = mm(w)
        tw = " + ".join(f"{fmt_int(t['weighted']) if t['weighted'] == int(t['weighted']) else t['weighted']}"
                        for t in terms)
        worked = f"({tw}) × {int(D)} = {fmt_int(total)} × {int(D)} = {fmt_int(req)} mm"
        formula = {"text": "W = (N₁ + N₂ + 0.5 N₃ + 0.25 N₄) × 10 mm", "inputs": terms, "worked": worked,
                   "D_mm": D}
        out.append(_res(rule, model, s, meas >= req,
                        required={"value": req, "unit": "mm", "op": ">="},
                        measured={"value": meas, "unit": "mm"},
                        margin={"value": meas - req, "unit": "mm"},
                        formula=formula, method=method, depends_on=deps, location=loc,
                        summary=f"required {fmt_int(req)} mm, measured {fmt_int(meas)} mm",
                        extra={"persons": {t["deck"]: t["value"] for t in terms}}))
    return out


def stair_min_width(rule: Rule, model: Model, ctx: dict) -> list[CheckResult]:
    mn = float(rule.params.get("min_mm", 900))
    out = []
    for s in model.by_class("IfcStair"):
        w, flights = flight_width(model, s)
        kw = dict(required={"value": int(mn), "unit": "mm", "op": ">="}, location=stair_location(model, s),
                  method="Short side of the stair flight solid (IfcStairFlight).",
                  depends_on={f.guid for f in flights})
        if w is None:
            out.append(_res(rule, model, s, None, missing=["IfcStairFlight geometry"], summary="flight missing", **kw))
            continue
        out.append(_res(rule, model, s, mm(w) >= mn, measured={"value": mm(w), "unit": "mm"},
                        margin={"value": mm(w) - int(mn), "unit": "mm"},
                        summary=f"clear width {fmt_int(mm(w))} mm, min {fmt_int(mn)} mm", **kw))
    return out


def corridor_graph(model: Model) -> nx.Graph:
    """Corridor + stair spaces; edge where two footprints share >= 0.5 m of boundary."""
    G = nx.Graph()
    nodes = [e for e in model.spaces() if e.sq.get("category") in ("corridor", "stair") and e.poly is not None]
    for e in nodes:
        G.add_node(e.guid, cat=e.sq.get("category"))
    for i, a in enumerate(nodes):
        ab = a.poly.buffer(0.03)
        for b in nodes[i + 1:]:
            if not ab.intersects(b.poly):
                continue
            inter = ab.intersection(b.poly.buffer(0.03))
            if inter.is_empty:
                continue
            x0, y0, x1, y1 = inter.bounds
            if max(x1 - x0, y1 - y0) >= 0.5:
                G.add_edge(a.guid, b.guid)
    return G


def dead_end(rule: Rule, model: Model, ctx: dict) -> list[CheckResult]:
    G = ctx.get("corridor_graph")
    if G is None:
        G = ctx["corridor_graph"] = corridor_graph(model)
    out = []
    for c in model.spaces("corridor"):
        if c.poly is None:
            out.append(_res(rule, model, c, None, missing=["space geometry"], summary="no footprint"))
            continue
        nbrs = list(G.neighbors(c.guid)) if c.guid in G else []
        has_stair = any(G.nodes[n].get("cat") == "stair" for n in nbrs)
        cont = bool(c.sq.get("escape_continues"))
        corr_n = [n for n in nbrs if G.nodes[n].get("cat") == "corridor"]
        width, depth = rect(c.poly)
        is_dead = not has_stair and not cont and len(corr_n) <= 1
        deps = set(nbrs) | {c.guid}
        method = ("Corridor adjacency graph from space footprints (shared edge ≥ 0.5 m). A dead end is a corridor "
                  "with escape in one direction only: at most one corridor neighbour, no stair, and no "
                  "SonarIQ_Ship.escape_continues. Depth = long side, width = short side of the footprint.")
        if not is_dead:
            out.append(_res(rule, model, c, True, required={"value": round(width, 2), "unit": "m", "op": ">=",
                                                             "label": "depth ≤ width"},
                            measured={"value": None, "unit": "m", "label": f"{len(nbrs)} escape directions"},
                            depends_on=deps, method=method, summary=f"not a dead end · {len(nbrs)} connections",
                            extra={"dead_end": False, "neighbours": len(nbrs)}))
            continue
        ok = depth <= width + 1e-6
        out.append(_res(rule, model, c, ok, required={"value": round(width, 2), "unit": "m", "op": "<=",
                                                       "label": "depth ≤ width"},
                        measured={"value": round(depth, 2), "unit": "m"},
                        margin={"value": round(width - depth, 2), "unit": "m"},
                        depends_on=deps, method=method,
                        summary=f"dead end · depth {depth:.1f} m {'>' if not ok else '≤'} width {width:.1f} m",
                        extra={"dead_end": True, "depth_m": round(depth, 3), "width_m": round(width, 3)}))
    return out


def corridor_width(rule: Rule, model: Model, ctx: dict) -> list[CheckResult]:
    mn = float(rule.params["min_mm"])
    unit = rule.params.get("unit", "mm")
    out = []
    for c in model.spaces("corridor"):
        if rule.applicability.get("accessibility") and not c.sq.get("accessible_route", True):
            continue
        kw = dict(required={"value": int(mn), "unit": "mm", "op": ">="},
                  method="Clear width = short side of the corridor space footprint (IfcSpace), wall face to wall "
                         "face as modelled.")
        if unit == "in":
            kw["required"]["alt"] = {"value": round(mn / MM_PER_IN), "unit": "in"}
        if c.poly is None:
            out.append(_res(rule, model, c, None, missing=["space geometry"], summary="no footprint", **kw))
            continue
        w = mm(rect(c.poly)[0])
        alt = f" ({round(mn / MM_PER_IN)} in)" if unit == "in" else ""
        word = "guideline" if rule.severity == "warning" else "min"
        out.append(_res(rule, model, c, w >= mn, measured={"value": w, "unit": "mm"},
                        margin={"value": w - int(mn), "unit": "mm"},
                        summary=f"clear width {fmt_int(w)} mm, {word} {fmt_int(mn)} mm{alt}", **kw))
    return out


# ---------------------------------------------------------------- accessibility
def door_clear_width(rule: Rule, model: Model, ctx: dict) -> list[CheckResult]:
    mn_in = float(rule.params.get("min_in", 32))
    mn_mm = mn_in * MM_PER_IN
    out = []
    for d in model.by_class("IfcDoor"):
        if not d.sq.get("accessible_route"):
            continue
        kw = dict(required={"value": mn_in, "unit": "in", "op": ">=", "alt": {"value": round(mn_mm), "unit": "mm"}},
                  method="Clear opening = IfcDoor.OverallWidth (generated model writes the clear opening there). "
                         "RCRV: short horizontal side of the leaf's oriented bounding box.")
        w = d.sq.get("clear_width_m") or d.overall_width
        if w is None:
            out.append(_res(rule, model, d, None, missing=["IfcDoor.OverallWidth"], summary="width missing", **kw))
            continue
        w_mm = w * 1000
        w_in = w_mm / MM_PER_IN
        out.append(_res(rule, model, d, w_mm + 1e-6 >= mn_mm,
                        measured={"value": round(w_in, 1), "unit": "in", "alt": {"value": round(w_mm), "unit": "mm"}},
                        margin={"value": round(w_in - mn_in, 1), "unit": "in"},
                        summary=f"clear {w_in:.1f} in ({round(w_mm)} mm), min {mn_in:.0f} in", **kw))
    return out


# ---------------------------------------------------------------- hvac / class
def duct_damper(rule: Rule, model: Model, ctx: dict) -> list[CheckResult]:
    rad = float(rule.params.get("search_radius_m", 1.0))
    walls = [w for w in model.by_class("IfcWall") if w.poly is not None
             and is_a_class(w.prop("Pset_WallCommon", "FireRating"))]
    dampers = [d for d in model.by_class("IfcDamper") if d.poly is not None]
    out = []
    for duct in model.by_class("IfcDuctSegment"):
        if duct.poly is None:
            continue
        for w in walls:
            if not duct.poly.intersects(w.poly):
                continue
            if duct.z0 is not None and w.z1 is not None and (duct.z0 > w.z1 or duct.z1 < w.z0):
                continue
            cross = duct.poly.intersection(w.poly)
            near = [d for d in dampers if d.poly.distance(cross) <= rad]
            r = _res(rule, model, duct, bool(near),
                     required={"value": "fire damper", "unit": "", "op": "present"},
                     measured={"value": near[0].name if near else "none", "unit": ""},
                     method=f"Duct footprint intersected with A-class wall footprints; an IfcDamper within {rad} m "
                            "of the crossing counts.",
                     depends_on={w.guid} | {d.guid for d in dampers},
                     summary=f"crosses {w.name} ({w.prop('Pset_WallCommon', 'FireRating')}) · "
                             f"{'damper ' + near[0].name if near else 'no damper'}",
                     extra={"wall": w.name})
            out.append(r)
    return out


def plate_thickness(rule: Rule, model: Model, ctx: dict) -> list[CheckResult]:
    a, b, cap = (float(rule.params[k]) for k in ("a_mm", "b_mm_per_m", "l_cap_m"))
    L = model.ship.get("length_m")
    out = []
    for p in model.by_class("IfcPlate"):
        if p.sq.get("category") != "deck_plate":
            continue
        if L is None:
            out.append(_res(rule, model, p, None, missing=["SonarIQ_Ship.length_m on the ship"],
                            summary="ship length missing"))
            continue
        req = round(a + b * min(float(L), cap), 2)
        if p.z0 is None:
            out.append(_res(rule, model, p, None, missing=["plate geometry"], summary="no solid"))
            continue
        t = round((p.z1 - p.z0) * 1000, 1)
        out.append(_res(rule, model, p, t + 1e-6 >= req, required={"value": req, "unit": "mm", "op": ">="},
                        measured={"value": t, "unit": "mm"}, margin={"value": round(t - req, 1), "unit": "mm"},
                        method="Plate thickness = vertical extent of the IfcPlate solid. "
                               f"t0 = {a} + {b} × min(L, {cap:.0f}) with L = {L} m.",
                        summary=f"t {t} mm, min {req} mm (to verify)"))
    return out


def placeholder(rule: Rule, model: Model, ctx: dict) -> list[CheckResult]:
    return []


CHECKS: dict[str, Callable[[Rule, Model, dict], list[CheckResult]]] = {
    "door_fire_class": door_fire_class,
    "window_fire_class": window_fire_class,
    "door_self_closing": door_self_closing,
    "mvz_bulkhead_class": mvz_bulkhead_class,
    "stair_enclosure_class": stair_enclosure_class,
    "mvz_length": mvz_length,
    "stair_width_formula": stair_width_formula,
    "stair_min_width": stair_min_width,
    "dead_end": dead_end,
    "corridor_width": corridor_width,
    "door_clear_width": door_clear_width,
    "duct_damper": duct_damper,
    "plate_thickness": plate_thickness,
    "placeholder": placeholder,
}
