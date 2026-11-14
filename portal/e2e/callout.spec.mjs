// Step 8: rendered callouts. Select a finding → card with Is / Must be / clause / sources / actions, leader to the
// anchor, never over its element, numbers only from the finding; dimension lines; pins for the other findings;
// hidden behind solid parts; survives Section here and display modes; class findings get the "must be" outline.
import fs from 'node:fs';
import { browser, check, shot, done, BASE, openModel } from './lib.mjs';

const F = JSON.parse(fs.readFileSync(new URL('../src/viewer/fixtures/deck5_revB_findings.json', import.meta.url), 'utf8'));
const nums = (s) => (s.match(/\d[\d,]*(?:\.\d+)?/g) ?? []).map((x) => Number(x.replace(/,/g, '')));
const idle = (page, ms = 900) => page.waitForTimeout(ms);
const settle = (page) => page.waitForFunction(() => !window.__sqViewer.anim, null, { timeout: 120000 }).then(() => idle(page, 1600));
const geo = (page) => page.evaluate(() => {
  const c = document.querySelector('.co-card')?.getBoundingClientRect(), a = document.querySelector('.co-lead circle')?.getBoundingClientRect();
  return c && a ? { card: [c.left, c.top, c.right, c.bottom], anchor: [(a.left + a.right) / 2, (a.top + a.bottom) / 2] } : null;
});

const { b, page, errors } = await browser();
await page.goto(BASE + '#model');
await openModel(page, 'Deck 5', 'Rev B');
await page.waitForFunction(() => window.__sqViewer?.stats.firstFrame != null, null, { timeout: 300000 });
await page.getByRole('button', { name: 'Analyse' }).click();
await page.getByText('F-07').first().waitFor({ timeout: 60000 });
await idle(page, 1500);
check('pins for the findings before any is selected', (await page.locator('.co-pin').count()) >= 4, `${await page.locator('.co-pin').count()} pins`);

// F-07: stair narrower than the FSS formula
await page.locator('.fl-row', { hasText: 'F-07' }).first().click();
await settle(page);
const card = page.locator('.co-card');
check('callout shows for the selected finding', await card.isVisible());
const text = await card.innerText();
const f07 = F.find((c) => c.id === 'F-07');
const known = new Set(nums(JSON.stringify(f07)));
const stray = nums(text).filter((n) => !known.has(n));
check('callout: title, Is, Must be, formula, clause, location', /F-07/.test(text) && /Is/.test(text) && /1,350 mm/.test(text) && /Must be/.test(text) && /at least 1,380 mm/.test(text)
  && /= 1,380 mm/.test(text) && /FSS Code Ch\.13/.test(text) && text.includes(f07.location.label), text.replace(/\n/g, ' | '));
check('callout numbers all come from the finding JSON', stray.length === 0, stray.join(', '));
check('callout has source chips and the three actions', (await card.locator('.src-chip').count()) === 2
  && ['Section here', 'Isolate', 'Open evidence'].every((n) => text.includes(n)));
let g = await geo(page);
check('leader anchor is outside the card (card does not cover its element)', !!g && !(g.anchor[0] > g.card[0] && g.anchor[0] < g.card[2] && g.anchor[1] > g.card[1] && g.anchor[1] < g.card[3]), JSON.stringify(g));
const dims = await page.locator('.studio-dim').allInnerTexts();
check('dimension lines: measured and required', dims.some((t) => /measured 1,350 mm/.test(t)) && dims.some((t) => /required 1,380 mm/.test(t)), dims.join(' | '));
await shot(page, 'm8-01-deck5-callout-stair.png');

// orbit: the card follows the anchor
const before = g;
await page.mouse.move(500, 450); await page.mouse.down(); await page.mouse.move(380, 430, { steps: 6 }); await page.mouse.up();
await idle(page, 1500);
g = await geo(page);
const cam0 = before && await page.evaluate(() => window.__sqViewer.camera.position.toArray());
check('after orbiting the card is still beside its anchor, not over it', !!g && !(g.anchor[0] > g.card[0] && g.anchor[0] < g.card[2] && g.anchor[1] > g.card[1] && g.anchor[1] < g.card[3]), `${before?.card} → ${g?.card} · cam ${cam0?.map((x) => x.toFixed(1))}`);

// hidden when occluded: everything solid again, look from below the deck → plates in front of the anchor
await page.evaluate(() => { const v = window.__sqViewer; v.isolate(null); const t = v.controls.target; v.camera.position.set(t.x, t.y - 0.5, t.z - 25); v.controls.update(); });
await page.locator('.co-pin.is-hidden-anchor').waitFor({ timeout: 15000 }).catch(() => {});
check('callout collapses to a pin when solid parts hide the anchor', await page.locator('.co-pin.is-hidden-anchor').isVisible() && !(await card.isVisible()));
await page.locator('.fl-row', { hasText: 'F-07' }).first().click();      // reselect: back in front
await settle(page);
check('reselecting shows the card again', await card.isVisible());

// Section here keeps the callout and the evidence
await card.getByRole('button', { name: 'Section here' }).click();
await settle(page);
const cuts = await page.evaluate(() => window.__sqViewer.cuts.length);
check('Section here: one cut, callout still there', cuts === 1 && await card.isVisible() && /F-07/.test(await card.innerText()), `${cuts} cut(s)`);
await shot(page, 'm8-02-deck5-callout-section.png');
await page.getByRole('tab', { name: 'View' }).click();
await page.getByRole('radio', { name: 'X-ray' }).click(); await idle(page, 1500);
check('X-ray mode: callout still there', await card.isVisible());
await shot(page, 'm8-03-deck5-callout-xray.png');
await page.getByRole('radio', { name: 'Shaded + edges' }).click();
await page.getByRole('tab', { name: 'Findings' }).click();
await page.getByRole('button', { name: /^Clear cut 1/ }).click().catch(() => {});

// pins: clicking one makes it the active finding
await page.getByRole('button', { name: 'Iso', exact: true }).click(); await settle(page);
await page.locator('.co-pin', { hasText: 'F-08' }).first().click();
await settle(page);
check('clicking a pin selects that finding', /F-08/.test(await card.innerText()) && /dead end 4\.2 m deep/.test(await card.innerText()));
const dd = await page.locator('.studio-dim').allInnerTexts();
check('dead end: depth line and allowed depth', dd.some((t) => /depth 4\.2 m/.test(t)) && dd.some((t) => /allowed depth/.test(t)), dd.join(' | '));
await shot(page, 'm8-04-deck5-callout-dead-end.png');

// class finding: element tinted by what it is, dashed outline labelled with what it must be
await page.locator('.fl-row', { hasText: 'F-01' }).first().click();
await settle(page);
const lab = await page.locator('.studio-dim').allInnerTexts();
check('fire class: "must be A-60" outline label', lab.includes('must be A-60') && /rated A-0/.test(await card.innerText()), lab.join(' | '));
await shot(page, 'm8-05-deck5-callout-fire-class.png');
await card.getByRole('button', { name: 'Close callout' }).click();
check('closing the callout', !(await card.isVisible()));
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await b.close();
done();
