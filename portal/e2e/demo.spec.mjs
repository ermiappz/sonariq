// Step 9.1: demo run-through. Plays by itself, → / Space step, Esc stops; every step does its real action:
// readiness → 3D → analyse + accuracy banner → F-07 callout → section at finding → x-ray solo → compare → BCF.
import { browser, check, shot, done, BASE } from './lib.mjs';

const { b, page, errors } = await browser();
await page.goto(BASE + '#model');
await page.waitForLoadState('networkidle');
const bar = page.getByRole('region', { name: 'Demo run-through' });
const at = async (n) => { await bar.filter({ hasText: `step ${n} of 8` }).waitFor({ timeout: 600000 });
  await page.waitForFunction(() => !/working…/.test(document.querySelector('.demo-bar')?.textContent ?? ''), null, { timeout: 600000 }); };
const next = (n) => page.keyboard.press(n % 2 ? 'ArrowRight' : 'Space');
const v = (f) => page.evaluate(f);

await page.getByRole('button', { name: 'Demo run-through' }).click();
await at(1);
const rd = await page.locator('.studio-setup').getByText('Spaces').first().waitFor({ timeout: 60000 }).then(() => true, () => false);
check('1 readiness card for deck5_revB', rd);
await shot(page, 'm9-01-demo-readiness.png');
// plays by itself: step 2 starts without a key press
await at(2);
check('advances by itself', true);
check('2 the model is in the 3D', await v(() => window.__sqViewer?.stats.firstFrame != null));
await next(2); await at(3);
const s3 = { banner: await page.locator('.acc-banner').isVisible(), f07: await page.getByText('F-07').count() };
check('3 analysed, accuracy banner shown', s3.banner && s3.f07 > 0, `${JSON.stringify(s3)} ${(await page.locator('.acc-banner').innerText()).slice(0, 60)}`);
await shot(page, 'm9-03-demo-banner.png');
await next(3); await at(4);
check('4 F-07 callout', /F-07/.test(await page.locator('.co-card').innerText()));
await shot(page, 'm9-04-demo-callout.png');
await next(4); await at(5);
await page.waitForFunction(() => !window.__sqViewer.anim, null, { timeout: 120000 });
check('5 section at the finding', await v(() => window.__sqViewer.cuts.length) === 1 && await page.locator('.co-card').isVisible());
await shot(page, 'm9-05-demo-section.png');
await next(5); await at(6);
const s6 = await v(() => ({ mode: window.__sqViewer.mode, solo: window.__sqViewer.index.groups[window.__sqViewer.solo], cuts: window.__sqViewer.cuts.length }));
check('6 x-ray with one system solo, cut cleared', s6.mode === 'xray' && s6.solo === 'hvac' && s6.cuts === 0, JSON.stringify(s6));
await page.waitForTimeout(1500);
await shot(page, 'm9-06-demo-xray-solo.png');
await next(6); await at(7);
const cmp = page.getByRole('region', { name: 'Compare revisions' });
await cmp.waitFor({ timeout: 30000 });
const ct = (await cmp.innerText()).replace(/\s+/g, ' ');
check('7 timeline compares Rev A with this Rev B analysis: 3 new', /New 3 findings/i.test(ct) && ['F-07', 'F-08', 'F-09'].every((f) => ct.includes(f)), ct.slice(0, 120));
await shot(page, 'm9-07-demo-compare.png');
const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 120000 }), next(7)]);
await at(8);
check('8 BCF export downloads and saves', dl.suggestedFilename().endsWith('.bcfzip') && await page.locator('.sq-banner', { hasText: 'BCF exported' }).isVisible(), dl.suggestedFilename());
await shot(page, 'm9-08-demo-bcf.png');
await page.keyboard.press('ArrowRight');
check('→ on the last step finishes', await bar.count() === 0);
// Esc stops mid-way
await page.getByRole('button', { name: 'Demo run-through' }).click();
await at(1);
await page.keyboard.press('Escape');
check('Esc stops the demo', await bar.count() === 0);
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await b.close();
done();
