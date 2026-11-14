// Whole-ship viewer (DECISIONS M1-M4, M9): Meshopt glTF tiles from the engine's model pipeline, plain three.js.
// One draw call per tile; every vertex carries its element index, so a click maps to the engine's element (GPU pick).
// Coordinates are the engine's frame (metres, Z up): evidence boxes from findings draw without a transform.
// Element state lives in one RGBA texture: rgb = colour, a = 0 hidden · 1-254 ghosted (x-ray) · 255 solid.
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { MeshoptDecoder } from "meshoptimizer/decoder";

export type TileFile = { f: string; lod: number; group: string; deck: number; base: number; n: number; tris: number; min: number[]; max: number[] };
export type TileIndex = { elements: number; box: [number[], number[]]; groups: string[]; files: TileFile[]; aliases?: Record<string, string[]>; tris: number };
export type ElementRow = [string, string | null, string, string];   // stable id, source id, ifc class, name
export type ViewName = "iso" | "top" | "port" | "starboard" | "bow" | "stern";
export type DisplayMode = "shaded" | "edges" | "realistic" | "xray" | "lines" | "wireframe";
type Tile = TileFile & { box: THREE.Box3; mesh: THREE.Mesh | null; loading: Promise<void> | null; cancel?: boolean; pinned?: boolean };

const W = 1024;                                    // element texture width
const GHOST = 40;                                  // alpha of a ghosted element (x-ray)
const ISO_DIR = new THREE.Vector3(-0.55, -0.75, 0.42).normalize();   // from aft, starboard, above (bow = +x, port = +y)

const VERT = /* glsl */ `
  in float _batchid;
  uniform float uBase; uniform sampler2D uElem;
  flat out vec4 vCol; flat out float vId; out vec3 vPos;
  #include <clipping_planes_pars_vertex>
  void main() {
    int id = int(uBase + _batchid);
    vCol = texelFetch(uElem, ivec2(id % ${W}, id / ${W}), 0);
    vId = float(id + 1);
    vec4 w = modelMatrix * vec4(position, 1.0);
    vPos = w.xyz;
    vec4 mvPosition = viewMatrix * w;
    gl_Position = projectionMatrix * mvPosition;
    #include <clipping_planes_vertex>
  }`;
const FRAG = /* glsl */ `
  precision highp float;
  uniform float uPass;        // 0 solid, 1 ghost, 2 pick
  uniform float uLight;       // 0 flat, 1 realistic
  uniform float uFill;        // 1 = draw the background colour (hidden-line "Lines" mode: only the edge pass shows)
  uniform vec3 uGhost; uniform vec3 uBg;
  flat in vec4 vCol; flat in float vId; in vec3 vPos; out vec4 o;
  #include <clipping_planes_pars_fragment>
  void main() {
    #include <clipping_planes_fragment>
    float a = vCol.a * 255.0;
    if (a < 0.5) discard;
    bool solid = a > 254.5;
    if (uPass == 2.0) { o = vec4(mod(vId, 256.0), mod(floor(vId / 256.0), 256.0), floor(vId / 65536.0), 255.0) / 255.0; return; }
    if ((uPass == 0.0) != solid) discard;
    vec3 n = normalize(cross(dFdx(vPos), dFdy(vPos)));
    float l = 0.38 + 0.62 * abs(dot(n, normalize(vec3(0.35, 0.25, 0.9))));
    if (uLight > 0.5) l = 0.30 + 0.45 * max(dot(n, normalize(vec3(0.4, 0.3, 0.85))), 0.0) + 0.25 * (0.5 + 0.5 * n.z);
    if (uPass == 1.0) { if (uFill > 0.5) discard; o = vec4(mix(uGhost, vCol.rgb, 0.25) * (0.7 + 0.3 * l), a / 255.0 * 0.6); return; }
    o = uFill > 0.5 ? vec4(uBg, 1.0) : vec4(vCol.rgb * l, 1.0);
  }`;

