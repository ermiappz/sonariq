// SonarIQ portal v2 (design 12-portal-new): Home at / (no hash), workspace screens behind #<screen>. Data comes from the
// engine API; the portal never computes a verdict. #inbox/<run id> (FreeCAD Export) opens that run and offers a report.
import { useEffect, useRef, useState } from "react";
import { api, SCOPE, useIncorrect, type Check, type Project, type Report, type RevModel, type Revision, type Run, type RunMeta } from "./api";
import Inbox from "./screens/Inbox";
import Thread from "./screens/Thread";
import Studio from "./screens/Studio";
import Rulebook from "./screens/Rulebook";
import Mapping from "./screens/Mapping";
import Simulate from "./screens/Simulate";
import { Lockup } from "./components/Brand";
import Revisions from "./screens/Revisions";
import Board from "./screens/Board";
import Home from "./screens/Home";
import { Pill } from "./components/ui";
import PrintReport from "./screens/PrintReport";

type Screen = "simulate" | "projects" | "inbox" | "board" | "thread" | "model" | "rules" | "mapping" | "benchmark" | "revisions" | "settings";
const USER = { name: "Mikko Saari", role: "Fire & life safety lead", initials: "MS" }; // sample person from the design

const hashParts = () => location.hash.slice(1).split("/");
const RUN_RE = /^[0-9]{4,}_[0-9]{8}-[0-9]{6}$/;

