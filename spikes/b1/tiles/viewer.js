// Spike B1, option 2 viewer: plain three.js, Meshopt GLB tiles, one draw call per tile, element id per vertex.
// URL: ?detail=stream|all|none &budget=<detail triangles> &radius=<m>
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
// the npm decoder, not three's bundled copy: pack.mjs writes vertex codec v1, which the older bundled decoder rejects
import { MeshoptDecoder } from '/node_modules/meshoptimizer/meshopt_decoder.mjs';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const T0 = performance.now();
const q = new URLSearchParams(location.search);
const DETAIL = q.get('detail') || 'stream', BUDGET = Number(q.get('budget') || 1.5e6), RADIUS = Number(q.get('radius') || 24);
const DATA = '/data/tiles/', W = 1024;

const renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: 'high-performance' });
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 600);
camera.up.set(0, 0, 1);                       // tiles are in the engine's frame: metres, Z up
const controls = new OrbitControls(camera, renderer.domElement);

const [index, colors] = await Promise.all([
  fetch(DATA + 'index.json').then(r => r.json()),
  fetch(DATA + 'colors.bin').then(r => r.arrayBuffer())]);
const H = Math.ceil(index.elements / W);
const elem = new Uint8Array(W * H * 4); elem.set(new Uint8Array(colors));
const elemTex = new THREE.DataTexture(elem, W, H, THREE.RGBAFormat);   // rgb = colour, a = 0 hidden / 255 shown
elemTex.needsUpdate = true;

const material = new THREE.ShaderMaterial({
  glslVersion: THREE.GLSL3,
  uniforms: { uElem: { value: elemTex }, uBase: { value: 0 }, uPick: { value: 0 } },
  vertexShader: `
    in float _batchid; uniform float uBase; uniform sampler2D uElem;
    flat out vec4 vCol; flat out float vId; out vec3 vPos;
    void main() {
      int id = int(uBase + _batchid);
      vCol = texelFetch(uElem, ivec2(id % ${W}, id / ${W}), 0);
      vId = float(id + 1);
      vec4 w = modelMatrix * vec4(position, 1.0);
      vPos = w.xyz;
      gl_Position = vCol.a == 0.0 ? vec4(2.0, 2.0, 2.0, 1.0) : projectionMatrix * viewMatrix * w;
    }`,
  fragmentShader: `
    precision highp float; uniform float uPick;
    flat in vec4 vCol; flat in float vId; in vec3 vPos; out vec4 o;
    void main() {
      if (uPick > 0.5) { o = vec4(mod(vId, 256.0), mod(floor(vId / 256.0), 256.0), floor(vId / 65536.0), 255.0) / 255.0; return; }
      vec3 n = normalize(cross(dFdx(vPos), dFdy(vPos)));      // flat shading, no stored normals
      float l = 0.35 + 0.65 * abs(dot(n, normalize(vec3(0.4, 0.3, 0.85))));
      o = vec4(vCol.rgb * l, 1.0);
    }`,
});

const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
MeshoptDecoder.useWorkers(4);                 // decode off the main thread
const tiles = index.files.map(f => ({ ...f, box: new THREE.Box3(new THREE.Vector3(...f.min), new THREE.Vector3(...f.max)), mesh: null, loading: null }));
const stats = { loaded: 0, bytes: 0, detailTris: 0, firstFrame: null, overviewDone: null };
let inflight = 0;

function load(t) {
  if (t.mesh || t.loading) return t.loading || Promise.resolve();
  inflight++;
  t.loading = loader.loadAsync(DATA + t.f).then(g => {
    const m = g.scene.children[0];
    m.material = material; m.matrixAutoUpdate = false; m.updateMatrix();
    m.onBeforeRender = () => { material.uniforms.uBase.value = t.base; material.uniformsNeedUpdate = true; };
    if (t.cancel) { m.geometry.dispose(); } else { scene.add(m); t.mesh = m; stats.loaded++; if (t.lod) stats.detailTris += t.tris; }
  }).finally(() => { inflight--; t.loading = null; t.cancel = false; });
  return t.loading;
}
function unload(t) {
  if (t.loading) t.cancel = true;
  if (!t.mesh) return;
  scene.remove(t.mesh); t.mesh.geometry.dispose(); t.mesh = null; stats.loaded--; stats.detailTris -= t.tris;
}

const whole = new THREE.Box3(); tiles.forEach(t => whole.union(t.box));
const centre = whole.getCenter(new THREE.Vector3()), size = whole.getSize(new THREE.Vector3());
controls.target.copy(centre);
camera.position.set(centre.x + size.x * 0.7, centre.y - size.x * 0.7, centre.z + size.x * 0.45);

const overview = tiles.filter(t => t.lod === 0), detail = tiles.filter(t => t.lod === 1);
(async () => {                                   // overview first, 6 requests at a time
  let i = 0;
  await Promise.all(Array.from({ length: 6 }, async () => { while (i < overview.length) await load(overview[i++]); }));
  stats.overviewDone = performance.now() - T0;
  if (DETAIL === 'all') { i = 0; await Promise.all(Array.from({ length: 6 }, async () => { while (i < detail.length) await load(detail[i++]); })); stats.allDone = performance.now() - T0; }
})();

