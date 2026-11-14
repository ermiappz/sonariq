// Web Studio ("Review in the browser"): open a demo model or upload an IFC, Analyse with scope + disciplines like the
// FreeCAD panel, and inspect findings next to the 3D. The viewer always loads the exact file of the run shown
// (the engine converts that file once to web tiles: POST /models/prepare); every verdict and number comes from the engine.
import { useEffect, useMemo, useRef, useState } from "react";
import { api, apiFetch, download, WORD, useIncorrect, type Check, type Incorrect, type RevModel, type Revision, type Run, type RunMeta } from "../api";
import RevisionTimeline from "../components/RevisionTimeline";
import ShipView, { type ModelSrc, type View } from "../components/ShipView";
import { AccuracyBanner, NotRun, ReadinessCard, SourceChips } from "../components/Evidence";
import FindingsList from "../components/FindingsList";
import TraceMatrix from "../components/TraceMatrix";
import ViewPane from "../components/ViewPane";
import type { ShipViewer } from "../viewer/ShipViewer";
import { Pill } from "../components/ui";
import { DISC } from "./Board";
import { valueLine } from "./Inbox";

const DEMOS = [
  { rev: "A", file: "deck5_revA.ifc", note: "Deck 5 · baseline" },
  { rev: "B", file: "deck5_revB.ifc", note: "OR-117 · 4 cabins added" },
  { rev: "Bfix2", file: "deck5_revB_fix2.ifc", note: "fix 2 · one berth each" },
];
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

type Target = { kind: "demo"; rev: string; name: string } | { kind: "upload"; path: string | null; rev: string | null; name: string }
  | { kind: "rcrv"; name: string };
type Shown = { meta: RunMeta & { bounds?: number[] | null; edited?: boolean }; run: Run };

