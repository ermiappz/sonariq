// Shared by e2e/*.spec.mjs: browser with software GL, screenshots to docs/screenshots/, tiny assert helpers.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export const BASE = process.env.E2E_BASE || 'http://127.0.0.1:5197/';
export const SHOTS = path.resolve(new URL('../../docs/screenshots/', import.meta.url).pathname);
const exe = process.env.CHROME || `${os.homedir()}/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`;

export async function browser({ width = 1440, height = 900, theme = 'dark' } = {}) {
  const b = await chromium.launch({ executablePath: exe, headless: true,
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-precise-memory-info'] });
  const ctx = await b.newContext({ viewport: { width, height }, colorScheme: theme });
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