function stream() {                              // nearest detail tiles within RADIUS, inside the triangle budget
  if (DETAIL !== 'stream') return;
  const near = detail.map(t => [t.box.distanceToPoint(camera.position), t]).filter(d => d[0] < RADIUS).sort((a, b) => a[0] - b[0]);
  const want = new Set(); let tris = 0;
  for (const [, t] of near) { if (tris + t.tris > BUDGET && want.size) break; want.add(t); tris += t.tris; }
  for (const t of detail) if ((t.mesh || t.loading) && !want.has(t) && !t.pinned) unload(t);
  for (const t of want) if (inflight < 6) load(t);
  stats.wanted = want.size;
}

let frames = 0;
function frame() {
  if (stats.paused) { requestAnimationFrame(frame); return; }   // pick tests draw their own single-pixel passes
  controls.update();
  if (frames % 10 === 0) stream();
  renderer.render(scene, camera);
  frames++;
  if (stats.firstFrame === null && renderer.info.render.triangles > 0) stats.firstFrame = performance.now() - T0;
  requestAnimationFrame(frame);
}
frame();

const pickTarget = new THREE.WebGLRenderTarget(1, 1);
function pickAt(x, y) {                          // GPU pick: draw element ids into one pixel
  const dpr = renderer.getPixelRatio(), w = renderer.domElement.width, h = renderer.domElement.height;
  camera.setViewOffset(w, h, x * dpr, y * dpr, 1, 1);
  material.uniforms.uPick.value = 1;
  renderer.setRenderTarget(pickTarget); renderer.setClearColor(0, 0); renderer.clear(); renderer.render(scene, camera);
  const px = new Uint8Array(4); renderer.readRenderTargetPixels(pickTarget, 0, 0, 1, 1, px);
  renderer.setRenderTarget(null); material.uniforms.uPick.value = 0; camera.clearViewOffset();
  const id = px[0] + px[1] * 256 + px[2] * 65536;
  return id ? index.dbid[id - 1] : null;
}
renderer.domElement.addEventListener('click', e => console.log('picked dbid', pickAt(e.clientX, e.clientY)));

const nextFrame = () => new Promise(r => requestAnimationFrame(r));
window.bench = {
  stats, index, closeTarget: [centre.x, centre.y, 6.8],
  info: () => ({ ...stats, calls: renderer.info.render.calls, tris: renderer.info.render.triangles, geometries: renderer.info.memory.geometries,
                 heapMB: performance.memory ? performance.memory.usedJSHeapSize / 1048576 : null, gl: renderer.getContext().getParameter(renderer.getContext().VERSION),
                 gpu: (e => e ? renderer.getContext().getParameter(e.UNMASKED_RENDERER_WEBGL) : null)(renderer.getContext().getExtension('WEBGL_debug_renderer_info')) }),
  async settle(ms = 30000) { const t = performance.now(); do { await nextFrame(); await new Promise(r => setTimeout(r, 200)); stream(); } while ((inflight > 0 || stats.overviewDone === null || (DETAIL === 'all' && !stats.allDone)) && performance.now() - t < ms); },
  async orbit(seconds, target, radius, height) {  // orbit `target` at `radius`, count real frames
    controls.enabled = false;
    const c = target ? new THREE.Vector3(...target) : centre, r = radius || size.x * 0.9, hz = height ?? size.x * 0.4;
    const t = performance.now(); let n = 0, calls = 0, tris = 0, worst = 0, last = t;
    while (performance.now() - t < seconds * 1000) {
      const a = (performance.now() - t) / 1000 * 0.5;
      camera.position.set(c.x + Math.cos(a) * r, c.y + Math.sin(a) * r, c.z + hz); camera.lookAt(c); controls.target.copy(c);
      await nextFrame();
      const now = performance.now(); worst = Math.max(worst, now - last); last = now;
      n++; calls = Math.max(calls, renderer.info.render.calls); tris = Math.max(tris, renderer.info.render.triangles);
    }
    return { frames: n, fps: n / seconds, worstFrameMs: worst, calls, tris };
  },
  async pick(test, sign) {                        // test.d metres off the element's largest triangle, looking at it
    const c = new THREE.Vector3(...test.c), n = new THREE.Vector3(...test.n);
    const i = index.dbid.indexOf(test.dbid);
    const t = tiles.find(t => i >= t.base && i < t.base + t.n);
    t.pinned = true; stats.paused = true; await load(t);
    controls.enabled = false; camera.near = test.d / 10; camera.far = 5; camera.updateProjectionMatrix();
    camera.up.set(Math.abs(n.z) > 0.9 ? 1 : 0, 0, Math.abs(n.z) > 0.9 ? 0 : 1);
    camera.position.copy(c).addScaledVector(n, test.d * sign); camera.lookAt(c); camera.updateMatrixWorld();
    // a part can sit inside another (pipe in its insulation): hide whatever was hit and look again, up to 6 layers
    const hidden = []; let got = pickAt(innerWidth / 2, innerHeight / 2), first = got;
    while (got !== null && got !== test.dbid && hidden.length < 6) {
      const k = index.dbid.indexOf(got); hidden.push(k); elem[k * 4 + 3] = 0; elemTex.needsUpdate = true;
      got = pickAt(innerWidth / 2, innerHeight / 2);
    }
    for (const k of hidden) elem[k * 4 + 3] = 255;
    elemTex.needsUpdate = true;
    return { first, got, peeled: hidden.length };
  },
};
window.benchReady = true;