export default function App() {
  const [home, setHome] = useState(!location.hash || location.hash === "#");
  useEffect(() => {
    const on = () => setHome(!location.hash || location.hash === "#");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  if (location.hash.startsWith("#print/")) return <PrintReport id={decodeURIComponent(location.hash.slice(7))} />;
  if (home) return <Home onLogin={() => { location.hash = "#inbox"; setHome(false); }} />;
  return <Workspace />;
}

// per-browser conveniences only (the open project and revision); every read and write may fail (private mode)
export const LS = {
  get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string | null) => { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch { /* not kept */ } },
};
type RevData = RunMeta & { run: Run; bounds?: number[] | null; edited?: boolean };
export type Scope = { project: Project | null; rev: Revision | null; model: RevModel | null; data: RevData | null; loading: boolean };
const countsLine = (r: Revision) => (r.counts ? `${r.counts.fail ?? 0} fail · ${r.counts.pass ?? 0} pass · ${r.counts.unk ?? 0} cannot verify` : "not analysed");

function Workspace() {
  const first = hashParts();
  const [screen, setScreenState] = useState<Screen>(((first[0] || "model") as Screen));
  const [simOn, setSimOn] = useState(false);
  useEffect(() => { api.health().then((h: any) => setSimOn(!!h.simulate)).catch(() => {}); }, []);
  const setScreen = (s: Screen) => { setScreenState(s); history.replaceState(null, "", "#" + s); };
  const [units, setUnits] = useState<"mm" | "in">("mm");
  const [light, setLight] = useState(false);
  const [open, setOpen] = useState<string | null>(first[0] === "thread" ? first[1] : null);
  const [error, setError] = useState("");
  // Export landing: #inbox/<run id> opens that run's revision and asks "Create report from this run?"
  const [pinned, setPinned] = useState<string | null>(first[0] === "inbox" && RUN_RE.test(first[1] ?? "") ? first[1] : null);
  const [ask, setAsk] = useState<(RunMeta & { run: Run }) | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [toast, setToast] = useState("");
  const [nameAsk, setNameAsk] = useState<{ mode: "new" | "rename"; text: string } | null>(null);
  const [incorrect] = useIncorrect();
  useEffect(() => {   // an Export link opened in a tab that already shows the portal
    const on = () => {
      const h = hashParts();
      if (h[0] === "inbox" && RUN_RE.test(h[1] ?? "")) { setPinned(h[1]); setScreenState("inbox"); }
    };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  // ---------------------------------------------------------------- scope: project → model → revision
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [revId, setRevId] = useState<number | null>(null);
  const [data, setData] = useState<RevData | null>(null);
  const [loading, setLoading] = useState(false);
  SCOPE.rev = revId;
  const rev = project?.models.flatMap((m) => m.revisions).find((r) => r.id === revId) ?? null;
  const model = rev ? project!.models.find((m) => m.id === rev.model_id) ?? null : null;
  const dataFor = useRef<{ id: number | null; run: string | null }>({ id: null, run: null });
  const loadData = async (id: number | null) => {
    dataFor.current = { id, run: null };
    if (id == null) { setData(null); return; }
    setLoading(true);
    try {
      const d = await api.revGet(id);
      if (dataFor.current.id !== id) return;
      dataFor.current.run = d.run_id; setData(d.data as RevData | null); setError("");
    } catch (e) { if (dataFor.current.id === id) { setData(null); setError(`Could not open this revision: ${e}`); } }
    finally { if (dataFor.current.id === id) setLoading(false); }
  };
  /** switch scope. `pid` opens that project first (the demo, an Export link); revision null = no model open */
  const openRev = async (id: number | null, pid?: number) => {
    let p = project;
    if (pid != null && pid !== project?.id) {
      p = await api.project(pid);
      setProject(p);
      if (!p.demo) LS.set("sq.project", String(pid));
    }
    if (p && !p.demo) LS.set(`sq.rev.${p.id}`, id == null ? null : String(id));
    SCOPE.rev = id; setRevId(id);
    await loadData(id);
  };
  const openProject = async (pid: number) => {
    const p = await api.project(pid);
    const saved = Number(LS.get(`sq.rev.${pid}`));
    const has = p.models.some((m) => m.revisions.some((r) => r.id === saved));
    setProject(p);
    if (!p.demo) LS.set("sq.project", String(pid));
    SCOPE.rev = has ? saved : null; setRevId(has ? saved : null);
    await loadData(has ? saved : null);
  };
  const refresh = async () => {
    const ps = await api.projects().catch(() => null);
    if (ps) setProjects(ps.projects);
    if (!project) return;
    const p = await api.project(project.id).catch(() => null);
    if (!p) return;
    setProject(p);
    const r = p.models.flatMap((m) => m.revisions).find((x) => x.id === dataFor.current.id);
    if (r && r.run_id !== dataFor.current.run) await loadData(r.id);   // a new analysis landed (Studio or FreeCAD panel)
  };
  useEffect(() => {   // start: the project this browser had open, else the shared demo project
    api.projects().then(async (r) => {
      setProjects(r.projects);
      const want = Number(LS.get("sq.project"));
      const p = r.projects.find((x) => x.id === want) ?? r.projects.find((x) => x.shared) ?? r.projects[0];
      if (p && !pinned) await openProject(p.id);
    }).catch((e) => setError(`Engine not reachable (${e}).` + (["localhost", "127.0.0.1"].includes(location.hostname) ? " Start it with: make api" : " The hosted engine may be restarting; reload in a minute.")));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const projRef = useRef(project); projRef.current = project;
  const refreshRef = useRef(refresh); refreshRef.current = refresh;
  useEffect(() => { const t = setInterval(() => { if (projRef.current) refreshRef.current(); }, 3000); return () => clearInterval(t); }, []);
  const [runs, setRuns] = useState<RunMeta[] | null>(null);
  useEffect(() => { if (screen === "revisions") api.runs().then((r) => setRuns(r.runs)).catch(() => {}); }, [screen, data?.id]);

  useEffect(() => { api.reports().then((r) => setReports(r.reports)).catch(() => {}); }, []);
  useEffect(() => {
    if (!pinned) return;
    api.runScope(pinned).then((s) => openRev(s.rid, s.pid)).catch(() => {});
    api.runGet(pinned).then((r) => { if (!reports.find((x) => x.run_id === pinned)) setAsk(r); }).catch(() => setPinned(null));
  }, [pinned]); // eslint-disable-line react-hooks/exhaustive-deps
  const createReport = async () => {
    if (!ask) return;
    try {
      const rep = await api.report(ask.id);
      setReports((rs) => rs.some((x) => x.id === rep.id) ? rs : [...rs, rep]);
      const rv = (rep as { saved_revision?: { label: string } }).saved_revision;
      setToast((rep.existing ? `Report ${rep.id} already exists for this run` : `Report ${rep.id} created`) + (rv ? ` · saved as ${rv.label}` : ""));
      setTimeout(() => setToast(""), 5000);
      refresh();
    } catch (e) { setError(String(e)); }
    setAsk(null); setScreen("inbox");
  };
  const saveName = async () => {
    if (!nameAsk) return;
    const name = nameAsk.text.trim();
    if (!name) return;
    try {
      if (nameAsk.mode === "new") { const p = await api.projectCreate(name); await refresh(); await openProject(p.id); }
      else if (project) { setProject(await api.projectUpdate(project.id, { name })); await refresh(); }
      setNameAsk(null);
    } catch (e) { setError(String(e)); setNameAsk(null); }
  };

  const run = data?.run ?? null;
  const openFinding = (c: Check) => { setOpen(c.id ?? c.check_key); setScreenState("thread"); history.replaceState(null, "", "#thread/" + (c.id ?? c.check_key)); };
  const inboxN = run?.findings.length ?? 0;
  const nav: [Screen, string, number?][] = [["model", "Studio"], ["inbox", "Inbox", inboxN], ["board", "Tasks", inboxN], ["projects", "Projects"],
    ["rules", "Rules"], ["benchmark", "Benchmark"], ["revisions", "Revisions"], ...(simOn ? [["simulate", "Simulate"] as [Screen, string]] : []),
    ["mapping", "Mapping review"]];
  const report = data ? reports.find((x) => x.run_id === data.id) : undefined;
  const title = screen === "thread" ? "Inbox" : screen === "settings" ? "Settings" : nav.find(([k]) => k === screen)?.[1] ?? "Workspace";
  useEffect(() => { document.title = `SonarIQ — ${title}`; }, [title]);
  const scope: Scope = { project, rev, model, data, loading };
  const where = project ? [project.name, model?.name, rev?.label].filter(Boolean).join(" · ") : "";
  const simRev = data && ["A", "B", "Bfix2"].includes(data.revision) ? data.revision : "B";
  const noModel = (what: string) => <NoRuns loaded={projects !== null} what={what} hasModel={!!rev} go={() => setScreen("model")} />;

  return (
    <div className={`sq ${light ? "sq-light" : "sq-dark"} sq-portal app`}>
      <nav className="rail sq-rail">
        <a href="#" onClick={(e) => { e.preventDefault(); history.replaceState(null, "", location.pathname); window.dispatchEvent(new HashChangeEvent("hashchange")); }}
           aria-label="SonarIQ home" style={{ padding: "4px 12px 14px", height: "auto" }}><Lockup size={18} /></a>
        {nav.map(([k, label, n]) => (
          <a key={k} href="#" className={screen === k || (k === "inbox" && screen === "thread") ? "is-on" : ""}
             onClick={(e) => { e.preventDefault(); setScreen(k); }}>
            <Icon k={k} /><span style={{ flex: 1 }}>{label}</span>{n ? <span className="mono sq-faint">{n}</span> : null}
          </a>
        ))}
        <span style={{ flex: 1 }} />
        <a href="#" className={screen === "settings" ? "is-on" : ""} onClick={(e) => { e.preventDefault(); setScreen("settings"); }}><Icon k="settings" />Settings</a>
        <div className="sq-faint" style={{ fontSize: 11, padding: "8px 12px" }}>Prototype · v0.3</div>
      </nav>
      <div style={{ minWidth: 0 }}>
        <header className="topbar">
          <span className="sq-faint">Project</span>
          <select className="sq-input tb-sel" aria-label="Project" value={project?.id ?? ""} onChange={(e) => openProject(Number(e.target.value))}>
            {!project && <option value="">…</option>}
            {(projects ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            {project?.demo ? <option value={project.id}>{project.name}</option> : null}
          </select>
          <button className="sq-btn is-sm" onClick={() => setNameAsk({ mode: "new", text: "" })} title="New project">New</button>
          <button className="sq-btn is-sm" disabled={!project || !!project.demo} onClick={() => setNameAsk({ mode: "rename", text: project?.name ?? "" })} title="Rename this project">Rename</button>
          <span className="sq-faint" style={{ marginLeft: 8 }}>Revision</span>
          <select className="sq-input tb-sel" aria-label="Revision" disabled={!model} value={revId ?? ""} onChange={(e) => openRev(Number(e.target.value))}
                  title={rev ? `${model?.name} · ${rev.label} · ${rev.file ?? ""}` : "Open a model in Studio"}>
            {!model && <option value="">No model open</option>}
            {model && [...model.revisions].reverse().map((r) => <option key={r.id} value={r.id}>{r.label}{r.state === "saved" ? " (saved)" : ""} · {countsLine(r)}</option>)}
          </select>
          <span style={{ flex: 1 }} />
          <span className="sq-faint">Units</span>
          <div className="sq-seg">{(["mm", "in"] as const).map((u) => <button key={u} className={units === u ? "is-on" : ""} onClick={() => setUnits(u)}>{u}</button>)}</div>
          <button className="sq-btn is-sm" title="Light / dark" aria-label="Light / dark theme" aria-pressed={light} onClick={() => setLight(!light)}>◐</button>
          <span className="tb-user"><b className="tb-av">{USER.initials}</b><span><span>{USER.name}</span><span className="sq-faint">{USER.role}</span></span></span>
        </header>
        <main className="page" key={screen === "model" ? "studio" : `${project?.id ?? 0}:${revId ?? 0}:${data?.id ?? ""}`}>
          {error && <div className="sq-banner" style={{ marginBottom: 16 }}>{error}</div>}
          {report && ["inbox", "board"].includes(screen) && (
            <div className="sq-banner is-acc" style={{ marginBottom: 16 }}>
              <span>✓</span><span style={{ flex: 1 }}>Exported as report <b className="mono">{report.id}</b> · {report.time.slice(11, 16)} · {report.file} · Rev {report.revision} · {report.open_findings} open findings. The report keeps these verdicts; a new run from FreeCAD starts a new version.</span>
              {pinned && <button className="sq-btn is-sm" onClick={() => setPinned(null)}>Done</button>}
            </div>
          )}
          {screen === "inbox" && (run ? <Inbox run={run} hvac={null} meta={data} where={where} onOpen={openFinding} /> : noModel("Inbox"))}
          {screen === "board" && (run ? <Board run={run} hvac={null} where={where} onOpen={openFinding} /> : noModel("Tasks"))}
          {screen === "revisions" && <Revisions runs={runs} />}
          {screen === "thread" && open && <Thread id={open} units={units} user={`${USER.name} · ${USER.role}`} back={() => setScreen("inbox")} />}
          {screen === "model" && <Studio scope={scope} openRev={openRev} refresh={refresh} onOpenFinding={openFinding} />}
          {screen === "simulate" && <Simulate user={`${USER.name} · ${USER.role}`} rev={simRev} run={run} />}
          {screen === "rules" && <Rulebook />}
          {screen === "mapping" && <Mapping />}
          {screen === "projects" && <Projects projects={projects} current={project?.id ?? null} open={async (id) => { await openProject(id); setScreen("model"); }} />}
          {screen === "settings" && <Settings />}
          {screen === "benchmark" && (
            <div className="flex flex-col gap-3"><h1 className="sq-h1">Benchmark</h1>
              <p className="sq-muted">Planted violations and clean controls are run by <span className="mono">make eval</span>; results land in docs/EVAL.md and stay <span className="sq-ph">[after run]</span> here until the suite writes them.</p></div>
          )}
        </main>
      </div>
      {ask && (
        <div className="sq-overlay" onClick={() => setAsk(null)}>
          <div className="sq-card sq-modal" onClick={(e) => e.stopPropagation()}>
            <div className="sq-faint" style={{ fontSize: 12 }}>From FreeCAD · Export</div>
            <h2 className="sq-h2" style={{ margin: "4px 0 6px" }}>Create report from this run?</h2>
            <div className="mono sq-muted" style={{ fontSize: 13 }}>{ask.file} · Rev {ask.revision} · {ask.total_checks} checks · {ask.run.findings.filter((f) => !incorrect[f.check_key]).length} open findings · {ask.time.slice(11, 16)}</div>
            {ask.run.findings.some((f) => incorrect[f.check_key]) && <div className="sq-muted" style={{ fontSize: 13, marginTop: 4 }}>Left out: {ask.run.findings.filter((f) => incorrect[f.check_key]).map((f) => `${f.id} (marked incorrect: ${incorrect[f.check_key].reason})`).join(", ")}</div>}
            <div className="flex gap-2" style={{ margin: "12px 0", flexWrap: "wrap" }}>
              {(["fail", "warn", "unk"] as const).map((s) => <span key={s} className="flex items-center gap-1"><b className="mono">{ask.counts[s] ?? 0}</b><Pill s={s} /></span>)}
            </div>
            <p className="sq-muted">The report keeps this run's verdicts and evidence as they are now. Later runs do not change it. All findings are exported except those marked incorrect.</p>
            <div className="flex gap-2" style={{ justifyContent: "flex-end" }}>
              <button className="sq-btn" onClick={() => setAsk(null)}>Cancel</button>
              <button className="sq-btn is-primary" onClick={createReport}>Create report</button>
            </div>
          </div>
        </div>
      )}
      {nameAsk && (
        <div className="sq-overlay" onClick={() => setNameAsk(null)}>
          <form className="sq-card sq-modal" role="dialog" aria-label={nameAsk.mode === "new" ? "New project" : "Rename project"} onClick={(e) => e.stopPropagation()}
                onSubmit={(e) => { e.preventDefault(); saveName(); }}>
            <h2 className="sq-h2" style={{ margin: "0 0 10px" }}>{nameAsk.mode === "new" ? "New project" : "Rename project"}</h2>
            <input className="sq-input" style={{ width: "100%" }} autoFocus maxLength={80} aria-label="Project name" placeholder="e.g. Hull 1384 · fire zone 3"
                   value={nameAsk.text} onChange={(e) => setNameAsk({ ...nameAsk, text: e.target.value })} />
            <div className="flex gap-2" style={{ justifyContent: "flex-end", marginTop: 12 }}>
              <button type="button" className="sq-btn" onClick={() => setNameAsk(null)}>Cancel</button>
              <button className="sq-btn is-primary" disabled={!nameAsk.text.trim()}>{nameAsk.mode === "new" ? "Create" : "Save"}</button>
            </div>
          </form>
        </div>
      )}
      {toast && <div className="sq-toast">✓ {toast}</div>}
    </div>
  );
}

function Settings() {
  const [resetAsk, setResetAsk] = useState(false);
  const [typed, setTyped] = useState("");
  const [resetting, setResetting] = useState(false);
  const [err, setErr] = useState("");
  return (
    <div className="flex flex-col gap-3" style={{ maxWidth: 640 }}><h1 className="sq-h1">Settings</h1>
      <section className="sq-card danger-zone" style={{ padding: 16 }} aria-label="Danger zone">
        <div className="sq-label" style={{ color: "var(--st-fail)" }}>Danger zone · for administrators</div>
        <b>Reset all data</b>
        <p className="sq-muted" style={{ margin: "6px 0 12px" }}>Removes every project's runs, findings, revisions, reports, tasks and history for everyone using this server, so the next report is R-001. Everything is archived on the server (data/archive), never deleted. The demo models and simulation stay.</p>
        {err && <div className="sq-banner" style={{ marginBottom: 8 }}>{err}</div>}
        {!resetAsk ? <div><button className="sq-btn" onClick={() => setResetAsk(true)}>Reset all data…</button></div> : (
          <form className="flex flex-col gap-2" onSubmit={async (e) => {
            e.preventDefault(); if (typed !== "RESET") return;
            setResetting(true);
            try { await api.resetAll(); ["sq.project"].forEach((k) => LS.set(k, null)); location.hash = "#model"; location.reload(); }
            catch (x) { setResetting(false); setErr(`Reset failed: ${String(x)}`); }
          }}>
            <label className="sq-muted" htmlFor="reset-typed">Type <b className="mono">RESET</b> to confirm.</label>
            <input id="reset-typed" className="sq-input" autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
            <div className="flex gap-2"><button type="button" className="sq-btn" onClick={() => { setResetAsk(false); setTyped(""); }}>Cancel</button>
              <button className="sq-btn is-primary" disabled={typed !== "RESET" || resetting}>{resetting ? "Resetting…" : "Reset all data"}</button></div>
          </form>
        )}
      </section>
    </div>
  );
}

export function NoRuns({ loaded, what = "", hasModel = false, go }: { loaded: boolean; what?: string; hasModel?: boolean; go?: () => void }) {
  return (
    <div className="sq-card is-dashed" style={{ padding: 24, maxWidth: 640 }}>
      <h2 className="sq-h2">{!loaded ? "Connecting to the rule engine…" : hasModel ? "This revision has not been analysed yet" : "No model open in this project"}</h2>
      {loaded && <p className="sq-muted">{hasModel ? `Press Analyse in Studio. ${what || "Findings"} for this revision show here.` : `Open a model in Studio and press Analyse. ${what || "Findings"} show only what belongs to the open model revision.`}</p>}
      {loaded && go && <button className="sq-btn is-primary" onClick={go}>Go to Studio</button>}
    </div>
  );
}

function Projects({ projects, current, open }: { projects: Project[] | null; current: number | null; open: (id: number) => void }) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="sq-h1">Projects</h1>
      {!projects && <p className="sq-muted">Loading projects…</p>}
      <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
        {(projects ?? []).map((p) => (
          <div key={p.id} className="sq-card" style={{ padding: 16, borderColor: p.id === current ? "var(--accent)" : undefined }}>
            <div className="flex items-center gap-2"><h2 className="sq-h2" style={{ flex: 1 }}>{p.name}</h2>{p.id === current && <span className="sq-chip">✓ Open</span>}</div>
            {p.models.map((m) => { const r = m.revisions[m.revisions.length - 1]; return (
              <p key={m.id} className="sq-muted" style={{ margin: "4px 0" }}>{m.name} · {m.revisions.length} revision{m.revisions.length === 1 ? "" : "s"}{r ? ` · latest ${r.label}: ${countsLine(r)}` : ""}</p>); })}
            {!p.models.length && <p className="sq-muted">No models yet. Upload an IFC in Studio.</p>}
            <button className="sq-btn is-primary" style={{ marginTop: 8 }} onClick={() => open(p.id)}>Open in Studio</button>
          </div>
        ))}
      </div>
    </div>
  );
}

function Icon({ k }: { k: string }) {
  const p: Record<string, string> = {
    projects: "M2 4h5l1.5 2H14v7H2z", inbox: "M2 9l2-6h8l2 6v4H2zM2 9h4l1 2h2l1-2h4", board: "M2 3h3v10H2zM6.5 3h3v7h-3zM11 3h3v5h-3z",
    model: "M8 2l6 3v6l-6 3-6-3V5zM8 8l6-3M8 8v6M8 8L2 5", rules: "M4 2h6l3 3v9H4zM6 7h5M6 10h5", benchmark: "M3 13V8M6.5 13V4M10 13V7M13.5 13V10",
    revisions: "M4 3v10M4 5a3 3 0 0 0 6 0 M12 11a1.5 1.5 0 1 1-3 0a1.5 1.5 0 1 1 3 0", simulate: "M2 13C6 13 9 6 14 3",
    mapping: "M2 4h5M2 8h5M2 12h5M9 4h5M9 8h5M9 12h5", settings: "M8 5.5a2.5 2.5 0 1 1 0 5a2.5 2.5 0 1 1 0-5M8 1v2M8 13v2M1 8h2M13 8h2",
  };
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"><path d={p[k] ?? ""} /></svg>;
}
