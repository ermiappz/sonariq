// Studio reliability step 2-3: everything belongs to one project → model → revision. Open Deck 5 Rev B, assign a task
// and mark a finding; switch to RCRV → Inbox and Tasks show nothing from Deck 5; switch back → it is all there;
// Clear all with Save → Studio empty, Rev B saved with the mark in its snapshot.
import { browser, check, shot, done, BASE, openModel } from './lib.mjs';

const { b, page, errors } = await browser();
const rail = (name) => page.locator('nav.rail a', { hasText: name });
const railN = (name) => rail(name).locator('.mono').innerText().catch(() => '');
await page.goto(BASE + '#model');
await page.waitForLoadState('networkidle');
await openModel(page, 'Deck 5', 'Rev B');
await page.getByRole('button', { name: 'Analyse' }).click();
await page.locator('.fl-row', { hasText: 'F-07' }).first().waitFor({ timeout: 120000 });
// mark F-07 incorrect
await page.locator('.fl-row', { hasText: 'F-07' }).first().click();
await page.getByRole('button', { name: 'Incorrect finding' }).click();
await page.getByPlaceholder('Why is this finding wrong?').fill('stair is 1,400 mm in the GA drawing');
await page.getByRole('button', { name: 'Mark incorrect' }).click();
await page.locator('.fl-row.is-incorrect', { hasText: 'F-07' }).waitFor({ timeout: 10000 });
// a task: assign F-08 in the Inbox
await rail('Inbox').click();
const row = page.locator('tr', { hasText: 'F-08' }).first();
await row.locator('input[type=checkbox]').check();
await page.getByRole('button', { name: 'Assign…' }).click();
await page.locator('.board-person', { hasText: 'Mikko Saari' }).click();
await row.locator('.tb-av').waitFor({ timeout: 10000 });
const before = { inbox: await railN('Inbox'), header: await page.locator('h1 + .sq-muted').first().innerText() };
check('Inbox is scoped to Demo ship · Deck 5 · Rev B', /Demo ship · Deck 5 · Rev B/.test(before.header) && Number(before.inbox) > 0, JSON.stringify(before));
await shot(page, 'r2-01-inbox-deck5-revB.png');

// switch to the RCRV: nothing from Deck 5
await rail('Studio').click();
const hasRcrv = await page.getByRole('list', { name: 'Models in this project' }).getByText('RCRV whole ship').count().catch(() => 0)
  || await page.getByRole('button', { name: 'Open model', exact: true }).click().then(() => page.getByRole('list', { name: 'Models in this project' }).getByText('RCRV whole ship').count());
const other = hasRcrv ? 'RCRV whole ship' : 'Deck 5';
if (hasRcrv) await openModel(page, 'RCRV whole ship'); else await openModel(page, 'Deck 5', 'Rev A');
await page.locator('.studio-file', { hasText: other === 'Deck 5' ? 'Rev A' : 'RCRV' }).waitFor({ timeout: 10000 });
await rail('Inbox').click();
const inbox2 = await page.locator('main').innerText();
check(`after switching to ${other}: Inbox shows nothing from Deck 5 Rev B`, !/F-07|F-08/.test(inbox2) && /not been analysed|No model open/.test(inbox2), inbox2.slice(0, 120).replace(/\n/g, ' '));
check('sidebar badges count only the current scope', (await railN('Inbox')) === '' && (await railN('Tasks')) === '');
await rail('Tasks').click();
check('Tasks shows nothing from Deck 5 Rev B', !/F-0[78]|Mikko/.test(await page.locator('main').innerText()));
await shot(page, 'r2-02-tasks-other-model.png');

// switch back with the Revision menu
await rail('Studio').click();
await openModel(page, 'Deck 5', 'Rev B');
await rail('Inbox').click();
await page.locator('tr', { hasText: 'F-08' }).first().waitFor({ timeout: 30000 });
await page.locator('tr.is-incorrect', { hasText: 'F-07' }).waitFor({ timeout: 10000 }).catch(() => {});
const back = { f07: await page.locator('tr.is-incorrect', { hasText: 'F-07' }).count(), owner: await page.locator('tr', { hasText: 'F-08' }).first().locator('.tb-av').innerText().catch(() => '') };
check('back on Deck 5 Rev B: the mark and the task are there', back.f07 === 1 && back.owner === 'MS', JSON.stringify(back));
await rail('Tasks').click();
check('Tasks shows the assigned card', await page.locator('.board-who', { hasText: 'Mikko Saari' }).first().waitFor({ timeout: 15000 }).then(() => true, () => false));

// Clear all → Save and clear
await rail('Studio').click();
await page.getByRole('button', { name: 'Clear all' }).click();
const dlg = page.getByRole('dialog', { name: 'Clear all' });
check('Clear all asks to save to Rev B first', /Save your progress to Rev B first\?/.test(await dlg.innerText()) && /Findings, marks, inbox items and tasks will be kept on this revision/.test(await dlg.innerText()));
await shot(page, 'r3-01-clear-all-dialog.png');
await dlg.getByRole('button', { name: 'Save and clear' }).click();
await page.locator('.studio-file', { hasText: 'No model open' }).waitFor({ timeout: 30000 });
const empty = { studio: await page.locator('.studio-file').innerText(), rev: await page.locator('select[aria-label="Revision"]').inputValue(), pins: await page.locator('.co-pin').count() };
const snap = await page.evaluate(async () => {
  const p = (await (await fetch('/api/projects')).json()).projects.find((x) => x.name === 'Demo ship');
  const r = p.models.find((m) => m.name === 'Deck 5').revisions.find((x) => x.label === 'Rev B');
  const d = await (await fetch(`/api/revisions/${r.id}`)).json();
  return { state: r.state, marks: Object.keys(d.data?.snapshot?.marks?.incorrect ?? {}).length, tasks: Object.keys(d.data?.snapshot?.tasks ?? {}).length };
});
check('Studio is empty after Clear all', empty.studio === 'No model open' && empty.rev === '' && empty.pins === 0, JSON.stringify(empty));
check('Rev B is saved with its mark and task in the snapshot', snap.state === 'saved' && snap.marks === 1 && snap.tasks === 1, JSON.stringify(snap));
await rail('Inbox').click();
check('Inbox is empty after Clear all', /No model open/.test(await page.locator('main').innerText()));
await shot(page, 'r3-02-cleared.png');
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await b.close();
done();
