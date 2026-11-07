// 3D toggle (context only): That Open Engine world (same setup as W4) with a Deck 4–7 stack built from the
// engine's Deck 5 geometry, the stair shafts, Deck 5 people from the replay, and the other decks' people
// waiting at each stair (inflow_wait_series). The 2D replay stays the main view.
import { useEffect, useRef } from "react";
import * as OBC from "@thatopen/components";
import * as THREE from "three";
import type { SimReplay } from "../api";

const DECK_H = 2.9; // m between decks (display only)

function shape(r: { outer: number[][]; holes: number[][][] }) {
  const s = new THREE.Shape(r.outer.map((p) => new THREE.Vector2(p[0], p[1])));
  r.holes.forEach((h) => s.holes.push(new THREE.Path(h.map((p) => new THREE.Vector2(p[0], p[1])))));
  return s;
}

export default function Deck3D({ rep, t, height = 400 }: { rep: SimReplay; t: number; height?: number }) {
  const host = useRef<HTMLDivElement>(null);
  const live = useRef<{ people: THREE.InstancedMesh; waiting: Record<string, THREE.InstancedMesh>; render: () => void } | null>(null);

  useEffect(() => {
    if (!host.current) return;
    const components = new OBC.Components();
    const world = components.get(OBC.Worlds).create<OBC.SimpleScene, OBC.SimpleCamera, OBC.SimpleRenderer>();
    world.scene = new OBC.SimpleScene(components);
    world.renderer = new OBC.SimpleRenderer(components, host.current);
    world.camera = new OBC.SimpleCamera(components);
    components.init();
    world.scene.setup();
    const css = getComputedStyle(host.current);
    const scene = world.scene.three as THREE.Scene;
    scene.background = new THREE.Color(css.getPropertyValue("--plan-bg").trim() || "#17191c");
    const ink = new THREE.Color(css.getPropertyValue("--fg-1").trim() || "#eeeeee");
    const faint = new THREE.Color(css.getPropertyValue("--fg-3").trim() || "#777777");
    const root = new THREE.Group();
    root.rotation.x = -Math.PI / 2; // model x, y, z-up -> three
    scene.add(root);
    const g = rep.geometry;
    const rings = Array.isArray(g.walkable) ? g.walkable : [g.walkable];
    [4, 5, 6, 7].forEach((deck) => {
      const z = (deck - 5) * DECK_H;
      rings.forEach((r) => {
        const m = new THREE.Mesh(new THREE.ShapeGeometry(shape(r)),
          new THREE.MeshBasicMaterial({ color: deck === 5 ? 0x2a2d33 : 0x202227, transparent: true, opacity: deck === 5 ? 0.95 : 0.35, side: THREE.DoubleSide }));
        m.position.z = z;
        root.add(m);
        const e = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.ShapeGeometry(shape(r))), new THREE.LineBasicMaterial({ color: deck === 5 ? ink : faint, transparent: true, opacity: deck === 5 ? 0.7 : 0.25 }));
        e.position.z = z + 0.01;
        root.add(e);
      });
    });
    // Deck 5 walls as thin boxes
    g.walls.forEach((w) => {
      const xs = w.poly.outer.map((p) => p[0]), ys = w.poly.outer.map((p) => p[1]);
      const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
      const h = w.rating === "A-60" ? 2.4 : 1.6;
      const b = new THREE.Mesh(new THREE.BoxGeometry(Math.max(0.05, x1 - x0), Math.max(0.05, y1 - y0), h),
        new THREE.MeshBasicMaterial({ color: faint, transparent: true, opacity: w.rating?.startsWith("A") ? 0.55 : 0.25 }));
      b.position.set((x0 + x1) / 2, (y0 + y1) / 2, h / 2);
      root.add(b);
    });
    // stair shafts Decks 4-7
    const waiting: Record<string, THREE.InstancedMesh> = {};
    g.stairs.forEach((s) => {
      const xs = s.flight.outer.map((p) => p[0]), ys = s.flight.outer.map((p) => p[1]);
      const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
      const shaft = new THREE.Mesh(new THREE.BoxGeometry(x1 - x0, y1 - y0, 3 * DECK_H + 2.4),
        new THREE.MeshBasicMaterial({ color: ink, transparent: true, opacity: 0.08 }));
      shaft.position.set((x0 + x1) / 2, (y0 + y1) / 2, (-DECK_H + 2 * DECK_H + 2.4) / 2);
      root.add(shaft);
      root.add(Object.assign(new THREE.LineSegments(new THREE.EdgesGeometry(shaft.geometry), new THREE.LineBasicMaterial({ color: ink, transparent: true, opacity: 0.4 })), { position: shaft.position.clone() }));
      const im = new THREE.InstancedMesh(new THREE.SphereGeometry(0.2, 8, 6), new THREE.MeshBasicMaterial({ color: faint }), 400);
      im.count = 0;
      im.userData = { x: (x0 + x1) / 2, y: (y0 + y1) / 2, w: x1 - x0 };
      root.add(im);
      waiting[s.name] = im;
    });
    const people = new THREE.InstancedMesh(new THREE.SphereGeometry(0.22, 10, 8), new THREE.MeshBasicMaterial({ color: ink }), 2000);
    people.count = 0;
    root.add(people);
    const box = new THREE.Box3().setFromObject(root);
    world.camera.controls.fitToBox(box, false).then(() => world.camera.controls.rotateTo(-0.5, 0.95, false))
      .then(() => world.camera.controls.fitToBox(box, false, { paddingTop: 1, paddingBottom: 1, paddingLeft: 1, paddingRight: 1 }));
    live.current = { people, waiting, render: () => world.renderer?.update() };
    return () => { live.current = null; components.dispose(); };
  }, [rep]);

  useEffect(() => {
    const L = live.current;
    if (!L) return;
    const fr = rep.frames;
    let i = 0;
    while (i < fr.length - 1 && fr[i + 1][0] <= t) i++;
    const pts = fr[i]?.[1] ?? [];
    const m = new THREE.Matrix4();
    pts.forEach((p, k) => { m.makeTranslation(p[1], p[2], 0.25); L.people.setMatrixAt(k, m); });
    L.people.count = pts.length;
    L.people.instanceMatrix.needsUpdate = true;
    const si = Math.max(0, Math.floor(t - rep.series_t0_s));
    Object.entries(L.waiting).forEach(([st, im]) => {
      const n = Math.min(400, rep.inflow_wait_series?.[st]?.[si] ?? 0);
      const { x, y, w } = im.userData as { x: number; y: number; w: number };
      for (let k = 0; k < n; k++) {
        const deck = [4, 6, 7][k % 3], row = Math.floor(k / 3);
        m.makeTranslation(x - w / 2 - 0.5 - (row % 6) * 0.45, y + (Math.floor(row / 6) - 1) * 0.45, (deck - 5) * DECK_H + 0.25);
        im.setMatrixAt(k, m);
      }
      im.count = n;
      im.instanceMatrix.needsUpdate = true;
    });
  }, [t, rep]);

  return (
    <div style={{ position: "relative", height, border: "1px solid var(--line)" }}>
      <div ref={host} style={{ position: "absolute", inset: 0 }} />
      <div className="sq-faint" style={{ position: "absolute", left: 8, top: 8, fontSize: 11, background: "var(--bg-1)", padding: "2px 6px" }}>
        3D · Decks 4–7 · context only · people from Decks 4, 6, 7 shown waiting at their stair</div>
    </div>
  );
}
