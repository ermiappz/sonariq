// Live smoke (Studio reliability step 6) against the deployed site, in real Chromium with software GL:
//   E2E_BASE=https://34-88-130-224.sslip.io/ E2E_RESOLVE="MAP 34-88-130-224.sslip.io <NIC ip>" node e2e/live/smoke.mjs
// /health converter ok · RCRV whole ship first frame < 10 s with a non-blank canvas · the demo completes all 8 steps ·
// a fresh browser gets the first-run guide. Screenshots: docs/screenshots/live/. Writes nothing into the shared
// project (the demo uses its own throwaway project and deletes it).
import { browser, check, shot, done, BASE, openModel, canvasColours } from '../lib.mjs';

// 1. fresh browser: / → /studio, the guide, and the engine's health as the portal reads it
const g = await browser({ guide: true });
const health = g.page.waitForResponse((r) => r.url().includes('/api/health'), { timeout: 60000 });
await g.page.goto(BASE);
const h = await (await health).json();
check('/health: converter ok', h.converter?.state === 'ok', JSON.stringify(h.converter));
check('/ lands in /studio', new URL(g.page.url()).pathname.endsWith('/studio'), g.page.url());
check('first-run guide appears in a fresh browser', await g.page.locator('.guide-card').waitFor({ timeout: 30000 }).then(() => true, () => false));
await shot(g.page, 'live/01-first-run-guide.png');
await g.b.close();

// 2. RCRV whole ship: pre-converted, first frame < 10 s, non-blank
const { b, page, errors } = await browser();
await page.goto(BASE + 'studio#model');
await page.waitForLoadState('networkidle');
const t0 = Date.now();
await openModel(page, 'RCRV whole ship');
await page.waitForFunction(() => window.__sqViewer?.stats.firstFrame != null, null, { timeout: 120000 });
const wall = Date.now() - t0;
const prep = await page.locator('.ship-progress').count();
check('RCRV whole ship: first frame < 10 s (from the click, software GL)', wall < 10000, `${wall} ms`);
await page.waitForTimeout(3000);
const colours = await canvasColours(page);
check('RCRV canvas has non-blank pixels', colours > 8, `${colours} distinct colours`);
check('no 3D error card', (await page.locator('.ship-error').count()) === 0 && prep === 0);
await shot(page, 'live/02-rcrv-whole-ship.png');

// 3. the demo, all 8 steps (Next as soon as each step is done)
const bar = page.getByRole('region', { name: 'Demo run-through' });
await page.getByRole('button', { name: 'Demo run-through' }).click();
let ok = true;
for (let n = 1; n <= 8; n++) {
  await bar.filter({ hasText: `step ${n} of 8` }).waitFor({ timeout: 90000 });
  await page.waitForFunction(() => !/working…/.test(document.querySelector('.demo-bar')?.textContent ?? ''), null, { timeout: 90000 });
  const err = await bar.locator('.demo-err').count() ? await bar.locator('.demo-err').innerText() : '';
  check(`demo step ${n} completes`, !err, err.replace(/\n/g, ' '));
  ok &&= !err;
  if (n === 2) check('demo step 2: canvas non-blank', (await canvasColours(page)) > 8);
  await shot(page, `live/demo-${n}.png`);
  if (n === 8) break;
  await page.keyboard.press('ArrowRight');
}
await page.keyboard.press('ArrowRight');
check('demo finishes and the bar closes', await bar.count() === 0);
await page.locator('.studio-file', { hasText: 'RCRV' }).waitFor({ timeout: 60000 }).catch(() => {});
check('finish returns to the RCRV whole ship', /RCRV/.test(await page.locator('.studio-file').innerText()));
await page.waitForTimeout(1000);
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await b.close();
done();
