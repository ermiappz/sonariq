// Step 4: findings grouped by rule with counts, filters, a virtualised list on the whole ship, traceability matrix,
// printable report and CSV.
import { browser, check, shot, done, BASE, openModel } from './lib.mjs';

const { b, page, errors } = await browser();
await page.goto(BASE + '#model');
await openModel(page, 'Deck 5', 'Rev B');
await page.getByRole('button', { name: 'Analyse' }).click();
await page.locator('.fl-head').first().waitFor({ timeout: 120000 });
// the virtualised list renders the rows that fit; wait until it has its full height
await page.waitForFunction(() => document.querySelectorAll('.fl-head').length >= 5, null, { timeout: 15000 }).catch(() => {});
const heads = await page.locator('.fl-head').allTextContents();
check('Rev B findings grouped by rule, fails first, with counts', /Fire door class[\s\S]*part/.test(heads[0]) && heads.length >= 5, heads.slice(0, 3).join(' | '));
await page.getByText('F-07').first().click();
check('selected finding shows its full card', await page.locator('.fl-detail .studio-card').count() === 1);
await shot(page, 'm4-01-grouped-revB.png');
await page.getByRole('tab', { name: 'Traceability' }).click();
await page.waitForTimeout(600);
await shot(page, 'm4-02-matrix-revB.png');

const rid = await page.evaluate(async () => (await fetch('/api/runs').then((r) => r.json())).runs[0].id);
const csv = await page.evaluate(async (id) => (await fetch(`/api/runs/${id}/csv`)).text(), rid);
check('CSV has one row per check', csv.trim().split('\n').length === 97, `${csv.trim().split('\n').length - 1} rows`);
const rp = await b.contexts()[0].newPage();
await rp.goto(BASE + '#print/' + rid);
await rp.locator('.pr-table').first().waitFor({ timeout: 60000 });
const rtext = await rp.locator('.pr').innerText();
check('printable report has readiness, per-rule counts and findings with sources', /Data readiness/.test(rtext) && /Checks per rule/.test(rtext) && /F-07[\s\S]*Is model/.test(rtext));
await rp.screenshot({ path: new URL('../../docs/screenshots/m4-03-report.png', import.meta.url).pathname, fullPage: false });
await rp.close();

const has = await page.evaluate(async () => (await fetch('/api/models/rcrv')).ok);
if (has) {
  await page.getByRole('tab', { name: 'List' }).click();
  await openModel(page, 'RCRV whole ship');
  await page.getByRole('button', { name: 'Analyse' }).click();
  await page.waitForFunction(() => document.querySelector('.studio-sum') && document.querySelector('.studio-file')?.textContent?.includes('RCRV'), null, { timeout: 300000 });
  await page.locator('.fl-head').first().waitFor({ timeout: 60000 });
  // collapse one at a time: the list is virtualised, so a snapshot of handles goes stale after the first click
  for (let i = 0; i < 20 && await page.locator('.fl-head[aria-expanded="true"]').count(); i++) await page.locator('.fl-head[aria-expanded="true"]').first().click();
  const h2 = await page.locator('.fl-head').allTextContents();
  check('RCRV: per-rule counts over the whole ship', h2.some((h) => /R-SYS-01[\s\S]*2,391 parts: 41 warning, 232 cannot verify, 2,118 pass/.test(h)), h2.join(' | ').slice(0, 300));
  await page.locator('.ib-chip', { hasText: 'Pass' }).click();
  await page.waitForTimeout(800);
  await page.locator('.fl-head', { hasText: 'R-DQ-02' }).click();          // open a 9,672-row group
  await page.waitForTimeout(400);
  const dom = await page.locator('.fl-row').count();
  const shown = await page.locator('.fl-count').innerText();
  check('36,481 passes listed, a 9,672-row group open, only a screenful of rows in the DOM', /36,481 shown/.test(shown) && dom > 5 && dom < 80, `${shown}, ${dom} rows in DOM`);
  await page.locator('.fl-list').evaluate((el) => { el.scrollTop = 200000; });
  await page.waitForTimeout(500);
  check('scrolling deep into the list still renders rows', await page.locator('.fl-row').count() > 5);
  await page.locator('.ib-chip', { hasText: 'Pass' }).click();
  await page.selectOption('select[aria-label="Rule source"]', 'Data quality');
  await page.waitForTimeout(400);
  const dq = await page.locator('.fl-count').innerText();
  check('source filter (Data quality)', /48 shown/.test(dq), dq);
  await shot(page, 'm4-04-rcrv-filtered.png');
  await page.selectOption('select[aria-label="Rule source"]', '');
  await page.getByRole('tab', { name: 'Traceability' }).click();
  await page.waitForTimeout(1500);
  const leg = await page.locator('.tm-legend').innerText();
  check('RCRV traceability matrix', /parts × 5 rules/.test(leg), leg.slice(0, 80));
  await shot(page, 'm4-05-rcrv-matrix.png');
}
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await b.close();
done();
