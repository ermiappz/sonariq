// Caps and section edges for cuts (spec A3, DECISIONS M5).
// Caps: the stencil method. For each cut and each group of closed solids, the tiles crossing the plane are drawn into
// the stencil only (back faces +1, front faces −1, clipped by that one plane); where the count is not 0 the pixel
// lies inside a cut solid, and a quad on the plane fills it with the group's colour. Groups whose meshes are not
// guaranteed closed (pipes, ducts, cables, equipment from the CAD export) get no cap, only section outlines: a cap
// over an open mesh would leak across the screen.
// Edges: plane ∩ triangles on the CPU, in a worker, for every loaded tile crossing the plane (section.worker.ts).
import * as THREE from "three";
import { AXIS, plane, type Cut } from "./section";

export const CLOSED_GROUPS = new Set(["structure", "architecture"]);

export const toPlane = (c: Cut) => { const p = plane(c); return new THREE.Plane(new THREE.Vector3(...p.normal), p.constant); };

/** Whether a box straddles an axis-aligned cut (only those tiles can have a cap or an edge there). */
export const crosses = (box: THREE.Box3, c: Cut) => { const a = AXIS[c.kind]; return box.min.getComponent(a) < c.pos && box.max.getComponent(a) > c.pos; };

/** The two stencil-count passes for one cut: the tile shader as is (hidden / ghosted elements still discard), no
 *  colour, no depth, clipped by that cut's plane only. Uniforms are shared with the tile material. */
export function stencilMaterials(tile: THREE.ShaderMaterial, pl: THREE.Plane): [THREE.ShaderMaterial, THREE.ShaderMaterial] {
  return ([[THREE.BackSide, THREE.IncrementWrapStencilOp], [THREE.FrontSide, THREE.DecrementWrapStencilOp]] as const).map(([side, op]) => {
    const m = tile.clone();
    m.uniforms = tile.uniforms;
    Object.assign(m, { side, wireframe: false, transparent: false, colorWrite: false, depthWrite: false, depthTest: false,
      stencilWrite: true, stencilFunc: THREE.AlwaysStencilFunc, stencilRef: 0, stencilFail: op, stencilZFail: op, stencilZPass: op });
    m.clippingPlanes = [pl];
    return m;
  }) as [THREE.ShaderMaterial, THREE.ShaderMaterial];
}

/** Flat fill on the plane where the stencil is not 0; clipped by the other planes; writes depth so edges sort on it.
 *  Colours are sRGB bytes / 255 like the tile shader's. */
export function capMesh(c: Cut, box: THREE.Box3, others: THREE.Plane[]): THREE.Mesh<THREE.PlaneGeometry, THREE.ShaderMaterial> {
  const size = box.getSize(new THREE.Vector3()), ctr = box.getCenter(new THREE.Vector3());
  const a = AXIS[c.kind];
  const [u, v] = a === 0 ? [size.y, size.z] : a === 1 ? [size.x, size.z] : [size.x, size.y];
  const mat = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3, clipping: true, side: THREE.DoubleSide,
    stencilWrite: true, stencilFunc: THREE.NotEqualStencilFunc, stencilRef: 0,
    stencilFail: THREE.KeepStencilOp, stencilZFail: THREE.KeepStencilOp, stencilZPass: THREE.ZeroStencilOp,
    uniforms: { uColor: { value: new THREE.Color() } },
    vertexShader: `#include <clipping_planes_pars_vertex>
      void main() { vec4 mvPosition = modelViewMatrix * vec4(position, 1.0); gl_Position = projectionMatrix * mvPosition;
        #include <clipping_planes_vertex>
      }`,
    fragmentShader: `precision highp float; uniform vec3 uColor; out vec4 o;
      #include <clipping_planes_pars_fragment>
      void main() {
        #include <clipping_planes_fragment>
        o = vec4(uColor, 1.0); }`,
  });
  mat.clippingPlanes = others;
  const m = new THREE.Mesh(new THREE.PlaneGeometry(u * 1.2 + 1, v * 1.2 + 1), mat);
  if (a === 0) m.rotation.y = Math.PI / 2;
  else if (a === 1) m.rotation.x = Math.PI / 2;
  m.position.copy(ctr).setComponent(a, c.pos);
  m.updateMatrixWorld(true);
  m.frustumCulled = false;
  return m;
}

