// Studio 3D on the whole-ship tile viewer (DECISIONS M1). The engine prepares a web version of the exact file of the
// run (POST /models/prepare, cached by content hash); this component shows progress, loads the tiles and draws the
// engine's findings on them. Every number on screen comes from the finding JSON; the viewer only places it.
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { API, HDR, apiFetch, type Check } from "../api";
import { ShipViewer, type ElementRow, type ViewName } from "../viewer/ShipViewer";
import { cutForFinding } from "../viewer/section";
import SectionBar from "./SectionBar";
import Callout, { type CalloutGeo } from "./Callout";
import { fmtVal } from "../viewer/callout";

export type ModelSrc = { revision?: string; path?: string; run?: string; source?: "rcrv" } | null;
export type View = {
  focus: (c: Check) => boolean; isolate: (c: Check) => void; showAll: () => void; zoom: () => void; resetView: () => void;
  paint: (cs: Check[]) => void; setBounds: (b?: number[] | null) => void; viewer: () => ShipViewer | null; modelId: () => string | null;
  /** Section at finding: one cut through the finding (deck plan through its room, else cross section through the part). */
  sectionAt: (c: Check) => Promise<boolean>;
};
type Label = { text: string; x: number; y: number; dashed: boolean; visible: boolean };
type Line = { a: [number, number]; b: [number, number]; text: string; dashed: boolean };

export const STATUS_RGB: Record<string, [number, number, number]> = {
  fail: [213, 94, 0], warn: [230, 159, 0], unk: [201, 205, 212], pass: [0, 158, 115], dor: [149, 154, 164] };
const hex = (c: [number, number, number]) => (c[0] << 16) | (c[1] << 8) | c[2];
const fmtV = (v: any) => (v?.unit === "mm" && typeof v.value === "number" ? `${v.value.toLocaleString("en-US")} mm` : `${v?.value} ${v?.unit ?? ""}`.trim());

// Same rule as the FreeCAD panel: positions from the engine's evidence box, labels = engine values as returned.
export function overlaySpec(c: Check): { z: number; lines: Line[]; title: string; bbox: number[] } | null {
  const ev = c.evidence, ms = c.measured, rq = c.required;
  if (!ev?.bbox || ev.z == null || ms?.value == null || rq?.value == null) return null;
  const [x0, y0, x1, y1] = ev.bbox, longY = y1 - y0 >= x1 - x0, off = 0.6, lines: Line[] = [];
  let title: string;
  if (c.rule === "R-FLS-02" && (c as any).extra?.dead_end) {
    if (longY) { lines.push({ a: [x1 + off, y0], b: [x1 + off, y1], text: `depth ${fmtV(ms)}`, dashed: false }); lines.push({ a: [x0, y1 + off], b: [x1, y1 + off], text: `width ${fmtV(rq)} = allowed depth`, dashed: true }); }
    else { lines.push({ a: [x0, y1 + off], b: [x1, y1 + off], text: `depth ${fmtV(ms)}`, dashed: false }); lines.push({ a: [x1 + off, y0], b: [x1 + off, y1], text: `width ${fmtV(rq)} = allowed depth`, dashed: true }); }
    title = `Dead end ${fmtV(ms)} > width ${fmtV(rq)}`;
  } else if (["R-FLS-03", "R-FLS-04", "R-FLS-09", "R-ACC-01"].includes(c.rule) && ms.unit === "mm") {
    const req = (rq.value as number) / 1000;
    if (longY) { const cy = y1 + off, cx = (x0 + x1) / 2; lines.push({ a: [x0, cy], b: [x1, cy], text: `measured ${fmtV(ms)}`, dashed: false }); lines.push({ a: [cx - req / 2, cy + off], b: [cx + req / 2, cy + off], text: `required ${fmtV(rq)}`, dashed: true }); }
    else { const cx = x1 + off, cy = (y0 + y1) / 2; lines.push({ a: [cx, y0], b: [cx, y1], text: `measured ${fmtV(ms)}`, dashed: false }); lines.push({ a: [cx + off, cy - req / 2], b: [cx + off, cy + req / 2], text: `required ${fmtV(rq)}`, dashed: true }); }
    title = `${c.element?.name ?? c.id} · ${fmtV(ms)} measured / ${fmtV(rq)} required`;
  } else return null;
  return { z: ev.z + 0.15, lines, title, bbox: ev.bbox };
}

