# Viewer performance

Measured by `scripts/perf_report.mjs` on 2026-11-14 (`cd portal && ./e2e/run.sh ../scripts/perf_report.mjs`).

**All browser numbers are software GL** (headless Chromium + SwiftShader on a CPU-only VM, 1440 × 900). A laptop GPU is
many times faster; read fps here as a floor and as a comparison between models, not as what a user sees.

| Model | Elements | Triangles | Web size | Conversion | First frame | fps orbiting | Draw calls | Peak JS heap |
|---|---|---|---|---|---|---|---|---|
| deck5_revB | 258 | 4,244 | 53 KB | 1 s | 0.6 s | 7.2 | 63 | 36 MB |
| RCRV whole ship | 90,331 | 50,843,045 | 195.9 MB | 110.8 s | 2.5 s | 0.1 | 525 | 152 MB |
| Infra-Landscaping (buildingSMART sample) | 101 | 20,153 | 101 KB | 4 s | 1.4 s | 7.1 | 45 | 36 MB |

- **Conversion**: engine time to read the file and write Meshopt tiles (`summary.seconds.total` of the model status),
  measured once when the file is first converted; later openings reuse the tiles (same bytes → same id).
- **First frame**: from opening the model in the Studio to the first frame with triangles (`stats.firstFrame`),
  including the conversion when it was not cached.
- **fps orbiting**: frames rendered during a 5 s orbit of a quarter turn around the view target.
- **Draw calls**: per frame at the whole-model view: each loaded tile is drawn twice (colour pass and the element-id pass the edges are found from), plus overlay passes.
- **Peak JS heap**: `performance.memory.usedJSHeapSize` (Chromium); GPU memory is not measurable from the page.
- Open sample: buildingSMART Sample-Test-Files, IFC4 `Simple-Scene/Infra-Landscaping.ifc` (2.3 MB, the largest
  geometry sample in that repo). The repo states no licence, so the file is downloaded by the script and not committed.
  No larger open-licence ship IFC was available offline.
