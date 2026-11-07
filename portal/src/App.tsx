// SonarIQ portal: Rail + TopBar (page 8) and screens W1, W2, W3, W4, W5, W6. Data comes from the engine API.
import { useEffect, useState } from "react";
import { api, type Check, type Run } from "./api";
import Inbox from "./screens/Inbox";
import Thread from "./screens/Thread";
import Viewer from "./screens/Viewer";
import Rulebook from "./screens/Rulebook";
import Mapping from "./screens/Mapping";
import Simulate from "./screens/Simulate";
import Revisions from "./screens/Revisions";
import { type RunMeta } from "./api";

type Screen = "simulate" | "projects" | "inbox" | "thread" | "model" | "rules" | "mapping" | "benchmark" | "revisions" | "settings";
const USER = { name: "Mikko Saari", role: "Fire & life safety lead", initials: "MS" }; // sample person from the design

export default function App() {
  const [screen, setScreenState] = useState<Screen>(((location.hash.slice(1).split("/")[0] || "inbox") as Screen));
  const [simOn, setSimOn] = useState(false);
  useEffect(() => { api.health().then((h: any) => setSimOn(!!h.simulate)).catch(() => {}); }, []);
  const setScreen = (s: Screen) => { setScreenState(s); history.replaceState(null, "", "#" + s); };
  const [rev, setRev] = useState("B");
  const [units, setUnits] = useState<"mm" | "in">("mm");
  const [run, setRun] = useState<Run | null>(null);
  const [hvac, setHvac] = useState<Run | null>(null);
  const [open, setOpen] = useState<string | null>(location.hash.startsWith("#thread/") ? location.hash.split("/")[1] : null);
  const [error, setError] = useState("");

  // The portal never analyses on its own: it shows the newest stored run (from the FreeCAD panel or the
  // Analyse buttons below) and polls for new runs every 2 s.
  const [runs, setRuns] = useState<RunMeta[] | null>(null);
  const [latest, setLatest] = useState<RunMeta | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true, last = "";
    const tick = async () => {
      try {
        const r = await api.runs();
        if (!alive) return;
        setRuns(r.runs); setError("");
        const top = r.runs[0];
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
  }, []);
  const analyseNow = async (r: string) => {
    setBusy(true);
    try { await api.analyse(r, ["fls", "acc", "dnv"]); } catch (e) { setError(String(e)); }
    setBusy(false);
  };

  const openFinding = (c: Check) => { setOpen(c.id ?? c.check_key); setScreenState("thread"); history.replaceState(null, "", "#thread/" + (c.id ?? c.check_key)); };
  const inboxN = (run?.findings.length ?? 0) + (hvac?.findings.length ?? 0);
  const nav: [Screen, string, number?][] = [["projects", "Projects"], ["inbox", "Inbox", inboxN], ["model", "Model"],
    ...(simOn ? [["simulate", "Simulate"] as [Screen, string]] : []), ["rules", "Rules"], ["mapping", "Mapping review"], ["benchmark", "Benchmark"], ["revisions", "Revisions"]];

  return (
    <div className="sq sq-dark sq-portal app">
      <nav className="rail sq-rail">
        <div style={{ fontWeight: 700, fontSize: 16, padding: "4px 12px 14px" }}>SonarIQ</div>
        {nav.map(([k, label, n]) => (
          <a key={k} href="#" className={screen === k || (k === "inbox" && screen === "thread") ? "is-on" : ""}
             onClick={(e) => { e.preventDefault(); setScreen(k); }}>
            <span style={{ flex: 1 }}>{label}</span>{n ? <span className="mono sq-faint">{n}</span> : null}
          </a>
        ))}
        <span style={{ flex: 1 }} />
        <a href="#" className={screen === "settings" ? "is-on" : ""} onClick={(e) => { e.preventDefault(); setScreen("settings"); }}>Settings</a>
        <div className="sq-faint" style={{ fontSize: 11, padding: "8px 12px" }}>Data stays on-premises<br />v0.2 · prototype</div>
      </nav>
      <div>
        <header className="topbar">
          <span className="sq-faint">Project</span><span className="sq-chip">Demo ship</span>
          <span className="sq-faint">Revision</span>
          {latest ? <span className="sq-chip mono" title={`Run ${latest.id} · ${latest.source}`}>{latest.file} · Rev {latest.revision}</span>
                  : <span className="sq-faint">no run yet</span>}
          <span className="sq-faint">Analyse</span>
          <div className="sq-seg">{["A", "B"].map((r) => <button key={r} disabled={busy} className={latest?.revision === r ? "is-on" : ""} onClick={() => analyseNow(r)}>Rev {r}</button>)}</div>
          <span style={{ flex: 1 }} />
          <span className="sq-faint">Units</span>
          <div className="sq-seg">{(["mm", "in"] as const).map((u) => <button key={u} className={units === u ? "is-on" : ""} onClick={() => setUnits(u)}>{u}</button>)}</div>
          <span className="sq-chip"><b>{USER.initials}</b> {USER.name} · {USER.role}</span>
        </header>
        <main className="page">
          {error && <div className="sq-banner" style={{ marginBottom: 16 }}>{error}</div>}
          {screen === "inbox" && (run || error ? <Inbox run={run} hvac={hvac} onOpen={openFinding} /> : <NoRuns loaded={runs !== null} />)}
          {screen === "revisions" && <Revisions runs={runs} />}
          {screen === "thread" && open && <Thread id={open} units={units} user={`${USER.name} · ${USER.role}`} back={() => setScreen("inbox")} />}
          {screen === "model" && (run ? <Viewer rev={rev} run={run} hvac={hvac} onOpen={openFinding} /> : <NoRuns loaded={runs !== null} />)}
          {screen === "simulate" && <Simulate user={`${USER.name} · ${USER.role}`} rev={rev} run={run} />}
          {screen === "rules" && <Rulebook />}
          {screen === "mapping" && <Mapping />}
          {screen === "projects" && <Projects run={run} hvac={hvac} go={setScreen} />}
          {["benchmark", "settings"].includes(screen) && (
            <div className="flex flex-col gap-3"><h1 className="sq-h1">{screen[0].toUpperCase() + screen.slice(1)}</h1>
              <p className="sq-muted">Built in round 2. Benchmark results stay <span className="sq-ph">[after run]</span> until the suite produces them.</p></div>
          )}
        </main>
      </div>
    </div>
  );
}

