// Step 9.3: Studio with a finding callout at 1280 / 1440 / 1920 wide, dark and light theme: no horizontal page
// scroll, the callout inside the 3D, the 3D background follows the theme; keyboard: Tab reaches the view tools with
// a visible focus ring, arrow keys in the findings list open a callout.
import { browser, check, shot, done, BASE } from './lib.mjs';

for (const width of [1280, 1440, 1920]) {
  for (const theme of ['dark', 'light']) {
    const tag = `${width} ${theme}`;
    const { b, page, errors } = await browser({ width, height: width === 1920 ? 1080 : 900 });
    await page.goto(BASE + '#model');
    await page.waitForLoadState('networkidle'); await page.waitForTimeout(1500);
    // later passes: the Studio opens the previous pass's run and closes the model list
    if (!(await page.getByRole('button', { name: /deck5_revB\.ifc/ }).isVisible())) await page.getByRole('button', { name: 'Open model', exact: true }).click();
    await page.getByRole('button', { name: /deck5_revB\.ifc/ }).click();
    await page.waitForFunction(() => window.__sqViewer?.stats.firstFrame != null, null, { timeout: 300000 });
    await page.getByRole('button', { name: 'Analyse' }).click();
    await page.locator('.fl-row', { hasText: 'F-07' }).first().waitFor({ timeout: 60000 });
    if (theme === 'light') await page.getByRole('button', { name: 'Light / dark theme' }).click();
    await page.locator('.fl-row', { hasText: 'F-07' }).first().click();
    await page.waitForFunction(() => !window.__sqViewer.anim, null, { timeout: 120000 });
    await page.waitForTimeout(1500);
    const r = await page.evaluate(() => {
      const host = document.querySelector('.studio-3d').getBoundingClientRect(), c = document.querySelector('.co-card')?.getBoundingClientRect();
      const bg = window.__sqViewer.bg, lum = 0.2126 * bg.r + 0.7152 * bg.g + 0.0722 * bg.b;
      return { scroll: document.documentElement.scrollWidth - window.innerWidth, inside: !!c && c.left >= host.left && c.right <= host.right && c.top >= host.top && c.bottom <= host.bottom, lum };
    });
    check(`${tag}: no horizontal page scroll`, r.scroll <= 0, `${r.scroll} px`);
    check(`${tag}: callout inside the 3D`, r.inside);
    check(`${tag}: 3D background follows the theme`, theme === 'light' ? r.lum > 0.5 : r.lum < 0.2, r.lum.toFixed(2));
    await shot(page, `m9-layout-${width}-${theme}.png`);
    if (width === 1440 && theme === 'dark') {
      // keyboard: focus the view tools, then a findings row
      // arrive by keyboard (Tab from the button before), so :focus-visible applies as for a real keyboard user
      await page.locator('.ship-tools button').nth(1).focus(); await page.keyboard.press('Shift+Tab');
      const ring = await page.evaluate(() => { const s = getComputedStyle(document.activeElement); return s.outlineStyle !== 'none' || s.boxShadow !== 'none'; });
      check('keyboard: view tools take focus with a visible ring', ring);
      await page.keyboard.press('Tab');
      check('keyboard: Tab moves along the toolbar', await page.evaluate(() => !!document.activeElement.closest('.ship-tools')));
      await page.locator('.co-card').getByRole('button', { name: 'Close callout' }).click();
      await page.locator('.fl-list').focus();
      await page.keyboard.press('ArrowDown');
      await page.locator('.co-card').waitFor({ timeout: 15000 }).catch(() => {});
      check('keyboard: arrow keys in the findings list open a callout', await page.locator('.co-card').isVisible());
      await shot(page, 'm9-keyboard-focus.png');
    }
    check(`${tag}: no page errors`, errors.length === 0, errors.slice(0, 3).join(' | '));
    await b.close();
  }
}
done();
