// SonarIQ portal v2 (design 12-portal-new): Home at / (no hash), workspace screens behind #<screen>. Data comes from the
// engine API; the portal never computes a verdict. #inbox/<run id> (FreeCAD Export) opens that run and offers a report.
import { useEffect, useState } from "react";
import { api, useIncorrect, type Check, type Report, type Run, type RunMeta } from "./api";
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

function Workspace() {
  const first = hashParts();
  const [screen, setScreenState] = useState<Screen>(((first[0] || "inbox") as Screen));
  const [simOn, setSimOn] = useState(false);
  useEffect(() => { api.health().then((h: any) => setSimOn(!!h.simulate)).catch(() => {}); }, []);
  const setScreen = (s: Screen) => { setScreenState(s); history.replaceState(null, "", "#" + s); };
  const [rev, setRev] = useState("B");
  const [units, setUnits] = useState<"mm" | "in">("mm");
  const [light, setLight] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const [hvac, setHvac] = useState<Run | null>(null);
  const [open, setOpen] = useState<string | null>(first[0] === "thread" ? first[1] : null);
  const [error, setError] = useState("");
  // Export landing: #inbox/<run id> pins that run and asks "Create report from this run?"
  const [pinned, setPinned] = useState<string | null>(first[0] === "inbox" && RUN_RE.test(first[1] ?? "") ? first[1] : null);
  const [ask, setAsk] = useState<(RunMeta & { run: Run }) | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [toast, setToast] = useState("");
  const [resetAsk, setResetAsk] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [incorrect] = useIncorrect();
  useEffect(() => {   // an Export link opened in a tab that already shows the portal
    const on = () => {
      const h = hashParts();
      if (h[0] === "inbox" && RUN_RE.test(h[1] ?? "")) { setPinned(h[1]); setScreenState("inbox"); }
    };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  // The portal never analyses on its own: it shows the newest stored run (or the pinned one) and polls every 2 s.
  const [runs, setRuns] = useState<RunMeta[] | null>(null);
  const [latest, setLatest] = useState<RunMeta | null>(null);
  useEffect(() => {
    let alive = true, last = "";
    const tick = async () => {
      try {
        const r = await api.runs();
        if (!alive) return;
        setRuns(r.runs); setError("");
        const top = pinned ? r.runs.find((x) => x.id === pinned) ?? null : r.runs[0];
        if (!top) { last = ""; setLatest(null); setRun(null); setHvac(null); return; }
        if (top.id !== last) {
          last = top.id;
          const full = await api.runGet(top.id);
          if (!alive) return;
          setLatest(top); setRun(full.run); setHvac(null);
          if (["A", "B", "Bfix2"].includes(top.revision)) setRev(top.revision);
        }
      } catch (e) { if (alive) setError(`Engine not reachable (${e}).` + (["localhost", "127.0.0.1"].includes(location.hostname) ? " Start it with: make api" : " The hosted engine may be restarting; reload in a minute.")); }
    };
    tick();
    const t = setInterval(tick, 2000);
    return () => { alive = false; clearInterval(t); };
  }, [pinned]);
  useEffect(() => { api.reports().then((r) => setReports(r.reports)).catch(() => {}); }, []);
  useEffect(() => {
    if (!pinned) return;
    api.runGet(pinned).then((r) => { if (!reports.find((x) => x.run_id === pinned)) setAsk(r); }).catch(() => setPinned(null));
  }, [pinned]); // eslint-disable-line react-hooks/exhaustive-deps
  const createReport = async () => {
    if (!ask) return;
    try {
      const rep = await api.report(ask.id);
      setReports((rs) => rs.some((x) => x.id === rep.id) ? rs : [...rs, rep]);
      setToast(rep.existing ? `Report ${rep.id} already exists for this run` : `Report ${rep.id} created`);
      setTimeout(() => setToast(""), 5000);
    } catch (e) { setError(String(e)); }
    setAsk(null); setScreen("inbox");
  };

  const openFinding = (c: Check) => { setOpen(c.id ?? c.check_key); setScreenState("thread"); history.replaceState(null, "", "#thread/" + (c.id ?? c.check_key)); };
  const inboxN = (run?.findings.length ?? 0) + (hvac?.findings.length ?? 0);
  const nav: [Screen, string, number?][] = [["projects", "Projects"], ["inbox", "Inbox", inboxN], ["board", "Tasks"], ["model", "Studio"],
    ["rules", "Rules"], ["benchmark", "Benchmark"], ["revisions", "Revisions"], ...(simOn ? [["simulate", "Simulate"] as [Screen, string]] : []),
    ["mapping", "Mapping review"]];
  const report = latest ? reports.find((x) => x.run_id === latest.id) : undefined;
  const title = screen === "thread" ? "Inbox" : screen === "settings" ? "Settings" : nav.find(([k]) => k === screen)?.[1] ?? "Workspace";
  useEffect(() => { document.title = `SonarIQ — ${title}`; }, [title]);

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
        <div className="sq-faint" style={{ fontSize: 11, padding: "8px 12px" }}>Prototype · v0.2<br />
          <a href="#" className="rail-reset" onClick={(e) => { e.preventDefault(); setResetAsk(true); }}>Reset all data</a></div>
      </nav>
      <div style={{ minWidth: 0 }}>
        <header className="topbar">
          <span className="sq-faint">Project</span><span className="sq-chip tb-chip">Demo ship ▾</span>
          <span className="sq-faint">Revision</span>
          {latest ? <span className="sq-chip tb-chip mono" title={`Run ${latest.id} · ${latest.source}`}>Rev {latest.revision} ▾</span>
                  : <span className="sq-faint">no run yet</span>}
          {latest && <span className="mono sq-faint" style={{ fontSize: 12 }}>{latest.file} · {latest.time.slice(11, 16)}</span>}
          <span style={{ flex: 1 }} />
          <span className="sq-faint">Units</span>
          <div className="sq-seg">{(["mm", "in"] as const).map((u) => <button key={u} className={units === u ? "is-on" : ""} onClick={() => setUnits(u)}>{u}</button>)}</div>
          <button className="sq-btn is-sm" title="Light / dark" onClick={() => setLight(!light)}>◐</button>
          <span className="tb-user"><b className="tb-av">{USER.initials}</b><span><span>{USER.name}</span><span className="sq-faint">{USER.role}</span></span></span>
        </header>
        <main className="page">
          {error && <div className="sq-banner" style={{ marginBottom: 16 }}>{error}</div>}
          {report && ["inbox", "board"].includes(screen) && (
            <div className="sq-banner is-acc" style={{ marginBottom: 16 }}>
              <span>✓</span><span style={{ flex: 1 }}>Exported as report <b className="mono">{report.id}</b> · {report.time.slice(11, 16)} · {report.file} · Rev {report.revision} · {report.open_findings} open findings. The report keeps these verdicts; a new run from FreeCAD starts a new version.</span>
              {pinned && <button className="sq-btn is-sm" onClick={() => setPinned(null)}>New · follow latest run</button>}
            </div>
          )}
          {screen === "inbox" && (run || error ? <Inbox run={run} hvac={hvac} meta={latest} onOpen={openFinding} /> : <NoRuns loaded={runs !== null} />)}
          {screen === "board" && (run ? <Board run={run} hvac={hvac} onOpen={openFinding} /> : <NoRuns loaded={runs !== null} />)}
          {screen === "revisions" && <Revisions runs={runs} />}
          {screen === "thread" && open && <Thread id={open} units={units} user={`${USER.name} · ${USER.role}`} back={() => setScreen("inbox")} />}
          {screen === "model" && <Studio latest={latest as any} run={run} onOpenFinding={openFinding} />}
          {screen === "simulate" && <Simulate user={`${USER.name} · ${USER.role}`} rev={rev} run={run} />}
          {screen === "rules" && <Rulebook />}
          {screen === "mapping" && <Mapping />}
          {screen === "projects" && <Projects run={run} hvac={hvac} go={setScreen} />}
          {screen === "settings" && (
            <div className="flex flex-col gap-3" style={{ maxWidth: 640 }}><h1 className="sq-h1">Settings</h1>
              <div className="sq-card" style={{ padding: 16 }}>
                <b>Reset all data</b>
                <p className="sq-muted" style={{ margin: "6px 0 12px" }}>Removes all runs, findings, reports, tasks and history, so the next report is R-001. Everything is archived on the server (data/archive), never deleted. The demo models and simulation stay.</p>
                <button className="sq-btn" onClick={() => setResetAsk(true)}>Reset all data…</button>
              </div>
            </div>
          )}
          {screen === "benchmark" && (
            <div className="flex flex-col gap-3"><h1 className="sq-h1">{screen[0].toUpperCase() + screen.slice(1)}</h1>
              <p className="sq-muted">{screen === "benchmark" ? <>Planted violations and clean controls are run by <span className="mono">make eval</span>; results land in docs/EVAL.md and stay <span className="sq-ph">[after run]</span> here until the suite writes them.</> : "Nothing to set in the demo workspace."}</p></div>
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
      {resetAsk && (
        <div className="sq-overlay" onClick={() => !resetting && setResetAsk(false)}>
          <div className="sq-card sq-modal" role="dialog" aria-label="Reset all data" onClick={(e) => e.stopPropagation()}>
            <h2 className="sq-h2" style={{ margin: "0 0 6px" }}>Reset all data?</h2>
            <p className="sq-muted">This removes all runs, findings, reports, tasks and history. The demo models and simulation stay.</p>
            <div className="flex gap-2" style={{ justifyContent: "flex-end" }}>
              <button className="sq-btn" disabled={resetting} onClick={() => setResetAsk(false)}>Cancel</button>
              <button className="sq-btn is-primary" disabled={resetting} onClick={async () => {
                setResetting(true);
                try { await api.resetAll(); location.hash = "#model"; location.reload(); }
                catch (e) { setResetting(false); setResetAsk(false); setToast(`Reset failed: ${String(e)}`); }
              }}>{resetting ? "Resetting…" : "Reset"}</button>
            </div>
          </div>
        </div>
      )}
      {toast && <div className="sq-toast">✓ {toast}</div>}
    </div>
  );
}

export function NoRuns({ loaded }: { loaded: boolean }) {
  return (
    <div className="sq-card is-dashed" style={{ padding: 24, maxWidth: 640 }}>
      <h2 className="sq-h2">{loaded ? "No runs yet" : "Connecting to the rule engine…"}</h2>
      {loaded && <p className="sq-muted">Open a model in Studio (or in FreeCAD) and press Analyse. Each run appears here within a few seconds and is kept as a version (Revisions).</p>}
    </div>
  );
}

function Projects({ run, hvac, go }: { run: Run | null; hvac: Run | null; go: (s: Screen) => void }) {
  const c = run?.counts;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="sq-h1">Projects</h1>
      <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
        <div className="sq-card" style={{ padding: 16, borderColor: "var(--accent)" }}>
          <div className="flex items-center gap-2"><h2 className="sq-h2" style={{ flex: 1 }}>Demo ship</h2><span className="sq-chip">✓ Active project</span></div>
          <p className="sq-muted">IFC4 · Deck 5 · Rev {run?.revision ?? "…"}</p>
          {c && <div className="flex gap-2" style={{ flexWrap: "wrap" }}>{(["fail", "warn", "unk", "pass", "dor"] as const).map((s) => <span key={s} className="flex items-center gap-1"><b className="mono">{c[s]}</b><Pill s={s} /></span>)}</div>}
          {hvac && <p className="sq-muted">HVAC model: {hvac.findings.map((f) => f.id).join(", ") || "no findings"}</p>}
          <div className="flex gap-2" style={{ marginTop: 12 }}><button className="sq-btn is-primary" onClick={() => go("inbox")}>Open inbox</button><button className="sq-btn" onClick={() => go("model")}>Open model</button></div>
        </div>
        <div className="sq-card" style={{ padding: 16 }}>
          <h2 className="sq-h2">RCRV <span className="sq-chip mono" style={{ fontSize: 11 }}>Navisworks → IFC</span></h2>
          <p className="sq-muted">Research vessel, 28 on board. Rules for ships carrying more than 36 passengers are Not applicable.</p>
          <button className="sq-btn" onClick={() => go("mapping")}>Review mapping</button>
        </div>
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