export function NoRuns({ loaded }: { loaded: boolean }) {
  return (
    <div className="sq-card is-dashed" style={{ padding: 24, maxWidth: 640 }}>
      <h2 className="sq-h2">{loaded ? "No runs yet" : "Connecting to the rule engine…"}</h2>
      {loaded && <p className="sq-muted">No runs yet — open a model in FreeCAD and press Analyse. Each run appears here within a few seconds and is kept as a version (Revisions).</p>}
    </div>
  );
}

function Projects({ run, hvac, go }: { run: Run | null; hvac: Run | null; go: (s: Screen) => void }) {
  const c = run?.counts;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="sq-h1">Projects</h1>
      <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
        <div className="sq-card" style={{ padding: 16 }}>
          <h2 className="sq-h2">Demo ship</h2>
          <p className="sq-muted">IFC4 · Deck 5 · Rev {run?.revision ?? "…"}</p>
          {c && <p className="mono">{c.fail} · {c.warn} · {c.unk} · {c.pass} · {c.dor}</p>}
          {hvac && <p className="sq-muted">HVAC model: {hvac.findings.map((f) => f.id).join(", ") || "no findings"}</p>}
          <button className="sq-btn" onClick={() => go("inbox")}>Open inbox</button>
        </div>
        <div className="sq-card" style={{ padding: 16 }}>
          <h2 className="sq-h2">RCRV</h2>
          <p className="sq-muted">Navisworks → IFC · research vessel, 28 on board. Rules for ships carrying more than 36 passengers are Not applicable.</p>
          <button className="sq-btn" onClick={() => go("mapping")}>Review mapping</button>
        </div>
      </div>
    </div>
  );
}
