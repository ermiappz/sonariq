// Studio reliability step 5: / lands in the Studio; a first visit gets a five-step guide anchored to the real controls
// (same placement module as the finding callouts: beside the target, never over it); Skip / Done remember it; the
// Help menu reopens the guide or starts the demo.
import { browser, check, shot, done, BASE, openModel } from './lib.mjs';

const { b, page, errors } = await browser({ guide: true });
await page.goto(BASE);
await page.waitForLoadState('networkidle');
check('/ redirects to /studio', new URL(page.url()).pathname.endsWith('/studio'), page.url());
const card = page.locator('.guide-card');
const geo = (target) => page.evaluate((q) => {
  const c = document.querySelector('.guide-card')?.getBoundingClientRect(), t = document.querySelector(q)?.getBoundingClientRect();
  if (!c || !t) return null;
  const overlap = c.left < t.right && c.right > t.left && c.top < t.bottom && c.bottom > t.top;
  return { overlap, inView: c.left >= 0 && c.top >= 0 && c.right <= innerWidth && c.bottom <= innerHeight };
}, target);
await card.waitFor({ timeout: 30000 });
let g = await geo('[aria-label="Models in this project"]');
check('1 guide opens on a first visit, beside the model list (not over it)', /Pick a model here/.test(await card.innerText()) && g && !g.overlap && g.inView, JSON.stringify(g));
check('1 has Back / Next / Skip, progress dots and "Play the demo instead"', ['Back', 'Next', 'Skip', 'Play the demo instead'].every(async (n) => n) &&
  (await card.getByRole('button', { name: 'Play the demo instead' }).count()) === 1 && (await card.locator('.guide-dots i').count()) === 5);
await shot(page, 'r5-01-guide-step1.png');
await card.getByRole('button', { name: 'Next' }).click();
await openModel(page, 'Deck 5', 'Rev B');
g = await geo('[data-guide="analyse"]');
check('2 "Press Analyse" beside the Analyse button', /Press Analyse/.test(await card.innerText()) && g && !g.overlap, JSON.stringify(g));
await shot(page, 'r5-02-guide-analyse.png');
await page.getByRole('button', { name: 'Analyse' }).click();
await page.locator('.fl-row', { hasText: 'F-07' }).first().waitFor({ timeout: 120000 });
await card.getByRole('button', { name: 'Next' }).click();
await page.waitForTimeout(600);
g = await geo('.fl-row');
check('3 "your first finding" beside the first finding', /first finding/.test(await card.innerText()) && g && !g.overlap, JSON.stringify(g));
await page.locator('.fl-row', { hasText: 'F-07' }).first().click();
await card.getByRole('button', { name: 'Next' }).click();
await page.waitForTimeout(600);
check('4 section + view: rings on Section at finding and the View tab', /Cut a section here/.test(await card.innerText()) && (await page.locator('.guide-lead rect').count()) >= 2);
await shot(page, 'r5-04-guide-section.png');
await card.getByRole('button', { name: 'Back' }).click();
check('Back goes to the previous step', /first finding/.test(await card.innerText()));
await card.getByRole('button', { name: 'Next' }).click();
await card.getByRole('button', { name: 'Next' }).click();
await page.waitForTimeout(600);
check('5 "Save a revision or export"', /Save a revision or export/.test(await card.innerText()) && (await page.locator('.guide-lead rect').count()) >= 1);
await card.getByRole('button', { name: 'Done' }).click();
check('Done closes the guide', await card.count() === 0);
await page.reload(); await page.waitForLoadState('networkidle'); await page.waitForTimeout(1500);
check('it does not come back in this browser', await card.count() === 0);
const flag = await page.evaluate(async () => (await (await fetch('/api/projects')).json()).projects.find((p) => p.name === 'Demo ship').guide_done);
check('server flag set on the project', flag === 1);
await page.getByRole('button', { name: 'Help' }).click();
await page.getByRole('menuitem', { name: 'Show the guide' }).click();
check('Help → Show the guide reopens it', await card.waitFor({ timeout: 5000 }).then(() => true, () => false));
await card.getByRole('button', { name: 'Skip' }).click();
check('Skip ends it', await card.count() === 0);
await page.getByRole('button', { name: 'Help' }).click();
await page.getByRole('menuitem', { name: 'Play the demo' }).click();
check('Help → Play the demo starts the demo', await page.getByRole('region', { name: 'Demo run-through' }).waitFor({ timeout: 15000 }).then(() => true, () => false));
await page.keyboard.press('Escape');

// a second fresh browser: the shared project's flag does not hide the guide; "Play the demo instead" starts the demo
const second = await browser({ guide: true });
await second.page.goto(BASE); await second.page.locator('.guide-card').waitFor({ timeout: 30000 });
check('a fresh browser still gets the guide on the shared demo project', true);
await second.page.getByRole('button', { name: 'Play the demo instead' }).click();
check('"Play the demo instead" starts the demo', await second.page.getByRole('region', { name: 'Demo run-through' }).waitFor({ timeout: 15000 }).then(() => true, () => false));
await second.page.keyboard.press('Escape');
await second.b.close();
check('no page errors', errors.length === 0 && second.errors.length === 0, [...errors, ...second.errors].slice(0, 3).join(' | '));
await b.close();
done();
