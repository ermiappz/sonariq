// Viewer performance report (plan 9.2) → docs/PERFORMANCE.md. Opens each model in the real Studio (headless Chromium,
// SwiftShader software GL on this VM, so fps is a floor, not what a GPU gives) and reads:
// conversion time / size / triangles from the engine's model status, time to first frame, fps while orbiting,
// draw calls per frame and peak JS heap from the page.
// usage: cd portal && ./e2e/run.sh ../scripts/perf_report.mjs     (throwaway engine + Vite, never the live services)
import fs from 'node:fs';
import path from 'node:path';
import { browser, BASE } from '../portal/e2e/lib.mjs';

const ROOT = path.resolve(new URL('..', import.meta.url).pathname);
// buildingSMART Sample-Test-Files, largest IFC4 geometry sample (2.3 MB); the repo states no licence, so it is
// downloaded here and never committed
const OPEN_URL = 'https://raw.githubusercontent.com/buildingSMART/Sample-Test-Files/main/IFC%204.0.2.1%20(IFC%204%20ADD2%20TC1)/Simple-Scene/Infra-Landscaping.ifc';
const OPEN = path.join(ROOT, 'data/open/Infra-Landscaping.ifc');
if (!fs.existsSync(OPEN)) {
  try { const r = await fetch(OPEN_URL); if (r.ok) { fs.mkdirSync(path.dirname(OPEN), { recursive: true }); fs.writeFileSync(OPEN, Buffer.from(await r.arrayBuffer())); } } catch { /* offline: row says so */ }
}

const MODELS = [
  { name: 'deck5_revB', open: (p) => p.getByRole('button', { name: /deck5_revB\.ifc/ }).click() },
  { name: 'RCRV whole ship', open: (p) => p.getByRole('button', { name: /RCRV whole ship/ }).click(), need: '/api/models/rcrv' },
  { name: 'Infra-Landscaping (buildingSMART sample)', file: OPEN, open: (p) => p.locator('input[type=file][accept=".ifc"]').setInputFiles(OPEN) },
];

async function measure(m) {
  const { b, page } = await browser({ width: 1440, height: 900 });
  try {
    await page.goto(BASE + '#model');
    await page.waitForLoadState('networkidle');
    if (m.need && !(await page.evaluate(async (u) => (await fetch(u)).ok, m.need))) return { name: m.name, skip: 'not on this engine (data/rcrv is not in git)' };
    if (m.file && !fs.existsSync(m.file)) return { name: m.name, skip: 'not available offline' };
    const t0 = Date.now();
    await m.open(page);
    await page.waitForFunction(() => window.__sqViewer?.stats.firstFrame != null && window.__sqViewer.stats.overviewMs != null, null, { timeout: 900000 });
    const wall = Date.now() - t0;
    await page.waitForTimeout(3000);
    const r = await page.evaluate(async () => {
      const v = window.__sqViewer;
      const mem = () => performance.memory?.usedJSHeapSize ?? 0;
      let peak = mem();
      // orbit 5 s: turn the camera around the target a little every frame, count rendered frames
      const t = v.controls.target.clone(), off = v.camera.position.clone().sub(t);
      let frames = 0; const orig = v.render.bind(v); v.render = () => { frames++; orig(); };
      const start = performance.now();
      await new Promise((res) => { const step = () => { const a = (performance.now() - start) / 5000 * Math.PI / 2;
        v.camera.position.copy(t).add(off.clone().applyAxisAngle({ x: 0, y: 0, z: 1, isVector3: true }, a)); v.controls.update(); v.dirty = true; peak = Math.max(peak, mem());
        if (performance.now() - start < 5000) requestAnimationFrame(step); else res(); }; requestAnimationFrame(step); });
      const secs = (performance.now() - start) / 1000;
      v.render = orig;
      const inf = v.renderer.info; inf.autoReset = false; inf.reset(); v.render(); const calls = inf.render.calls; inf.autoReset = true;   // one frame = several passes
      return { firstFrame: v.stats.firstFrame, overview: v.stats.overviewMs, fps: frames / secs, calls, heapMB: peak / 1048576 };
    });
    // conversion numbers from the engine's model status (measured when the model was first converted)
    const st = await page.evaluate(async () => {
      const ids = performance.getEntriesByType('resource').map((e) => /\/api\/models\/([0-9a-f]{16}|rcrv)\//.exec(e.name)?.[1]).filter(Boolean);
      const id = ids[ids.length - 1]; if (!id) return null;
      return (await fetch(`/api/models/${id}`)).json();
    });
    return { name: m.name, wall, ...r, sum: st?.summary ?? null };
  } finally { await b.close(); }
}

const rows = [];
for (const m of MODELS) { const r = await measure(m); console.log(JSON.stringify(r)); rows.push(r); }

const mb = (x) => (x >= 1048576 ? `${(x / 1048576).toFixed(1)} MB` : `${Math.ceil(x / 1024)} KB`);
const n = (x) => x.toLocaleString('en-US');
const lines = rows.map((r) => r.skip ? `| ${r.name} | ${r.skip} | | | | | | | |`
  : `| ${r.name} | ${n(r.sum?.elements ?? 0)} | ${n(r.sum?.tris ?? 0)} | ${r.sum ? mb(r.sum.bytes) : '?'} | ${r.sum?.seconds ? `${r.sum.seconds.total} s` : '?'} | ${(r.firstFrame / 1000).toFixed(1)} s | ${r.fps.toFixed(1)} | ${r.calls} | ${r.heapMB.toFixed(0)} MB |`);
const md = `# Viewer performance

Measured by \`scripts/perf_report.mjs\` on ${new Date().toISOString().slice(0, 10)} (\`cd portal && ./e2e/run.sh ../scripts/perf_report.mjs\`).

**All browser numbers are software GL** (headless Chromium + SwiftShader on a CPU-only VM, 1440 × 900). A laptop GPU is
many times faster; read fps here as a floor and as a comparison between models, not as what a user sees.

| Model | Elements | Triangles | Web size | Conversion | First frame | fps orbiting | Draw calls | Peak JS heap |
|---|---|---|---|---|---|---|---|---|
${lines.join('\n')}

- **Conversion**: engine time to read the file and write Meshopt tiles (\`summary.seconds.total\` of the model status),
  measured once when the file is first converted; later openings reuse the tiles (same bytes → same id).
- **First frame**: from opening the model in the Studio to the first frame with triangles (\`stats.firstFrame\`),
  including the conversion when it was not cached.
- **fps orbiting**: frames rendered during a 5 s orbit of a quarter turn around the view target.
- **Draw calls**: per frame at the whole-model view: each loaded tile is drawn twice (colour pass and the element-id pass the edges are found from), plus overlay passes.
- **Peak JS heap**: \`performance.memory.usedJSHeapSize\` (Chromium); GPU memory is not measurable from the page.
- Open sample: buildingSMART Sample-Test-Files, IFC4 \`Simple-Scene/Infra-Landscaping.ifc\` (2.3 MB, the largest
  geometry sample in that repo). The repo states no licence, so the file is downloaded by the script and not committed.
  No larger open-licence ship IFC was available offline.
`;
fs.writeFileSync(path.join(ROOT, 'docs/PERFORMANCE.md'), md);
console.log(md);
