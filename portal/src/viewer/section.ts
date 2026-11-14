// Section maths (spec A3, DECISIONS M5/M6), free of three.js so `node --test` runs it (section.test.ts).
// Ship frame: x forward (bow = +x), y to port, z up, metres. Cross section = plane x = const (a frame), longitudinal =
// y = const (offset from centreline), deck plan = z = const. Every cut is axis-aligned.
// Plane convention = three.js clipping: points with n·p + c >= 0 are kept, the rest is cut away.

export type CutKind = "cross" | "long" | "deck";
export type Cut = { kind: CutKind; pos: number; flip: boolean };
export type Grid = { frame0_x: number; spacing_m: number; source?: string };
export type DeckLevel = { deck: number; z: number };
export type Box = [number[], number[]];

export const AXIS: Record<CutKind, 0 | 1 | 2> = { cross: 0, long: 1, deck: 2 };
export const KIND_LABEL: Record<CutKind, string> = { cross: "Cross section", long: "Longitudinal", deck: "Deck plan" };
export const PLAN_HEIGHT = 1.5;      // deck plan cut height above the deck (GA convention: through doors and windows)
const STEP_M = 0.1;                  // single step for longitudinal / deck cuts

/** Unflipped keeps the low side (aft, starboard, below); flipped keeps the high side. */
export function plane(c: Cut): { normal: [number, number, number]; constant: number } {
  const n: [number, number, number] = [0, 0, 0];
  n[AXIS[c.kind]] = c.flip ? 1 : -1;
  return { normal: n, constant: c.flip ? -c.pos : c.pos };
}
export const keeps = (c: Cut, p: number[]) => { const { normal: n, constant } = plane(c); return n[0] * p[0] + n[1] * p[1] + n[2] * p[2] + constant >= 0; };

/** "Cut removes the near side": the flip that throws away the side the camera is on. */
export const nearSideFlip = (kind: CutKind, pos: number, camera: number[]) => camera[AXIS[kind]] < pos;

/** Direction from the cut towards the camera that faces it (the removed side). */
export function faceDir(c: Cut): [number, number, number] {
  const n = plane(c).normal;
  const d: [number, number, number] = [-n[0], -n[1], -n[2]];
  if (c.kind === "deck") d[1] = -1e-4;     // looking straight down: OrbitControls needs a hint which way is "up" on screen
  return d;
}

export const frameAt = (x: number, g: Grid) => (x - g.frame0_x) / g.spacing_m;
export const xOfFrame = (f: number, g: Grid) => g.frame0_x + f * g.spacing_m;
const r1 = (v: number) => Math.round(v * 10) / 10;

export function range(kind: CutKind, box: Box): [number, number] { const a = AXIS[kind]; return [box[0][a], box[1][a]]; }

/** Cross sections sit on frames; the others on 0.1 m. */
export function snap(kind: CutKind, pos: number, g: Grid): number {
  return kind === "cross" ? xOfFrame(Math.round(frameAt(pos, g)), g) : r1(pos);
}

export function clampTo(kind: CutKind, pos: number, box: Box): number {
  const [lo, hi] = range(kind, box);
  return Math.min(hi, Math.max(lo, pos));
}

/** One arrow-key step: a frame (cross) or 0.1 m; `big` (Shift) = 10 steps. Stays inside the model box. */
export function step(kind: CutKind, pos: number, dir: 1 | -1, g: Grid, box: Box, big = false): number {
  const d = (kind === "cross" ? g.spacing_m : STEP_M) * (big ? 10 : 1) * dir;
  const [lo, hi] = range(kind, box);
  const next = snap(kind, pos + d, g);
  // a snap can land outside the box at the ends; keep the last frame inside instead
  if (next > hi + 1e-9) return snap(kind, hi - (kind === "cross" ? g.spacing_m / 2 : 0), g);
  if (next < lo - 1e-9) return snap(kind, lo + (kind === "cross" ? g.spacing_m / 2 : 0), g);
  return next;
}

/** Deck the cut is on: the highest deck whose floor is at or below z. */
export function deckBelow(z: number, decks: DeckLevel[]): DeckLevel | null {
  let best: DeckLevel | null = null;
  for (const d of decks) if (d.z <= z + 1e-6 && (!best || d.z > best.z)) best = d;
  return best;
}

