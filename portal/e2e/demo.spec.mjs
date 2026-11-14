// Studio reliability step 4: the demo cannot get stuck. Full run in Chromium (software GL): its own throwaway project,
// non-blank 3D at step 2, the expected element at every step, Next works while a step is still working, Stop restores
// the previous project / revision / tab / display mode and deletes the demo project. Screenshots: docs/screenshots/demo/.
import { browser, check, shot, done, BASE, openModel, canvasColours } from './lib.mjs';

const { b, page, errors } = await browser();
await page.goto(BASE + '#model');
await page.waitForLoadState('networkidle');
const bar = page.getByRole('region', { name: 'Demo run-through' });
const at = async (n, ms = 90000) => {
  await bar.filter({ hasText: `step ${n} of 8` }).waitFor({ timeout: ms });
  await page.waitForFunction(() => !/working…/.test(document.querySelector('.demo-bar')?.textContent ?? ''), null, { timeout: ms });
  const err = await bar.locator('.demo-err').count();
  if (err) console.log('step error:', await bar.locator('.demo-err').innerText());
  return err === 0;
};
const next = () => page.keyboard.press('ArrowRight');
const v = (f) => page.evaluate(f);
const projects = () => v(async () => (await (await fetch('/api/projects')).json()).projects.map((p) => p.name));

// before: the user has Deck 5 Fix 2 open in the View tab, x-ray mode
await openModel(page, 'Deck 5', 'Fix 2');
await page.waitForFunction(() => window.__sqViewer?.stats.firstFrame != null, null, { timeout: 300000 });
await page.getByRole('tab', { name: 'View' }).click();
await page.getByRole('radio', { name: 'X-ray', exact: true }).click();
const before = { file: await page.locator('.studio-file').innerText(), mode: await v(() => window.__sqViewer.mode) };

await page.getByRole('button', { name: 'Demo run-through' }).click();
check('1 readiness card in the demo copy of Deck 5', await at(1) && await page.locator('.studio-setup .ready-card').isVisible()
  && /Demo run-through/.test(await page.locator('select[aria-label="Project"] option:checked').innerText()));
await shot(page, 'demo/01-readiness.png');
check('2 plays by itself; the 3D has a non-blank picture', await at(2));
await page.waitForTimeout(1500);
const colours = await canvasColours(page);
check('2 canvas has non-blank pixels', colours > 8, `${colours} distinct colours`);
await shot(page, 'demo/02-3d.png');
await next(); check('3 analysed, accuracy banner shown', await at(3) && await page.locator('.acc-banner').isVisible() && await page.getByText('F-07').count() > 0);
await shot(page, 'demo/03-banner.png');
await next(); check('4 F-07 callout', await at(4) && /F-07/.test(await page.locator('.co-card').innerText()));
await shot(page, 'demo/04-callout.png');
await next(); check('5 section at the finding', await at(5) && await v(() => window.__sqViewer.cuts.length) === 1);
await shot(page, 'demo/05-section.png');
await next(); await at(6);
const s6 = await v(() => ({ mode: window.__sqViewer.mode, solo: window.__sqViewer.index.groups[window.__sqViewer.solo], cuts: window.__sqViewer.cuts.length }));
check('6 x-ray with one system solo, cut cleared', s6.mode === 'xray' && s6.solo === 'hvac' && s6.cuts === 0, JSON.stringify(s6));
await shot(page, 'demo/06-xray-solo.png');
await next(); check('7 compare Rev A → Rev B: 3 new', await at(7) && /New 3 findings/i.test((await page.getByRole('region', { name: 'Compare revisions' }).innerText()).replace(/\s+/g, ' ')));
await shot(page, 'demo/07-compare.png');
const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }), next()]);
check('8 BCF export downloads', await at(8) && dl.suggestedFilename().endsWith('.bcfzip'), dl.suggestedFilename());
await shot(page, 'demo/08-bcf.png');
await next();
check('→ on the last step finishes', await bar.count() === 0);
await page.locator('.studio-file', { hasText: 'Fix 2' }).waitFor({ timeout: 30000 });
await page.waitForFunction((m) => window.__sqViewer?.mode === m, before.mode, { timeout: 60000 }).catch(() => {});
const after = { file: await page.locator('.studio-file').innerText(), mode: await v(() => window.__sqViewer?.mode), tab: await page.getByRole('tab', { name: 'View' }).getAttribute('aria-selected') };
check('finish restores project, revision, tab and display mode', after.file === before.file && after.mode === before.mode && after.tab === 'true', JSON.stringify({ before, after }));
await page.waitForTimeout(500);
check('the demo project is deleted; the user\'s project has no demo revisions', !(await projects()).some((n) => /Demo run-through/.test(n))
  && await v(async () => { const p = (await (await fetch('/api/projects')).json()).projects[0]; return p.models[0].revisions.every((r) => r.run_id === null); }));

// Next and Stop respond while a step is still working
await page.getByRole('button', { name: 'Demo run-through' }).click();
await bar.filter({ hasText: 'step 1 of 8' }).waitFor({ timeout: 30000 });
await next();
check('Next responds while a step is working', await bar.filter({ hasText: 'step 2 of 8' }).waitFor({ timeout: 5000 }).then(() => true, () => false));
await page.keyboard.press('Escape');
check('Esc stops at once', await bar.count() === 0);
await page.locator('.studio-file', { hasText: 'Fix 2' }).waitFor({ timeout: 30000 });
check('Stop restores the previous revision', true);

// a step that fails says why, with Retry and Skip step (here the 3D version is not prepared on the server)
await page.route('**/api/models/prepare', (r) => r.fulfill({ status: 200, contentType: 'application/json',
  body: JSON.stringify({ id: 'x', state: 'not-prepared', message: "This model's 3D version is not prepared on the server yet." }) }));
await page.getByRole('button', { name: 'Demo run-through' }).click();
await bar.filter({ hasText: 'step 2 of 8' }).waitFor({ timeout: 60000 });
const errBox = bar.locator('.demo-err');
await errBox.waitFor({ timeout: 70000 });
const et = await errBox.innerText();
check('a failed step shows the reason with Retry and Skip step', /Couldn't load the 3D model: .*not prepared/.test(et) && /Retry/.test(et) && /Skip step/.test(et), et.replace(/\n/g, ' '));
await shot(page, 'demo/09-step-error.png');
await errBox.getByRole('button', { name: 'Retry' }).click();
await errBox.waitFor({ timeout: 70000 });
await page.unroute('**/api/models/prepare');
await errBox.getByRole('button', { name: 'Skip step' }).click();
check('Skip step moves on', await bar.filter({ hasText: 'step 3 of 8' }).waitFor({ timeout: 5000 }).then(() => true, () => false));
await bar.getByRole('button', { name: 'Stop demo (Esc)' }).click();
check('Stop button stops', await bar.count() === 0);
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await b.close();
done();