export class ShipViewer {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene = new THREE.Scene();
  readonly overlay = new THREE.Group();            // evidence lines, outlines (drawn after the model)
  persp: THREE.PerspectiveCamera;
  ortho: THREE.OrthographicCamera;
  camera: THREE.PerspectiveCamera | THREE.OrthographicCamera;
  controls: OrbitControls;
  index!: TileIndex;
  elements: ElementRow[] = [];
  byId = new Map<string, number>();
  base: Uint8Array = new Uint8Array(0);             // model colours as loaded
  state: Uint8Array = new Uint8Array(0);            // current texture contents
  tex!: THREE.DataTexture;
  stats = { firstFrame: null as number | null, overviewMs: null as number | null, loaded: 0, detailTris: 0, inflight: 0, wanted: 0 };
  clipPlanes: THREE.Plane[] = [];
  onSelect: ((i: number | null) => void) | null = null;
  onHover: ((i: number | null) => void) | null = null;
  onChange: (() => void) | null = null;
  hovered: number | null = null;
  selected: number | null = null;
  mode: DisplayMode = "edges";                    // spec default: shaded with edges
  private tiles: Tile[] = [];
  private material!: THREE.ShaderMaterial;
  private loader = new GLTFLoader();
  private url = "";
  private disposed = false;
  private t0 = performance.now();
  private frames = 0;
  private dirty = true;
  private pickTarget = new THREE.WebGLRenderTarget(1, 1);
  private ro: ResizeObserver;
  private deckClip: THREE.Plane | null = null;
  private budget = 1.5e6;
  private radius = 24;
  private hoverTimer = 0;
  bg = new THREE.Color("#17191c");
  private ghostRgb = new THREE.Color("#8b95a1");
  // the tile shader writes element colours as stored (sRGB bytes), so its uniforms are sRGB too
  private bgSrgb = this.bg.clone().convertLinearToSRGB();
  private ghostSrgb = this.ghostRgb.clone().convertLinearToSRGB();

