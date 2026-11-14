// Step 6: section blade with capping. Position (readout, arrows, slider, field), Cut (near side removed, camera faces
// the cut, caps on closed groups, section edges), Flip, Section view, Clear, three cuts, modes with cuts, Section at
// finding, named views. deck5_revB, then the whole RCRV (skipped when the engine does not have it).
import { browser, check, shot, done, BASE } from './lib.mjs';

const ready = (page) => page.waitForFunction(() => window.__sqViewer?.stats.overviewMs != null && window.__sqViewer.stats.firstFrame != null, null, { timeout: 300000 });
const idle = (page, ms = 900) => page.waitForTimeout(ms);
const st = (page) => page.evaluate(() => { const v = window.__sqViewer;
  return { cuts: v.cuts.map((c) => ({ ...c })), blade: v.blade && { ...v.blade }, planes: v.clipPlanes.length, caps: v.capStats.groups,
    proj: v.cameraState().projection, mode: v.mode, edges: v.sectionGroup.children.filter((o) => o.isLineSegments).reduce((n, o) => n + o.geometry.attributes.position.count / 2, 0) }; });
// share of canvas pixels the caps change: render with caps, without, compare
const capShare = (page) => page.evaluate(() => {
  const v = window.__sqViewer, gl = v.renderer.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
  const grab = () => { v.render(); const px = new Uint8Array(w * h * 4); gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px); return px; };
  const on = grab(); v.capsOn = false; const off = grab(); v.capsOn = true; v.render();
  let n = 0; for (let i = 0; i < on.length; i += 16) if (Math.abs(on[i] - off[i]) + Math.abs(on[i + 1] - off[i + 1]) + Math.abs(on[i + 2] - off[i + 2]) > 30) n++;
  return n / (on.length / 16);
});
const readout = (page) => page.locator('.sec-readout b').innerText();
const frameNo = async (page) => Number((await readout(page)).match(/^Fr (-?\d+)/)?.[1]);

async function blade(page, tag) {
  await page.getByRole('button', { name: /^Section/ }).click();
  await page.locator('.sec-bar').waitFor();
  let s = await st(page);
  const r0 = await readout(page);
  check(`${tag}: blade shows, nothing clipped yet`, !!s.blade && s.cuts.length === 0 && s.planes === 0 && /^Fr \d+$/.test(r0), `${r0}, ${s.planes} planes`);
  const f0 = await frameNo(page);
  const slider = page.getByRole('slider', { name: 'Section position' });
  await slider.focus(); await page.keyboard.press('ArrowRight');
  const f1 = await frameNo(page);
  await page.keyboard.press('Shift+ArrowLeft');
  const f2 = await frameNo(page);
  check(`${tag}: arrow = one frame, Shift+arrow = ten`, f1 === f0 + 1 && f2 === f1 - 10, `Fr ${f0} → ${f1} → ${f2}`);
  await page.getByLabel('Frame number').fill(String(f0));
  check(`${tag}: frame field moves the blade`, (await frameNo(page)) === f0 && Math.abs((await st(page)).blade.pos - (await page.evaluate((f) => window.__sqViewer.grid.frame0_x + f * window.__sqViewer.grid.spacing_m, f0))) < 1e-6);
  await idle(page, 1500);
}

async function cutAndCheck(page, tag, file, min = 0.01) {
  const camBefore = await page.evaluate(() => window.__sqViewer.camera.position.toArray());
  await page.getByRole('button', { name: 'Cut', exact: true }).click();
  await page.waitForFunction(() => !window.__sqViewer.anim, null, { timeout: 180000 });   // the ease spans slow frames on software GL
  await idle(page, 1500);
  const s = await st(page);
  const c = s.cuts[0];
  const removedCam = await page.evaluate(([c, cam]) => { const a = { cross: 0, long: 1, deck: 2 }[c.kind]; return c.flip ? cam[a] < c.pos : cam[a] > c.pos; }, [c, camBefore]);
  const faces = await page.evaluate(() => { const v = window.__sqViewer, c = v.cuts[0], a = { cross: 0, long: 1, deck: 2 }[c.kind];
    const d = v.camera.position.clone().sub(v.controls.target).normalize(); return Math.abs(d.getComponent(a)); });
  const share = await capShare(page);
  check(`${tag}: Cut removes the near side`, s.cuts.length === 1 && s.planes === 1 && removedCam, JSON.stringify(c));
  check(`${tag}: camera eases to face the cut`, faces > 0.99, `|view · axis| = ${faces.toFixed(3)}`);
  check(`${tag}: caps drawn on the cut faces`, s.caps > 0 && share > min, `${s.caps} cap passes, ${(share * 100).toFixed(1)} % of pixels are cap`);
  check(`${tag}: section edges`, s.edges > 20, `${s.edges} segments`);
  await shot(page, file);
  return share;
}

