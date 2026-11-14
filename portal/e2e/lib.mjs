// Shared by e2e/*.spec.mjs: browser with software GL, screenshots to docs/screenshots/, tiny assert helpers.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export const BASE = process.env.E2E_BASE || 'http://127.0.0.1:5197/';
export const SHOTS = path.resolve(new URL('../../docs/screenshots/', import.meta.url).pathname);
const exe = process.env.CHROME || `${os.homedir()}/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`;

export async function browser({ width = 1440, height = 900, theme = 'dark', guide = false } = {}) {
  const b = await chromium.launch({ executablePath: exe, headless: true,
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-precise-memory-info'] });
  const ctx = await b.newContext({ viewport: { width, height }, colorScheme: theme });
  // specs other than the guide's start as a returning visitor (the first-run guide already done in this browser)
  if (!guide) await ctx.addInitScript(() => { try { localStorage.setItem('sq.guide.done', '1'); } catch {} });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|404/.test(m.text())) errors.push(m.text()); });
  return { b, page, errors };
}

const results = [];
export function check(name, ok, detail = '') {
  results.push({ name, ok, detail });
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? ' · ' + detail : ''}`);
}
export async function shot(page, name) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name), timeout: 120000 }); }
export function done() { const f = results.filter((r) => !r.ok); if (f.length) { console.log(`${f.length} failed`); process.exit(1); } }

/** Studio: open a model of the current project from the "Open model" list, then (optionally) one of its revisions
 *  from the header's Revision menu. The model list opens the model's latest revision. */
export async function openModel(page, model, rev) {
  const list = page.getByRole('list', { name: 'Models in this project' });
  if (!(await list.isVisible())) await page.getByRole('button', { name: 'Open model', exact: true }).click();
  await list.getByRole('listitem').filter({ hasText: model }).first().click({ timeout: 60000 });
  if (rev) {
    const sel = page.locator('select[aria-label="Revision"]');
    await page.waitForFunction((r) => [...document.querySelectorAll('select[aria-label="Revision"] option')].some((o) => o.textContent.startsWith(r + ' ')), rev, { timeout: 30000 });
    const v = await sel.evaluate((s, r) => [...s.options].find((o) => o.textContent.startsWith(r + ' '))?.value, rev);
    if ((await sel.inputValue()) !== v) await sel.selectOption(v);
  }
}

/** Non-blank check for the WebGL canvas: screenshot it, decode in the page, count distinct colours in a 64×64 sample. */
export async function canvasColours(page, sel = '.studio-3d canvas') {
  const el = page.locator(sel).first();
  const png = (await el.screenshot({ timeout: 60000 })).toString('base64');
  return page.evaluate(async (b64) => {
    const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
    const c = document.createElement('canvas'); c.width = 64; c.height = 64;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0, 64, 64);
    const d = g.getImageData(0, 0, 64, 64).data, seen = new Set();
    for (let i = 0; i < d.length; i += 4) seen.add((d[i] >> 3) << 10 | (d[i + 1] >> 3) << 5 | (d[i + 2] >> 3));
    return seen.size;
  }, png);
}
