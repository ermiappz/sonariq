// Step 5: View pane: six display modes, discipline show/hide/solo, colour by; dark and light themes.
import { browser, check, shot, done, BASE } from './lib.mjs';
import crypto from 'node:crypto';

const MODES = [['shaded', 'Shaded'], ['edges', 'Shaded + edges'], ['realistic', 'Realistic'], ['xray', 'X-ray'], ['lines', 'Lines'], ['wireframe', 'Wireframe']];
const canvasHash = async (page) => crypto.createHash('md5').update(await page.locator('.studio-3d canvas').screenshot({ timeout: 120000 })).digest('hex');
const bgShare = (page) => page.evaluate(() => {      // share of canvas pixels equal to the background (Lines mode check)
  const v = window.__sqViewer; v.render();
  const gl = v.renderer.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight, px = new Uint8Array(w * h * 4);
  gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
  const bg = [px[0], px[1], px[2]]; let n = 0;                  // a corner pixel is background
  for (let i = 0; i < px.length; i += 16) if (Math.abs(px[i] - bg[0]) < 3 && Math.abs(px[i + 1] - bg[1]) < 3 && Math.abs(px[i + 2] - bg[2]) < 3) n++;
  return n / (px.length / 16);
});

for (const theme of ['dark', 'light']) {
  const { b, page, errors } = await browser({ theme });
  await page.goto(BASE + '#model');
  if (theme === 'light') await page.getByRole('button', { name: /theme|◐/i }).first().click().catch(() => {});
  const model = theme === 'dark' ? /RCRV whole ship/ : /deck5_revB\.ifc/;
  const has = theme === 'light' || await page.evaluate(async () => (await fetch('/api/models/rcrv')).ok);
  await page.getByRole('button', { name: has ? model : /deck5_revB\.ifc/ }).click();
  await page.waitForFunction(() => window.__sqViewer?.stats.overviewMs != null, null, { timeout: 300000 });
  await page.getByRole('tab', { name: 'View' }).click();
  const tag = theme === 'dark' && has ? 'rcrv' : 'deck5';
  const hashes = new Set();
  for (const [k, label] of MODES) {
    await page.getByRole('radio', { name: label, exact: true }).click();
    await page.waitForTimeout(700);
    const m = await page.evaluate(() => window.__sqViewer.mode);
    hashes.add(await canvasHash(page));
    if (m !== k) check(`${theme}: mode ${k}`, false, m);
    await shot(page, `m5-${tag}-${theme}-${k}.png`);
  }
  check(`${theme} ${tag}: six display modes draw six different pictures`, hashes.size === 6, `${hashes.size} distinct`);
  await page.getByRole('radio', { name: 'Lines' }).click(); await page.waitForTimeout(500);
  const share = await bgShare(page);
  check(`${theme} ${tag}: Lines mode is mostly background (hidden lines removed)`, share > 0.6, `${Math.round(share * 100)} % background`);
  await page.getByRole('radio', { name: 'Shaded + edges' }).click();
  if (tag === 'rcrv') {
    await page.locator('.vp-disc', { hasText: 'Piping' }).getByRole('button', { name: 'Solo' }).click();
    await page.waitForTimeout(800);
    const solo = await page.evaluate(() => { const v = window.__sqViewer, p = v.index.groups.indexOf('piping'); let s = 0, g = 0;
      for (let i = 0; i < v.index.elements; i++) { const a = v.state[i * 4 + 3]; if (v.disc[i] === p && a === 255) s++; else if (a > 0 && a < 255) g++; } return { s, g }; });
    check('RCRV solo piping: piping solid, the rest x-ray', solo.s > 40000 && solo.g > 30000, JSON.stringify(solo));
    await shot(page, 'm5-rcrv-solo-piping.png');
    await page.locator('.vp-disc', { hasText: 'Piping' }).getByRole('button', { name: 'Unsolo' }).click();
    await page.locator('.vp-disc', { hasText: 'Structure' }).getByRole('checkbox').uncheck();
    await page.waitForTimeout(600);
    const hidden = await page.evaluate(() => { const v = window.__sqViewer, p = v.index.groups.indexOf('structure'); let n = 0; for (let i = 0; i < v.index.elements; i++) if (v.disc[i] === p && v.state[i * 4 + 3] === 0) n++; return n; });
    check('hide Structure', hidden === 23000, `${hidden} structure parts hidden`);
    await page.locator('.vp-disc', { hasText: 'Structure' }).getByRole('checkbox').check();
  } else {
    await page.selectOption('select[aria-label="Colour by"]', 'fire');
    await page.waitForTimeout(1200);
    const leg = await page.locator('.vp-legend').innerText();
    const a60 = await page.evaluate(async () => { const v = window.__sqViewer;
      const col = await fetch(`/api/models/${window.__sqModelId ?? ''}`).then(() => null);
      let n = 0; for (let i = 0; i < v.index.elements; i++) if (v.state[i * 4] === 213 && v.state[i * 4 + 1] === 94 && v.state[i * 4 + 3] > 0) n++; return n; });
    const want = await page.evaluate(async () => { const st = await fetch('/api/models/prepare', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revision: 'B' }) }).then((r) => r.json());
      const col = await fetch(`/api/models/${st.id}/column/fire_rating`).then((r) => r.json()); return col.filter((x) => /^A-?60/i.test(x ?? '')).length; });
    check('colour by fire class (Rev B): every A-60 element in the A-60 colour', /A-60/.test(leg) && a60 === want && want > 0, `${a60} coloured, ${want} rated A-60 in the model`);
    await shot(page, `m5-deck5-${theme}-fireclass.png`);
  }
  check(`${theme}: no page errors`, errors.length === 0, errors.slice(0, 3).join(' | '));
  await b.close();
}
done();
