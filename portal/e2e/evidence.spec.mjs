// Step 3: readiness before analysis, accuracy banner computed, source chips on values, RCRV structure & systems run.
import { browser, check, shot, done, BASE } from './lib.mjs';

const { b, page, errors } = await browser();
await page.goto(BASE + '#model');
await page.getByRole('button', { name: /deck5_revB\.ifc/ }).click();
await page.locator('.ready-card').waitFor({ timeout: 60000 });
const rd = await page.locator('.ready-card').innerText();
check('readiness card before analysis (Rev B)', /Spaces/.test(rd) && /Ready/.test(rd) && /Partial/.test(rd), rd.replace(/\s+/g, ' ').slice(0, 160));
await shot(page, 'm3-01-readiness-revB.png');
await page.getByRole('button', { name: 'Analyse' }).click();
await page.locator('.acc-banner.is-ok').waitFor({ timeout: 120000 });
const ban = await page.locator('.acc-banner').innerText();
check('accuracy banner computed for Rev B', /6\/6 hand-checked findings found · 0 false alarms · 3\/3 expected passes · counts match independent scan/.test(ban), ban);
await page.getByText('F-07').first().click();
const chips = await page.locator('.studio-card.is-on .src-chip').allTextContents();
check('F-07 values carry source chips', chips.some((c) => c.startsWith('Is · model')) && chips.some((c) => c.startsWith('Must be · derived')), chips.join(' | '));
await page.locator('.studio-card.is-on .src-chip').nth(1).click();
await page.waitForTimeout(400);
await shot(page, 'm3-02-banner-chips.png');

const has = await page.evaluate(async () => (await fetch('/api/models/rcrv')).ok);
if (has) {
  await page.getByRole('button', { name: 'Open model', exact: true }).click();
  await page.getByRole('button', { name: /RCRV whole ship/ }).click();
  await page.locator('.ready-card').waitFor({ timeout: 120000 });
  const r2 = await page.locator('.ready-card').innerText();
  check('RCRV readiness: fire not possible (no spaces), structure & systems partial', /Not possible[\s\S]*No spaces/.test(r2) && /Partial[\s\S]*pipe parts without a material/.test(r2));
  await shot(page, 'm3-03-readiness-rcrv.png');
  const t0 = Date.now();
  await page.getByRole('button', { name: 'Analyse' }).click();
  await page.locator('.acc-banner.is-ok, .acc-banner.is-off').waitFor({ timeout: 300000 });
  const b2 = await page.locator('.acc-banner').innerText();
  check('RCRV structure & systems: banner computed', /96\/96 hand-checked findings found · 0 false alarms · 3\/3 expected passes · counts match independent scan \(5 rules\)/.test(b2), `${b2} · ${Date.now() - t0} ms`);
  const nr = await page.locator('.not-run summary').innerText().catch(() => '');
  check('rules that cannot run are listed as Cannot verify', /not run on this model/.test(nr), nr);
  await shot(page, 'm3-04-rcrv-analysed.png');
}
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await b.close();
done();
