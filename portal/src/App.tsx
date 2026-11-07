// SonarIQ portal: Rail + TopBar (page 8) and screens W1, W2, W3, W4, W5, W6. Data comes from the engine API.
import { useEffect, useState } from "react";
import { api, type Check, type Run } from "./api";
import Inbox from "./screens/Inbox";
import Thread from "./screens/Thread";
import Viewer from "./screens/Viewer";
import Rulebook from "./screens/Rulebook";
import Mapping from "./screens/Mapping";

type Screen = "projects" | "inbox" | "thread" | "model" | "rules" | "mapping" | "benchmark" | "revisions" | "settings";
const USER = { name: "Mikko Saari", role: "Fire & life safety lead", initials: "MS" }; // sample person from the design

export default function App() {
  const [screen, setScreenState] = useState<Screen>(((location.hash.slice(1) || "inbox") as Screen));
  const setScreen = (s: Screen) => { setScreenState(s); history.replaceState(null, "", "#" + s); };
  const [rev, setRev] = useState("B");
  const [units, setUnits] = useState<"mm" | "in">("mm");
  const [run, setRun] = useState<Run | null>(null);
  const [hvac, setHvac] = useState<Run | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setRun(null);
    (async () => {
      try {
        const h = await api.analyse(rev, ["hvac"]);
        const r = await api.analyse(rev, ["fls", "acc", "dnv"]);
        setHvac(h); setRun(r); setError("");
      } catch (e) { setError(`Engine not reachable (${e}). Start it with: make api`); }
    })();
  }, [rev]);

  const openFinding = (c: Check) => { setOpen(c.id ?? c.check_key); setScreen("thread"); };
  const inboxN = (run?.findings.length ?? 0) + (hvac?.findings.length ?? 0);
  const nav: [Screen, string, number?][] = [["projects", "Projects"], ["inbox", "Inbox", inboxN], ["model", "Model"],
    ["rules", "Rules"], ["mapping", "Mapping review"], ["benchmark", "Benchmark"], ["revisions", "Revisions"]];

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
          <div className="sq-seg">{["A", "B"].map((r) => <button key={r} className={rev === r ? "is-on" : ""} onClick={() => setRev(r)}>Rev {r}</button>)}</div>
          {rev === "B" && <span className="sq-faint mono">OR-117</span>}
          <span style={{ flex: 1 }} />
          <span className="sq-faint">Units</span>
          <div className="sq-seg">{(["mm", "in"] as const).map((u) => <button key={u} className={units === u ? "is-on" : ""} onClick={() => setUnits(u)}>{u}</button>)}</div>
          <span className="sq-chip"><b>{USER.initials}</b> {USER.name} · {USER.role}</span>
        </header>
        <main className="page">
          {error && <div className="sq-banner" style={{ marginBottom: 16 }}>{error}</div>}
          {screen === "inbox" && <Inbox run={run} hvac={hvac} onOpen={openFinding} />}
          {screen === "thread" && open && <Thread id={open} units={units} user={`${USER.name} · ${USER.role}`} back={() => setScreen("inbox")} />}
          {screen === "model" && <Viewer rev={rev} run={run} hvac={hvac} onOpen={openFinding} />}
          {screen === "rules" && <Rulebook />}
          {screen === "mapping" && <Mapping />}
          {screen === "projects" && <Projects run={run} hvac={hvac} go={setScreen} />}
          {["benchmark", "revisions", "settings"].includes(screen) && (
            <div className="flex flex-col gap-3"><h1 className="sq-h1">{screen[0].toUpperCase() + screen.slice(1)}</h1>
              <p className="sq-muted">Built in round 2. Benchmark results stay <span className="sq-ph">[after run]</span> until the suite produces them.</p></div>
          )}
        </main>
      </div>
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
