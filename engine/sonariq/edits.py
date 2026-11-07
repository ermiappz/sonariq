"""The only four model edits SonarIQ may make, and engine-verified fix proposals.

The guard is code: anything that does not parse as one of the four edit models is refused (E1), whatever
an AI client asks for. Edits act on the in-memory model; the engine re-checks the result.
"""
from __future__ import annotations

import hashlib
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from shapely.geometry import box

from .checks import fire_rank
from .engine import analyse, impact
from .model import Element, Model, rect

ALLOWED = ("add_cabin_block", "move_wall", "set_door_width", "set_door_fire_class")


class EditRefused(Exception):
    pass


class AddCabinBlock(BaseModel):
    kind: Literal["add_cabin_block"] = "add_cabin_block"
    deck: str = "5"
    frame_from: float = Field(description="aft end of the block, frame number")
    count: int = Field(ge=1, le=12)
    berths_per_cabin: int = Field(ge=1, le=4, default=2)
    y_from: float = -6.0              # inboard block by default (m, +y = port)
    cabin_width_m: float = 2.0        # across the ship
    cabin_length_m: float = 6.0       # along the ship
    change_request: str = "OR-117"
    replace_existing: bool = True     # replace an earlier block of the same change request


class MoveWall(BaseModel):
    kind: Literal["move_wall"] = "move_wall"
    space: str = Field(description="corridor whose boundary wall moves, e.g. COR-5-152-S")
    width_mm: float = Field(gt=300, lt=5000, description="resulting clear width")


class SetDoorWidth(BaseModel):
    kind: Literal["set_door_width"] = "set_door_width"
    door: str
    width_mm: float = Field(gt=300, lt=3000)


class SetDoorFireClass(BaseModel):
    kind: Literal["set_door_fire_class"] = "set_door_fire_class"
    door: str
    fire_class: str


Edit = Annotated[Union[AddCabinBlock, MoveWall, SetDoorWidth, SetDoorFireClass], Field(discriminator="kind")]
_adapter = TypeAdapter(Edit)


def parse_edit(edit: dict) -> BaseModel:
    if not isinstance(edit, dict) or edit.get("kind") not in ALLOWED:
        raise EditRefused(f"Edit not allowed. SonarIQ only makes these edits: {', '.join(ALLOWED)}.")
    try:
        return _adapter.validate_python(edit)
    except ValidationError as e:
        raise EditRefused(f"Edit {edit.get('kind')} has invalid fields: {e.errors()[0]['msg']}") from e


def _gid(name: str) -> str:
    return "SQ" + hashlib.sha1(name.encode()).hexdigest()[:20]


def apply_edit(model: Model, edit: dict) -> tuple[Model, BaseModel, str]:
    """Return (new model, parsed edit, preview text). The input model is not changed."""
    e = parse_edit(edit)
    m = model.copy()
    fs = m.frame_spacing_m
    if isinstance(e, AddCabinBlock):
        if e.replace_existing:
            for g in [g for g, el in m.elements.items() if el.sq.get("change_request") == e.change_request
                      and el.sq.get("category") == "cabin"]:
                del m.elements[g]
        x0 = e.frame_from * fs
        x1 = x0 + e.cabin_length_m
        block = box(x0, e.y_from, x1, e.y_from + e.count * e.cabin_width_m)
        mvz_zone = None
        for z in m.by_class("IfcZone"):
            mem = [m.elements[g] for g in z.members if g in m.elements and m.elements[g].poly is not None]
            if mem and min(s.poly.bounds[0] for s in mem) <= x0 < max(s.poly.bounds[2] for s in mem):
                mvz_zone = z
        mvz = mvz_zone.sq.get("mvz") if mvz_zone else None
        # existing spaces under the block are cut back (corridors keep their largest remaining piece)
        for s in m.spaces(deck=e.deck):
            if s.poly is None or s.sq.get("change_request") == e.change_request:
                continue
            if s.poly.intersection(block).area > 0.05:
                rest = s.poly.difference(block)
                if rest.is_empty:
                    del m.elements[s.guid]
                    continue
                if rest.geom_type == "MultiPolygon":
                    rest = max(rest.geoms, key=lambda p: p.area)
                s.poly = rest
        for i in range(e.count):
            y0 = e.y_from + i * e.cabin_width_m
            name = f"CAB-{e.deck}-{e.change_request}-{i + 1}"
            el = Element(guid=_gid(name + str(e.frame_from)), ifc_class="IfcSpace", name=name,
                         psets={"SonarIQ_Ship": {"category": "cabin", "deck": e.deck, "berths": e.berths_per_cabin,
                                                 "mvz": mvz, "side": "P" if y0 + 1 > 0.3 else "C",
                                                 "frame": f"{round(x0 / fs)}-{round(x1 / fs)}",
                                                 "change_request": e.change_request}},
                         poly=box(x0, y0, x1, y0 + e.cabin_width_m), z0=14.5, z1=17.3, storey=f"Deck {e.deck}")
            m.elements[el.guid] = el
            if mvz_zone is not None:
                mvz_zone.members.append(el.guid)
        prev = (f"Add {e.count} cabins × {e.berths_per_cabin} berths ({e.count * e.berths_per_cabin} berths) "
                f"on Deck {e.deck}, Fr {e.frame_from:g}–{(x1 / fs):g}, {mvz or 'MVZ ?'} · {e.change_request}")
    elif isinstance(e, MoveWall):
        s = m.by_name(e.space)
        if s is None or s.ifc_class != "IfcSpace" or s.poly is None:
            raise EditRefused(f"No corridor called {e.space}.")
        x0, y0, x1, y1 = s.poly.bounds
        w = e.width_mm / 1000
        old = rect(s.poly)[0]
        # the outboard boundary moves (port: +y, starboard: -y); corridors along the ship
        if (x1 - x0) >= (y1 - y0):
            s.poly = box(x0, y0, x1, y0 + w) if (y0 + y1) / 2 > 0 else box(x0, y1 - w, x1, y1)
        else:
            s.poly = box(x0, y0, x0 + w, y1)
        prev = f"Move the outboard wall of {e.space}: clear width {round(old * 1000):,} → {round(e.width_mm):,} mm"
    elif isinstance(e, SetDoorWidth):
        d = m.by_name(e.door)
        if d is None or d.ifc_class != "IfcDoor":
            raise EditRefused(f"No door called {e.door}.")
        old = d.overall_width
        d.overall_width = e.width_mm / 1000
        prev = f"Set door {e.door} clear width {round((old or 0) * 1000):,} → {round(e.width_mm):,} mm"
    else:
        assert isinstance(e, SetDoorFireClass)
        d = m.by_name(e.door)
        if d is None or d.ifc_class != "IfcDoor":
            raise EditRefused(f"No door called {e.door}.")
        if fire_rank(e.fire_class) is None:
            raise EditRefused(f"Unknown fire class {e.fire_class}.")
        old = d.prop("Pset_DoorCommon", "FireRating")
        d.psets.setdefault("Pset_DoorCommon", {})["FireRating"] = e.fire_class.upper()
        prev = f"Set door {e.door} fire class {old or 'empty'} → {e.fire_class.upper()}"
    return m, e, prev


