// W9 Simulate setup, W10 results + replay, W10b compare + fix explorer (design/screens/10-simulate.pdf).
// Every number here comes from the engine (setup, results, replay JSON). People are neutral dots; status colours
// stay with findings.
import { useEffect, useMemo, useState } from "react";
import { sim, type Run, type SimCompare, type SimReplay, type SimResults, type SimScenario, type SimStatus } from "../api";
import DeckPlan, { ringPath } from "../components/DeckPlan";
import { Controls, Histogram, QueueChart, ReplayView, useClock, mmss } from "../components/Replay";
import Deck3D from "../components/Deck3D";

const REVS = [["A", "Rev A"], ["B", "Rev B · OR-117"], ["Bfix2", "Rev B + fix 2"]] as const;
const LABEL = "Deck 5 sub-model with inflows from Decks 4, 6, 7 · design insight, not a full-ship Circ.1533 analysis";

type Setup = {
  people: { deck5: number; passengers: number; crew: number; where: string; source: string; positions: number[][] };
  stairs: { name: string; width_mm: number; open: boolean; deck5: number; inflow: number; persons_by_deck: Record<string, number>; capacity_p_s: number }[];
  routes: Record<string, number[][]>; closed: { name: string; xy: number[] }[]; fire_origin: { space: string; xy: number[]; label: string } | null;
  smoke: { t: number; spaces: string[] }[]; doors_out_options: string[]; gaps: { kind: string; count: number; items: string[]; text: string; severity: number }[];
  sentence: string; geometry: any; scenario: SimScenario; scenario_label: string; revision: string; runs_default: number;
  reader?: { text: string; source: string };
};

function Honest() { return <div className="sq-faint" style={{ fontSize: 11 }}>{LABEL}</div>; }

