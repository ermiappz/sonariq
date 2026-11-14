// Web Studio ("Review in the browser"): open a model revision of the current project or upload an IFC, Analyse with
// scope + disciplines like the FreeCAD panel, and inspect findings next to the 3D. Everything shown belongs to the open
// revision (App's scope). The viewer loads the revision's own file (converted once, cached by content hash); every
// verdict and number comes from the engine.
import { useEffect, useMemo, useRef, useState } from "react";
import { api, apiFetch, download, WORD, useIncorrect, type Check, type RevModel, type Run, type RunMeta } from "../api";
import type { Scope } from "../App";
import RevisionTimeline from "../components/RevisionTimeline";
import ShipView, { type ModelSrc, type View } from "../components/ShipView";
import { AccuracyBanner, NotRun, ReadinessCard, SourceChips } from "../components/Evidence";
import FindingsList from "../components/FindingsList";
import DemoRun, { type DemoStep } from "../components/DemoRun";
import TraceMatrix from "../components/TraceMatrix";
import ViewPane from "../components/ViewPane";
import type { ShipViewer } from "../viewer/ShipViewer";
import { Pill } from "../components/ui";
import { DISC } from "./Board";
import { valueLine } from "./Inbox";

const DISCS: { code: string; packs: string[]; color: string; sets: string }[] = [
  { code: "FIRE", packs: ["fls"], color: "#e27dff", sets: "SOLAS II-2 ✓ · FSS Code ✓" },
  { code: "HULL", packs: ["dnv", "sts"], color: "#5c9dff", sets: "DNV Pt.3 · IACS UR W11 / S6 · data quality · To verify" },
  { code: "INT", packs: ["acc"], color: "#b98cff", sets: "Accessibility (PVAG/ADA) ✓" },
  { code: "HVAC", packs: ["hvac"], color: "#3fd0e6", sets: "SOLAS II-2/9.7 dampers ✓" },
  { code: "GA", packs: [], color: "#c3c9d4", sets: "Coming" },
  { code: "PIPE", packs: ["sts"], color: "#c4e35c", sets: "SOLAS II-2/4.2.2.5.1 oil fuel pipes · To verify" },
  { code: "ELEC", packs: [], color: "#82dd8a", sets: "Coming" },
  { code: "MACH", packs: [], color: "#a3a3ff", sets: "Coming" },
];
const MAX_MB = 60;

type Shown = { meta: RunMeta & { bounds?: number[] | null; edited?: boolean }; run: Run };

/** a revision's file as the viewer and the readiness card name it */
export function srcOf(source: string | null | undefined): { view: ModelSrc; ready: { revision?: string; path?: string } | null } {
  if (!source) return { view: null, ready: null };
  if (source === "rcrv") return { view: { source: "rcrv" }, ready: { revision: "RCRV" } };
  if (source.startsWith("demo:")) return { view: { revision: source.slice(5) }, ready: { revision: source.slice(5) } };
  if (source.startsWith("path:")) return { view: { path: source.slice(5) }, ready: { path: source.slice(5) } };
  return { view: null, ready: null };
}