const only = process.env.E2E_ONLY;     // deck5 | rcrv: run one half while iterating
// ------------------------------------------------------------------------------------------------ deck5_revB
if (only !== 'rcrv') {
  const { b, page, errors } = await browser();
  await page.goto(BASE + '#model');
  await page.getByRole('button', { name: /deck5_revB\.ifc/ }).click();
  await ready(page);
  await blade(page, 'deck5');
  await shot(page, 'm6-01-deck5-blade.png');
  // deck plan through the cabins: walls capped
  await page.getByRole('radio', { name: 'Deck plan' }).click();
  const dr = await readout(page);
  check('deck5: deck plan readout', dr === 'Deck 5 + 1.5 m', dr);
  await idle(page, 1200);
  // deck5 walls are ~0.1 m thick: at whole-deck zoom a wall cap is a pixel wide, so the share is small here
  await cutAndCheck(page, 'deck5 deck plan', 'm6-02-deck5-plan-cut.png', 0.0005);
  await page.getByRole('button', { name: 'Section view' }).click(); await idle(page, 1500);
  check('deck5: Section view is orthographic', (await st(page)).proj === 'orthographic');
  await shot(page, 'm6-03-deck5-plan-section-view.png');
  // close in on stair 3A (x 125-131 m): the flights are capped solid, not hollow shells
  await page.evaluate(() => { const v = window.__sqViewer; v.camera.zoom = 7; v.camera.updateProjectionMatrix(); v.controls.target.x = 128; v.camera.position.x = 128; v.controls.update(); });
  const z = await capShare(page);
  check('deck5: caps fill the cut stair and walls (close up)', z > 0.01, `${(z * 100).toFixed(1)} % of pixels are cap`);
  await shot(page, 'm6-03b-deck5-plan-stair-caps.png');
  await page.getByRole('button', { name: 'Section view' }).click(); await idle(page, 1200);
  // nudge + re-cut keeps the side
  const before = (await st(page)).cuts[0];
  await page.getByRole('slider', { name: 'Section position' }).focus();
  await page.keyboard.press('ArrowUp'); await page.keyboard.press('ArrowUp');
  check('deck5: nudging shows the blade, the cut stays until Re-cut', (await st(page)).blade !== null && (await st(page)).cuts[0].pos === before.pos);
  await page.getByRole('button', { name: 'Re-cut' }).click(); await idle(page);
  const after = (await st(page)).cuts[0];
  check('deck5: Re-cut moves the cut, keeps the side', Math.abs(after.pos - before.pos - 0.2) < 1e-6 && after.flip === before.flip && (await st(page)).blade === null, `${before.pos} → ${after.pos}`);
  await page.getByRole('button', { name: 'Flip' }).click(); await idle(page, 1500);
  check('deck5: Flip keeps the other side', (await st(page)).cuts[0].flip === !before.flip);
  await page.getByRole('button', { name: 'Flip' }).click(); await idle(page, 1200);
  // modes combine with cuts: Lines + deck plan
  await page.getByRole('tab', { name: 'View' }).click();
  await page.getByRole('radio', { name: 'Lines' }).click(); await idle(page);
  check('deck5: Lines + deck plan keeps caps', (await capShare(page)) > 0.0005);
  await shot(page, 'm6-04-deck5-lines-plan.png');
  // second cut: a cross section; third: longitudinal; a fourth is not offered
  await page.getByRole('button', { name: 'Add cut' }).click();
  await page.getByRole('radio', { name: 'Cross section' }).click();
  await page.getByLabel('Frame number').fill('150'); await idle(page, 600);
  await page.getByRole('button', { name: 'Cut', exact: true }).click(); await idle(page, 1500);
  await page.getByRole('button', { name: 'Add cut' }).click();
  await page.getByRole('radio', { name: 'Longitudinal' }).click();
  await page.getByLabel('Position in metres').fill('-2'); await idle(page, 600);
  await page.getByRole('button', { name: 'Cut', exact: true }).click(); await idle(page, 1500);
  let s = await st(page);
  check('deck5: three simultaneous cuts', s.cuts.length === 3 && s.planes === 3 && await page.getByRole('button', { name: 'Add cut' }).isDisabled(),
    s.cuts.map((c) => `${c.kind} ${c.pos}`).join(', '));
  await page.getByRole('radio', { name: 'X-ray' }).click(); await idle(page);
  await page.getByRole('button', { name: 'Iso' }).click(); await idle(page, 1200);
  await shot(page, 'm6-05-deck5-three-cuts-xray.png');
  await page.getByRole('radio', { name: 'Shaded + edges' }).click(); await idle(page, 600);
  await shot(page, 'm6-06-deck5-three-cuts.png');
  // named view: save, clear everything, open it again
  await page.getByLabel('View name').fill('Three cuts iso');
  await page.getByRole('button', { name: 'Save view' }).click();
  await page.getByRole('button', { name: 'Three cuts iso', exact: true }).waitFor();
  const saved = await page.evaluate(() => ({ cam: window.__sqViewer.camera.position.toArray(), cuts: window.__sqViewer.cuts.length }));
  for (let i = 0; i < 3; i++) await page.getByRole('button', { name: /^Clear cut \d/ }).first().click();
  await page.getByRole('radio', { name: 'Wireframe' }).click();
  await page.getByRole('button', { name: 'Top' }).click(); await idle(page);
  s = await st(page);
  check('deck5: Clear cut removes every cut', s.cuts.length === 0 && s.planes === 0);
  await page.getByRole('button', { name: 'Three cuts iso', exact: true }).click(); await idle(page, 1200);
  s = await st(page);
  const cam = await page.evaluate(() => window.__sqViewer.camera.position.toArray());
  check('deck5: named view restores cuts, camera and mode', s.cuts.length === saved.cuts && s.mode === 'edges' && cam.every((x, i) => Math.abs(x - saved.cam[i]) < 1e-3),
    `${s.cuts.length} cuts, ${s.mode}`);
  // Section at finding (Rev B: F-07, the corridor narrowed by the new cabins)
  for (let i = 0; i < 3; i++) await page.getByRole('button', { name: /^Clear cut \d/ }).first().click();
  await page.getByRole('tab', { name: 'Findings' }).click();
  await page.getByRole('button', { name: 'Analyse' }).click();
  await page.getByText('F-07').first().waitFor({ timeout: 60000 });
  await page.getByText('F-07').first().click(); await idle(page, 800);
  await page.getByRole('button', { name: 'Section at finding' }).click(); await idle(page, 2500);
  s = await st(page);
  check('deck5: Section at finding cuts a deck plan through the finding', s.cuts.length === 1 && s.cuts[0].kind === 'deck' && (await capShare(page)) > 0.01,
    `${s.cuts[0]?.kind} ${(await page.locator('.sec-chip').first().innerText()).split('\n')[0]}`);
  await shot(page, 'm6-07-deck5-section-at-finding.png');
  check('deck5: no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
  await b.close();
}

// ------------------------------------------------------------------------------------------------ RCRV
if (only !== 'deck5') {
  const { b, page, errors } = await browser();
  await page.goto(BASE + '#model');
  if (!(await page.evaluate(async () => (await fetch('/api/models/rcrv')).ok))) {
    console.log('skip RCRV: not on this engine (data/rcrv is not in git)');
  } else {
    await page.waitForLoadState('networkidle'); await idle(page, 1500);
    if (!(await page.getByRole('button', { name: /RCRV whole ship/ }).isVisible())) await page.getByRole('button', { name: 'Open model', exact: true }).click();
    await page.getByRole('button', { name: /RCRV whole ship/ }).click();
    await ready(page);
    await blade(page, 'RCRV');
    await shot(page, 'm6-08-rcrv-blade.png');
    const t0 = Date.now();
    await cutAndCheck(page, 'RCRV cross section', 'm6-09-rcrv-cross-cut.png');
    console.log(`     RCRV cut + caps + edges settled within ${Date.now() - t0} ms (software GL)`);
    await page.getByRole('button', { name: 'Section view' }).click(); await idle(page, 2500);
    await shot(page, 'm6-10-rcrv-cross-section-view.png');
    await page.getByRole('button', { name: /^Clear cut 1/ }).click();
    await page.getByRole('radio', { name: 'Deck plan' }).click();
    await page.getByLabel('Deck', { exact: true }).selectOption({ index: 2 }); await idle(page, 1500);
    await page.getByRole('button', { name: 'Persp' }).click();
    // a plan cut 1.5 m above the deck crosses walls only (no plates): at whole-ship zoom the caps are thin lines
    await cutAndCheck(page, 'RCRV deck plan', 'm6-11-rcrv-deck-plan.png', 0.001);
    await page.getByRole('button', { name: /^Clear cut 1/ }).click();
    await page.getByRole('radio', { name: 'Longitudinal' }).click(); await idle(page, 1500);
    await page.getByRole('button', { name: 'Port' }).click(); await idle(page, 800);
    await cutAndCheck(page, 'RCRV longitudinal on CL', 'm6-12-rcrv-longitudinal.png');
    check('RCRV: no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
  }
  await b.close();
}
done();
