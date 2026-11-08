// Web Studio ("Review in the browser"): open a demo model or upload an IFC, Analyse with scope + disciplines like the
// FreeCAD panel, and inspect findings next to the 3D. The viewer always loads the exact file of the run shown
// (GET /runs/<id>/ifc); every verdict and number comes from the engine.
import { useEffect, useMemo, useRef, useState } from "react";
import * as OBC from "@thatopen/components";
import * as THREE from "three";
import { api, apiFetch, API, BASE, HDR, ORDER, WORD, useIncorrect, type Check, type Run, type RunMeta } from "../api";
import { Pill } from "../components/ui";
import { DISC } from "./Board";
import { valueLine } from "./Inbox";

const DEMOS = [
  { rev: "A", file: "deck5_revA.ifc", note: "Deck 5 · baseline" },
  { rev: "B", file: "deck5_revB.ifc", note: "OR-117 · 4 cabins added" },
  { rev: "Bfix2", file: "deck5_revB_fix2.ifc", note: "fix 2 · one berth each" },
];
const DISCS: { code: string; pack: string | null; color: string; sets: string }[] = [
  { code: "FIRE", pack: "fls", color: "#e27dff", sets: "SOLAS II-2 ✓ · FSS Code ✓" },
  { code: "HULL", pack: "dnv", color: "#5c9dff", sets: "DNV Pt.3 · To verify" },
  { code: "INT", pack: "acc", color: "#b98cff", sets: "Accessibility (PVAG/ADA) ✓" },
  { code: "HVAC", pack: "hvac", color: "#3fd0e6", sets: "SOLAS II-2/9.7 dampers ✓" },
  { code: "GA", pack: null, color: "#c3c9d4", sets: "Coming" },
  { code: "PIPE", pack: null, color: "#c4e35c", sets: "Coming" },
  { code: "ELEC", pack: null, color: "#82dd8a", sets: "Coming" },
  { code: "MACH", pack: null, color: "#a3a3ff", sets: "Coming" },
];
const STATUS_HEX: Record<string, number> = { fail: 0xd55e00, warn: 0xe69f00, unk: 0xc9cdd4, pass: 0x009e73, dor: 0x959aa4 };
const MAX_MB = 60;

type Target = { kind: "demo"; rev: string; name: string } | { kind: "upload"; path: string | null; rev: string | null; name: string };
type Shown = { meta: RunMeta & { bounds?: number[] | null; edited?: boolean }; run: Run };

// ---------------------------------------------------------------------------------------------- overlay spec
// Same rule as the FreeCAD panel: positions from the engine's evidence box, labels = engine values as returned.
type Line = { a: [number, number]; b: [number, number]; text: string; dashed: boolean };
const fmtV = (v: any) => (v?.unit === "mm" && typeof v.value === "number" ? `${v.value.toLocaleString("en-US")} mm` : `${v?.value} ${v?.unit ?? ""}`.trim());
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

// ---------------------------------------------------------------------------------------------- 3D
type Label = { text: string; x: number; y: number; dashed: boolean; visible: boolean };
type View = { focus: (c: Check) => boolean; isolate: (c: Check) => void; showAll: () => void; zoom: () => void; resetView: () => void;
  paint: (cs: Check[]) => void; setBounds: (b?: number[] | null) => void };

