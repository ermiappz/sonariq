# Whole-ship viewer

Why this design: `docs/DECISIONS.md` M1–M10. Plan: `docs/PLAN.md`.

## Pipeline (engine)

```
IFC (2x3 / 4 / 4x3) ──ifcopenshell.geom──┐
RCRV glTF + properties.jsonl ────────────┼─> pipeline/tiles.py ─> raw GLB tiles + elements.json + meta.json + colors.bin
                                         │                      └─> scripts/node/pack_tiles.mjs (Meshopt + integrity check)
                                         └─ discipline: config/discipline_mapping.yaml (class first, then rules)
```

- `POST /models` (upload) or `POST /models/prepare` (`{revision | path | run | source: "rcrv"}`) stores the original
  under `data/models/<sha256[:16]>/original.ifc`, never changed, and converts once in the background.
  `GET /models/<id>` reports `state` and `progress` ("Preparing a fast web version"). Same bytes → same id → no new work.
- `GET /models/<id>/files/{index.json, elements.json, colors.bin, tiles/*.glb}` with
  `Cache-Control: public, max-age=31536000, immutable`. `meta.json` stays on the server; the properties card reads
  `GET /models/<id>/elements/<index>`.
- Rebuild RCRV by hand: `PYTHONPATH=engine:. .venv/bin/python -m sonariq.pipeline.build rcrv data/models/rcrv/web`
  (≈ 2 min, peak ≈ 4 GB), or `POST /models/prepare {"source": "rcrv"}`.

| Model | Elements | Triangles | Tiles | Size | Conversion |
|---|---|---|---|---|---|
| deck5_revB | 258 | 4,244 | 31 | 53 KB | 1.2 s |
| RCRV | 90,331 | 50.8 M | 551 | 196 MB | 111 s (read 42 s) |

Both pack with 0 vertex and 0 triangle mismatches; maximum quantisation error 0.21 mm (deck5) and 0.16 mm (RCRV).

## IDs

`elements.json[i] = [GlobalId, source id, IFC class, name]`; every vertex carries `i`. The viewer's GPU pick returns `i`.
RCRV GlobalIds are the same function `scripts/rcrv_to_ifc.py` uses, so findings on `rcrv_*.ifc` land on the tiles.
Aggregates without geometry (IfcStair → flights, IfcZone → spaces) resolve through `index.json.aliases`.
Proof: `tests/test_pipeline.py` (every finding of Rev B, every product GlobalId of RCRV decks 1, 5, 7) and
`portal/e2e/viewer.spec.mjs` (picks in the browser return the same GlobalId).

## Viewer (portal/src/viewer/ShipViewer.ts)

- Overview tiles first (≤ 4 M triangles), detail tiles streamed within 24 m of the camera (1.5 M triangle budget,
  6 requests in flight); tiles of a focused or picked element are loaded and pinned.
- Element state is one RGBA texture: colour + 0 hidden / 1–254 ghosted (x-ray) / 255 solid. Two passes when anything is
  ghosted (solid, then ghost with blending), one otherwise.
- Hover highlight, click select → properties card (class, GlobalId, source id, deck, discipline, SWBS, system,
  material, grade, thickness, fire rating), isolate / hide / show all, standard views (iso, top, port, starboard, bow,
  stern: bow = +x, port = +y), perspective / orthographic, zoom to cursor, deck selector (clips everything above).

## Tests

- `make test`: pipeline, models API, ID mapping.
- `portal/e2e/run.sh`: throwaway engine (8797) + Vite (5197) + headless Chromium with software GL; screenshots go to
  `docs/screenshots/m*.png`. This VM has no GPU, so frame rates measured here are lower bounds.

## Known limits

- glTF/GLB upload is not converted yet (IFC only); the RCRV glTF is a built-in source.
- Overview = biggest size-per-triangle parts, not exterior-visibility sampling.
- One RCRV sample out of 12 returns no hit in the pick test (a very small part); never a wrong element.