/** Live readout: "Fr 152", "3.2 m PS of CL", "Deck 5 + 1.5 m" (main) and the coordinate behind it (sub). */
export function readout(kind: CutKind, pos: number, g: Grid, decks: DeckLevel[], box: Box): { main: string; sub: string } {
  if (kind === "cross") {
    const f = frameAt(pos, g), fr = Math.round(f), off = (f - fr) * g.spacing_m;
    const main = Math.abs(off) < 0.005 ? `Fr ${fr}` : `Fr ${fr} ${off > 0 ? "+" : "−"} ${Math.abs(off).toFixed(2)} m`;
    return { main, sub: `${(pos - box[0][0]).toFixed(1)} m from aft end` };
  }
  if (kind === "long") {
    const y = r1(pos);
    const main = Math.abs(y) < 0.05 ? "On CL" : `${Math.abs(y).toFixed(1)} m ${y > 0 ? "PS" : "SB"} of CL`;
    return { main, sub: `y ${pos.toFixed(2)} m` };
  }
  const d = deckBelow(pos, decks);
  const main = d ? `Deck ${d.deck} + ${(pos - d.z).toFixed(1)} m` : `${(pos - box[0][2]).toFixed(1)} m above keel`;
  return { main, sub: `z ${pos.toFixed(2)} m` };
}

/** Short label for a cut chip. */
export const chip = (c: Cut, g: Grid, decks: DeckLevel[], box: Box) => readout(c.kind, c.pos, g, decks, box).main;

/** "Section at finding": a deck plan through the room when the finding has a plan box on a deck (escape, doors,
 *  corridors), otherwise a cross section on the frame through the element's centre (plates, pipes). */
export function cutForFinding(f: { evidence?: { bbox?: number[] | null; z?: number | null } | null; elementBox?: number[] | null },
                              g: Grid): Cut | null {
  const ev = f.evidence;
  if (ev?.bbox && ev.z != null) return { kind: "deck", pos: r1(ev.z + PLAN_HEIGHT), flip: false };
  const b = f.elementBox;
  if (b && b.length === 6) return { kind: "cross", pos: snap("cross", (b[0] + b[3]) / 2, g), flip: false };
  return null;
}

/** Plane ∩ triangles for an axis-aligned plane, on a tile as stored: uint16 positions (x, y, z, element) per vertex,
 *  world = q * scale + offset. Returns segment end points in world metres and the element (tile-local) of each
 *  segment. Triangles lying in the plane give nothing (their neighbours give the outline). */
export function sliceTile(q: Uint16Array, stride: number, idx: Uint32Array | Uint16Array, scale: number[], offset: number[],
                          axis: 0 | 1 | 2, value: number): { seg: Float32Array; elem: Uint16Array } {
  const t = (value - offset[axis]) / scale[axis];
  const out: number[] = [], el: number[] = [];
  const P = [0, 0, 0];
  const put = (i: number, j: number, k: number) => {   // the point on edge i-j where the coordinate crosses t
    const a = q[i * stride + axis], b = q[j * stride + axis], s = (t - a) / (b - a);
    for (let c = 0; c < 3; c++) P[c] = (q[i * stride + c] + s * (q[j * stride + c] - q[i * stride + c])) * scale[c] + offset[c];
    out.push(P[0], P[1], P[2]);
    if (k >= 0) el.push(q[k * stride + 3]);
  };
  for (let f = 0; f < idx.length; f += 3) {
    const i0 = idx[f], i1 = idx[f + 1], i2 = idx[f + 2];
    const d0 = q[i0 * stride + axis] - t, d1 = q[i1 * stride + axis] - t, d2 = q[i2 * stride + axis] - t;
    // a vertex exactly on the plane counts as above: each crossing edge then has one end strictly on each side
    const s0 = d0 >= 0, s1 = d1 >= 0, s2 = d2 >= 0;
    if (s0 === s1 && s1 === s2) continue;
    // the lone vertex is on one side, the other two on the other; the segment joins its two edges
    const [a, b, c] = s0 === s1 ? [i2, i0, i1] : s0 === s2 ? [i1, i2, i0] : [i0, i1, i2];
    put(a, b, -1); put(a, c, a);
  }
  return { seg: new Float32Array(out), elem: new Uint16Array(el) };
}
