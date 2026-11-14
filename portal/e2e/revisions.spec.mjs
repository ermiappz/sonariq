// Step 7 + Studio reliability: model revisions in a project. Deck 5 has Rev A, Rev B and Fix 2 (seeded). Analyse fills
// a revision's draft, Export saves it; the timeline shows the open model's revisions, compare counts new / resolved /
// still open, a saved revision opens read-only, and an upload is filed as a new revision of a model.
import path from 'node:path';
import { browser, check, shot, done, BASE, openModel } from './lib.mjs';

const { b, page, errors } = await browser();
await page.goto(BASE + '#model');
await page.waitForLoadState('networkidle');
const sum = page.locator('.studio-sum');

async function analyse(rev) {
  await openModel(page, 'Deck 5', rev);
  await page.getByRole('button', { name: 'Analyse' }).click();
  await sum.filter({ hasText: `${rev} ·` }).waitFor({ timeout: 120000 });
}
async function exportAs(fmt) {
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 120000 }), sum.getByRole('button', { name: fmt, exact: true }).click()]);
  const msg = page.locator('.sq-banner', { hasText: `${fmt} exported` });
  await msg.waitFor({ timeout: 60000 });
  return { file: dl.suggestedFilename(), msg: await msg.innerText() };
}

await analyse('Rev A');
const e1 = await exportAs('BCF');
check('Export (BCF) saves Rev A', /Rev A is saved/.test(e1.msg) && e1.file.endsWith('.bcfzip'), `${e1.file} · ${e1.msg}`);
await analyse('Rev B');
const e2 = await exportAs('CSV');
check('Export (CSV) saves Rev B', /Rev B is saved/.test(e2.msg) && e2.file.endsWith('.csv'), e2.msg);

await page.getByRole('tab', { name: 'Revisions' }).click();
const tl = page.getByRole('region', { name: 'Revisions of Deck 5' });
await tl.waitFor();
await page.waitForFunction(() => document.querySelectorAll('.rtl-row').length === 3 && /Saved \d/.test(document.querySelectorAll('.rtl-row')[1].textContent), null, { timeout: 10000 });
const rows = await tl.locator('.rtl-row').evaluateAll((els) => els.map((e) => [e.getAttribute('data-rev'), /Saved \d/.test(e.textContent)]));
check('timeline: Rev A and Rev B saved, Fix 2 not yet', JSON.stringify(rows) === JSON.stringify([['Rev A', true], ['Rev B', true], ['Fix 2', false]]), JSON.stringify(rows));
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
await page.getByRole('tab', { name: 'Findings' }).click();
await page.locator('.studio-past').waitFor();
await page.getByText('F-01').first().click();
const ro = { inc: await page.getByRole('button', { name: 'Incorrect finding' }).count(), fail: await page.locator('.studio-chips .ib-chip').first().innerText() };
check('a saved revision opens read-only', ro.inc === 0 && /^1\s*Fail/.test(ro.fail), JSON.stringify(ro));
await shot(page, 'm7-02-rev-a-read-only.png');

// upload dialog: file a new file as the next revision of the model
await page.getByRole('button', { name: 'Open model', exact: true }).click();
await page.locator('input[type=file]').setInputFiles(path.resolve(new URL('../../data/deck5_revB_fix2.ifc', import.meta.url).pathname));
const dlg = page.getByRole('dialog', { name: 'Add the uploaded model' });
await dlg.waitFor({ timeout: 30000 });
const opts = await dlg.locator('label').allInnerTexts();
check('upload offers New model or New revision of <model>', opts[0].trim() === 'New model in this project' && opts.some((o) => o.includes('New revision of Deck 5')), opts.join(' | '));
await dlg.getByLabel('New revision of Deck 5').check();
await dlg.getByRole('button', { name: 'Add' }).click();
await page.locator('.studio-file', { hasText: 'Deck 5 · Rev D' }).waitFor({ timeout: 10000 });
await page.getByRole('button', { name: 'Analyse' }).click();
await sum.filter({ hasText: 'Rev D ·' }).waitFor({ timeout: 120000 });
check('the upload is Rev D of the same model and analyses as a draft', /not analysed|Rev D/.test(await page.locator('.studio-file').innerText()));
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await b.close();
done();
