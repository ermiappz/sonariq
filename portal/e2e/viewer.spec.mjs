// Step 2: Studio opens a model through the pipeline, shows it, paints findings, focuses one, and a pick returns the
// engine's element. Then the whole RCRV (skipped when the engine does not have it).
import { browser, check, shot, done, BASE, openModel } from './lib.mjs';

const { b, page, errors } = await browser();
const ready = () => page.waitForFunction(() => window.__sqViewer?.stats.overviewMs != null && window.__sqViewer.stats.firstFrame != null, null, { timeout: 300000 });

// pick each element on its own: isolate it, face it, read the id under the screen centre
const pickIds = (ids) => page.evaluate(async (ids) => {
  const v = window.__sqViewer, out = [];
  const THREE = v.modelBox.constructor;           // no import: reuse three through the viewer's own objects
  for (const id of ids) {
    const [i] = v.indices([id]);
    if (i === undefined) { out.push({ id, got: null, why: 'not in tiles' }); continue; }
    const m = await fetch(`/api/models/${window.__sqModelId}/elements/${i}`).then((r) => r.json());
    await v.loadElements([i]);
    v.isolate([i], 'hide');
    const box = new THREE(); box.min.set(...m.bbox.slice(0, 3)); box.max.set(...m.bbox.slice(3));
    v.fit(box, v.camera.position.clone().sub(v.controls.target).normalize(), 0.5);
    await new Promise((r) => setTimeout(r, 50));
    const w = v.host.clientWidth / 2, h = v.host.clientHeight / 2;
    let got = null;
    for (const [dx, dy] of [[0, 0], [8, 0], [-8, 0], [0, 8], [0, -8], [20, 20], [-20, -20]]) { got = v.pick(w + dx, h + dy); if (got !== null) break; }
    out.push({ id, got: got === null ? null : v.elements[got][0] });
  }
  v.showAll();
  return out;
}, ids);

await page.goto(BASE + '#model');
await openModel(page, 'Deck 5', 'Rev B');
let t0 = Date.now();
await ready();
const s1 = await page.evaluate(() => ({ ...window.__sqViewer.stats, elements: window.__sqViewer.index.elements, calls: window.__sqViewer.renderer.info.render.calls }));
check('deck5_revB opens through the pipeline', s1.elements === 258, `${s1.elements} elements, first frame ${Math.round(s1.firstFrame)} ms, wall ${Date.now() - t0} ms`);
await shot(page, 'm2-01-deck5-open.png');

await page.getByRole('button', { name: 'Analyse' }).click();
await page.getByText('F-07').first().waitFor({ timeout: 60000 });
await page.waitForTimeout(800);
await shot(page, 'm2-02-deck5-analysed.png');
await page.getByText('F-07').first().click();
await page.waitForTimeout(1500);
const labels = await page.locator('.studio-dim').allTextContents();
check('F-07 focus draws the engine numbers', labels.some((l) => l.includes('1,350 mm')) && labels.some((l) => l.includes('1,380 mm')), labels.join(' | '));
await shot(page, 'm2-03-f07-focus.png');

// ID mapping in the browser: every finding element of Rev B picks back to its own GlobalId
await page.evaluate(() => { window.__sqModelId = null; });
const mid = await page.evaluate(async () => (await fetch('/api/models/prepare', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revision: 'B' }) }).then((r) => r.json())).id);
await page.evaluate((m) => { window.__sqModelId = m; }, mid);
const guids = await page.evaluate(async () => {
  const runs = await fetch('/api/runs').then((r) => r.json());
  const run = await fetch(`/api/runs/${runs.runs[0].id}`).then((r) => r.json());
  return [...new Set(run.run.findings.map((f) => f.element?.guid).filter(Boolean))];
});
const own = await page.evaluate((gs) => gs.filter((g) => window.__sqViewer.byId.has(g)), guids);  // stairs/zones resolve to parts
const picks = await pickIds(own);
check('deck5_revB: finding elements pick back to their GlobalId', picks.every((p) => p.got === p.id), `${picks.filter((p) => p.got === p.id).length}/${picks.length}`);

// click on screen selects and opens the properties card
await page.getByRole('button', { name: 'Reset view' }).click();
await page.waitForTimeout(600);
const box = await page.locator('.studio-3d canvas').boundingBox();
await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.5);
await page.waitForTimeout(800);
const card = await page.locator('.ship-props').count();
check('click selects an element and opens its properties', card === 1);
if (card) await shot(page, 'm2-04-properties.png');

// whole RCRV
const has = await page.evaluate(async () => (await fetch('/api/models/rcrv')).ok);
if (has) {
  await openModel(page, 'RCRV whole ship');
  t0 = Date.now();
  await page.waitForFunction(() => window.__sqViewer?.index?.elements > 90000, null, { timeout: 300000 });
  await ready();
  const s2 = await page.evaluate(() => ({ ...window.__sqViewer.stats, calls: window.__sqViewer.renderer.info.render.calls, tris: window.__sqViewer.renderer.info.render.triangles,
    heapMB: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : null }));
  check('RCRV whole ship first frame < 10 s (software GL)', s2.firstFrame < 10000, `first frame ${Math.round(s2.firstFrame)} ms, overview ${Math.round(s2.overviewMs)} ms, ${s2.calls} draw calls, ${(s2.tris / 1e6).toFixed(1)} M tris, heap ${s2.heapMB} MB`);
  await shot(page, 'm2-05-rcrv-whole.png');
  await page.evaluate(() => { window.__sqModelId = 'rcrv'; });
  const sample = await page.evaluate(() => { const v = window.__sqViewer, out = []; for (let k = 0; k < 12; k++) out.push(v.elements[Math.floor((k + 0.5) * v.elements.length / 12)][0]); return out; });
  const rp = await pickIds(sample);
  check('RCRV: sampled elements pick back to their GlobalId', rp.filter((p) => p.got === p.id).length >= 10, `${rp.filter((p) => p.got === p.id).length}/${rp.length} ${JSON.stringify(rp.filter((p) => p.got !== p.id))}`);
  await page.getByRole('button', { name: 'Iso', exact: true }).click();
  await page.selectOption('.ship-deck select', '3');
  await page.waitForTimeout(1500);
  const drawn = await page.evaluate(() => { const v = window.__sqViewer, m = v.mode; v.setMode('shaded'); v.render(); const t = v.renderer.info.render.triangles; v.setMode(m); return t; });   // edge pass off: its 2-triangle quad would reset the counter
  check('deck selector cuts above deck 3 and still draws the decks below', drawn > 100000, `${drawn} triangles drawn`);
  await shot(page, 'm2-06-rcrv-deck3.png');
}
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await b.close();
done();