// Look: dark background, every element translucent grey ("x-ray"), isometric camera from front-left-above fitted with
// a small margin. The model loads as soon as it is opened; after Analyse the same viewer stays (camera unchanged) and
// only elements with findings get their status colour.
const ISO: [number, number] = [0.45, 0.9];   // camera-controls azimuth, polar (rad)
function Viewer3D({ url, bounds, findings, onReady, apiRef }: { url: string | null; bounds?: number[] | null; findings: Check[] | null; onReady: (s: string) => void; apiRef: React.MutableRefObject<View | null> }) {
  const host = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [err, setErr] = useState("");
  const [labels, setLabels] = useState<Label[]>([]);
  const [legend, setLegend] = useState<string | null>(null);
  useEffect(() => {
    if (!host.current || !url) { setState("idle"); return; }
    let disposed = false, timer = 0;
    const components = new OBC.Components();
    const world = components.get(OBC.Worlds).create<OBC.SimpleScene, OBC.SimpleCamera, OBC.SimpleRenderer>();
    world.scene = new OBC.SimpleScene(components);
    world.renderer = new OBC.SimpleRenderer(components, host.current);
    world.camera = new OBC.SimpleCamera(components);
    components.init();
    world.scene.setup();
    (world.scene.three as THREE.Scene).background = new THREE.Color("#17191c");
    const loader = components.get(OBC.IfcLoader);
    let group: any = null, modelBox = new THREE.Box3();
    let off = new THREE.Vector3();
    let extras: THREE.Object3D[] = [];
    let labelPts: { text: string; v: THREE.Vector3; dashed: boolean }[] = [];
    let painted: THREE.Object3D[] = [];
    let focusBox: THREE.Box3 | null = null;
    const T = (x: number, y: number, z: number) => new THREE.Vector3(x + off.x, z + off.y, -y + off.z);
    const mats = () => { const out: THREE.Material[] = []; group?.items.forEach((f: any) => { const m = f.mesh.material; (Array.isArray(m) ? m : [m]).forEach((mm: THREE.Material) => out.push(mm)); }); return out; };
    // x-ray: translucent grey; while a finding is focused the rest fades further
    const ghost = (on: boolean) => mats().forEach((m: any) => {
      m.color?.set?.(0x9aa3ad); m.transparent = true; m.opacity = on ? 0.08 : 0.2; m.depthWrite = false; m.needsUpdate = true;
    });
    const cloneIn = (guid: string | undefined, color: number, intensity: number, into: THREE.Object3D[], box?: THREE.Box3) => {
      const eid = guid ? group.globalToExpressIDs.get(guid) : undefined;
      if (eid === undefined) return false;
      const fmap = group.getFragmentMap([eid]);
      for (const fid of Object.keys(fmap)) {
        const frag = group.items.find((f: any) => f.id === fid);
        if (!frag) continue;
        const cl = frag.clone(fmap[fid]);
        cl.mesh.material = [new THREE.MeshLambertMaterial({ color, emissive: color, emissiveIntensity: intensity })];
        group.add(cl.mesh); into.push(cl.mesh);
        if (box) { cl.mesh.updateMatrixWorld(true); box.union(new THREE.Box3().setFromObject(cl.mesh)); }
      }
      return true;
    };
    const paint = (cs: Check[]) => {
      painted.forEach((o) => { o.parent?.remove(o); (o as any).geometry?.dispose?.(); }); painted = [];
      if (!group) return;
      for (const c of cs) cloneIn(c.element?.guid, STATUS_HEX[c.status] ?? 0xe392c8, 0.2, painted);
      painted.forEach((o) => { o.visible = !focusBox && !extras.length; });
    };
    const home = async (smooth: boolean) => {
      if (modelBox.isEmpty()) return;
      // isometric from front-left-above; fitToSphere keeps the angle (fitToBox would snap to the nearest axis)
      const sph = modelBox.getBoundingSphere(new THREE.Sphere()); sph.radius *= 0.75;
      await world.camera.controls.rotateTo(ISO[0], ISO[1], false);
      await world.camera.controls.fitToSphere(sph, smooth);
    };
    const visibility = (on: boolean) => group?.items.forEach((f: any) => f.setVisibility(on));
    const clear = () => {
      extras.forEach((o) => { o.parent?.remove(o); (o as any).geometry?.dispose?.(); });
      extras = []; labelPts = []; focusBox = null; setLegend(null); setLabels([]);
      visibility(true); ghost(false); painted.forEach((o) => { o.visible = true; });
    };
    const update = () => {
      if (disposed || !host.current) return;
      const cam = world.camera.three as THREE.Camera; cam.updateMatrixWorld();
      const w = host.current.clientWidth, h = host.current.clientHeight;
      setLabels(labelPts.map(({ text, v, dashed }) => { const p = v.clone().project(cam); return { text, dashed, x: (p.x + 1) / 2 * w, y: (1 - p.y) / 2 * h, visible: p.z < 1 && Math.abs(p.x) < 1.2 && Math.abs(p.y) < 1.2 }; }));
    };
    const fit = (b: THREE.Box3) => {
      const bb = b.clone(); const size = bb.getSize(new THREE.Vector3()); bb.expandByVector(new THREE.Vector3(Math.max(5, size.x), 2, Math.max(5, size.z)));
      // keep the current viewing angle (fitToBox would snap to the nearest axis and show a flat side view)
      world.camera.controls.fitToSphere(bb.getBoundingSphere(new THREE.Sphere()), true);
    };
    const focus = (c: Check) => {
      clear();
      if (!group) return false;
      const color = STATUS_HEX[c.status] ?? 0xe392c8;
      const box = new THREE.Box3();
      painted.forEach((o) => { o.visible = false; });
      const eid = cloneIn(c.element?.guid, color, 0.35, extras, box) ? 1 : undefined;
      // the engine's evidence box, outlined in the status colour (spaces have no solid to colour)
      const ev = c.evidence;
      if (ev?.bbox && ev.z != null) {
        const [x0, y0, x1, y1] = ev.bbox, z = ev.z + 0.05;
        const ring = [T(x0, y0, z), T(x1, y0, z), T(x1, y1, z), T(x0, y1, z), T(x0, y0, z)];
        const ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints(ring), new THREE.LineBasicMaterial({ color, depthTest: false }));
        ln.renderOrder = 10; world.scene.three.add(ln); extras.push(ln);
        const fill = new THREE.Mesh(new THREE.PlaneGeometry(Math.abs(x1 - x0), Math.abs(y1 - y0)), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthTest: false }));
        fill.rotation.x = -Math.PI / 2; fill.position.copy(T((x0 + x1) / 2, (y0 + y1) / 2, z)); fill.renderOrder = 9;
        world.scene.three.add(fill); extras.push(fill);
        if (box.isEmpty()) box.setFromPoints(ring);
      }
      // dimension overlay (engine numbers only)
      const spec = overlaySpec(c);
      if (spec) {
        for (const l of spec.lines) {
          const a = T(l.a[0], l.a[1], spec.z), b = T(l.b[0], l.b[1], spec.z);
          const mat = l.dashed ? new THREE.LineDashedMaterial({ color, dashSize: 0.25, gapSize: 0.15, depthTest: false }) : new THREE.LineBasicMaterial({ color: 0xffffff, depthTest: false });
          const g = new THREE.BufferGeometry().setFromPoints([a, b]);
          const line = new THREE.Line(g, mat); if (l.dashed) line.computeLineDistances(); line.renderOrder = 11;
          world.scene.three.add(line); extras.push(line);
          labelPts.push({ text: l.text, v: a.clone().add(b).multiplyScalar(0.5).add(new THREE.Vector3(0, 0.3, 0)), dashed: l.dashed });
        }
        setLegend(spec.title);
      }
      ghost(true);
      focusBox = box.isEmpty() ? null : box;
      if (focusBox) fit(focusBox);
      update();
      return eid !== undefined || !!ev?.bbox;
    };
    apiRef.current = {
      focus,
      isolate: (c: Check) => { focus(c); visibility(false); ghost(false); },
      showAll: () => { clear(); home(true); },
      zoom: () => { if (focusBox) fit(focusBox); },
      resetView: () => { clear(); home(true); },
      paint,
      setBounds: (b) => { if (b && !modelBox.isEmpty()) off = new THREE.Vector3(modelBox.min.x - b[0], modelBox.min.y - b[2], modelBox.min.z + b[4]); },
    };
    (async () => {
      setState("loading"); setErr("");
      try {
        loader.settings.autoSetWasm = false;
        loader.settings.wasm = { path: BASE + "wasm/", absolute: true };
        loader.settings.webIfc.COORDINATE_TO_ORIGIN = false;
        await loader.setup();
        const r = await fetch(url, { headers: HDR });
        if (!r.ok) throw new Error(r.status === 409 ? "This run includes edits made in chat; the file on disk is the version before them." : `${r.status} ${await r.text()}`);
        const buf = new Uint8Array(await r.arrayBuffer());
        group = await loader.load(buf);
        if (disposed) return;
        world.scene.three.add(group);
        modelBox = new THREE.Box3().setFromObject(group);
        if (bounds) off = new THREE.Vector3(modelBox.min.x - bounds[0], modelBox.min.y - bounds[2], modelBox.min.z + bounds[4]);
        ghost(false);
        await home(false);
        world.camera.controls.addEventListener("update", update);
        timer = window.setInterval(update, 200);
        setState("ready"); onReady("ready");
      } catch (e) { if (!disposed) { setErr(String((e as Error).message ?? e)); setState("error"); onReady("error"); } }
    })();
    return () => { disposed = true; apiRef.current = null; window.clearInterval(timer); components.dispose(); };
  }, [url]); // eslint-disable-line react-hooks/exhaustive-deps
  const fkey = (findings ?? []).map((c) => c.check_key + c.status).join("|");
  useEffect(() => { if (state === "ready") apiRef.current?.setBounds(bounds); }, [state, bounds?.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (state === "ready") apiRef.current?.paint(findings ?? []); }, [state, fkey]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="viewer studio-3d" ref={host}>
      {state === "idle" && <div className="studio-empty">Open a model and press Analyse. The 3D shows the exact file of the run.</div>}
      {state === "ready" && <button className="sq-btn is-sm studio-resetview" onClick={() => apiRef.current?.resetView()}>Reset view</button>}
      {state === "loading" && <div className="sq-muted" style={{ position: "absolute", left: 16, top: 12 }}>Loading the file of this run…</div>}
      {state === "error" && <div className="sq-banner" style={{ position: "absolute", left: 16, top: 12, right: 16 }}>3D preview not available for this run: {err} The findings list still works.</div>}
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

// ---------------------------------------------------------------------------------------------- Studio
export default function Studio({ latest, run, onOpenFinding }: { latest: (RunMeta & { bounds?: number[] | null; edited?: boolean }) | null; run: Run | null; onOpenFinding: (c: Check) => void }) {
  const [local, setLocal] = useState<Shown | null>(null);
  const shown: Shown | null = local && (!latest || latest.seq <= local.meta.seq) ? local : latest && run ? { meta: latest, run } : null;
  const [target, setTarget] = useState<Target | null>(null);
  const [scope, setScope] = useState<"deck:5" | "whole">("deck:5");
  const [discs, setDiscs] = useState<string[]>(["FIRE", "HULL", "INT"]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [why, setWhy] = useState<{ key: string; text: string } | null>(null);
  const [setup, setSetup] = useState(true);
  const [incorrect, reloadInc] = useIncorrect();
  const view = useRef<View | null>(null);
  const fileIn = useRef<HTMLInputElement>(null);
  useEffect(() => { if (shown) setSetup(false); }, [shown?.meta.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const packs = DISCS.filter((d) => d.pack && discs.includes(d.code)).map((d) => d.pack!) as string[];
  // the viewer loads the model as soon as it is opened; after Analyse it keeps that file (same camera) when the run
  // read the same file unedited, otherwise it loads exactly the run's file
  const targetUrl = target ? (target.kind === "demo" ? `${API}/model-file?revision=${encodeURIComponent(target.rev)}`
    : target.path ? `${API}/model-file?path=${encodeURIComponent(target.path)}` : target.rev ? `${API}/model-file?revision=${encodeURIComponent(target.rev)}` : null) : null;
  const runUrl = shown ? `${API}/runs/${encodeURIComponent(shown.meta.id)}/ifc` : null;
  const [viewSrc, setViewSrc] = useState<{ url: string | null; file: string | null }>({ url: null, file: null });
  useEffect(() => {
    if (target) { if (targetUrl !== viewSrc.url) setViewSrc({ url: targetUrl, file: target.name }); return; }
    if (!shown) { setViewSrc({ url: null, file: null }); return; }
    if (viewSrc.url && viewSrc.file === shown.meta.file && !shown.meta.edited) return;
    setViewSrc({ url: runUrl, file: shown.meta.file });
  }, [targetUrl, runUrl]); // eslint-disable-line react-hooks/exhaustive-deps
  const ifcUrl = viewSrc.url;
  const painted = useMemo(() => (shown && !target ? shown.run.checks.filter((c) => ["fail", "warn", "unk"].includes(c.status) && !incorrect[c.check_key]) : null), [shown, target, incorrect]);
  const cards = useMemo(() => {
    if (!shown) return [];
    const rows = shown.run.checks.filter((c) => (status ? c.status === status : ["fail", "warn", "unk"].includes(c.status)));
    return rows.sort((a, b) => Number(!!incorrect[a.check_key]) - Number(!!incorrect[b.check_key]) || ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || (a.id ?? "").localeCompare(b.id ?? ""));
  }, [shown, status, incorrect]);

  const upload = async (f: File) => {
    setMsg("");
    if (!/\.ifc$/i.test(f.name)) { setMsg("Choose an .ifc file (IFC4)."); return; }
    if (f.size > MAX_MB * 1024 * 1024) { setMsg(`${f.name} is ${(f.size / 1048576).toFixed(0)} MB; the browser studio takes up to ${MAX_MB} MB. Use the FreeCAD add-on for larger models.`); return; }
    const head = await f.slice(0, 4096).text();
    if (!head.startsWith("ISO-10303-21")) { setMsg(`${f.name} is not an IFC (STEP) file.`); return; }
    const schema = /FILE_SCHEMA\s*\(\s*\(\s*'([A-Za-z0-9_]+)'/i.exec(head)?.[1]?.toUpperCase();
    if (schema && !schema.startsWith("IFC4")) { setMsg(`${f.name} is ${schema}; SonarIQ reads IFC4. Export the model as IFC4 and try again.`); return; }
    setBusy(true);
    try {
      const r = await apiFetch(`/upload?name=${encodeURIComponent(f.name)}`, { method: "POST", body: f, headers: { "Content-Type": "application/octet-stream" } });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail ?? r.statusText);
      setTarget({ kind: "upload", path: j.path, rev: j.revision, name: f.name }); setSetup(true);
      setMsg(j.known ? `${f.name} is the demo file Rev ${j.revision}.` : `${f.name} uploaded. Press Analyse.`);
    } catch (e) { setMsg(`Upload failed: ${(e as Error).message}`); }
    setBusy(false);
  };
  const analyse = async () => {
    const t = target ?? (shown ? { kind: "demo", rev: shown.meta.revision, name: shown.meta.file } as Target : null);
    if (!t || !packs.length) return;
    setBusy(true); setMsg(""); setSel(null); view.current?.showAll();
    try {
      const body = t.kind === "demo" ? { revision: t.rev, scope, packs } : { revision: t.path ? null : t.rev, path: t.path, scope, packs };
      const r = await apiFetch("/analyse", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail ?? r.statusText);
      setLocal({ meta: { ...d.run_meta }, run: d }); setTarget(null); setStatus(null);
    } catch (e) { setMsg(`Analyse failed: ${(e as Error).message}`); }
    setBusy(false);
  };
  const pick = (c: Check) => { setSel(c.check_key); view.current?.focus(c); };
  const mark = async (c: Check, reason: string) => {
    if (!reason.trim()) return;
    await api.markIncorrect({ check_key: c.check_key, finding: c.id, reason: reason.trim(), by: "Reviewer (browser)", revision: shown?.meta.revision, file: shown?.meta.file });
    setWhy(null); reloadInc();
  };
  const undo = async (key: string) => { await api.undoIncorrect(key); reloadInc(); };
  const label = target ? target.name : shown ? shown.meta.file : null;

  return (
    <div className="studio">
      <div className="studio-left">
        <Viewer3D url={ifcUrl} bounds={shown && !target ? shown.meta.bounds : null} findings={painted} onReady={() => {}} apiRef={view} />
      </div>
      <aside className="studio-panel">
        <header className="studio-head">
          <span className="studio-title"><b>Studio</b>
            <span className="mono sq-muted studio-file" title={label ?? ""}>{label ? label.replace(/\.ifc$/i, "") : "No model open"}{shown && !target ? ` · Rev ${shown.meta.revision}` : target ? " · not analysed yet" : ""}</span></span>
          <span style={{ flex: 1 }} />
          <button className="sq-btn" onClick={() => setSetup(!setup)}>{setup ? "Close" : "Open model"}</button>
          <button className="sq-btn is-primary" disabled={busy || (!target && !shown) || !packs.length} title={!target && !shown ? "Open an IFC model to analyse" : ""} onClick={analyse}>{busy ? "Analysing…" : "Analyse"}</button>
          {shown && !target && <button className="sq-btn" onClick={() => { location.hash = `#inbox/${shown.meta.id}`; }}>Export</button>}
        </header>
        {shown && !target && <div className="sq-faint" style={{ fontSize: 12, textAlign: "right", padding: "0 12px 6px" }}>All findings are exported except those marked incorrect.</div>}
        {msg && <div className="sq-banner" style={{ margin: "0 12px 8px" }}>{msg}</div>}
        {!setup && shown && (
          <div className="studio-sum">
            <span style={{ flex: 1 }}>{scope === "whole" ? "Whole model" : "Deck 5"} · {discs.filter((d) => DISCS.find((x) => x.code === d)?.pack).join(" ")}<br />
              <span className="mono sq-faint" style={{ fontSize: 12 }}>Rev {shown.meta.revision} · {shown.run.total_checks} checks · {shown.meta.time.slice(11, 16)}{shown.meta.scope_note ? " · whole model" : ""}</span></span>
            <button className="sq-btn is-sm" onClick={() => setSetup(true)}>Edit</button>
          </div>
        )}
        {setup && (
          <div className="studio-setup">
            <div className="sq-label">Open model</div>
            <div className="flex flex-col gap-1">
              {DEMOS.map((d) => (
                <button key={d.rev} className={`studio-model${target?.kind === "demo" && target.rev === d.rev ? " is-on" : ""}`} onClick={() => { setTarget({ kind: "demo", rev: d.rev, name: d.file }); setMsg(""); }}>
                  <span className="mono">{d.file}</span><span className="sq-faint">{d.note}</span>
                </button>
              ))}
              <button className="studio-model" onClick={() => fileIn.current?.click()}><span>Upload IFC…</span><span className="sq-faint">IFC4 · up to {MAX_MB} MB</span></button>
              <input ref={fileIn} type="file" accept=".ifc" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
            </div>
            <div className="sq-label" style={{ marginTop: 10 }}>Scope</div>
            <div className="sq-seg">{([["deck:5", "Deck 5"], ["whole", "Whole model"]] as const).map(([k, l]) => <button key={k} className={scope === k ? "is-on" : ""} onClick={() => setScope(k)}>{l}</button>)}</div>
            <div className="sq-label" style={{ marginTop: 10 }}>Disciplines</div>
            <div className="flex gap-1" style={{ flexWrap: "wrap" }}>
              {DISCS.map((d) => {
                const on = discs.includes(d.code);
                return <button key={d.code} className="studio-disc" style={on ? { color: d.color, borderColor: d.color, background: "var(--bg-2)" } : undefined} title={d.sets}
                  onClick={() => setDiscs((s) => (on ? s.filter((x) => x !== d.code) : [...s, d.code]))}>{d.code}</button>;
              })}
            </div>
            <div className="sq-card studio-sets">
              <div className="sq-faint" style={{ fontSize: 12 }}>Rule sets selected automatically</div>
              {DISCS.filter((d) => discs.includes(d.code)).map((d) => (
                <div key={d.code} className="flex gap-2" style={{ fontSize: 12 }}><b className="mono" style={{ color: d.color, width: 40 }}>{d.code}</b><span className={d.pack ? "" : "sq-faint"}>{d.sets}</span></div>
              ))}
              {!packs.length && <div className="sq-muted" style={{ fontSize: 12 }}>Pick a discipline with rule sets.</div>}
            </div>
          </div>
        )}
        {shown && !target && (
          <>
            <div className="flex gap-1 studio-chips">
              {(["fail", "warn", "unk", "pass", "dor"] as const).map((s) => (
                <button key={s} className={`ib-chip${status === s ? " is-on" : ""}`} onClick={() => setStatus(status === s ? null : s)}>
                  <span className={`sq-pill s-${s}`} style={{ border: 0, background: "none", padding: 0 }}><i className="sq-ico" /></span><b>{shown.run.counts[s] ?? 0}</b> {WORD[s]}
                </button>
              ))}
            </div>
            <div className="studio-cards">
              {cards.map((c) => {
                const [tag, color] = DISC[c.group] ?? ["··", "var(--fg-3)"];
                const inc = incorrect[c.check_key];
                const on = sel === c.check_key;
                return (
                  <div key={c.check_key} className={`studio-card${on ? " is-on" : ""}${inc ? " is-incorrect" : ""}${c.status === "unk" ? " is-dashed" : ""}`}
                       style={{ borderLeftColor: inc ? "var(--line-2)" : color }} onClick={() => pick(c)}>
                    <div className="flex items-center gap-2"><b className="mono" style={{ color, fontSize: 11 }}>{tag}</b><Pill s={c.status} /><span className="mono sq-faint" style={{ fontSize: 12 }}>{c.id}</span>
                      {c.to_verify && <span style={{ color: "var(--st-warn)", fontSize: 11 }}>To verify</span>}</div>
                    <div style={{ fontWeight: 600 }}>{c.title}</div>
                    <div className="mono sq-faint" style={{ fontSize: 11 }}>{[c.element?.name && !c.location.label.includes(c.element.name) ? c.element.name : "", c.location.label, `${c.source.startsWith("SOLAS") ? "SOLAS" : c.source} ${c.clause}`].filter(Boolean).join(" · ")}</div>
                    <div className="mono" style={{ fontSize: 11 }}>{valueLine(c)}</div>
                    {inc && <div className="inc-why flex items-center gap-2"><span style={{ flex: 1 }}>Marked incorrect · {inc.reason} · not exported</span>
                      <button className="studio-link" onClick={(e) => { e.stopPropagation(); undo(c.check_key); }}>Undo</button></div>}
                    {on && (
                      <div className="flex gap-1" style={{ flexWrap: "wrap", marginTop: 4 }} onClick={(e) => e.stopPropagation()}>
                        <button className="sq-btn is-sm is-primary" onClick={() => view.current?.zoom()}>Zoom to</button>
                        <button className="sq-btn is-sm" onClick={() => view.current?.isolate(c)}>Isolate</button>
                        <button className="sq-btn is-sm" onClick={() => { view.current?.showAll(); setSel(null); }}>Show all</button>
                        {!inc && <button className="sq-btn is-sm studio-warn" onClick={() => setWhy({ key: c.check_key, text: "" })}>Incorrect finding</button>}
                        <button className="sq-btn is-sm" onClick={() => onOpenFinding(c)}>Thread →</button>
                      </div>
                    )}
                    {on && why?.key === c.check_key && (
                      <form className="flex gap-1" style={{ marginTop: 4 }} onClick={(e) => e.stopPropagation()} onSubmit={(e) => { e.preventDefault(); mark(c, why.text); }}>
                        <input className="sq-input studio-why" autoFocus maxLength={140} placeholder="Why is this finding wrong?" value={why.text} onChange={(e) => setWhy({ key: c.check_key, text: e.target.value })} />
                        <button className="sq-btn is-sm studio-warn" disabled={!why.text.trim()}>Mark incorrect</button>
                      </form>
                    )}
                  </div>
                );
              })}
              {cards.length === 0 && <p className="sq-muted" style={{ padding: 12 }}>No findings with this status.</p>}
            </div>
          </>
        )}
      </aside>
    </div>
  );
}