/** Translucent blade with its frame (spec: "position, then cut"). Drawn in the overlay pass, depth-tested. */
export function bladeMesh(c: Cut, box: THREE.Box3, color: THREE.Color): THREE.Group {
  const g = new THREE.Group();
  const size = box.getSize(new THREE.Vector3()), ctr = box.getCenter(new THREE.Vector3());
  const a = AXIS[c.kind];
  const [u, v] = a === 0 ? [size.y, size.z] : a === 1 ? [size.x, size.z] : [size.x, size.y];
  const geo = new THREE.PlaneGeometry(u + 2, v + 2);
  const quad = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.16, side: THREE.DoubleSide, depthWrite: false }));
  const rim = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.9, depthTest: false }));
  quad.name = "blade";
  g.add(quad, rim);
  if (a === 0) g.rotation.y = Math.PI / 2;
  else if (a === 1) g.rotation.x = Math.PI / 2;
  g.position.copy(ctr).setComponent(a, c.pos);
  g.updateMatrixWorld(true);
  return g;
}

export type SliceTile = { f: string; base: number; group: string; mesh: THREE.Mesh | null };
export type SliceOut = { tile: SliceTile; seg: Float32Array; elem: Uint16Array };

/** Client of section.worker.ts: sends a tile's quantised arrays once, then slices by key. */
export class Slicer {
  private worker: Worker | null = null;
  private sent = new Set<string>();
  private wait = new Map<number, (r: { key: string; seg: Float32Array; elem: Uint16Array }[]) => void>();
  private id = 0;

  private get w(): Worker {
    if (!this.worker) {
      this.worker = new Worker(new URL("./section.worker.ts", import.meta.url), { type: "module" });
      this.worker.onmessage = (e) => { const f = this.wait.get(e.data.id); this.wait.delete(e.data.id); f?.(e.data.out); };
    }
    return this.worker;
  }

  private send(t: SliceTile) {
    if (this.sent.has(t.f) || !t.mesh) return;
    const geo = t.mesh.geometry, pa = geo.attributes.position, ba = geo.attributes._batchid;
    const n = pa.count, q = new Uint16Array(n * 4);
    const il = pa as THREE.InterleavedBufferAttribute;
    if (il.isInterleavedBufferAttribute && il.data.stride === 4 && il.offset === 0 && il.data.array instanceof Uint16Array
        && (ba as THREE.InterleavedBufferAttribute).offset === 3) q.set(il.data.array.subarray(0, n * 4));
    else for (let i = 0; i < n; i++) { q[i * 4] = pa.getX(i); q[i * 4 + 1] = pa.getY(i); q[i * 4 + 2] = pa.getZ(i); q[i * 4 + 3] = ba.getX(i); }
    const idx = (geo.index!.array as Uint32Array).slice();
    const tile = { q, idx, scale: t.mesh.scale.toArray(), offset: t.mesh.position.toArray() };
    this.w.postMessage({ type: "tile", key: t.f, tile }, [q.buffer, idx.buffer]);
    this.sent.add(t.f);
  }

  drop(f: string) { if (this.sent.delete(f)) this.w.postMessage({ type: "drop", key: f }); }

  slice(c: Cut, tiles: SliceTile[]): Promise<SliceOut[]> {
    const live = tiles.filter((t) => t.mesh);
    live.forEach((t) => this.send(t));
    const by = new Map(live.map((t) => [t.f, t]));
    const id = ++this.id;
    return new Promise((res) => {
      this.wait.set(id, (out) => res(out.filter((o) => by.has(o.key)).map((o) => ({ tile: by.get(o.key)!, seg: o.seg, elem: o.elem }))));
      this.w.postMessage({ type: "slice", id, axis: AXIS[c.kind], value: c.pos, keys: live.map((t) => t.f) });
    });
  }

  dispose() { this.worker?.terminate(); this.worker = null; this.sent.clear(); this.wait.clear(); }
}

/** Line segments from slice results, coloured per segment; `keep(i)` filters by element (hidden / ghosted out). */
export function edgeLines(out: SliceOut[], color: (t: SliceTile) => THREE.Color, keep: (i: number) => boolean,
                          shift: THREE.Vector3, clip: THREE.Plane[], opacity = 1): THREE.LineSegments | null {
  let n = 0;
  for (const o of out) n += o.elem.length;
  if (!n) return null;
  const pos = new Float32Array(n * 6), col = new Float32Array(n * 6);
  let k = 0;
  for (const o of out) {
    const c = color(o.tile);
    for (let s = 0; s < o.elem.length; s++) {
      if (!keep(o.tile.base + o.elem[s])) continue;
      for (let e = 0; e < 2; e++) {
        pos[k] = o.seg[s * 6 + e * 3] + shift.x; pos[k + 1] = o.seg[s * 6 + e * 3 + 1] + shift.y; pos[k + 2] = o.seg[s * 6 + e * 3 + 2] + shift.z;
        col[k] = c.r; col[k + 1] = c.g; col[k + 2] = c.b; k += 3;
      }
    }
  }
  if (!k) return null;
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos.subarray(0, k), 3));
  g.setAttribute("color", new THREE.BufferAttribute(col.subarray(0, k), 3));
  const m = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ vertexColors: true, transparent: opacity < 1, opacity, clippingPlanes: clip }));
  m.frustumCulled = false;
  return m;
}