export default function Simulate({ user, rev, run }: { user: string; rev: string; run: Run | null }) {
  const parse = () => location.hash.replace(/^#simulate\/?/, "").split("/").filter(Boolean);
  const [path, setPath] = useState<string[]>(parse());
  const go = (p: string[]) => { setPath(p); history.replaceState(null, "", "#simulate" + (p.length ? "/" + p.join("/") : "")); };
  if (path[0] === "compare" && path[1] && path[2]) return <Compare a={path[1]} b={path[2]} back={() => go([path[1]])} open={(id) => go([id])} go={go} />;
  if (path[0]) return <Results id={path[0]} back={() => go([])} user={user} go={go} />;
  return <SetupView rev={rev} run={run} open={(id) => go([id])} />;
}

// ------------------------------------------------------------------------------------------------ W9 setup
function SetupView({ rev: topRev, run, open }: { rev: string; run: Run | null; open: (id: string) => void }) {
  const [sc, setSc] = useState<SimScenario & { closed_door?: string | null }>({ case: "night", route: "primary" });
  const [rev, setRev] = useState(topRev === "A" ? "A" : "B");
  const [fireOn, setFireOn] = useState(false);
  const [pick, setPick] = useState(false);
  const [runs, setRuns] = useState(500);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [showF, setShowF] = useState(false);
  const [job, setJob] = useState<SimStatus | null>(null);
  const [err, setErr] = useState("");
  const [text, setText] = useState("");
  const [list, setList] = useState<{ id: string; scenario_label: string; revision: string; runs: number; tA_p95_s: number }[]>([]);
  const scen = useMemo(() => ({ ...sc, fire_origin: fireOn ? (sc.fire_origin || "@near:3A") : null }), [sc, fireOn]);
  useEffect(() => {
    setErr("");
    fetch("/api/simulate/setup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario: scen, revision: rev, explain: true }) })
      .then(async (r) => { if (!r.ok) throw new Error(await r.text()); return r.json(); }).then(setSetup).catch((e) => setErr(String(e)));
  }, [JSON.stringify(scen), rev]);
  useEffect(() => { sim.list().then((r) => setList(r.results)).catch(() => {}); }, [job?.state]);
  useEffect(() => {
    if (!job || ["done", "error"].includes(job.state)) return;
    const h = setInterval(async () => setJob(await sim.status(job.id)), 1000);
    return () => clearInterval(h);
  }, [job]);
  const runIt = async () => {
    const r = await sim.start({ scenario: { ...scen, fire_origin: setup?.fire_origin?.space ?? null } as SimScenario, revision: rev, runs });
    setJob(r);
  };
  const fromWords = async () => {
    try {
      const p = await sim.preview({ text, revision: rev });
      const s = p.preview.scenario as any;
      setSc({ case: s.case, route: s.route, closed_stair: s.closed_stair ?? null, closed_door: s.closed_door ?? null, fire_origin: s.fire_origin ?? null });
      setFireOn(!!s.fire_origin); setRev(p.preview.revision); setErr("");
    } catch (e) { setErr(String(e).replace(/^Error: \d+ /, "")); }
  };
  const outName = sc.closed_stair ? `Stair ${sc.closed_stair}` : sc.closed_door ?? null;
  const setOut = (name: string | null) => {
    if (!name) { setSc({ ...sc, route: "primary", closed_stair: null, closed_door: null }); return; }
    if (name.startsWith("Stair ")) setSc({ ...sc, route: "secondary", closed_stair: name.slice(6), closed_door: null });
    else setSc({ ...sc, route: "secondary", closed_door: name, closed_stair: null });
  };
  const s3b = setup?.stairs.find((s) => s.name === "3B");
  const g = setup?.geometry;
  const onPlan = (x: number, y: number) => {
    if (!pick || !g) return;
    const sp = g.spaces.find((s: any) => { const xs = s.poly.outer.map((p: number[]) => p[0]), ys = s.poly.outer.map((p: number[]) => p[1]);
      return x >= Math.min(...xs) && x <= Math.max(...xs) && y >= Math.min(...ys) && y <= Math.max(...ys) && !["corridor", "stair", "cabin"].includes(s.category); });
    if (sp) { setSc({ ...sc, fire_origin: sp.name }); setFireOn(true); setPick(false); }
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline gap-3"><h1 className="sq-h1" style={{ margin: 0 }}>Simulate</h1>
        <span className="sq-muted">Evacuation as a design-review tool · people are neutral dots · results come from runs, never from hand</span></div>
      <div className="grid gap-3" style={{ gridTemplateColumns: "280px minmax(0,1fr) 300px", alignItems: "start" }}>
        {/* Scenario */}
        <div className="sq-card flex flex-col" style={{ padding: 0 }}>
          <div className="flex items-center" style={{ padding: "10px 12px", borderBottom: "1px solid var(--line)" }}>
            <b style={{ flex: 1 }}>Scenario</b>
            <select className="sq-input mono" value={rev} onChange={(e) => setRev(e.target.value)} style={{ width: 150 }}>
              {REVS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
          <Sect title="Describe it">
            <div className="flex gap-2"><input className="sq-input" style={{ flex: 1, minWidth: 0 }} value={text} placeholder="night, FD-5-165P out, fire near stair 3A"
              onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && fromWords()} /><button className="sq-btn" onClick={fromWords}>Read</button></div>
          </Sect>
          <Sect title="Occupancy">
            <div className="sq-seg">{(["day", "night"] as const).map((c) => <button key={c} className={sc.case === c ? "is-on" : ""} onClick={() => setSc({ ...sc, case: c })}>{c[0].toUpperCase() + c.slice(1)}</button>)}</div>
            {setup && <p className="sq-muted" style={{ margin: "6px 0 0", fontSize: 12 }}>{sc.case === "night" ? "Night" : "Day"} · {setup.people.deck5} people start {setup.people.where}.</p>}
            {s3b && <p className="sq-muted" style={{ margin: 0, fontSize: 12 }}>Inflow to Stair 3B · {Object.entries(s3b.persons_by_deck).sort((a, b) => b[1] - a[1]).map(([d, n]) => `Deck ${d} ${n}`).join(" · ")}</p>}
          </Sect>
          <Sect title="Routes">
            <div className="sq-seg"><button className={!outName ? "is-on" : ""} onClick={() => setOut(null)}>Primary</button>
              <button className={outName ? "is-on" : ""} onClick={() => !outName && setOut("FD-5-165P")}>Secondary</button></div>
            {outName !== null && <div className="flex flex-col gap-1" style={{ marginTop: 6 }}>
              <span className="sq-faint" style={{ fontSize: 12 }}>Which route is out</span>
              {[...(setup?.stairs ?? []).map((s) => [`Stair ${s.name}`, s.name === "3A" ? "MVZ 5" : "Decks 4–7"]),
                ...(setup?.doors_out_options ?? []).filter((d) => d.startsWith("FD-5-165")).map((d) => [d, `Fr 165 · ${d.slice(-1)}`])].map(([n, sub]) => (
                <button key={n} className="sq-btn" onClick={() => setOut(n)} style={{ justifyContent: "flex-start", gap: 8, borderColor: outName === n ? "var(--accent)" : undefined }}>
                  <span>{outName === n ? "◉" : "○"}</span><span style={{ flex: 1, textAlign: "left" }}>{n}</span><span className="sq-faint mono" style={{ fontSize: 11 }}>{sub}</span></button>))}
            </div>}
          </Sect>
          <Sect title={<span className="flex items-center" style={{ width: "100%" }}><span style={{ flex: 1 }}>Fire what-if</span>
            <button className="sq-switch" onClick={() => setFireOn(!fireOn)}>{fireOn ? "☑ On" : "☐ Off"}</button></span>}>
            {fireOn && <>
              <span className="sq-faint" style={{ fontSize: 12 }}>Origin</span>
              <div className="flex gap-2 items-center" style={{ flexWrap: "wrap" }}><span className="sq-chip mono">○ {setup?.fire_origin?.label ?? "…"}</span>
                <button className="sq-btn" style={{ borderColor: pick ? "var(--accent)" : undefined }} onClick={() => setPick(!pick)}>{pick ? "Click a space…" : "Pick on plan"}</button></div>
              <p className="sq-faint" style={{ fontSize: 11, margin: "4px 0 0" }}>Smoke spread is illustrative (space to space through open boundaries and doors that are not self-closing), not a fire model.</p>
            </>}
          </Sect>
          <Sect title="Runs">
            <div className="flex items-center gap-2"><button className="sq-btn" onClick={() => setRuns(Math.max(20, runs - (runs > 100 ? 100 : 20)))}>−</button>
              <span className="mono" style={{ minWidth: 60, textAlign: "center" }}>{runs}</span><button className="sq-btn" onClick={() => setRuns(Math.min(1000, runs + (runs >= 100 ? 100 : 20)))}>+</button></div>
            <p className="sq-faint" style={{ fontSize: 11, margin: "4px 0 0" }}>Each run varies walking speed and start delay. Circ.1533 asks for at least 500.</p>
          </Sect>
          <div style={{ padding: 12 }}><button className="sq-btn is-primary" style={{ width: "100%" }} onClick={runIt} disabled={!setup}>Run {runs}</button></div>
          {job && <div style={{ padding: "0 12px 12px" }}>
            <div className="mono" style={{ fontSize: 12 }}>{job.state === "done" ? "Done" : job.state} · {job.runs_done} / {job.runs_target} runs{job.cached ? " · from cache" : ""}</div>
            <div style={{ height: 4, background: "var(--bg-3)", margin: "4px 0" }}><div style={{ height: 4, width: `${(100 * job.runs_done) / job.runs_target}%`, background: "var(--fg-2)" }} /></div>
            {job.live && <div className="sq-faint" style={{ fontSize: 11 }}>So far p95 {mmss(job.live.tA_p95_s)} over {job.runs_done} runs · not final</div>}
            {job.error && <div className="sq-banner is-unk">{job.error}</div>}
            {job.state === "done" && <button className="sq-btn" style={{ width: "100%", marginTop: 6 }} onClick={() => open(job.id)}>Open results and replay</button>}
          </div>}
        </div>
        {/* Plan */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2"><b>Deck 5</b><span className="sq-muted" style={{ flex: 1 }}>{setup ? `Rev ${setup.revision}` : ""} · click the plan to move the fire origin</span>
            <button className="sq-switch" onClick={() => setShowF(!showF)}>{showF ? "☑" : "☐"} Show findings</button></div>
          <div style={{ border: "1px solid var(--line)", height: 360, cursor: pick ? "crosshair" : "default", position: "relative" }}>
            {g ? <PlanSetup g={g} s={setup!} showF={showF} run={run} onClick={onPlan} /> : <p className="sq-muted" style={{ padding: 12 }}>{err || "Reading the model…"}</p>}
          </div>
          <div className="flex gap-4 sq-faint" style={{ fontSize: 12, flexWrap: "wrap" }}>
            <span>● Person · {setup?.people.deck5 ?? "…"} on Deck 5</span><span>- - - Route to a stair</span><span>✕ Route out of use</span><span>○ Fire origin</span></div>
          <div className="sq-faint" style={{ fontSize: 12 }}>Status colours stay with findings; none are used here.</div>
          {err && <div className="sq-banner is-unk">{err}</div>}
          <div className="sq-card" style={{ padding: 10 }}>
            <div className="sq-label">Saved results</div>
            {!list.length && <p className="sq-muted" style={{ margin: 0 }}>None yet.</p>}
            {list.slice(0, 8).map((r) => (
              <a key={r.id} href="#" onClick={(e) => { e.preventDefault(); open(r.id); }} className="flex gap-2" style={{ padding: "3px 0", textDecoration: "none", fontSize: 13 }}>
                <span style={{ flex: 1 }}>{r.scenario_label} · {r.revision}</span><span className="mono sq-faint">p95 {mmss(r.tA_p95_s)} · {r.runs} runs</span></a>))}
          </div>
        </div>
        {/* Model reader */}
        <div className="flex flex-col gap-3">
          <div className="sq-card" style={{ padding: 0 }}>
            <div className="flex items-center" style={{ padding: "10px 12px", borderBottom: "1px solid var(--line)" }}><b style={{ flex: 1 }}>Model reader</b><span className="sq-engine">From the model</span></div>
            {setup && <div style={{ padding: 12, display: "grid", gridTemplateColumns: "70px 1fr", gap: "8px 10px", fontSize: 13 }}>
              <span className="sq-faint">People</span><span>{setup.people.deck5} on Deck 5 · {setup.people.source}</span>
              <span className="sq-faint">Inflow</span><span>{setup.stairs.map((s) => `Stair ${s.name} · ${Object.entries(s.persons_by_deck).sort((a, b) => b[1] - a[1]).map(([d, n]) => `D${d} ${n}`).join(" · ")}`).join("; ")}</span>
              <span className="sq-faint">Stairs</span><span>{setup.stairs.map((s) => `${s.name} (clear ${s.width_mm.toLocaleString("en-US")} mm)`).join(" · ")}</span>
              <span className="sq-faint">Doors</span><span>self-closing from Pset_DoorCommon; unknown = open (worst case)</span>
            </div>}
            {setup?.gaps.map((gp) => (
              <div key={gp.kind} style={{ margin: "0 12px 10px", padding: 10, border: "1px dashed var(--line-2)", fontSize: 12 }}>
                <b>{gp.text}</b><div className="sq-muted">{gp.items.join(", ")}{gp.count > gp.items.length ? ` and ${gp.count - gp.items.length} more` : ""}</div></div>))}
            {setup?.reader && <div style={{ margin: "0 12px 12px", fontSize: 12 }}><span className="sq-ai">{setup.reader.source === "ai" ? "AI ranking · numbers checked" : "Rule engine text"}</span>
              <p style={{ margin: "4px 0 0" }}>{setup.reader.text}</p></div>}
          </div>
          <div className="sq-card" style={{ padding: 12 }}>
            <div className="sq-label">Scenario in one sentence</div>
            <p style={{ margin: 0 }}>{setup ? setup.sentence.replace(/\.$/, "") + `, over ${runs} runs.` : "…"}</p>
          </div>
          <Honest />
        </div>
      </div>
    </div>
  );
}

function Sect({ title, children }: { title: React.ReactNode; children: React.ReactNode }) {
  return <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--line)" }}><div className="sq-label" style={{ marginBottom: 6 }}>{title}</div>{children}</div>;
}

function PlanSetup({ g, s, showF, run, onClick }: { g: any; s: Setup; showF: boolean; run: Run | null; onClick: (x: number, y: number) => void }) {
  const routes = Object.values(s.routes);
  return (
    <div style={{ position: "absolute", inset: 0 }} onClick={(e) => {
      const svg = (e.currentTarget.querySelector("svg") as SVGSVGElement); const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
      const p = pt.matrixTransform(svg.getScreenCTM()!.inverse()); onClick(p.x, -p.y);
    }}>
      <DeckPlan g={g}>
        {routes.map((r, i) => <polyline key={i} points={r.map((p) => `${p[0]},${-p[1]}`).join(" ")} fill="none" stroke="var(--fg-3)" strokeOpacity={0.45} strokeWidth={1} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />)}
        {s.people.positions.map((p, i) => <circle key={i} cx={p[0]} cy={-p[1]} r={0.22} fill="var(--fg-1)" />)}
        {s.closed.map((c) => <g key={c.name}><text x={c.xy[0]} y={-c.xy[1] + 0.45} fontSize={1.4} textAnchor="middle" fill="var(--fg-1)">✕</text>
          <text x={c.xy[0] + 0.9} y={-c.xy[1] - 0.9} fontSize={0.8} fill="var(--fg-1)">Out: {c.name}</text></g>)}
        {s.fire_origin && <g><circle cx={s.fire_origin.xy[0]} cy={-s.fire_origin.xy[1]} r={0.9} fill="none" stroke="var(--fg-1)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          <path d={ringPath(g.spaces.find((x: any) => x.name === s.fire_origin!.space)?.poly ?? { outer: [], holes: [] })} fill="url(#smokehatch)" />
          <text x={s.fire_origin.xy[0]} y={-s.fire_origin.xy[1] + 2} fontSize={0.8} textAnchor="middle" fill="var(--fg-1)">Fire origin</text></g>}
        {showF && run?.findings.filter((f) => f.evidence?.bbox).map((f) => {
          const b = f.evidence!.bbox!; const cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2;
          return <g key={f.check_key}><rect x={cx - 0.7} y={-cy - 0.45} width={1.4} height={0.9} fill="var(--bg-1)" stroke="var(--fg-2)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
            <text x={cx} y={-cy + 0.25} fontSize={0.6} textAnchor="middle" fill="var(--fg-1)">{f.id}</text></g>;
        })}
      </DeckPlan>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ W10 results
function Results({ id, back, user, go }: { id: string; back: () => void; user: string; go: (p: string[]) => void }) {
  const [r, setR] = useState<SimResults & { congestion?: any[]; events?: any[]; scenario?: any } | null>(null);
  const [rep, setRep] = useState<SimReplay | null>(null);
  const [ai, setAi] = useState<{ text: string; badge: string } | null>(null);
  const [heat, setHeat] = useState(true);
  const [dim, setDim] = useState<"2D" | "3D">("2D");
  const [pick, setPick] = useState<{ x: number; y: number; peak: number; over4: number; t: number } | null>(null);
  const [pinned, setPinned] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => {
    setR(null); setRep(null); setAi(null);
    sim.results(id).then(setR).catch((e) => setErr(String(e)));
    sim.replay(id).then(setRep).catch(() => {});
    sim.explain(id).then(setAi).catch(() => {});
  }, [id]);
  const t0 = rep?.t_start_s ?? 0, t1 = rep?.frames.at(-1)?.[0] ?? 1;
  const clock = useClock(t0, t1);
  const smokeNow = useMemo(() => (rep?.smoke_events ?? []).filter((e: any) => e.t <= clock.t).flatMap((e: any) => e.spaces), [rep, clock.t]);
  const queueLanding = useMemo(() => rep ? Object.keys(rep.queue_series).sort((a, b) => Math.max(...rep.queue_series[b]) - Math.max(...rep.queue_series[a]))[0] : null, [rep]);
  const stair = queueLanding?.slice(0, 2) ?? "3B";
  if (err) return <div className="sq-banner is-unk">{err}</div>;
  if (!r) return <p className="sq-muted">Loading results…</p>;
  const sc = r.scenario ?? {};
  const onPick = (x: number, y: number) => {
    if (!rep) return;
    const d = rep.density, i = Math.floor((x - d.origin[0]) / d.cell_m), j = Math.floor((y - d.origin[1]) / d.cell_m);
    if (i < 0 || j < 0 || i >= d.nx || j >= d.ny) return;
    setPick({ x: +x.toFixed(1), y: +y.toFixed(1), peak: d.peak[j][i], over4: d.over4_s[j][i], t: Math.round(clock.t) }); setPinned("");
  };
  const queuePeak = (r.events ?? []).find((e: any) => e.kind === "queue_peak");
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
        <button className="sq-btn is-ghost" onClick={back}>← Scenario</button>
        <h1 className="sq-h1" style={{ margin: 0 }}>{sc.case === "day" ? "Day" : "Night"} evacuation · Deck 5</h1>
        <span className="sq-chip">{sc.case === "day" ? "Day" : "Night"}</span>
        <span className="sq-chip">{sc.closed_stair ? `Secondary · Stair ${sc.closed_stair} out` : sc.closed_door ? `Secondary · ${sc.closed_door} out` : "Primary"}</span>
        {sc.fire_origin && <span className="sq-chip">Fire what-if · {sc.fire_origin}</span>}
        <span className="sq-chip mono">{r.runs} runs</span><span className="sq-chip mono">{r.revision}</span>
        <span style={{ flex: 1 }} /><span className="sq-faint">finished · {r.elapsed_s} s</span>
      </div>
      <div className="grid gap-3" style={{ gridTemplateColumns: "minmax(0,1fr) 340px", alignItems: "start" }}>
        <div className="flex flex-col gap-2">
          <div className="sq-faint mono" style={{ fontSize: 12 }}>t = {mmss(clock.t)} · illustrative frame from the p{r.percentile} run (seed {rep?.seed ?? "…"})</div>
          {rep ? (dim === "2D"
            ? <ReplayView rep={rep} t={clock.t} heat={heat} smoke={smokeNow} onPick={onPick} height={400} />
            : <Deck3D rep={rep} t={clock.t} height={400} />) : <p className="sq-muted">Loading replay…</p>}
          <div className="flex gap-3" style={{ flexWrap: "wrap", fontSize: 12 }}>
            <button className="sq-switch" onClick={() => setHeat(!heat)}>{heat ? "☑" : "☐"} Density heatmap</button>
            {rep?.smoke_label && <span className="sq-faint">▨ Smoke (illustrative) · {rep.smoke_label}</span>}
            <span className="sq-faint">● Person · ◌ Person waiting</span>
          </div>
          {rep && <Controls clock={clock} t0={t0} t1={t1} events={r.events ?? []} extra={
            <div className="sq-seg">{(["2D", "3D"] as const).map((d) => <button key={d} className={dim === d ? "is-on" : ""} onClick={() => setDim(d)}>{d}</button>)}</div>} />}
          {pick && (
            <div className="sq-card flex flex-col gap-1" style={{ padding: 10 }}>
              <div className="sq-label">Hotspot · Deck 5 · Fr {Math.round(pick.x / 0.8)} · {pick.y > 0.3 ? "P" : pick.y < -0.3 ? "S" : "CL"}</div>
              <div className="mono">peak {pick.peak} p/m² · {pick.over4} s above 4 p/m² · viewed at t = {mmss(pick.t)}</div>
              <div className="flex gap-2"><button className="sq-btn" onClick={async () => {
                try { const p = await sim.pin(id, { t: pick.t, x: pick.x, y: pick.y, finding: "F-07", note: `Replay ${r.scenario_label} (${r.revision}): peak ${pick.peak} p/m² at Fr ${Math.round(pick.x / 0.8)}, t ${mmss(pick.t)}`, by: user }); setPinned(`Pinned to F-07 review · BCF viewpoint + comment (${p.topic})`); }
                catch (e) { setPinned(String(e)); }
              }}>Pin to review</button>{pinned && <span className="sq-muted">{pinned}</span>}</div>
            </div>)}
          <div className="grid gap-3" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <table className="sq-table"><thead><tr><th>Stair</th><th>p/s</th><th>Deck 5 (mean)</th><th>Decks 4, 6, 7</th><th>Clears p95</th></tr></thead>
              <tbody>{Object.entries(r.stairs).map(([k, s]) => <tr key={k}><td>Stair {k}</td><td className="mono">{s.capacity_p_s}</td><td className="mono">{s.deck5_mean}</td><td className="mono">{s.inflow}</td><td className="mono">{mmss(s.last_p95_s)}</td></tr>)}</tbody></table>
            <table className="sq-table"><thead><tr><th>Landing</th><th>Queue p95</th><th>Mean of max</th><th>Max</th></tr></thead>
              <tbody>{Object.entries(r.landings).map(([k, s]) => <tr key={k}><td>{k}</td><td className="mono">{s.queue_max_p95}</td><td className="mono">{s.queue_max_mean}</td><td className="mono">{s.queue_max_max}</td></tr>)}</tbody></table>
          </div>
          <div className="sq-faint" style={{ fontSize: 12 }}>Longest route: {r.longest_route.space} → Stair {r.longest_route.stair}, {r.longest_route.length_m} m · {r.people_deck5} people on Deck 5{(r as any).smoke ? "" : ""}</div>
        </div>
        <div className="flex flex-col gap-3">
          <div className="sq-card" style={{ padding: 12 }}>
            <div className="flex"><span className="sq-label" style={{ flex: 1 }}>P{r.percentile} evacuation time</span><span className="sq-tag">Simulation · {r.runs} runs</span></div>
            <div className="mono" style={{ fontSize: 28, fontWeight: 600 }}>{mmss(r.tA_p95_s)} <span className="sq-faint" style={{ fontSize: 13 }}>mm:ss</span></div>
            <div className="sq-faint" style={{ fontSize: 11 }}>p50 {mmss(r.tA_p50_s)} · Deck 5 clear {mmss(r.deck5_last_p95_s)} (p95)</div>
            <Histogram r={r} height={100} />
            <div className="sq-faint" style={{ fontSize: 11 }}>time per run</div>
          </div>
          <div className="sq-card" style={{ padding: 12 }}>
            <div className="flex"><span className="sq-label" style={{ flex: 1 }}>Queue at Stair {stair} landing</span><span className="sq-faint" style={{ fontSize: 11 }}>persons · time</span></div>
            {rep && <QueueChart rep={rep} t={clock.t} height={110} only={stair} />}
            {queuePeak && <div className="sq-faint mono" style={{ fontSize: 11 }}>peak {queuePeak.people} on {queuePeak.landing} at {mmss(queuePeak.t_s)}</div>}
          </div>
          <div className="sq-card" style={{ padding: 12 }}>
            <div className="flex"><span className="sq-label" style={{ flex: 1 }}>Congestion · sorted after run</span><span className="sq-faint" style={{ fontSize: 11 }}>peak p/m²</span></div>
            {(r.congestion ?? []).map((c: any) => (
              <div key={c.place} className="flex gap-2" style={{ padding: "4px 0", borderTop: "1px solid var(--line)", fontSize: 13 }}>
                <span style={{ flex: 1 }}>{c.label}</span>{c.finding && <span className="sq-tag">{c.finding}</span>}<span className="mono">{c.peak_p_m2}</span></div>))}
          </div>
          {ai && <div className="sq-card" style={{ padding: 12 }}><span className="sq-ai">{ai.badge}</span><p style={{ margin: "6px 0 0" }}>{ai.text}</p></div>}
          <div className="flex gap-2">
            <button className="sq-btn" onClick={() => pick ? null : setPick({ x: 0, y: 0, peak: 0, over4: 0, t: Math.round(clock.t) })} title="Click the plan to choose a moment and place">Pin to review</button>
            <button className="sq-btn is-primary" onClick={() => go(["compare", id, "fixes"])}>Try fixes</button>
          </div>
        </div>
      </div>
      <Honest />
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ W10b compare + fixes
function Compare({ a, b, back, open, go }: { a: string; b: string; back: () => void; open: (id: string) => void; go: (p: string[]) => void }) {
  const [fx, setFx] = useState<any | null>(null);
  const [right, setRight] = useState<string | null>(b === "fixes" ? null : b);
  const [ra, setRa] = useState<SimResults & any | null>(null);
  const [repA, setRepA] = useState<SimReplay | null>(null);
  const [repB, setRepB] = useState<SimReplay | null>(null);
  const [cmp, setCmp] = useState<SimCompare & any | null>(null);
  const [rb, setRb] = useState<SimResults & any | null>(null);
  const [status, setStatus] = useState<Record<string, SimStatus>>({});
  const [err, setErr] = useState("");
  useEffect(() => { sim.results(a).then(setRa); sim.replay(a).then(setRepA); }, [a]);
  useEffect(() => {
    if (b !== "fixes") return;
    fetch(`/api/simulate/${a}/fixes`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ finding: "F-07", ai: true }) })
      .then(async (r) => { if (!r.ok) throw new Error(await r.text()); return r.json(); }).then(setFx).catch((e) => setErr(String(e)));
  }, [a, b]);
  useEffect(() => {
    if (!fx) return;
    const ids = fx.candidates.filter((c: any) => c.sim_id).map((c: any) => c.sim_id as string);
    const tick = async () => {
      const st: Record<string, SimStatus> = {};
      for (const i of ids) st[i] = await sim.status(i);
      setStatus(st);
      if (!right) { const first = fx.candidates.find((c: any) => c.sim_id && st[c.sim_id]?.state === "done"); if (first) setRight(first.sim_id); }
    };
    tick(); const h = setInterval(tick, 1500); return () => clearInterval(h);
  }, [fx, right]);
  const [fxRes, setFxRes] = useState<Record<string, any>>({});
  useEffect(() => {
    Object.entries(status).forEach(([i, s]) => { if (s.state === "done" && !fxRes[i]) sim.results(i).then((x) => setFxRes((o) => ({ ...o, [i]: x }))); });
  }, [status]);
  useEffect(() => {
    if (!right) return;
    sim.replay(right).then(setRepB); sim.results(right).then(setRb); sim.compare(a, right).then(setCmp);
  }, [right, a]);
  const t0 = Math.min(repA?.t_start_s ?? 0, repB?.t_start_s ?? 1e9);
  const t1 = Math.max(repA?.frames.at(-1)?.[0] ?? 1, repB?.frames.at(-1)?.[0] ?? 0);
  const clock = useClock(t0, t1);
  const pk = (x: any) => x?.peak_density_p95;
  const ql = (x: any, k: string) => x?.landings?.[k]?.queue_max_p95;
  const land = repA ? Object.keys(repA.queue_series).sort((p, q) => Math.max(...repA.queue_series[q]) - Math.max(...repA.queue_series[p]))[0] : "3BS";
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}><button className="sq-btn is-ghost" onClick={back}>← Results</button>
        <h1 className="sq-h1" style={{ margin: 0 }}>Compare · before and after a fix</h1>
        {ra && <><span className="sq-chip">{ra.scenario_label}</span><span className="sq-chip mono">{ra.runs} runs before · fixes {fx?.runs_each ?? 100} runs each</span></>}</div>
      {err && <div className="sq-banner is-unk">{err}</div>}
      <div className="grid gap-3" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div><div className="flex"><b style={{ flex: 1 }}>{ra?.revision ?? "…"} · {ra?.people_deck5 ?? "…"} on Deck 5 · before fix</b><span className="mono sq-faint">t = {mmss(clock.t)}</span></div>
          {repA ? <ReplayView rep={repA} t={clock.t} heat height={300} /> : <p className="sq-muted">…</p>}</div>
        <div><div className="flex"><b style={{ flex: 1 }}>{rb ? `${rb.revision} · ${rb.people_deck5} on Deck 5` : "Fix replay appears when its runs finish"}</b><span className="mono sq-faint">t = {mmss(clock.t)}</span></div>
          {repB ? <ReplayView rep={repB} t={clock.t} heat height={300} /> : <div style={{ height: 300, border: "1px dashed var(--line-2)" }} />}</div>
      </div>
      <Controls clock={clock} t0={t0} t1={t1} synced />
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        <Delta k={`P${ra?.percentile ?? 95} evacuation time`} a={ra ? mmss(ra.tA_p95_s) : "…"} b={rb ? mmss(rb.tA_p95_s) : "[run]"} d={cmp?.delta.tA_p95_s != null ? `${cmp.delta.tA_p95_s > 0 ? "+" : ""}${cmp.delta.tA_p95_s} s` : "…"} unit="mm:ss" />
        <Delta k="Peak density" a={pk(ra) ?? "…"} b={pk(rb) ?? "[run]"} d={pk(ra) != null && pk(rb) != null ? `${(pk(rb) - pk(ra)).toFixed(2)}` : "…"} unit="p/m²" />
        <Delta k={`Queue peak · ${land} landing`} a={ql(ra, land) ?? "…"} b={ql(rb, land) ?? "[run]"} d={ql(ra, land) != null && ql(rb, land) != null ? `${(ql(rb, land) - ql(ra, land)).toFixed(1)}` : "…"} unit="people (p95)" />
      </div>
      {fx && <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        {fx.candidates.filter((c: any) => !c.rejected).map((c: any) => {
          const st = status[c.sim_id]; const res = fxRes[c.sim_id];
          return (
            <div key={c.n} className="sq-card flex flex-col gap-1" style={{ padding: 12, borderColor: right === c.sim_id ? "var(--accent)" : undefined }}>
              <div className="flex gap-2"><b style={{ flex: 1 }}>{c.n} · {c.label}</b><span className="sq-pill is-pass">✓ Pass</span></div>
              <div className="mono" style={{ fontSize: 12 }}>{c.summary}</div>
              <div className="flex gap-2 items-center" style={{ fontSize: 12 }}><span className="sq-engine">Rule engine</span>
                <span className="sq-muted">new p95 {res ? mmss(res.tA_p95_s) : st ? `${st.runs_done}/${st.runs_target} runs` : "…"}</span></div>
              {c.needs && <div className="sq-faint" style={{ fontSize: 12 }}>Needs {c.needs} review.</div>}
              {c.ai && <div className="sq-faint" style={{ fontSize: 12 }}>Suggested by the AI · checked by the rule engine.</div>}
              {right === c.sim_id ? <span className="sq-muted">Shown on the right</span> :
                <button className="sq-btn" disabled={!res} onClick={() => setRight(c.sim_id)}>Replay on the right</button>}
            </div>);
        })}
      </div>}
      {fx && fx.rejected > 0 && <details style={{ border: "1px dashed var(--line-2)", padding: 10 }}>
        <summary>{fx.rejected} idea{fx.rejected > 1 ? "s" : ""} rejected by the engine · not simulated</summary>
        {fx.candidates.filter((c: any) => c.rejected).map((c: any) => <div key={c.n} className="sq-muted" style={{ fontSize: 12 }}>{c.label} → {c.verdict}{c.summary ? ` · ${c.summary}` : ""}{c.reason ? ` · ${c.reason}` : ""}</div>)}
      </details>}
      {!fx && b === "fixes" && !err && <p className="sq-muted">Checking fixes with the rule engine and starting 100-run simulations…</p>}
      {rb && <a href="#" onClick={(e) => { e.preventDefault(); open(right!); }}>Open the fix result</a>}
      <Honest />
      <span style={{ display: "none" }}>{String(go)}</span>
    </div>
  );
}

function Delta({ k, a, b, d, unit }: { k: string; a: any; b: any; d: string; unit: string }) {
  return <div className="sq-card" style={{ padding: 12 }}><div className="sq-label">{k}</div>
    <div className="mono" style={{ fontSize: 20 }}>{a} → {b} <span className="sq-faint" style={{ fontSize: 12 }}>{unit}</span></div>
    <div className="sq-faint" style={{ fontSize: 11 }}>Δ {d} · before → fix</div></div>;
}