# ---------------------------------------------------------------- fix proposals (engine re-checks each)
def _verify(model: Model, groups, key: str, edit: dict | None, label: str, needs: str | None = None,
            stair_width_mm: float | None = None) -> dict:
    m = model.copy()
    preview = None
    if edit is not None:
        m, _, preview = apply_edit(m, edit)
    if stair_width_mm is not None:  # widening a stair is structural: modelled, never offered as a chat edit
        rule_el = m.elements[key.split("|")[1]]
        for g in rule_el.parts:
            f = m.elements[g]
            x0, y0, x1, y1 = f.poly.bounds
            cy = (y0 + y1) / 2
            w = stair_width_mm / 2000
            f.poly = box(x0, cy - w, x1, cy + w)
    run = analyse(m, groups)
    r = run.by_key().get(key)
    return {"label": label, "edit": edit, "preview": preview, "needs": needs,
            "verdict": r.status if r else "na", "required": r.required if r else None,
            "measured": r.measured if r else None, "summary": r.summary if r else "",
            "counts": run.counts(), "verified_by": "Rule engine"}


def propose_fixes(model: Model, run, key: str, groups=None) -> list[dict]:
    r = run.by_key()[key]
    rule = r.rule
    out: list[dict] = []
    if rule.check == "stair_width_formula":
        req = r.required["value"]
        widen = int(-(-req // 50) * 50) if req % 50 else req + 20
        out.append(_verify(model, groups, key, None, f"Widen Stair {r.element.name.split()[-1]} to {widen:,} mm",
                           needs="Structure", stair_width_mm=widen))
        block = [e for e in model.spaces("cabin") if e.sq.get("change_request")]
        if block:
            cr = block[0].sq["change_request"]
            fr = round(min(e.poly.bounds[0] for e in block) / model.frame_spacing_m, 1)
            n = len(block)
            out.append(_verify(model, groups, key, {"kind": "add_cabin_block", "frame_from": fr, "count": n,
                                                     "berths_per_cabin": 1, "change_request": cr},
                               f"{n} cabins, one berth each"))
            out.append(_verify(model, groups, key, {"kind": "add_cabin_block", "frame_from": fr, "count": 1,
                                                     "berths_per_cabin": 2, "change_request": cr},
                               "One cabin instead of four"))
            rej = _verify(model, groups, key, {"kind": "add_cabin_block", "frame_from": fr + 10, "count": n,
                                                "berths_per_cabin": int(block[0].sq.get("berths", 2)),
                                                "change_request": cr},
                          "Move the block 10 frames forward")
            rej["rejected"] = True
            out.append(rej)
    elif rule.check in ("door_fire_class",):
        out.append(_verify(model, groups, key, {"kind": "set_door_fire_class", "door": r.element.name,
                                                 "fire_class": r.required["value"]},
                           f"Fit an {r.required['value']} door"))
    elif rule.check == "corridor_width":
        out.append(_verify(model, groups, key, {"kind": "move_wall", "space": r.element.name,
                                                 "width_mm": r.required["value"]},
                           f"Move the wall to give {r.required['value']:,} mm"))
    elif rule.check == "door_clear_width":
        out.append(_verify(model, groups, key, {"kind": "set_door_width", "door": r.element.name,
                                                 "width_mm": r.required["alt"]["value"] + 2},
                           f"Widen to {r.required['alt']['value'] + 2} mm"))
    for f in out:
        f["fixes"] = f["verdict"] == "pass"
    return out


def recheck_after(model_before: Model, run_before, model_after: Model, groups=None):
    run_after = analyse(model_after, groups)
    return run_after, impact(model_before, run_before, model_after, run_after)
