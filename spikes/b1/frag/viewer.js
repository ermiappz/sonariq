// Spike B1, option 1 viewer: That Open Fragments 3.6.1 on plain three.js, one .frag per deck, worker from own origin.
// Same window.bench contract as ../tiles/viewer.js so bench.mjs runs the same scenarios on both.
// URL: ?decks=1,2,3,4,5,6,7  &lod=default|all
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import * as FRAGS from '@thatopen/fragments';

const T0 = performance.now();
const q = new URLSearchParams(location.search);
const DECKS = (q.get('decks') || '1,2,3,4,5,6,7').split(',');

const renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: 'high-performance' });
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.add(new THREE.AmbientLight(0xffffff, 1.2), new THREE.DirectionalLight(0xffffff, 1.5));
const camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 600);
const controls = new OrbitControls(camera, renderer.domElement);
camera.position.set(60, 40, 60);

const fragments = new FRAGS.FragmentsModels('/node_modules/@thatopen/fragments/dist/Worker/worker.mjs');
const stats = { loaded: 0, bytes: 0, firstFrame: null, overviewDone: null, fetchMs: 0, loadMs: {}, paused: false };
const models = [];
const whole = new THREE.Box3();
window.bench = { stats };

function frame() {
  if (!stats.paused) {
    controls.update();
    renderer.render(scene, camera);
    if (stats.firstFrame === null && renderer.info.render.triangles > 0) stats.firstFrame = performance.now() - T0;
  }
  requestAnimationFrame(frame);
}
frame();
controls.addEventListener('change', () => fragments.update());

console.log('start');
for (const d of DECKS) {                          // one at a time: each load copies the buffer into a worker
  const t = performance.now();
  const buf = await fetch(`/data/frag/deck_${d}.frag`).then(r => r.arrayBuffer());
  stats.fetchMs += performance.now() - t; stats.bytes += buf.byteLength;
  const model = await fragments.load(buf, { modelId: `deck_${d}`, camera });
  scene.add(model.object);
  models.push(model); stats.loaded++;
  stats.loadMs[d] = Math.round(performance.now() - t);
  console.log('deck', d, 'loaded in', stats.loadMs[d], 'ms');
  whole.union(model.box);
  if (models.length === 1) fit();
  await fragments.update(true);
}
function fit() {
  const c = whole.getCenter(new THREE.Vector3()), s = whole.getSize(new THREE.Vector3());
  controls.target.copy(c);
  camera.position.set(c.x + s.x * 0.7, c.y + s.x * 0.45, c.z + s.x * 0.7);
}
fit();
await fragments.update(true);
stats.overviewDone = performance.now() - T0;

// engine frame (metres, Z up) -> this scene (Y up, moved to the importer's origin): offset from the two whole-ship boxes
const tilesIndex = await fetch('/data/tiles/index.json').then(r => r.json()).catch(() => null);
let off = new THREE.Vector3();
if (tilesIndex) {
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (const f of tilesIndex.files.filter(f => DECKS.includes(String(f.deck)))) for (let k = 0; k < 3; k++) { lo[k] = Math.min(lo[k], f.min[k]); hi[k] = Math.max(hi[k], f.max[k]); }
  off = new THREE.Vector3(whole.min.x - lo[0], whole.min.y - lo[2], whole.min.z + hi[1]);
  stats.boxSizeDiff = [whole.max.x - whole.min.x - (hi[0] - lo[0]), whole.max.y - whole.min.y - (hi[2] - lo[2]), whole.max.z - whole.min.z - (hi[1] - lo[1])];
}
const T = (p) => new THREE.Vector3(p[0] + off.x, p[2] + off.y, -p[1] + off.z);
const Tn = (n) => new THREE.Vector3(n[0], n[2], -n[1]);

async function castAll() {                        // nearest hit over all deck models, as {model, localId, guid}
  const mouse = new THREE.Vector2(innerWidth / 2, innerHeight / 2);
  let best = null;
  for (const m of models) {
    const r = await m.raycast({ camera, mouse, dom: renderer.domElement });
    if (r && (!best || r.distance < best.r.distance)) best = { m, r };
  }
  if (!best) return null;
  const [guid] = await best.m.getGuidsByLocalIds([best.r.localId]);
  return { model: best.m, localId: best.r.localId, guid };
}
const nextFrame = () => new Promise(r => requestAnimationFrame(r));
const centre = whole.getCenter(new THREE.Vector3()), size = whole.getSize(new THREE.Vector3());
Object.assign(window.bench, {
  closeTarget: tilesIndex ? [(centre.x - off.x), -(centre.z - off.z), 6.8] : null,
  info: () => ({ ...stats, calls: renderer.info.render.calls, tris: renderer.info.render.triangles, geometries: renderer.info.memory.geometries,
                 heapMB: performance.memory ? performance.memory.usedJSHeapSize / 1048576 : null,
                 gpu: (e => e ? renderer.getContext().getParameter(e.UNMASKED_RENDERER_WEBGL) : null)(renderer.getContext().getExtension('WEBGL_debug_renderer_info')) }),
  async settle() { await fragments.update(true); await nextFrame(); await nextFrame(); },
  async orbit(seconds, target, radius, height) {
    controls.enabled = false;
    const c = target ? T(target) : centre, r = radius || size.x * 0.9, hy = height ?? size.x * 0.4;
    const t = performance.now(); let n = 0, calls = 0, tris = 0, worst = 0, last = t;
    while (performance.now() - t < seconds * 1000) {
      const a = (performance.now() - t) / 1000 * 0.5;
      camera.position.set(c.x + Math.cos(a) * r, c.y + hy, c.z - Math.sin(a) * r); camera.lookAt(c); controls.target.copy(c);
      fragments.update();
      await nextFrame();
      const now = performance.now(); worst = Math.max(worst, now - last); last = now;
      n++; calls = Math.max(calls, renderer.info.render.calls); tris = Math.max(tris, renderer.info.render.triangles);
    }
    return { frames: n, fps: n / seconds, worstFrameMs: worst, calls, tris };
  },
  async pick(test, sign) {                        // same camera as the tiles test; answer = IFC GlobalId
    stats.paused = true; controls.enabled = false;
    const c = T(test.c), n = Tn(test.n);
    camera.near = test.d / 10; camera.far = 5; camera.updateProjectionMatrix();
    camera.up.set(0, Math.abs(n.y) > 0.9 ? 0 : 1, Math.abs(n.y) > 0.9 ? 1 : 0);
    camera.position.copy(c).addScaledVector(n, test.d * sign); camera.lookAt(c); camera.updateMatrixWorld();
    await fragments.update(true);
    const hidden = []; let hit = await castAll(); const first = hit && hit.guid;
    while (hit && hit.guid !== test.guid && hidden.length < 6) {     // peel enclosing parts, as in the tiles test
      hidden.push(hit); await hit.model.setVisible([hit.localId], false); await fragments.update(true);
      hit = await castAll();
    }
    for (const h of hidden) await h.model.setVisible([h.localId], true);
    if (hidden.length) await fragments.update(true);
    return { first, got: hit && hit.guid, peeled: hidden.length };
  },
});
window.benchReady = true;
