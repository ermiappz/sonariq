// Spike B1 benchmark runner: headless Chromium (software GL on this VM), same scenarios for both viewers.
// usage: node bench.mjs <name> <url-path> [--picks] [--orbit=whole|close] [--shot]
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import { execSync } from 'node:child_process';

const [name, urlPath, ...flags] = process.argv.slice(2);
const out = new URL('../../data/rcrv/spike_b1/', import.meta.url).pathname;
const exe = process.env.CHROME || `${os.homedir()}/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`;
const userDir = fs.mkdtempSync(`${os.tmpdir()}/sq-bench-`);
const ctx = await chromium.launchPersistentContext(userDir, {
  executablePath: exe, headless: true, viewport: { width: 1440, height: 900 },
  args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-precise-memory-info',
         '--js-flags=--max-old-space-size=4096'] });   // no uncapped-frame-rate flags: with software GL they starve tile loading
const page = ctx.pages()[0];
const log = [];
page.on('console', m => log.push(m.text()));
page.on('pageerror', e => log.push('PAGEERROR ' + e.message));
const rss = () => {            // every process of this browser instance, MB (software GL: GPU buffers live in RAM too)
  const rows = execSync(`ps -eo rss,args | grep -F -- '${userDir}' | grep -v grep || true`).toString().trim().split('\n').filter(Boolean);
  return Math.round(rows.reduce((s, r) => s + Number(r.trim().split(/\s+/)[0]), 0) / 1024);
};
const res = { name, url: urlPath, when: new Date().toISOString() };
let peak = 0; const timer = setInterval(() => { peak = Math.max(peak, rss()); }, 500);
try {
  const t0 = Date.now();
  await page.goto('http://127.0.0.1:8899' + urlPath, { timeout: 600000 });
  await page.waitForFunction('window.benchReady === true', null, { timeout: 600000 });
  await page.waitForFunction('window.bench.stats.firstFrame !== null', null, { timeout: 600000 });
  res.firstFrameWallMs = Date.now() - t0;
  await page.evaluate('window.bench.settle(600000)');
  res.loaded = await page.evaluate('window.bench.info()');
  res.rssAfterLoadMB = rss();
  if (flags.includes('--shot')) await page.screenshot({ path: `${out}shot_${name}.png`, timeout: 180000 });
  const orbit = (flags.find(f => f.startsWith('--orbit=')) || '').split('=')[1];
  if (orbit === 'whole') res.orbitWhole = await page.evaluate('window.bench.orbit(20)');
  if (orbit === 'close') {
    res.orbitClose = await page.evaluate('(async()=>{const b=window.bench; await b.orbit(3,b.closeTarget,6,1.2); await b.settle(120000); return b.orbit(20,b.closeTarget,6,1.2)})()');
    res.closeInfo = await page.evaluate('window.bench.info()');
    if (flags.includes('--shot')) await page.screenshot({ path: `${out}shot_${name}_close.png`, timeout: 180000 });
  }
  if (flags.includes('--picks')) {
    const tests = JSON.parse(fs.readFileSync(out + 'tests.json'));
    res.picks = [];
    for (const t of tests) {
      const got = [await page.evaluate(([t, s]) => window.bench.pick(t, s), [t, 1]), await page.evaluate(([t, s]) => window.bench.pick(t, s), [t, -1])];
      res.picks.push({ dbid: t.dbid, ifc: t.ifc, got, direct: got.some(g => g.first === t.dbid || g.first === t.guid), ok: got.some(g => g.got === t.dbid || g.got === t.guid) });   // tiles answer with the source id, Fragments with the GlobalId
    }
    res.pickTotal = res.picks.length;
    res.pickDirect = res.picks.filter(p => p.direct).length;          // right element on the first hit
    res.pickAfterPeel = res.picks.filter(p => p.ok).length;           // right element once enclosing parts are hidden
  }
  res.rssEndMB = rss();
} catch (e) { res.error = String(e); }
clearInterval(timer);
res.peakRssMB = Math.max(peak, rss()); res.console = log.slice(-15);
fs.writeFileSync(`${out}bench_${name}.json`, JSON.stringify(res, null, 1));
const { picks, ...short } = res; console.log(JSON.stringify(short, null, 1));
await ctx.close(); fs.rmSync(userDir, { recursive: true, force: true });