const ISO = new THREE.Vector3(-0.55, -0.75, 0.42);
const VIEWS: [ViewName, string][] = [["iso", "Iso"], ["top", "Top"], ["port", "Port"], ["starboard", "Stbd"], ["bow", "Bow"], ["stern", "Stern"]];

export default function ShipView({ src, findings, apiRef, onSelectElement, onViewer, onPick, onOpenEvidence }: {
  src: ModelSrc; findings: Check[] | null; apiRef: React.MutableRefObject<View | null>;
  onSelectElement?: (guid: string | null) => void; onViewer?: (v: ShipViewer | null, modelId: string | null) => void;
  /** a pin was clicked: select that finding (Studio list + 3D) */ onPick?: (c: Check) => void;
  /** callout "Open evidence" */ onOpenEvidence?: (c: Check) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const vref = useRef<ShipViewer | null>(null);
  const [state, setState] = useState<"idle" | "preparing" | "loading" | "ready" | "error">("idle");
  const [msg, setMsg] = useState("");
  const [progress, setProgress] = useState(0);
  const [labels, setLabels] = useState<Label[]>([]);
  const [legend, setLegend] = useState<string | null>(null);
  const [props, setProps] = useState<{ i: number; row: ElementRow; meta: Record<string, any> | null } | null>(null);
  const [decks, setDecks] = useState<{ deck: number; z: number; top: number }[]>([]);
  const [deck, setDeck] = useState<number | null>(null);
  const [, bump] = useState(0);
  const [sectionOpen, setSectionOpen] = useState(false);
  const [summary, setSummary] = useState<Record<string, any> | null>(null);
  const key = JSON.stringify(src);
  // callout of the active finding + pins for the others (spec Phase 5)
  const [active, setActive] = useState<{ c: Check; unlocatable: boolean } | null>(null);
  const [geo, setGeo] = useState<CalloutGeo>(null);
  const [pins, setPins] = useState<{ c: Check; x: number; y: number }[]>([]);
  const [vsize, setVsize] = useState({ w: 800, h: 600 });
  const findRef = useRef<Check[] | null>(findings);
  findRef.current = findings;

  useEffect(() => {
    if (!host.current || !src) { setState("idle"); return; }
    let disposed = false, timer = 0, modelId: string | null = null;
    const v = new ShipViewer(host.current);
    vref.current = v;
    (window as any).__sqViewer = v;            // e2e checks (portal/e2e) read stats and pick through this handle
    const theme = () => {
      if (!host.current) return;
      const css = getComputedStyle(host.current);
      v.setTheme(css.getPropertyValue("--plan-bg").trim() || "#17191c", "#8b95a1", undefined, css.getPropertyValue("--fd-ink").trim() || "#c9ccd2");
      v.accent.set(css.getPropertyValue("--accent").trim() || "#e392c8");
    };
    theme();
    // the light / dark toggle swaps a class on the app root: follow it without reloading the model
    const themeObs = new MutationObserver(theme);
    const root = host.current.closest(".sq");
    if (root) themeObs.observe(root, { attributes: true, attributeFilter: ["class"] });
    v.onView = () => bump((n) => n + 1);
    let extras: THREE.Object3D[] = [];
    let labelPts: { text: string; v: THREE.Vector3; dashed: boolean }[] = [];
    let painted: { i: number; rgb: [number, number, number] }[] = [];
    let focusBox: THREE.Box3 | null = null;
    // active finding: anchor box (evidence footprint raised to room height, else the element's box) and its parts
    let act: { c: Check; ids: number[]; box: THREE.Box3 | null } | null = null;
    let occ = false, occKey = "", stillSince = 0, occDone = true;
    const update = () => {
      if (disposed || !host.current) return;
      const cam = v.camera; cam.updateMatrixWorld();
      const w = host.current.clientWidth, h = host.current.clientHeight;
      const scr = (p0: THREE.Vector3) => { const p = p0.clone().project(cam); return { x: (p.x + 1) / 2 * w, y: (1 - p.y) / 2 * h, on: p.z < 1 && Math.abs(p.x) <= 1 && Math.abs(p.y) <= 1 }; };
      const ls = labelPts.map(({ text, v: p0, dashed }) => { const p = p0.clone().project(cam); return { text, dashed, x: (p.x + 1) / 2 * w, y: (1 - p.y) / 2 * h, visible: p.z < 1 && Math.abs(p.x) < 1.2 && Math.abs(p.y) < 1.2 }; });
      // labels never overlap: push a later label down until it clears the earlier ones (width from 12 px mono glyphs)
      for (let i = 1; i < ls.length; i++) for (let j = 0; j < i; j++) {
        const a = ls[i], b = ls[j], ww = (a.text.length + b.text.length) * 3.6 + 12;
        const up = (l: typeof a) => (l.dashed ? 0 : 13);                  // solid labels sit above their point (CSS)
        if (Math.abs(a.x - b.x) < ww && Math.abs(a.y - up(a) - (b.y - up(b))) < 20) { a.y = b.y - up(b) + up(a) + 20; j = -1; }
      }
      setLabels(ls);
      // shortcut: pins only for findings with an evidence box (no element-box fetch per finding); cap 300 for big runs
      const ps: { c: Check; x: number; y: number }[] = [];
      for (const c of findRef.current ?? []) {
        const ev = c.evidence;
        if (!ev?.bbox || ev.z == null || c.check_key === act?.c.check_key) continue;
        const s = scr(new THREE.Vector3((ev.bbox[0] + ev.bbox[2]) / 2, (ev.bbox[1] + ev.bbox[3]) / 2, ev.z + 1));
        if (s.on) ps.push({ c, x: s.x, y: s.y });
        if (ps.length >= 300) break;
      }
      setPins(ps);
      if (act?.box) {
        const b = act.box, xs: number[] = [], ys: number[] = [];
        for (let k = 0; k < 8; k++) { const s = scr(new THREE.Vector3(k & 1 ? b.max.x : b.min.x, k & 2 ? b.max.y : b.min.y, k & 4 ? b.max.z : b.min.z)); xs.push(s.x); ys.push(s.y); }
        const a = scr(b.getCenter(new THREE.Vector3()));
        setGeo({ anchor: [a.x, a.y], rect: { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) }, occluded: occ || !a.on });
      } else setGeo(null);
      setVsize((o) => (o.w === w && o.h === h ? o : { w, h }));
    };
    // occlusion: one depth pixel once the view has been still for 300 ms (orbiting keeps the last answer)
    const occTick = () => {
      if (!act?.box) return;
      const k = v.camera.matrixWorld.elements.join() + (v.camera as any).zoom + JSON.stringify(v.cuts) + v.mode + v.solo + (v as any).visHash;
      if (k !== occKey) { occKey = k; stillSince = performance.now(); occDone = false; return; }
      if (occDone || performance.now() - stillSince < 300) return;
      occDone = true;
      const o = v.occluded(act.box.getCenter(new THREE.Vector3()), act.ids);
      if (o !== occ) { occ = o; update(); }
    };
    v.onChange = () => update();
    v.onSelect = (i) => {
      if (i === null) { setProps(null); onSelectElement?.(null); return; }
      const row = v.elements[i];
      setProps({ i, row, meta: null });
      onSelectElement?.(row[0]);
      if (modelId) apiFetch(`/models/${modelId}/elements/${i}`).then((r) => r.ok ? r.json() : null).then((m) => { if (!disposed) setProps((p) => (p && p.i === i ? { ...p, meta: m } : p)); });
    };
    const clearExtras = () => {
      extras.forEach((o) => { o.parent?.remove(o); (o as any).geometry?.dispose?.(); }); extras = [];
      labelPts = []; focusBox = null; v.currentFocusBox = null; setLegend(null); setLabels([]);
    };
    const restorePaint = () => { v.focus = null; v.setPaint(new Map(painted.map((p) => [p.i, p.rgb]))); };
    // zoom to a finding keeps the isometric angle and leaves room for the neighbouring rooms (2.2 x radius, at least 7 m)
    const fit = (b: THREE.Box3) => { const r = b.getBoundingSphere(new THREE.Sphere()).radius; v.fit(b, ISO, Math.max(r * 2.2, 7)); };
    const home = () => { v.currentFocusBox = null; v.view("iso"); };
    const outline = (box: THREE.Box3, color: number) => {
      const h = new THREE.Box3Helper(box, new THREE.Color(color));
      (h.material as THREE.LineBasicMaterial).depthTest = false;
      v.overlay.add(h); extras.push(h);
    };
    // evidence geometry of a finding: footprint ring + tint, dimension lines, "must be" outline for class findings
    const drawEvidence = (c: Check): THREE.Box3 => {
      const color = hex(STATUS_RGB[c.status] ?? [227, 146, 200]);
      const box = new THREE.Box3();
      const ev = c.evidence;
      if (ev?.bbox && ev.z != null) {
        const [x0, y0, x1, y1] = ev.bbox, z = ev.z + 0.05;
        const ring = [new THREE.Vector3(x0, y0, z), new THREE.Vector3(x1, y0, z), new THREE.Vector3(x1, y1, z), new THREE.Vector3(x0, y1, z), new THREE.Vector3(x0, y0, z)];
        const ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints(ring), new THREE.LineBasicMaterial({ color, depthTest: false }));
        v.overlay.add(ln); extras.push(ln);
        const fill = new THREE.Mesh(new THREE.PlaneGeometry(Math.abs(x1 - x0), Math.abs(y1 - y0)),
          new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.3, side: THREE.DoubleSide, depthTest: false }));
        fill.position.set((x0 + x1) / 2, (y0 + y1) / 2, z);
        v.overlay.add(fill); extras.push(fill);
        box.setFromPoints(ring);
        if (c.measured?.unit === "class" && c.required?.value != null) {
          // material / fire class: the element is tinted by what it is; the dashed outline is what it must be
          const bw = Math.max(Math.abs(x1 - x0), 0.2), bd = Math.max(Math.abs(y1 - y0), 0.2), bh = 2;
          const o = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(bw + 0.3, bd + 0.3, bh)),
            new THREE.LineDashedMaterial({ color: 0xffffff, dashSize: 0.18, gapSize: 0.12, depthTest: false }));
          o.position.set((x0 + x1) / 2, (y0 + y1) / 2, ev.z + bh / 2); o.computeLineDistances();
          v.overlay.add(o); extras.push(o);
          labelPts.push({ text: `must be ${fmtVal(c.required)}`, v: new THREE.Vector3((x0 + x1) / 2, (y0 + y1) / 2, ev.z + bh + 0.3), dashed: true });
        }
      }
      const spec = overlaySpec(c);
      if (spec) {
        for (const l of spec.lines) {
          const a = new THREE.Vector3(l.a[0], l.a[1], spec.z), b = new THREE.Vector3(l.b[0], l.b[1], spec.z);
          const mat = l.dashed ? new THREE.LineDashedMaterial({ color, dashSize: 0.25, gapSize: 0.15, depthTest: false }) : new THREE.LineBasicMaterial({ color: 0xffffff, depthTest: false });
          const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([a, b]), mat);
          if (l.dashed) line.computeLineDistances();
          v.overlay.add(line); extras.push(line);
          labelPts.push({ text: l.text, v: a.clone().add(b).multiplyScalar(0.5).add(new THREE.Vector3(0, 0, 0.3)), dashed: l.dashed });
        }
        setLegend(spec.title);
      }
      return box;
    };
    const setActiveFinding = (c: Check, ids: number[]) => {
      const ev = c.evidence;
      // shortcut: evidence boxes are 2D footprints; 2 m stands in for the room height until the engine sends z1
      const box = ev?.bbox && ev.z != null ? new THREE.Box3(new THREE.Vector3(ev.bbox[0], ev.bbox[1], ev.z), new THREE.Vector3(ev.bbox[2], ev.bbox[3], ev.z + 2)) : null;
      if (act?.c.check_key !== c.check_key || box) act = { c, ids, box };
      occ = false; occKey = "";
      setActive({ c, unlocatable: !ids.length && !box });
    };
    const clearActive = () => { act = null; occ = false; setActive(null); setGeo(null); };
    const focus = (c: Check) => {
      clearExtras();
      const ids = v.indices([c.element?.guid, ...(c.evidence?.guids ?? [])]);
      const rgb = STATUS_RGB[c.status] ?? [227, 146, 200];
      v.loadElements(ids);
      v.paint = new Map([...painted.map((p) => [p.i, p.rgb] as const), ...ids.map((i) => [i, rgb] as const)]);
      v.isolate(ids, "ghost");
      setActiveFinding(c, ids);
      const ev = c.evidence;
      const box = drawEvidence(c);
      if (ids.length) {
        const eb = new THREE.Box3();
        // precise element box from the metadata index when the finding has no evidence box
        if (box.isEmpty() && modelId) {
          Promise.all(ids.slice(0, 20).map((i) => apiFetch(`/models/${modelId}/elements/${i}`).then((r) => r.ok ? r.json() : null))).then((ms) => {
            for (const m of ms) if (m?.bbox) eb.union(new THREE.Box3(new THREE.Vector3(...m.bbox.slice(0, 3)), new THREE.Vector3(...m.bbox.slice(3))));
            if (!eb.isEmpty() && !disposed) { outline(eb, 0xffd2b8); focusBox = eb; v.currentFocusBox = eb; fit(eb); if (act?.c.check_key === c.check_key) { act.box = eb; update(); } }
          });
        }
      }
      if (!box.isEmpty()) { focusBox = box; v.currentFocusBox = box; fit(box); }
      v.invalidate(); update();
      return ids.length > 0 || !!ev?.bbox;
    };
    apiRef.current = {
      focus,
      isolate: (c) => { focus(c); v.isolate(v.indices([c.element?.guid, ...(c.evidence?.guids ?? [])]), "hide"); },
      showAll: () => { clearExtras(); clearActive(); restorePaint(); v.showAll(); home(); },
      zoom: () => { if (focusBox) fit(focusBox); },
      resetView: () => { clearExtras(); clearActive(); restorePaint(); home(); },
      paint: (cs) => {
        painted = [];
        for (const c of cs) for (const i of v.indices([c.element?.guid])) if (v.base[i * 4 + 3] > 0) painted.push({ i, rgb: STATUS_RGB[c.status] ?? [227, 146, 200] });
        restorePaint();
      },
      setBounds: () => { /* tiles are in the engine's frame: no offset */ },
      viewer: () => vref.current,
      modelId: () => modelId,
      sectionAt: async (c) => {
        const ids = v.indices([c.element?.guid, ...(c.evidence?.guids ?? [])]);
        let eb: number[] | null = null;
        const ev = c.evidence;
        if (!(ev?.bbox && ev.z != null) && ids.length && modelId) {
          const m = await apiFetch(`/models/${modelId}/elements/${ids[0]}`).then((r) => (r.ok ? r.json() : null));
          eb = m?.bbox ?? null;
        }
        // frame the finding on the cut (its evidence box, else its element), with the neighbouring rooms in view
        const around = ev?.bbox && ev.z != null ? new THREE.Box3(new THREE.Vector3(ev.bbox[0], ev.bbox[1], ev.z), new THREE.Vector3(ev.bbox[2], ev.bbox[3], ev.z + 2.5))
          : eb ? new THREE.Box3(new THREE.Vector3(...eb.slice(0, 3)), new THREE.Vector3(...eb.slice(3))) : undefined;
        const cut = cutForFinding({ evidence: c.evidence, elementBox: eb }, v.grid);
        if (!cut || disposed) return false;
        // the finding stays painted and selected-looking, with its evidence and callout; the rest of the ship is solid
        // so the section shows context
        clearExtras();
        drawEvidence(c);
        setActiveFinding(c, ids);
        v.loadElements(ids);
        v.focus = null;
        v.setPaint(new Map([...painted.map((p) => [p.i, p.rgb] as const), ...ids.map((i) => [i, STATUS_RGB[c.status] ?? [227, 146, 200]] as const)]));
        v.setCuts([cut]);
        v.faceCut(cut, 650, around, around ? Math.max(around.getBoundingSphere(new THREE.Sphere()).radius * 2.2, 7) : 0);
        setSectionOpen(true);
        return true;
      },
    };
    (async () => {
      try {
        setState("preparing"); setMsg("Preparing a fast web version"); setProgress(0);
        const r = await apiFetch("/models/prepare", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(src) });
        let st = await r.json();
        if (!r.ok) throw new Error(st.detail ?? r.statusText);
        modelId = st.id;
        while (st.state !== "ready") {
          if (disposed) return;
          if (st.state === "error") throw new Error(st.message);
          setProgress(st.progress ?? 0); setMsg(st.message ?? "Preparing a fast web version");
          await new Promise((res) => setTimeout(res, 700));
          st = await apiFetch(`/models/${modelId}`).then((x) => x.json());
        }
        if (disposed) return;
        setSummary(st.summary); setState("loading"); setMsg("Loading the ship");
        await v.load(`${API}/models/${modelId}/files/`, HDR);
        if (disposed) return;
        // discipline colours from the design tokens (--disc-*), colour by discipline by default (spec A4)
        const tok = getComputedStyle(host.current!);
        const c = new THREE.Color();
        v.discRgb = v.index.groups.map((g) => { c.set(tok.getPropertyValue(`--disc-${g}`).trim() || "#9a9da3"); return [Math.round(c.r * 255), Math.round(c.g * 255), Math.round(c.b * 255)]; });
        v.setColourBy({ kind: "discipline" });
        onViewer?.(v, modelId);
        setDecks(v.deckLevels());
        const g = await apiFetch(`/models/${modelId}/grid`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
        if (g && !disposed) v.grid = g;
        timer = window.setInterval(() => { update(); occTick(); }, 250);
        setState("ready");
      } catch (e) { if (!disposed) { setMsg(String((e as Error).message ?? e)); setState("error"); } }
    })();
    return () => { disposed = true; themeObs.disconnect(); apiRef.current = null; vref.current = null; window.clearInterval(timer); v.dispose(); setProps(null); setDeck(null); setSectionOpen(false); setActive(null); setGeo(null); setPins([]); onViewer?.(null, null); };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const fkey = (findings ?? []).map((c) => c.check_key + c.status).join("|");
  useEffect(() => { if (state === "ready") apiRef.current?.paint(findings ?? []); }, [state, fkey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const v = vref.current; if (!v || state !== "ready") return; const d = decks.find((x) => x.deck === deck); v.setDeckClip(d ? d.top : null); }, [deck, state]); // eslint-disable-line react-hooks/exhaustive-deps

  const v = vref.current;
  const meta = props?.meta;
  return (
    <div className="viewer studio-3d" ref={host}>
      {state === "idle" && <div className="studio-empty">Open a model and press Analyse. The 3D shows the exact file of the run.</div>}
      {(state === "preparing" || state === "loading") && (
        <div className="ship-progress" role="status"><div>{msg}…</div>
          {state === "preparing" && <div className="ship-bar"><i style={{ width: `${Math.round(progress * 100)}%` }} /></div>}
          <div className="sq-faint" style={{ fontSize: 12 }}>Converted once on the engine and kept, so the next opening is fast.</div></div>
      )}
      {state === "error" && <div className="sq-banner" style={{ position: "absolute", left: 16, top: 12, right: 16 }}>3D preview not available for this model: {msg} The findings list still works.</div>}
      {state === "ready" && v && (
        <div className="ship-tools" role="toolbar" aria-label="View tools">
          <div className="sq-seg">{VIEWS.map(([k, l]) => <button key={k} onClick={() => v.view(k)} title={`${l} view`}>{l}</button>)}</div>
          <div className="sq-seg">{(["perspective", "orthographic"] as const).map((p) => (
            <button key={p} className={v.cameraState().projection === p ? "is-on" : ""} onClick={() => v.setProjection(p)}>{p === "perspective" ? "Persp" : "Ortho"}</button>))}</div>
          <button className={`sq-btn is-sm sec-toggle${sectionOpen ? " is-on" : ""}`} aria-pressed={sectionOpen} onClick={() => setSectionOpen(!sectionOpen)}
                  title="Section blade: cross section, longitudinal, deck plan">Section{v.cuts.length ? ` · ${v.cuts.length}` : ""}</button>
          <label className="ship-deck">Deck
            <select className="sq-input" value={deck ?? ""} onChange={(e) => setDeck(e.target.value ? Number(e.target.value) : null)} aria-label="Cut above deck">
              <option value="">All</option>
              {decks.map((d) => <option key={d.deck} value={d.deck}>{d.deck}</option>)}
            </select></label>
          <button className="sq-btn is-sm" onClick={() => apiRef.current?.resetView()}>Reset view</button>
        </div>
      )}
      {state === "ready" && v && sectionOpen && <SectionBar v={v} modelId={v ? apiRef.current?.modelId() ?? null : null} decks={decks} onClose={() => setSectionOpen(false)} />}
      {state === "ready" && summary && (
        <div className="ship-stats mono sq-faint">{summary.elements.toLocaleString("en-US")} elements · {summary.tris >= 1e6 ? `${(summary.tris / 1e6).toFixed(1)} M` : summary.tris.toLocaleString("en-US")} triangles · {summary.bytes >= 1048576 ? `${(summary.bytes / 1048576).toFixed(0)} MB` : `${Math.ceil(summary.bytes / 1024)} KB`}</div>
      )}
      {state === "ready" && pins.map(({ c, x, y }) => (
        <button key={c.check_key} className={`co-pin s-${c.status}`} style={{ left: x, top: y }} onClick={() => onPick?.(c)}
                title={`${c.id}: ${c.title}`} aria-label={`Finding ${c.id}: ${c.title}`}>{c.id}</button>))}
      {state === "ready" && active && (
        <Callout c={active.c} geo={geo} view={vsize} unlocatable={active.unlocatable} onClose={() => apiRef.current?.resetView()}
          actions={[
            { label: "Section here", title: "Cut through this finding and face the cut", run: () => { apiRef.current?.sectionAt(active.c); } },
            { label: "Isolate", run: () => apiRef.current?.isolate(active.c) },
            ...(onOpenEvidence ? [{ label: "Open evidence", title: "Thread with clause text, inputs and history", run: () => onOpenEvidence(active.c) }] : []),
          ]} />
      )}
      {props && v && (
        <div className="ship-props sq-card" aria-live="polite">
          <div className="flex items-center gap-2"><b style={{ flex: 1 }}>{props.row[3]}</b>
            <button className="studio-link" onClick={() => { v.select(null); setProps(null); onSelectElement?.(null); }} aria-label="Close properties">×</button></div>
          <div className="mono sq-faint" style={{ fontSize: 11 }}>{props.row[2]} · {props.row[0]}{props.row[1] ? ` · source ${props.row[1]}` : ""}</div>
          {meta && (
            <table className="ship-kv"><tbody>
              {([["Deck", meta.deck], ["Discipline", meta.discipline], ["Frame", meta.frame], ["Side", meta.side], ["SWBS", meta.swbs], ["System", meta.system],
                 ["Material", meta.material], ["Grade", meta.grade], ["Thickness", meta.thickness_mm != null ? `${meta.thickness_raw ?? ""} = ${meta.thickness_mm} mm` : null],
                 ["Fire rating", meta.fire_rating], ["Part GUID", meta.part_guid]] as [string, any][]).filter(([, x]) => x != null && x !== "").map(([k, x]) => (
                <tr key={k}><th>{k}</th><td className="mono">{String(x)}</td></tr>))}
            </tbody></table>)}
          <div className="flex gap-1" style={{ marginTop: 6 }}>
            <button className="sq-btn is-sm" onClick={() => v.isolate([props.i], "ghost")}>Isolate</button>
            <button className="sq-btn is-sm" onClick={() => { v.hide([props.i]); v.select(null); setProps(null); }}>Hide</button>
            <button className="sq-btn is-sm" onClick={() => apiRef.current?.showAll()}>Show all</button>
          </div>
        </div>
      )}
      {labels.filter((l) => l.visible).map((l, i) => (
        <span key={i} className={`studio-dim${l.dashed ? " is-req" : ""}`} style={{ left: l.x, top: l.y }}>{l.text}</span>
      ))}
      {legend && (
        <div className="studio-legend"><b>{legend}</b><br />Measured by rule engine · check on drawing<br />
          <span className="mono">━━ measured &nbsp; ╍╍ required / allowed</span></div>
      )}
    </div>
  );
}