// ---------------------------------------------------------------------------------------------- Studio
export default function Studio({ latest, run, onOpenFinding }: { latest: (RunMeta & { bounds?: number[] | null; edited?: boolean }) | null; run: Run | null; onOpenFinding: (c: Check) => void }) {
  const [local, setLocal] = useState<Shown | null>(null);
  // a saved revision opened from the timeline: shown read-only with the marks it was saved with
  const [past, setPast] = useState<{ rev: Revision; shown: Shown; marks: Record<string, Incorrect> } | null>(null);
  const live: Shown | null = local && (!latest || latest.seq <= local.meta.seq) ? local : latest && run ? { meta: latest, run } : null;
  const shown = past ? past.shown : live;
  const [into, setInto] = useState("new");        // upload: "new" model or the id of the model it is a revision of
  const [revModels, setRevModels] = useState<RevModel[]>([]);
  const [target, setTarget] = useState<Target | null>(null);
  const [scope, setScope] = useState<"deck:5" | "whole">("deck:5");
  const [discs, setDiscs] = useState<string[]>(["FIRE", "HULL", "INT"]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [why, setWhy] = useState<{ key: string; text: string } | null>(null);
  const [setup, setSetup] = useState(true);
  const [listMode, setListMode] = useState<"list" | "matrix">("list");
  const [tab, setTab] = useState<"findings" | "view" | "revisions">("findings");
  const [viewer, setViewer] = useState<{ v: ShipViewer | null; id: string | null }>({ v: null, id: null });
  const [liveMarks, reloadInc] = useIncorrect();
  const incorrect = past ? past.marks : liveMarks;
  const view = useRef<View | null>(null);
  const fileIn = useRef<HTMLInputElement>(null);
  useEffect(() => { if (shown) setSetup(false); }, [shown?.meta.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const packs = [...new Set(DISCS.filter((d) => discs.includes(d.code)).flatMap((d) => d.packs))];
  // the viewer shows the model as soon as it is opened; after Analyse it keeps that file (same camera) when the run
  // read the same file unedited, otherwise it shows exactly the run's file
  const targetSrc: ModelSrc = target ? (target.kind === "rcrv" ? { source: "rcrv" } : target.kind === "demo" ? { revision: target.rev }
    : target.path ? { path: target.path } : target.rev ? { revision: target.rev } : null) : null;
  const runSrc: ModelSrc = shown ? { run: shown.meta.id } : null;
  const [viewSrc, setViewSrc] = useState<{ src: ModelSrc; file: string | null }>({ src: null, file: null });
  const tkey = JSON.stringify(targetSrc), rkey = JSON.stringify(runSrc);
  useEffect(() => {
    if (target) { if (tkey !== JSON.stringify(viewSrc.src)) setViewSrc({ src: targetSrc, file: target.name }); return; }
    if (!shown) { setViewSrc({ src: null, file: null }); return; }
    if (viewSrc.src && viewSrc.file === shown.meta.file && !shown.meta.edited) return;
    setViewSrc({ src: runSrc, file: shown.meta.file });
  }, [tkey, rkey]); // eslint-disable-line react-hooks/exhaustive-deps
  const painted = useMemo(() => (shown && !target ? shown.run.checks.filter((c) => ["fail", "warn", "unk"].includes(c.status) && !incorrect[c.check_key]) : null), [shown, target, incorrect]);

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
      setTarget({ kind: "upload", path: j.path, rev: j.revision, name: f.name }); setSetup(true); setPast(null); setInto("new");
      api.revisions().then((m) => setRevModels(m.models)).catch(() => {});
      setMsg(j.known ? `${f.name} is the demo file Rev ${j.revision}.` : `${f.name} uploaded. Press Analyse.`);
    } catch (e) { setMsg(`Upload failed: ${(e as Error).message}`); }
    setBusy(false);
  };
  const analyse = async () => {
    const t = target ?? (shown ? { kind: "demo", rev: shown.meta.revision, name: shown.meta.file } as Target : null);
    if (!t || !packs.length) return;
    setBusy(true); setMsg(""); setSel(null); view.current?.showAll();
    try {
      const body = t.kind === "rcrv" ? { revision: "RCRV", scope: "whole", packs }
        : t.kind === "demo" ? { revision: t.rev, scope, packs } : { revision: t.path ? null : t.rev, path: t.path, scope, packs,
          ...(into === "new" ? { new_model: t.name.replace(/\.ifc$/i, "") } : { model_id: Number(into) }) };
      const r = await apiFetch("/analyse", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail ?? r.statusText);
      setLocal({ meta: { ...d.run_meta }, run: d }); setTarget(null); setStatus(null); setPast(null);
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
  // Export = save (B11): the engine freezes this run's revision, then the file comes from that saved revision
  const exportAs = async (fmt: "bcf" | "csv") => {
    if (!shown) return;
    try {
      const r = await api.revExport(shown.meta.id, fmt);
      await download(r.download, `sonariq_${r.label.replace(/[^A-Za-z0-9_-]+/g, "_")}.${fmt === "bcf" ? "bcfzip" : "csv"}`);
      setMsg(`${fmt.toUpperCase()} exported · saved as ${r.label} (frozen; the next Analyse starts a new draft).`);
    } catch (e) { setMsg(`Export failed: ${(e as Error).message}`); }
  };
  const openPast = async (r: Revision) => {
    try {
      const d = await api.revGet(r.id);
      setPast({ rev: r, shown: { meta: d.data, run: d.data.run }, marks: d.data.snapshot?.marks.incorrect ?? {} });
      setTarget(null); setSel(null); setTab("findings"); setMsg("");
    } catch (e) { setMsg(`Could not open ${r.label}: ${(e as Error).message}`); }
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
                      {!past && <button className="studio-link" onClick={(e) => { e.stopPropagation(); undo(c.check_key); }}>Undo</button>}</div>}
                    {on && (
                      <div className="flex gap-1" style={{ flexWrap: "wrap", marginTop: 4 }} onClick={(e) => e.stopPropagation()}>
                        <button className="sq-btn is-sm is-primary" onClick={() => view.current?.zoom()}>Zoom to</button>
                        <button className="sq-btn is-sm" onClick={() => view.current?.isolate(c)}>Isolate</button>
                        <button className="sq-btn is-sm" onClick={() => view.current?.sectionAt(c)} title="Cut through this finding and face the cut">Section at finding</button>
                        <button className="sq-btn is-sm" onClick={() => { view.current?.showAll(); setSel(null); }}>Show all</button>
                        {!inc && !past && <button className="sq-btn is-sm studio-warn" onClick={() => setWhy({ key: c.check_key, text: "" })}>Incorrect finding</button>}
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
        <ShipView src={viewSrc.src} findings={painted} apiRef={view} onViewer={(v, id) => setViewer({ v, id })} onPick={pick} onOpenEvidence={onOpenFinding} />
      </div>
      <aside className="studio-panel">
        <header className="studio-head">
          <span className="studio-title"><b>Studio</b>
            <span className="mono sq-muted studio-file" title={label ?? ""}>{label ? label.replace(/\.ifc$/i, "") : "No model open"}{past ? ` · ${past.rev.label} · read-only` : shown && !target ? ` · Rev ${shown.meta.revision}` : target ? " · not analysed yet" : ""}</span></span>
          <span style={{ flex: 1 }} />
          {past ? <button className="sq-btn" onClick={() => setPast(null)}>Back to current</button> : <>
          <button className="sq-btn" onClick={() => setSetup(!setup)}>{setup ? "Close" : "Open model"}</button>
          <button className="sq-btn is-primary" disabled={busy || (!target && !shown) || !packs.length} title={!target && !shown ? "Open an IFC model to analyse" : ""} onClick={analyse}>{busy ? "Analysing…" : "Analyse"}</button>
          {shown && !target && <button className="sq-btn" onClick={() => { location.hash = `#inbox/${shown.meta.id}`; }}>Export</button>}</>}
        </header>
        <div className="sq-seg studio-tabs" role="tablist" aria-label="Panel">
          {(["findings", "view", "revisions"] as const).map((k) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "is-on" : ""} onClick={() => setTab(k)}>{k === "findings" ? "Findings" : k === "view" ? "View" : "Revisions"}</button>)}
        </div>
        {tab === "view" ? <ViewPane v={viewer.v} modelId={viewer.id} /> : tab === "revisions" ? <RevisionTimeline current={shown?.meta.id ?? null} onOpen={openPast} /> : <>
        {past && <div className="sq-banner studio-past"><span style={{ flex: 1 }}><b>{past.rev.label}</b> · saved {past.rev.saved_at?.replace("T", " ").slice(0, 16)} · read-only: verdicts and marks as they were saved.</span>
          <button className="sq-btn is-sm" onClick={() => setPast(null)}>Back to current</button></div>}
        {shown && !target && <div className="sq-faint" style={{ fontSize: 12, textAlign: "right", padding: "0 12px 6px" }}>All findings are exported except those marked incorrect.</div>}
        {msg && <div className="sq-banner" style={{ margin: "0 12px 8px" }}>{msg}</div>}
        {!setup && shown && (
          <div className="studio-sum">
            <span style={{ flex: 1 }}>{shown.run.scope === "whole" ? "Whole model" : "Deck 5"} · {discs.filter((d) => DISCS.find((x) => x.code === d)?.packs.length).join(" ")}<br />
              <span className="mono sq-faint" style={{ fontSize: 12 }}>Rev {shown.meta.revision} · {shown.run.total_checks} checks · {shown.meta.time.slice(11, 16)}{shown.meta.scope_note ? " · whole model" : ""}</span></span>
            <a className="sq-btn is-sm" href={`#print/${encodeURIComponent(shown.meta.id)}`} target="_blank" rel="noreferrer">Report</a>
            <button className="sq-btn is-sm" onClick={() => exportAs("csv")}>CSV</button>
            <button className="sq-btn is-sm" onClick={() => exportAs("bcf")}>BCF</button>
            {!past && <button className="sq-btn is-sm" onClick={() => setSetup(true)}>Edit</button>}
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
              <button className={`studio-model${target?.kind === "rcrv" ? " is-on" : ""}`} onClick={() => { setTarget({ kind: "rcrv", name: "RCRV whole ship" }); setMsg(""); setDiscs((d) => (d.includes("HULL") ? d : [...d, "HULL"])); }}>
                <span className="mono">RCRV whole ship</span><span className="sq-faint">research vessel · 90,331 parts</span>
              </button>
              <button className="studio-model" onClick={() => fileIn.current?.click()}><span>Upload IFC…</span><span className="sq-faint">IFC4 · up to {MAX_MB} MB</span></button>
              <input ref={fileIn} type="file" accept=".ifc" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
            </div>
            {target?.kind === "upload" && (
              <label className="flex flex-col gap-1" style={{ marginTop: 10 }}><span className="sq-label">Save as</span>
                <select className="sq-input" value={into} onChange={(e) => setInto(e.target.value)}>
                  <option value="new">New model</option>
                  {revModels.map((m) => <option key={m.id} value={String(m.id)}>New revision of {m.name}</option>)}
                </select></label>
            )}
            {target && <div style={{ marginTop: 10 }}><ReadinessCard src={target.kind === "rcrv" ? { revision: "RCRV" } : target.kind === "demo" ? { revision: target.rev } : target.path ? { path: target.path } : { revision: target.rev ?? "A" }} /></div>}
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
        {shown && !target && (
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
    </div>
  );
}