// ---------------------------------------------------------------------------------------------- Studio
export default function Studio({ scope: sc, openRev, refresh, onOpenFinding }: {
  scope: Scope; openRev: (id: number | null, pid?: number) => Promise<void>; refresh: () => Promise<void>; onOpenFinding: (c: Check) => void;
}) {
  const { project, rev, model, data } = sc;
  const shown: Shown | null = rev && data ? { meta: data, run: data.run } : null;
  const readOnly = rev?.state === "saved";
  const [upload, setUpload] = useState<{ name: string; revision: string | null; path: string | null; into: string } | null>(null);
  const [scope, setScope] = useState<"deck:5" | "whole">("deck:5");
  const [discs, setDiscs] = useState<string[]>(["FIRE", "HULL", "INT"]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [why, setWhy] = useState<{ key: string; text: string } | null>(null);
  const [setup, setSetup] = useState(!rev || !data);
  const [listMode, setListMode] = useState<"list" | "matrix">("list");
  const [tab, setTab] = useState<"findings" | "view" | "revisions">("findings");
  const [viewer, setViewer] = useState<{ v: ShipViewer | null; id: string | null }>({ v: null, id: null });
  const [incorrect, reloadInc] = useIncorrect();
  const view = useRef<View | null>(null);
  const fileIn = useRef<HTMLInputElement>(null);
  const [cmpPick, setCmpPick] = useState<number[] | undefined>(undefined);
  // demo run-through (spec B8): its own throwaway project; Stop restores what was open before
  const [demo, setDemo] = useState<{ pid: number; prev: { pid: number | null; rev: number | null; tab: typeof tab; mode: string | null; cuts: unknown[]; setup: boolean } } | null>(null);
  const vstat = useRef<{ state: string; msg: string }>({ state: "idle", msg: "" });
  useEffect(() => { setSetup(!rev || !data); setSel(null); setMsg(""); }, [rev?.id, !!data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (rev?.source === "rcrv") { setScope("whole"); setDiscs((d) => (d.includes("HULL") ? d : [...d, "HULL"])); } }, [rev?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const packs = [...new Set(DISCS.filter((d) => discs.includes(d.code)).flatMap((d) => d.packs))];
  // the 3D shows the revision's own file (cached by content hash); a run that chat edits changed shows that run's file
  const viewSrc: ModelSrc = shown?.meta.edited ? { run: shown.meta.id } : srcOf(rev?.source).view;
  const painted = useMemo(() => (shown ? shown.run.checks.filter((c) => ["fail", "warn", "unk"].includes(c.status) && !incorrect[c.check_key]) : null), [shown, incorrect]);

  const chooseFile = async (f: File) => {
    setMsg("");
    if (!project) return;
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
      setUpload({ name: f.name, revision: j.known ? j.revision : null, path: j.path, into: model ? String(model.id) : "new" });
    } catch (e) { setMsg(`Upload failed: ${(e as Error).message}`); }
    setBusy(false);
  };
  const fileUpload = async () => {
    if (!upload || !project) return;
    try {
      const body = { name: upload.name.replace(/\.ifc$/i, ""), revision: upload.revision, path: upload.path };
      const r = upload.into === "new" ? await api.modelAdd(project.id, body) : await api.revisionAdd(project.id, Number(upload.into), body);
      setUpload(null);
      await refresh(); await openRev(r.id);
      setMsg(`${upload.name} added as ${r.label}. Press Analyse.`);
    } catch (e) { setMsg(`Could not add the model: ${(e as Error).message}`); setUpload(null); }
  };
  const analyse = async () => {
    if (!rev || !packs.length) return;
    setBusy(true); setMsg(""); setSel(null); view.current?.showAll();
    try {
      const r = await apiFetch("/analyse", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ revision_id: rev.id, scope, packs }) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail ?? r.statusText);
      await refresh(); await openRev(d.run_meta.draft.id);
      if (d.run_meta.draft.id !== rev.id) setMsg(`${rev.label} is saved, so this analysis opened a new draft, ${d.run_meta.draft.label}, with the same marks and tasks.`);
    } catch (e) { setMsg(`Analyse failed: ${(e as Error).message}`); }
    setBusy(false);
  };
  const pick = (c: Check) => { setSel(c.check_key); view.current?.focus(c); };
  const mark = async (c: Check, reason: string) => {
    if (!reason.trim()) return;
    try { await api.markIncorrect({ check_key: c.check_key, finding: c.id, reason: reason.trim(), by: "Reviewer (browser)", revision: shown?.meta.revision, file: shown?.meta.file }); }
    catch (e) { setMsg(String((e as Error).message)); }
    setWhy(null); reloadInc();
  };
  const undo = async (key: string) => { try { await api.undoIncorrect(key); } catch (e) { setMsg(String((e as Error).message)); } reloadInc(); };
  // Export = save (B11): the engine freezes this revision, then the file comes from that saved revision
  const exportAs = async (fmt: "bcf" | "csv") => {
    if (!shown) return;
    try {
      const r = await api.revExport(shown.meta.id, fmt);
      await download(r.download, `sonariq_${r.label.replace(/[^A-Za-z0-9_-]+/g, "_")}.${fmt === "bcf" ? "bcfzip" : "csv"}`);
      await refresh();
      setMsg(`${fmt.toUpperCase()} exported · ${r.label} is saved as it is now. Analyse again to continue in a new draft.`);
    } catch (e) { setMsg(`Export failed: ${(e as Error).message}`); }
  };
  const latest = (m: RevModel) => m.revisions[m.revisions.length - 1];

  // ------------------------------------------------------------------ demo run-through
  const now = useRef({ sc, viewer, demo });
  now.current = { sc, viewer, demo };
  const [starting, setStarting] = useState(false);
  const startDemo = async () => {
    setStarting(true); setMsg("");
    try {
      const v = viewer.v;
      const prev = { pid: project?.id ?? null, rev: rev?.id ?? null, tab, mode: v?.mode ?? null, cuts: v ? [...v.cuts] : [], setup };
      const p = await api.projectDemo();
      setDemo({ pid: p.id, prev });
    } catch (e) { setMsg(`The demo could not start: ${(e as Error).message}`); }
    setStarting(false);
  };
  const stopDemo = async () => {
    const d = now.current.demo;
    if (!d) return;
    setDemo(null); setCmpPick(undefined);
    api.projectDelete(d.pid).catch(() => {});           // also deleted by the engine after an hour
    const { prev } = d;
    const v0 = now.current.viewer.v;
    if (v0) { v0.setSolo(null); v0.setCuts([]); }
    try {
      if (prev.pid != null) await openRev(prev.rev, prev.pid); else await openRev(null);
    } catch { /* the scope stays on what loads */ }
    setTab(prev.tab); setSetup(prev.setup); setSel(null);
    // display mode and cuts come back once the previous model is in the 3D again (at most 60 s)
    const t0 = Date.now();
    while (Date.now() - t0 < 60000) {
      const v = now.current.viewer.v;
      if (prev.rev == null) break;
      if (v && v.stats.firstFrame != null && vstat.current.state === "ready") {
        if (prev.mode) v.setMode(prev.mode as never);
        v.setCuts(prev.cuts as never);
        break;
      }
      if (vstat.current.state === "error") break;
      await new Promise((r) => setTimeout(r, 250));
    }
  };
  const dScope = () => now.current.sc;
  const dRev = (label: string) => dScope().project?.models[0]?.revisions.filter((r) => r.label === label || r.file === (label === "Rev A" ? "deck5_revA.ifc" : "deck5_revB.ifc")) ?? [];
  const demoFinding = () => dScope().data?.run.checks.find((c) => c.id === "F-07") ?? null;
  const inDemo = () => (dScope().project?.id === now.current.demo?.pid ? null : "the demo's own project is not open");
  const analyseRev = async (id: number) => {
    const r = await apiFetch("/analyse", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ revision_id: id, scope: "deck:5", packs: ["fls", "acc", "dnv"] }) });
    const d = await r.json(); if (!r.ok) throw new Error(d.detail ?? r.statusText);
    return d.run_meta as RunMeta & { draft: { id: number } };
  };
  const demoSteps: DemoStep[] = [
    { title: "1 · Data readiness", fail: "open the demo model",
      text: "The demo works in its own copy of the Deck 5 model, so nothing you have open changes. Before any rule runs, SonarIQ reads what the model actually contains (spaces, doors, fire ratings, systems). Rules the data cannot support are listed as not run, never guessed.",
      run: async ({ until }) => {
        const d = now.current.demo; if (!d) throw new Error("the demo project is missing");
        const p = await api.project(d.pid);
        const b = p.models[0]?.revisions.find((r) => r.label === "Rev B"); if (!b) throw new Error("Rev B is missing in the demo project");
        setTab("findings"); setSetup(true);
        await openRev(b.id, d.pid);
        await until(() => !!document.querySelector(".studio-setup .ready-card, .studio-setup [data-readiness]") || /Spaces/.test(document.querySelector(".studio-setup")?.textContent ?? ""), "the readiness check");
      } },
    { title: "2 · The whole model in 3D", fail: "load the 3D model", timeout: 60000, pre: inDemo,
      text: "The exact file is converted once on the engine into compressed web tiles and streamed. Every part keeps its IFC GlobalId, so a click maps to the engine's element.",
      run: async ({ until }) => {
        await until(() => {
          if (vstat.current.state === "error") throw new Error(vstat.current.msg || "the 3D view reported an error");
          return vstat.current.state === "ready" && now.current.viewer.v?.stats.firstFrame != null;
        }, "the 3D model", 60000);
        now.current.viewer.v?.view("iso");
      } },
    { title: "3 · Analyse, with the accuracy banner", fail: "run the analysis", pre: inDemo,
      text: "The deterministic rule engine runs. The banner compares the result with hand-checked findings and an independent scan: what was found, false alarms, expected passes.",
      run: async ({ until }) => {
        const a = dRev("Rev A")[0], b = dRev("Rev B").slice(-1)[0];
        if (!a || !b) throw new Error("the demo revisions are missing");
        // the compare step needs Rev A analysed and saved: done here, in the demo's own project
        if (a.state !== "saved") { const ra = await analyseRev(a.id); await api.revExport(ra.id, "report"); }
        const rb = await analyseRev(b.id);
        await refresh(); await openRev(rb.draft.id);
        setSetup(false);
        await until(() => !!demoFinding(), "the analysis");
        await until(() => !!document.querySelector(".acc-banner") && !/Checking/.test(document.querySelector(".acc-banner")?.textContent ?? ""), "the accuracy banner");
        document.querySelector(".acc-banner")?.scrollIntoView({ block: "nearest" });
      } },
    { title: "4 · One finding, with its callout", fail: "show the finding", pre: () => inDemo() ?? (demoFinding() ? null : "F-07 is not in this analysis"),
      text: "F-07: the stair is narrower than the FSS Code formula needs. The callout shows what the model has, what it must be with the formula filled in from the model, the clause, and where each value comes from.",
      run: async ({ until }) => { pick(demoFinding()!); await until(() => !!document.querySelector(".co-card, .co-pin.is-active"), "the callout"); } },
    { title: "5 · Section at the finding", fail: "cut the section", pre: () => inDemo() ?? (now.current.viewer.v ? null : "the 3D model is not loaded"),
      text: "One click cuts a deck plan through the finding and turns the camera to face it. Cut faces are capped, so walls and stairs read as solid.",
      run: async ({ until }) => {
        const c = demoFinding(); if (!c) throw new Error("F-07 is not in this analysis");
        if (!(await view.current?.sectionAt(c))) throw new Error("there is no position for the cut");
        await until(() => !(now.current.viewer.v as unknown as { anim: unknown } | null)?.anim, "the camera move");
      } },
    { title: "6 · X-ray, one system solo", fail: "switch the display", pre: () => inDemo() ?? (now.current.viewer.v ? null : "the 3D model is not loaded"),
      text: "X-ray with one system soloed and everything else as faint context. Deck 5 has no pipes, so this solos the HVAC ducts; on the RCRV whole ship the same button solos piping.",
      run: () => {
        const v = now.current.viewer.v!;
        view.current?.showAll(); setSel(null); v.setCuts([]);
        // piping when the model has pipes (the group can exist with no parts), else HVAC
        const g = v.index.groups, pipe = g.indexOf("piping"), k = pipe >= 0 && v.disc.includes(pipe) ? pipe : g.indexOf("hvac");
        v.setMode("xray"); if (k >= 0) v.setSolo(k); setTab("view");
      } },
    { title: "7 · Revisions and compare", fail: "compare the revisions", pre: inDemo,
      text: "Saving keeps a revision exactly as it was. Comparing the saved Rev A with this analysis of Rev B: the new cabins add three findings, matched by element ID.",
      run: async ({ until }) => {
        const v = now.current.viewer.v; if (v) { v.setSolo(null); v.setMode("edges"); }
        await refresh();
        const a = dRev("Rev A").find((r) => r.state === "saved"), b = dScope().rev;
        if (!a || !b) throw new Error("there is no Rev A / Rev B pair to compare");
        setCmpPick([a.id, b.id]); setTab("revisions");
        await until(() => !!document.querySelector('[aria-label="Compare revisions"]'), "the comparison");
      } },
    { title: "8 · BCF export", fail: "export BCF", pre: () => inDemo() ?? (dScope().data ? null : "there is no analysis to export"),
      text: "Findings go to the CAD tool as BCF (the FreeCAD panel reads them back on the right parts). Exporting saves this revision; findings marked incorrect are left out. All of this stays in the demo's own project, which is deleted when the demo ends.",
      run: async () => { setTab("findings"); await exportAs("bcf"); } },
  ];

  // Clear all: optionally save this revision (the step 7 save), then close the model; Studio, Inbox and Tasks go empty
  const [clearAsk, setClearAsk] = useState(false);
  const [clearing, setClearing] = useState(false);
  const canSave = !!shown && !readOnly;
  const clearAll = async (save: boolean) => {
    setClearing(true);
    try {
      if (save && shown) await api.revExport(shown.meta.id, "report");
      await openRev(null); await refresh();
      setClearAsk(false); setSetup(true);
      setMsg(save && rev ? `${rev.label} saved. Pick it again from the Revision menu any time.` : "");
    } catch (e) { setMsg(`Could not save: ${(e as Error).message}`); setClearAsk(false); }
    setClearing(false);
  };

  const renderCard = (c: Check) => {
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
                    <SourceChips c={c} />
                    {inc && <div className="inc-why flex items-center gap-2"><span style={{ flex: 1 }}>Marked incorrect · {inc.reason} · not exported</span>
                      {!readOnly && <button className="studio-link" onClick={(e) => { e.stopPropagation(); undo(c.check_key); }}>Undo</button>}</div>}
                    {on && (
                      <div className="flex gap-1" style={{ flexWrap: "wrap", marginTop: 4 }} onClick={(e) => e.stopPropagation()}>
                        <button className="sq-btn is-sm is-primary" onClick={() => view.current?.zoom()}>Zoom to</button>
                        <button className="sq-btn is-sm" onClick={() => view.current?.isolate(c)}>Isolate</button>
                        <button className="sq-btn is-sm" onClick={() => view.current?.sectionAt(c)} title="Cut through this finding and face the cut">Section at finding</button>
                        <button className="sq-btn is-sm" onClick={() => { view.current?.showAll(); setSel(null); }}>Show all</button>
                        {!inc && !readOnly && <button className="sq-btn is-sm studio-warn" onClick={() => setWhy({ key: c.check_key, text: "" })}>Incorrect finding</button>}
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
  };

  return (
    <div className="studio">
      <div className="studio-left">
        <ShipView src={viewSrc} findings={painted} apiRef={view} onViewer={(v, id) => setViewer({ v, id })} onPick={pick} onOpenEvidence={onOpenFinding}
          noConvert={!!demo} onStatus={(state, m) => { vstat.current = { state, msg: m }; }} />
        {demo && <DemoRun steps={demoSteps} onStop={stopDemo} />}
      </div>
      <aside className="studio-panel">
        <header className="studio-head">
          <span className="studio-title"><b>Studio</b>
            <span className="mono sq-muted studio-file" title={rev?.file ?? ""}>{rev ? `${model?.name} · ${rev.label}${readOnly ? " · saved, read-only" : !data ? " · not analysed yet" : ""}` : "No model open"}</span></span>
          <span style={{ flex: 1 }} />
          <button className="sq-btn" aria-expanded={setup} onClick={() => setSetup(!setup || !rev)}>Open model</button>
          {rev && <button className="sq-btn" onClick={() => setClearAsk(true)}>Clear all</button>}
          <button className="sq-btn is-primary" disabled={busy || !rev || !packs.length} title={!rev ? "Open a model to analyse" : ""} onClick={() => analyse()}>{busy ? "Analysing…" : "Analyse"}</button>
          {shown && <button className="sq-btn" onClick={() => { location.hash = `#inbox/${shown.meta.id}`; }}>Export</button>}
          <button className="sq-btn" aria-pressed={!!demo} aria-label="Demo run-through" disabled={starting} onClick={() => (demo ? stopDemo() : startDemo())}
                  title="Demo run-through: a guided tour that plays by itself (Space / → next, Esc stops). It works in its own copy of the demo model and changes nothing here.">{demo ? "Stop" : starting ? "Starting…" : "▶ Demo"}</button>
        </header>
        <div className="sq-seg studio-tabs" role="tablist" aria-label="Panel">
          {(["findings", "view", "revisions"] as const).map((k) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "is-on" : ""} onClick={() => setTab(k)}>{k === "findings" ? "Findings" : k === "view" ? "View" : "Revisions"}</button>)}
        </div>
        {tab === "view" ? <ViewPane v={viewer.v} modelId={viewer.id} /> : tab === "revisions" ? <RevisionTimeline models={model ? [model] : []} current={rev?.id ?? null} onOpen={(r) => openRev(r.id)} pick={cmpPick} /> : <>
        {readOnly && <div className="sq-banner studio-past"><span style={{ flex: 1 }}><b>{rev!.label}</b> · saved {rev!.saved_at?.replace("T", " ").slice(0, 16)} · read-only: verdicts, marks and tasks as they were saved. Analyse to continue in a new draft.</span></div>}
        {shown && !readOnly && <div className="sq-faint" style={{ fontSize: 12, textAlign: "right", padding: "0 12px 6px" }}>All findings are exported except those marked incorrect.</div>}
        {msg && <div className="sq-banner" style={{ margin: "0 12px 8px" }}>{msg}</div>}
        {!setup && shown && (
          <div className="studio-sum">
            <span style={{ flex: 1 }}>{shown.run.scope === "whole" ? "Whole model" : "Deck 5"} · {discs.filter((d) => DISCS.find((x) => x.code === d)?.packs.length).join(" ")}<br />
              <span className="mono sq-faint" style={{ fontSize: 12 }}>{rev?.label} · {shown.run.total_checks} checks · {shown.meta.time.slice(11, 16)}{shown.meta.scope_note ? " · whole model" : ""}</span></span>
            <a className="sq-btn is-sm" href={`#print/${encodeURIComponent(shown.meta.id)}`} target="_blank" rel="noreferrer">Report</a>
            <button className="sq-btn is-sm" onClick={() => exportAs("csv")}>CSV</button>
            <button className="sq-btn is-sm" onClick={() => exportAs("bcf")}>BCF</button>
            <button className="sq-btn is-sm" onClick={() => setSetup(true)}>Edit</button>
          </div>
        )}
        {setup && (
          <div className="studio-setup">
            <div className="sq-label">Open model · {project?.name ?? "…"}</div>
            <div className="flex flex-col gap-1 studio-models" role="list" aria-label="Models in this project">
              {(project?.models ?? []).map((m) => { const r = latest(m); return (
                <button key={m.id} role="listitem" className={`studio-model${model?.id === m.id ? " is-on" : ""}`} onClick={() => r && openRev(r.id)} disabled={!r}>
                  <span className="mono">{m.name}</span><span className="sq-faint">{r ? `${r.label}${r.counts ? ` · ${r.counts.fail ?? 0} fail` : " · not analysed"} · ${m.revisions.length} revision${m.revisions.length === 1 ? "" : "s"}` : "no revisions"}</span>
                </button>); })}
              {project && !project.models.length && <p className="sq-muted" style={{ fontSize: 12 }}>No models in this project yet.</p>}
              <button className="studio-model" disabled={!project || !!project.demo} onClick={() => fileIn.current?.click()}><span>Upload IFC…</span><span className="sq-faint">IFC4 · up to {MAX_MB} MB</span></button>
              <input ref={fileIn} type="file" accept=".ifc" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) chooseFile(f); e.target.value = ""; }} />
            </div>
            {rev && !data && <div style={{ marginTop: 10 }}><ReadinessCard src={srcOf(rev.source).ready} /></div>}
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
                <div key={d.code} className="flex gap-2" style={{ fontSize: 12 }}><b className="mono" style={{ color: d.color, width: 40 }}>{d.code}</b><span className={d.packs.length ? "" : "sq-faint"}>{d.sets}</span></div>
              ))}
              {!packs.length && <div className="sq-muted" style={{ fontSize: 12 }}>Pick a discipline with rule sets.</div>}
            </div>
          </div>
        )}
        {shown && (
          <>
            <AccuracyBanner revision={shown.meta.revision} verified={shown.run.rules_verified_against_official_text} />
            {shown.run.readiness && <details className="ready-details"><summary>Data readiness</summary><ReadinessCard src={null} given={shown.run.readiness} /></details>}
            <NotRun rows={shown.run.not_run ?? []} />
            <div className="flex gap-1 studio-chips">
              {(["fail", "warn", "unk", "pass", "dor"] as const).map((s) => (
                <button key={s} className={`ib-chip${status === s ? " is-on" : ""}`} onClick={() => setStatus(status === s ? null : s)}>
                  <span className={`sq-pill s-${s}`} style={{ border: 0, background: "none", padding: 0 }}><i className="sq-ico" /></span><b>{shown.run.counts[s] ?? 0}</b> {WORD[s]}
                </button>
              ))}
            </div>
            <div className="sq-seg studio-mode" role="tablist" aria-label="Findings view">
              {(["list", "matrix"] as const).map((k) => <button key={k} role="tab" aria-selected={listMode === k} className={listMode === k ? "is-on" : ""} onClick={() => setListMode(k)}>{k === "list" ? "List" : "Traceability"}</button>)}
            </div>
            {listMode === "list"
              ? <FindingsList run={shown.run} status={status} selected={sel} onPick={pick} renderCard={renderCard} incorrect={incorrect} />
              : <TraceMatrix run={shown.run} selected={sel} onPick={pick} />}
          </>
        )}
        </>}
      </aside>
      {clearAsk && rev && (
        <div className="sq-overlay" onClick={() => !clearing && setClearAsk(false)}>
          <div className="sq-card sq-modal" role="dialog" aria-label="Clear all" onClick={(e) => e.stopPropagation()}>
            <h2 className="sq-h2" style={{ margin: "0 0 6px" }}>{canSave ? `Save your progress to ${rev.label} first?` : `Close ${model?.name} · ${rev.label}?`}</h2>
            <p className="sq-muted">{canSave ? "Findings, marks, inbox items and tasks will be kept on this revision." : readOnly ? `${rev.label} is already saved, so nothing is lost.` : "Nothing has been analysed on this revision yet, so there is nothing to save."} Studio, Inbox and Tasks then start empty; you can reopen the model from Open model or the Revision menu.</p>
            <div className="flex gap-2" style={{ justifyContent: "flex-end", flexWrap: "wrap" }}>
              <button className="sq-btn" disabled={clearing} onClick={() => setClearAsk(false)}>Cancel</button>
              {canSave ? <>
                <button className="sq-btn" disabled={clearing} onClick={() => clearAll(false)}>Clear without saving</button>
                <button className="sq-btn is-primary" disabled={clearing} autoFocus onClick={() => clearAll(true)}>{clearing ? "Saving…" : "Save and clear"}</button>
              </> : <button className="sq-btn is-primary" disabled={clearing} autoFocus onClick={() => clearAll(false)}>Clear</button>}
            </div>
          </div>
        </div>
      )}
      {upload && (
        <div className="sq-overlay" onClick={() => setUpload(null)}>
          <form className="sq-card sq-modal" role="dialog" aria-label="Add the uploaded model" onClick={(e) => e.stopPropagation()} onSubmit={(e) => { e.preventDefault(); fileUpload(); }}>
            <h2 className="sq-h2" style={{ margin: "0 0 6px" }}>Add {upload.name} to {project?.name}</h2>
            <p className="sq-muted">Is this a new model, or a new version of a model you already have here?</p>
            <label className="flex items-center gap-2"><input type="radio" name="into" checked={upload.into === "new"} onChange={() => setUpload({ ...upload, into: "new" })} /> New model in this project</label>
            {(project?.models ?? []).map((m) => (
              <label key={m.id} className="flex items-center gap-2"><input type="radio" name="into" checked={upload.into === String(m.id)} onChange={() => setUpload({ ...upload, into: String(m.id) })} /> New revision of {m.name}</label>
            ))}
            <div className="flex gap-2" style={{ justifyContent: "flex-end", marginTop: 12 }}>
              <button type="button" className="sq-btn" onClick={() => setUpload(null)}>Cancel</button>
              <button className="sq-btn is-primary">Add</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
