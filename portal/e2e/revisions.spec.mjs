// Step 7: model revisions (B11). Export saves Rev A, a new analysis opens the next draft, export saves Rev B, the
// timeline shows both, compare counts new / resolved / still open, a saved revision opens read-only, and an upload
// can be filed as a new revision of a model.
import path from 'node:path';
import { browser, check, shot, done, BASE } from './lib.mjs';

const { b, page, errors } = await browser();
await page.goto(BASE + '#model');
await page.waitForLoadState('networkidle');
const sum = page.locator('.studio-sum');

async function analyse(file, rev) {
  if (!(await page.getByRole('button', { name: new RegExp(file) }).isVisible())) await page.getByRole('button', { name: 'Open model', exact: true }).click();
  await page.getByRole('button', { name: new RegExp(file) }).click();
  await page.getByRole('button', { name: 'Analyse' }).click();
  await sum.filter({ hasText: `Rev ${rev} ·` }).waitFor({ timeout: 120000 });
}
async function exportAs(fmt) {
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 120000 }), sum.getByRole('button', { name: fmt, exact: true }).click()]);
  const msg = page.locator('.sq-banner', { hasText: `${fmt} exported` });
  await msg.waitFor({ timeout: 60000 });
  return { file: dl.suggestedFilename(), msg: await msg.innerText() };
}

await analyse('deck5_revA\\.ifc', 'A');
const e1 = await exportAs('BCF');
check('Export (BCF) saves the analysis as Rev A', /saved as Rev A/.test(e1.msg) && e1.file.endsWith('.bcfzip'), `${e1.file} · ${e1.msg}`);
await analyse('deck5_revB\\.ifc', 'B');
const e2 = await exportAs('CSV');
check('a new analysis after the export is saved as Rev B', /saved as Rev B/.test(e2.msg) && e2.file.endsWith('.csv'), e2.msg);

await page.getByRole('tab', { name: 'Revisions' }).click();
const tl = page.getByRole('region', { name: 'Revisions of Deck 5 demo' });
await tl.waitFor();
const rows = await tl.locator('.rtl-row').evaluateAll((els) => els.map((e) => [e.getAttribute('data-rev'), /Saved \d/.test(e.textContent)]));
check('timeline shows two saved revisions', JSON.stringify(rows) === JSON.stringify([['Rev A', true], ['Rev B', true]]), JSON.stringify(rows));
const counts = await tl.locator('.rtl-counts').allInnerTexts();
check('timeline counts per revision', counts[0].startsWith('1 fail') && counts[1].startsWith('4 fail'), counts.join(' | '));

await page.getByLabel('Compare Rev A').check();
await page.getByLabel('Compare Rev B').check();
const cmp = page.getByRole('region', { name: 'Compare revisions' });
await cmp.waitFor({ timeout: 30000 });
const ct = (await cmp.innerText()).replace(/\s+/g, ' ');
check('compare Rev A → Rev B: 3 new, 0 resolved, 3 still open', /New 3 findings/i.test(ct) && /Resolved 0 findings/i.test(ct) && /Still open 3 by element ID/i.test(ct), ct.slice(0, 140));
check('compare lists the new findings', ['F-07', 'F-08', 'F-09'].every((f) => ct.includes(f)));
await shot(page, 'm7-01-timeline-compare.png');

await tl.getByRole('button', { name: 'Rev B', exact: true }).click();
await page.getByLabel('Revision label').fill('Rev B · OR-117');
await page.keyboard.press('Enter');
await tl.locator('[data-rev="Rev B · OR-117"]').waitFor({ timeout: 10000 });
check('label is editable', true);
const [bundle] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download Rev A bundle' }).click()]);
check('bundle downloads', bundle.suggestedFilename() === 'sonariq_Rev_A_bundle.zip', bundle.suggestedFilename());

await page.getByRole('button', { name: 'Open Rev A read-only' }).click();
await page.locator('.studio-past').waitFor();
const ro = { analyse: await page.getByRole('button', { name: 'Analyse' }).count(), fail: await page.locator('.studio-chips .ib-chip').first().innerText() };
await page.getByText('F-01').first().click();
ro.inc = await page.getByRole('button', { name: 'Incorrect finding' }).count();
check('a saved revision opens read-only', ro.analyse === 0 && ro.inc === 0 && /^1\s*Fail/.test(ro.fail), JSON.stringify(ro));
await shot(page, 'm7-02-rev-a-read-only.png');
await page.getByRole('button', { name: 'Back to current' }).first().click();

// upload dialog: file a new file as the next revision of the model
await page.getByRole('button', { name: 'Open model', exact: true }).click();
await page.locator('input[type=file]').setInputFiles(path.resolve(new URL('../../data/deck5_revB_fix2.ifc', import.meta.url).pathname));
const pick = page.getByLabel('Save as');
await pick.locator('option', { hasText: 'New revision of Deck 5 demo' }).waitFor({ state: 'attached' });   // the model list loads after the upload
const opts = await pick.locator('option').allInnerTexts();
check('upload offers New model or New revision of <model>', opts[0] === 'New model' && opts.includes('New revision of Deck 5 demo'), opts.join(' | '));
await pick.selectOption({ label: 'New revision of Deck 5 demo' });
await page.getByRole('button', { name: 'Analyse' }).click();
await sum.filter({ hasText: 'Rev Bfix2 ·' }).waitFor({ timeout: 120000 });
await page.getByRole('tab', { name: 'Revisions' }).click();
await tl.locator('[data-rev="Rev C"]').waitFor({ timeout: 10000 });
check('the upload opens draft Rev C of the same model', /Draft/.test(await tl.locator('[data-rev="Rev C"]').innerText()));
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await b.close();
done();
