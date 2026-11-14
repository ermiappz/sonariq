"""The whole RCRV as an engine Model, from the metadata index the pipeline wrote (data/models/rcrv/web/meta.json).

One parse of the Navisworks properties feeds both the viewer and the rules, and both use the same GlobalIds.
Element psets:
  SonarIQ_Ship    deck, side, x_from_aft_m (DECISIONS M6: no frame grid in this model)
  SonarIQ_Source  what the CAD export says: ShipConstructor stock thickness / material / grade / SWBS-like code /
                  part GUID, pipe system and material (from DWG block attributes), error values, source id (dbid)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import shapely

from .model import Element, Model
from .session import DATA

WEB = DATA / "models" / "rcrv" / "web"
SOURCE_FILE = "12100-RCRV-199_07-08-2021.nwd"
# vessel profile as written by scripts/rcrv_to_ifc.py (DECISIONS #26)
PROFILE = {"name": "RCRV", "vessel_type": "research", "persons_on_board": 28, "scientists": 16, "crew": 12,
           "accessibility": True, "units_of_source": "inches", "revision": "RCRV"}
SRC_KEYS = ("thickness_raw", "thickness_mm", "material", "grade", "stock", "swbs", "part_guid", "system",
            "error_values", "source_file", "layer", "mapped", "discipline")


def available() -> bool:
    return (WEB / "meta.json").exists() and (WEB / "elements.json").exists()


def load_rcrv(web: Path = WEB) -> Model:
    if not (web / "meta.json").exists():
        raise FileNotFoundError("RCRV is not prepared on this engine (POST /models/prepare {\"source\": \"rcrv\"}).")
    rows = json.loads((web / "elements.json").read_text())
    meta = json.loads((web / "meta.json").read_text())
    ix = json.loads((web / "index.json").read_text())
    x_aft = ix["box"][0][0]
    B = np.array([m["bbox"] for m in meta], dtype=float)
    B[:, 3] = np.maximum(B[:, 3], B[:, 0] + 1e-3)
    B[:, 4] = np.maximum(B[:, 4], B[:, 1] + 1e-3)
    polys = shapely.box(B[:, 0], B[:, 1], B[:, 3], B[:, 4])      # vectorised: 90k boxes in one call
    els: dict[str, Element] = {}
    for k, ((gid, src, cls, name), m) in enumerate(zip(rows, meta)):
        b = m["bbox"]
        cy = (b[1] + b[4]) / 2
        e = Element(guid=gid, ifc_class=cls, name=name or gid,
                    psets={"SonarIQ_Ship": {"deck": str(m.get("deck")), "side": "P" if cy > 0.3 else "S" if cy < -0.3 else "C",
                                            "x_from_aft_m": round((b[0] + b[3]) / 2 - x_aft, 1)},
                           "SonarIQ_Source": {"source_id": src, **{key: m[key] for key in SRC_KEYS if m.get(key) is not None}}})
        e.poly = polys[k]
        e.z0, e.z1 = b[2], b[5]
        e.storey = f"Deck {m.get('deck')}"
        els[gid] = e
    ship = dict(PROFILE, length_m=round(ix["box"][1][0] - x_aft, 2))
    return Model(path=str(web / "meta.json"), revision="RCRV", ship=ship, elements=els, frame_spacing_m=1.0)