  constructor(readonly host: HTMLElement, opts: { headers?: Record<string, string> } = {}) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.localClippingEnabled = true;
    this.renderer.domElement.style.display = "block";
    this.renderer.domElement.setAttribute("aria-label", "3D model view");
    host.appendChild(this.renderer.domElement);
    const w = host.clientWidth || 800, h = host.clientHeight || 600;
    this.persp = new THREE.PerspectiveCamera(45, w / h, 0.05, 2000);
    this.ortho = new THREE.OrthographicCamera(-w / 2, w / 2, h / 2, -h / 2, -2000, 2000);
    for (const c of [this.persp, this.ortho]) c.up.set(0, 0, 1);
    this.camera = this.persp;
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.zoomToCursor = true;
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.15;
    this.controls.screenSpacePanning = true;
    this.controls.addEventListener("change", () => { this.dirty = true; this.onChange?.(); });
    if (opts.headers) this.loader.setRequestHeader(opts.headers);
    this.loader.setMeshoptDecoder(MeshoptDecoder);
    this.scene.add(this.overlay);
    this.overlay.renderOrder = 10;
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(host);
    const el = this.renderer.domElement;
    let down: [number, number] | null = null;
    el.addEventListener("pointerdown", (e) => { down = [e.clientX, e.clientY]; });
    el.addEventListener("pointerup", (e) => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;      // a drag is not a click
      const r = el.getBoundingClientRect();
      const i = this.pick(e.clientX - r.left, e.clientY - r.top);
      this.select(i);
      this.onSelect?.(i);
    });
    el.addEventListener("pointermove", (e) => {
      if (e.buttons) return;
      window.clearTimeout(this.hoverTimer);
      this.hoverTimer = window.setTimeout(() => {
        const r = el.getBoundingClientRect();
        this.hover(this.pick(e.clientX - r.left, e.clientY - r.top));
      }, 90);
    });
    el.addEventListener("pointerleave", () => { window.clearTimeout(this.hoverTimer); this.hover(null); });
    this.loop();
  }

  async load(url: string, headers: Record<string, string> = {}) {
    this.url = url.replace(/\/?$/, "/");
    const get = (p: string) => fetch(this.url + p, { headers }).then((r) => { if (!r.ok) throw new Error(`${p}: ${r.status}`); return r; });
    const [index, elements, colors] = await Promise.all([
      get("index.json").then((r) => r.json()), get("elements.json").then((r) => r.json()), get("colors.bin").then((r) => r.arrayBuffer())]);
    this.index = index; this.elements = elements;
    elements.forEach((e: ElementRow, i: number) => this.byId.set(e[0], i));
    const H = Math.ceil(index.elements / W);
    this.base = new Uint8Array(W * H * 4); this.base.set(new Uint8Array(colors));
    this.state = this.base.slice();
    this.tex = new THREE.DataTexture(this.state, W, H, THREE.RGBAFormat);
    this.tex.needsUpdate = true;
    this.material = new THREE.ShaderMaterial({
      glslVersion: THREE.GLSL3, vertexShader: VERT, fragmentShader: FRAG, clipping: true, side: THREE.DoubleSide,
      uniforms: { uElem: { value: this.tex }, uBase: { value: 0 }, uPass: { value: 0 }, uLight: { value: 0 }, uFill: { value: 0 },
        uGhost: { value: this.ghostSrgb }, uBg: { value: this.bgSrgb } },
    });
    this.material.clippingPlanes = this.clipPlanes;
    this.tiles = index.files.map((f: TileFile) => ({ ...f, box: new THREE.Box3(new THREE.Vector3(...f.min), new THREE.Vector3(...f.max)), mesh: null, loading: null }));
    this.disc = new Uint8Array(index.elements); this.deckOf = new Int16Array(index.elements);
    for (const t of this.tiles) { const g = index.groups.indexOf(t.group); this.disc.fill(g, t.base, t.base + t.n); this.deckOf.fill(t.deck, t.base, t.base + t.n); }
    this.setMode(this.mode);
    this.view("iso");
    const overview = this.tiles.filter((t) => t.lod === 0);
    let i = 0;
    await Promise.all(Array.from({ length: 6 }, async () => { while (i < overview.length) await this.loadTile(overview[i++]); }));
    this.stats.overviewMs = performance.now() - this.t0;
  }

  private async loadTile(t: Tile) {
    if (t.mesh) return;
    if (t.loading) { t.cancel = false; return t.loading; }
    this.stats.inflight++;
    t.loading = this.loader.loadAsync(this.url + "tiles/" + t.f).then((g) => {
      const m = g.scene.children[0] as THREE.Mesh;
      m.material = this.material;
      m.updateMatrix(); m.matrixAutoUpdate = false;
      m.onBeforeRender = () => { this.material.uniforms.uBase.value = t.base; this.material.uniformsNeedUpdate = true; };
      if (t.cancel || this.disposed) { m.geometry.dispose(); return; }
      this.scene.add(m); t.mesh = m; this.stats.loaded++;
      if (t.lod) this.stats.detailTris += t.tris;
      this.dirty = true;
    }).catch(() => { /* a failed tile stays unloaded; the overview still shows the ship */ })
      .finally(() => { this.stats.inflight--; t.loading = null; t.cancel = false; });
    return t.loading;
  }

  tileOf(i: number): Tile | undefined { return this.tiles.find((t) => i >= t.base && i < t.base + t.n); }
  /** Load (and keep while pinned) the tiles holding these elements: a focused finding or a picked part must be drawn
   *  even when it sits in a detail tile outside the streaming radius. */
  async loadElements(ids: number[]) {
    for (const t of this.tiles) t.pinned = false;
    const want = new Set(ids.map((i) => this.tileOf(i)).filter((t): t is Tile => !!t));
    for (const t of want) t.pinned = true;
    await Promise.all([...want].map((t) => this.loadTile(t)));
    this.dirty = true;
  }

  private unloadTile(t: Tile) {
    if (t.loading) t.cancel = true;
    if (!t.mesh) return;
    this.scene.remove(t.mesh); t.mesh.geometry.dispose(); t.mesh = null; this.stats.loaded--;
    if (t.lod) this.stats.detailTris -= t.tris;
    this.dirty = true;
  }

  private stream() {                                // nearest detail tiles within the radius, inside the triangle budget
    if (!this.tiles.length) return;
    const p = this.camera === this.ortho ? this.controls.target : this.camera.position;
    const near = this.tiles.filter((t) => t.lod === 1).map((t) => [t.box.distanceToPoint(p), t] as const)
      .filter(([d, t]) => d < this.radius && !this.clipped(t)).sort((a, b) => a[0] - b[0]);
    const want = new Set<Tile>(); let tris = 0;
    for (const [, t] of near) { if (tris + t.tris > this.budget && want.size) break; want.add(t); tris += t.tris; }
    for (const t of this.tiles) if (t.lod === 1 && (t.mesh || t.loading) && !want.has(t) && !t.pinned) this.unloadTile(t);
    for (const t of want) if (this.stats.inflight < 6) this.loadTile(t);
    this.stats.wanted = want.size;
  }

  private clipped(t: Tile) {                          // whole tile on the removed side of a clip plane
    return this.clipPlanes.some((pl) => {
      const c = [t.box.min, t.box.max];
      for (let k = 0; k < 8; k++) if (pl.distanceToPoint(new THREE.Vector3(c[k & 1].x, c[(k >> 1) & 1].y, c[(k >> 2) & 1].z)) >= 0) return false;
      return true;
    });
  }

  private loop = () => {
    if (this.disposed) return;
    requestAnimationFrame(this.loop);
    if (this.controls.update()) this.dirty = true;
    if (!this.material) return;
    if (this.frames % 15 === 0) this.stream();
    this.frames++;
    if (!this.dirty) return;
    this.render();
    this.dirty = false;
  };

  render() {
    if (!this.material) return;                   // nothing loaded yet
    const r = this.renderer;
    r.setClearColor(this.bg, 1);
    r.autoClear = true;
    this.overlay.visible = false;
    this.material.transparent = false; this.material.depthWrite = true; this.material.uniforms.uPass.value = 0;
    r.render(this.scene, this.camera);
    r.autoClear = false;
    if (this.hasGhosts) {
      this.material.transparent = true; this.material.depthWrite = false; this.material.uniforms.uPass.value = 1;
      r.render(this.scene, this.camera);
      this.material.transparent = false; this.material.depthWrite = true; this.material.uniforms.uPass.value = 0;
    }
    if (this.edgesOn) this.renderEdges();
    if (this.overlay.children.length) {
      this.overlay.visible = true;
      const vis = this.scene.children.filter((c) => c !== this.overlay && c.visible);
      vis.forEach((c) => { c.visible = false; });
      r.render(this.scene, this.camera);
      vis.forEach((c) => { c.visible = true; });
    }
    r.autoClear = true;
    if (this.stats.firstFrame === null && r.info.render.triangles > 0) this.stats.firstFrame = performance.now() - this.t0;
  }

  // ---------------------------------------------------------------- edges: element ids at full resolution, a line
  // wherever neighbouring pixels belong to different elements (or to nothing). Clipping applies, so cuts keep their edges.
  private idTarget = new THREE.WebGLRenderTarget(1, 1, { minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter });
  private edgeCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private edgeMat = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3, transparent: true, depthTest: false, depthWrite: false,
    uniforms: { uId: { value: null as THREE.Texture | null }, uPx: { value: new THREE.Vector2() }, uColor: { value: new THREE.Vector4(0, 0, 0, 0.55) } },
    vertexShader: "out vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
    fragmentShader: `precision highp float; uniform sampler2D uId; uniform vec2 uPx; uniform vec4 uColor; in vec2 vUv; out vec4 o;
      void main() {
        vec4 c = texture(uId, vUv);
        float e = 0.0;
        e += float(texture(uId, vUv + vec2(uPx.x, 0.0)) != c);
        e += float(texture(uId, vUv + vec2(0.0, uPx.y)) != c);
        e += float(texture(uId, vUv - vec2(uPx.x, 0.0)) != c);
        e += float(texture(uId, vUv - vec2(0.0, uPx.y)) != c);
        if (e < 0.5) discard;
        o = vec4(uColor.rgb, uColor.a * min(1.0, e * 0.5));
      }`,
  });
  private edgeQuad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.edgeMat);
  private edgeScene = new THREE.Scene().add(this.edgeQuad);
  edgeColor = new THREE.Vector4(0, 0, 0, 0.55);
  private inkSrgb = new THREE.Color("#c9ccd2").convertLinearToSRGB();

  private renderEdges() {
    const r = this.renderer, w = r.domElement.width, h = r.domElement.height;
    if (this.idTarget.width !== w || this.idTarget.height !== h) this.idTarget.setSize(w, h);
    const vis = this.overlay.visible; this.overlay.visible = false;
    this.material.uniforms.uPass.value = 2;
    r.setRenderTarget(this.idTarget); r.setClearColor(0, 0); r.clear(); r.render(this.scene, this.camera);
    r.setRenderTarget(null); this.material.uniforms.uPass.value = 0; this.overlay.visible = vis;
    r.setClearColor(this.bg, 1);
    this.edgeMat.uniforms.uId.value = this.idTarget.texture;
    this.edgeMat.uniforms.uPx.value.set(1 / w, 1 / h);
    // outlines on shaded faces: soft dark; Lines / X-ray: the theme's ink so they read on the background
    const ink = this.mode === "lines" ? 0.85 : this.mode === "xray" ? 0.5 : 0;
    if (ink) this.edgeMat.uniforms.uColor.value.set(this.inkSrgb.r, this.inkSrgb.g, this.inkSrgb.b, ink);
    else this.edgeMat.uniforms.uColor.value.copy(this.edgeColor);
    r.autoClear = false; r.render(this.edgeScene, this.edgeCam);
  }

  private hasGhosts = false;
  /** Write the element texture after changing `state`. */
  commit() {
    if (!this.index) return;                       // not loaded yet: nothing to draw
    let g = false;
    for (let i = 3; i < this.index.elements * 4; i += 4) { const a = this.state[i]; if (a > 0 && a < 255) { g = true; break; } }
    this.hasGhosts = g;
    this.tex.needsUpdate = true; this.dirty = true;
  }

  pick(x: number, y: number): number | null {
    if (!this.material) return null;
    const dpr = this.renderer.getPixelRatio(), w = this.renderer.domElement.width, h = this.renderer.domElement.height;
    const cam = this.camera;
    cam.setViewOffset(w, h, x * dpr, y * dpr, 1, 1);
    this.material.uniforms.uPass.value = 2;
    this.overlay.visible = false;
    this.renderer.setRenderTarget(this.pickTarget); this.renderer.setClearColor(0, 0); this.renderer.clear();
    this.renderer.render(this.scene, cam);
    const px = new Uint8Array(4); this.renderer.readRenderTargetPixels(this.pickTarget, 0, 0, 1, 1, px);
    this.renderer.setRenderTarget(null); this.material.uniforms.uPass.value = 0; cam.clearViewOffset();
    this.dirty = true;
    const id = px[0] + px[1] * 256 + px[2] * 65536;
    return id ? id - 1 : null;
  }

  // ---------------------------------------------------------------- element state
  /** stable ids (IFC GlobalId) -> element indices; aggregates (stairs, zones) resolve to their parts */
  indices(ids: (string | null | undefined)[]): number[] {
    const out: number[] = [];
    if (!this.index) return out;
    for (const id of ids) {
      if (!id) continue;
      const i = this.byId.get(id);
      if (i !== undefined) out.push(i);
      else for (const p of this.index.aliases?.[id] ?? []) { const k = this.byId.get(p); if (k !== undefined) out.push(k); }
    }
    return out;
  }
  isShown(i: number) { return this.state[i * 4 + 3] > 0; }

  // Element look is composed from explicit state, so modes, solo, colour-by, finding focus, hide and selection combine.
  // alpha: 0 hidden · GHOST x-ray · 255 solid.  rgb: finding paint > colour-by > model colour; selection / hover on top.
  disc: Uint8Array = new Uint8Array(0);             // discipline index per element (index.groups)
  deckOf: Int16Array = new Int16Array(0);
  paint = new Map<number, [number, number, number]>();
  focus: { ids: Set<number>; rest: "ghost" | "hide" } | null = null;
  userHidden = new Set<number>();
  discOff = new Set<number>();
  solo: number | null = null;
  colourBy: { kind: "model" | "discipline" | "values"; rgb?: Map<number, [number, number, number]> | ((i: number) => [number, number, number] | null) } = { kind: "model" };
  discRgb: [number, number, number][] = [];

  compose() {
    if (!this.index) return;
    const n = this.index.elements, st = this.state, base = this.base, xray = this.mode === "xray";
    const by = this.colourBy;
    for (let i = 0; i < n; i++) {
      const o = i * 4;
      let a: number;
      if (base[o + 3] === 0 && !(this.focus?.ids.has(i))) a = 0;                 // spaces: shown only when focused
      else if (this.userHidden.has(i) || this.discOff.has(this.disc[i])) a = 0;
      else if (this.focus) a = this.focus.ids.has(i) ? 255 : this.focus.rest === "hide" ? 0 : GHOST;
      else if (this.solo !== null) a = this.disc[i] === this.solo ? 255 : GHOST;
      else a = xray ? GHOST : 255;
      const p = this.paint.get(i);
      let c: ArrayLike<number> | null = p ?? null;
      if (!c && by.kind === "discipline") c = this.discRgb[this.disc[i]] ?? null;
      else if (!c && by.kind === "values" && by.rgb) c = typeof by.rgb === "function" ? by.rgb(i) : by.rgb.get(i) ?? null;
      if (c) { st[o] = c[0]; st[o + 1] = c[1]; st[o + 2] = c[2]; } else { st[o] = base[o]; st[o + 1] = base[o + 1]; st[o + 2] = base[o + 2]; }
      st[o + 3] = a;
    }
    if (this.selected !== null) st.set([255, 210, 90], this.selected * 4);
    if (this.hovered !== null && this.hovered !== this.selected) {
      const o = this.hovered * 4; st[o] = Math.min(255, st[o] + 60); st[o + 1] = Math.min(255, st[o + 1] + 60); st[o + 2] = Math.min(255, st[o + 2] + 80);
    }
    this.commit();
  }

  private hover(i: number | null) {
    if (i === this.hovered) return;
    this.hovered = i;
    this.compose();
    this.renderer.domElement.style.cursor = i === null ? "" : "pointer";
    this.onHover?.(i);
  }
  select(i: number | null) { this.selected = i; this.hovered = null; this.compose(); }
  setPaint(p: Map<number, [number, number, number]>) { this.paint = p; this.compose(); }
  /** solid = these, everything else ghosted (x-ray) or hidden; null clears */
  isolate(ids: number[] | null, rest: "ghost" | "hide" = "hide") { this.focus = ids ? { ids: new Set(ids), rest } : null; this.compose(); }
  hide(ids: number[]) { ids.forEach((i) => this.userHidden.add(i)); this.compose(); }
  showAll() { this.focus = null; this.userHidden.clear(); this.compose(); }
  setDiscipline(d: number, visible: boolean) { if (visible) this.discOff.delete(d); else this.discOff.add(d); this.compose(); }
  setSolo(d: number | null) { this.solo = d; this.compose(); }
  setColourBy(c: ShipViewer["colourBy"]) { this.colourBy = c; this.compose(); }
  setMode(m: DisplayMode) {
    this.mode = m;
    if (this.material) {
      this.material.wireframe = m === "wireframe";
      this.material.uniforms.uLight.value = m === "realistic" ? 1 : 0;
      this.material.uniforms.uFill.value = m === "lines" ? 1 : 0;
    }
    this.compose();
  }
  get edgesOn() { return this.mode === "edges" || this.mode === "lines" || this.mode === "xray"; }

  // ---------------------------------------------------------------- camera
  boxOf(ids: number[]): THREE.Box3 {
    const b = new THREE.Box3();
    for (const i of ids) {
      const t = this.tileOf(i);
      if (t) b.union(t.box);              // tile box first; precise boxes come from meta (bbox) when the caller has it
    }
    return b;
  }
  get modelBox() { return new THREE.Box3(new THREE.Vector3(...this.index.box[0]), new THREE.Vector3(...this.index.box[1])); }

  fit(box: THREE.Box3 = this.modelBox, dir?: THREE.Vector3, minRadius = 0) {
    const s = box.getBoundingSphere(new THREE.Sphere());
    const r = Math.max(s.radius, minRadius);
    const d = (dir ?? this.camera.position.clone().sub(this.controls.target).normalize()).clone().normalize();
    const dist = r / Math.sin(THREE.MathUtils.degToRad(this.persp.fov / 2)) * 1.05;
    this.controls.target.copy(s.center);
    this.persp.position.copy(s.center).addScaledVector(d, dist);
    this.ortho.position.copy(s.center).addScaledVector(d, Math.max(dist, 50));
    const aspect = this.host.clientWidth / Math.max(1, this.host.clientHeight);
    this.ortho.zoom = 1;
    this.ortho.left = -r * 1.1 * aspect; this.ortho.right = r * 1.1 * aspect; this.ortho.top = r * 1.1; this.ortho.bottom = -r * 1.1;
    this.ortho.near = -dist * 4; this.ortho.far = dist * 4;
    this.persp.near = Math.max(0.02, dist / 2000); this.persp.far = dist * 8;
    this.persp.updateProjectionMatrix(); this.ortho.updateProjectionMatrix();
    this.controls.update(); this.dirty = true;
  }

  view(name: ViewName) {
    if (!this.index) return;
    const dirs: Record<ViewName, [number, number, number]> = {
      iso: [ISO_DIR.x, ISO_DIR.y, ISO_DIR.z], top: [0, -0.0001, 1], port: [0, 1, 0], starboard: [0, -1, 0], bow: [1, 0, 0], stern: [-1, 0, 0] };
    this.fit(this.modelBox, new THREE.Vector3(...dirs[name]));
  }

  setProjection(kind: "perspective" | "orthographic") {
    const next = kind === "orthographic" ? this.ortho : this.persp;
    if (next === this.camera) return;
    const dir = this.camera.position.clone().sub(this.controls.target).normalize();
    this.camera = next; this.controls.object = next;
    this.fit(this.currentFocusBox ?? this.modelBox, dir);
  }
  currentFocusBox: THREE.Box3 | null = null;

  // ---------------------------------------------------------------- clipping
  /** deck slider: everything above `z` is clipped; null clears */
  setDeckClip(z: number | null) {
    if (this.deckClip) this.clipPlanes.splice(this.clipPlanes.indexOf(this.deckClip), 1);
    this.deckClip = z === null ? null : new THREE.Plane(new THREE.Vector3(0, 0, -1), z);
    if (this.deckClip) this.clipPlanes.push(this.deckClip);
    this.clipsChanged();
  }
  /** the shader is compiled for a number of clip planes: recompile when it changes */
  clipsChanged() {
    if (this.material) this.material.needsUpdate = true;
    this.dirty = true;
  }
  /** z of each deck's floor: lowest structure tile of the deck (meta-free estimate, good enough for the slider) */
  deckLevels(): { deck: number; z: number; top: number }[] {
    const m = new Map<number, number[]>();
    for (const t of this.tiles) { const a = m.get(t.deck) ?? []; a.push(t.min[2]); m.set(t.deck, a); }
    const decks = [...m.keys()].filter((d) => d > 0).sort((a, b) => a - b);
    const floor = (d: number) => { const a = (m.get(d) ?? []).sort((x, y) => x - y); return a[Math.floor(a.length * 0.25)] ?? 0; };
    return decks.map((d, k) => ({ deck: d, z: floor(d), top: k + 1 < decks.length ? floor(decks[k + 1]) - 0.05 : this.index.box[1][2] }));
  }

  setTheme(bg: string, ghost: string, edge?: [number, number, number, number], ink?: string) {
    if (ink) this.inkSrgb.set(ink).convertLinearToSRGB();
    this.bg.set(bg); this.ghostRgb.set(ghost); if (edge) this.edgeColor.set(...edge);
    this.bgSrgb.copy(this.bg).convertLinearToSRGB(); this.ghostSrgb.copy(this.ghostRgb).convertLinearToSRGB(); this.dirty = true;
  }
  setLight(realistic: boolean) { if (!this.material) return; this.material.uniforms.uLight.value = realistic ? 1 : 0; this.dirty = true; }
  invalidate() { this.dirty = true; }

  private resize() {
    const w = this.host.clientWidth, h = this.host.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    this.persp.aspect = w / h; this.persp.updateProjectionMatrix();
    if (this.index) { const half = (this.ortho.top - this.ortho.bottom) / 2; this.ortho.left = -half * w / h; this.ortho.right = half * w / h; this.ortho.updateProjectionMatrix(); }
    this.dirty = true;
  }

  dispose() {
    this.disposed = true;
    this.ro.disconnect();
    this.controls.dispose();
    for (const t of this.tiles) if (t.mesh) t.mesh.geometry.dispose();
    this.tex?.dispose(); this.material?.dispose(); this.pickTarget.dispose(); this.idTarget.dispose(); this.edgeMat.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}
