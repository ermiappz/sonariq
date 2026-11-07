// W9 Simulate setup and W10 results + replay. Every number on this screen comes from the engine's results JSON.
import { useEffect, useMemo, useState } from "react";
import { sim, type SimCompare, type SimPreview, type SimReplay, type SimResults, type SimScenario, type SimStatus } from "../api";
import { Controls, Histogram, QueueChart, ReplayView, useClock } from "../components/Replay";

const REVS = [["A", "Rev A"], ["B", "Rev B · OR-117"], ["Bfix2", "Rev B + fix 2"]] as const;

function Honest({ label }: { label: string }) {
  return <div className="sq-banner" style={{ fontSize: 12 }}>{label}</div>;
}

export default function Simulate({ user }: { user: string }) {
  const [view, setView] = useState<string | null>(location.hash.split("/")[1] || null);
  const go = (id: string | null) => { setView(id); history.replaceState(null, "", "#simulate" + (id ? "/" + id : "")); };
  return view ? <Results id={view} back={() => go(null)} user={user} open={go} /> : <Setup open={go} />;
}

function Setup({ open }: { open: (id: string) => void }) {
  const [sc, setSc] = useState<SimScenario>({ case: "night", route: "primary", closed_stair: null });
  const [rev, setRev] = useState("B");
  const [runs, setRuns] = useState(500);
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<SimPreview["preview"] | null>(null);
  const [err, setErr] = useState("");
  const [job, setJob] = useState<SimStatus | null>(null);
  const [list, setList] = useState<{ id: string; scenario_label: string; revision: string; runs: number; tA_p95_s: number }[]>([]);
  useEffect(() => { sim.list().then((r) => setList(r.results)).catch(() => {}); }, [job?.state]);
  useEffect(() => {
    if (!job || ["done", "error"].includes(job.state)) return;
    const h = setInterval(async () => setJob(await sim.status(job.id)), 1000);
    return () => clearInterval(h);
  }, [job]);
  const fromWords = async () => {
    setErr("");
    try { const p = await sim.preview({ text }); setPreview(p.preview); setSc(p.preview.scenario); setRev(p.preview.revision); }
    catch (e) { setErr(String(e).replace(/^Error: \d+ /, "")); }
  };
  const doPreview = async () => {
    setErr("");
    try { const p = await sim.preview({ scenario: sc, revision: rev, runs }); setPreview(p.preview); } catch (e) { setErr(String(e)); }
  };
  const run = async () => {
    if (!preview) return;
    const r = await sim.start({ scenario: preview.scenario, revision: preview.revision, runs });
    setJob(r);
  };
  return (
    <div className="flex flex-col gap-4" style={{ maxWidth: 1100 }}>
      <h1 className="sq-h1">Simulate</h1>
      <Honest label="Deck 5 sub-model with inflows from Decks 4, 6, 7 · design insight, not a full-ship Circ.1533 analysis" />
      <div className="grid gap-4" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)" }}>
        <div className="sq-card flex flex-col gap-3" style={{ padding: 16 }}>
          <h2 className="sq-h2">Scenario</h2>
          <div className="sq-field"><label>Describe it</label>
            <div className="flex gap-2"><input className="sq-input" style={{ flex: 1 }} value={text} placeholder="night, stair 3A out of use"
                                               onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && fromWords()} />
              <button className="sq-btn" onClick={fromWords}>Read</button></div></div>
          <div className="sq-field"><label>Case (MSC.1/Circ.1533 Annex 3 §4)</label>
            <div className="sq-seg">{(["night", "day"] as const).map((c) => <button key={c} className={sc.case === c ? "is-on" : ""} onClick={() => { setSc({ ...sc, case: c }); setPreview(null); }}>{c[0].toUpperCase() + c.slice(1)}</button>)}</div></div>
          <div className="sq-field"><label>Escape routes</label>
            <div className="sq-seg">
              <button className={!sc.closed_stair ? "is-on" : ""} onClick={() => { setSc({ ...sc, route: "primary", closed_stair: null }); setPreview(null); }}>Primary</button>
              {["3A", "3B", "3C"].map((s) => <button key={s} className={sc.closed_stair === s ? "is-on" : ""} onClick={() => { setSc({ ...sc, route: "secondary", closed_stair: s }); setPreview(null); }}>Stair {s} out</button>)}
            </div></div>
          <div className="sq-field"><label>Model</label>
            <div className="sq-seg">{REVS.map(([k, l]) => <button key={k} className={rev === k ? "is-on" : ""} onClick={() => { setRev(k); setPreview(null); }}>{l}</button>)}</div></div>
          <div className="sq-field"><label>Runs (Circ.1533 asks for at least 500)</label>
            <div className="sq-seg">{[500, 100, 20].map((n) => <button key={n} className={runs === n ? "is-on" : ""} onClick={() => setRuns(n)}>{n}</button>)}</div></div>
          {sc.fire_origin && <p className="sq-muted">Fire what-if: origin {sc.fire_origin}. Illustrative smoke spread, not a fire model.</p>}
          <div className="flex gap-2"><button className="sq-btn" onClick={doPreview}>Preview</button></div>
          {err && <div className="sq-banner is-unk">{err}</div>}
        </div>
        <div className="flex flex-col gap-3">
          {preview && (
            <div className="sq-card flex flex-col gap-2" style={{ padding: 16 }}>
              <div className="sq-label">Scenario preview · confirm to run</div>
              <h2 className="sq-h2">{preview.label}</h2>
              <p className="sq-muted mono" style={{ margin: 0 }}>{JSON.stringify(preview.scenario)} · model {preview.revision} · {runs} runs · read by {preview.source}</p>
              <div className="flex gap-2"><button className="sq-btn is-primary" onClick={run}>Confirm and run</button>
                <button className="sq-btn is-ghost" onClick={() => setPreview(null)}>Cancel</button></div>
            </div>)}
          {job && (
            <div className="sq-card flex flex-col gap-2" style={{ padding: 16 }}>
              <div className="sq-label">{job.scenario_label} · {job.revision}</div>
              <div className="mono">{job.state === "done" ? "Done" : job.state} · {job.runs_done} / {job.runs_target} runs{job.elapsed_s ? ` · ${job.elapsed_s} s` : ""}{job.cached ? " · from cache" : ""}</div>
              <div style={{ height: 6, background: "var(--bg-3)" }}><div style={{ height: 6, width: `${(100 * job.runs_done) / job.runs_target}%`, background: "var(--fg-2)" }} /></div>
              {job.live && <p className="sq-muted" style={{ margin: 0 }}>So far: p95 {job.live.tA_p95_s} s over {job.runs_done} runs (not final)</p>}
              {job.error && <div className="sq-banner is-unk">{job.error}</div>}
              {job.state === "done" && <button className="sq-btn is-primary" onClick={() => open(job.id)}>Open results and replay</button>}
            </div>)}
          <div className="sq-card" style={{ padding: 16 }}>
            <div className="sq-label">Saved results</div>
            {!list.length && <p className="sq-muted">None yet.</p>}
            {list.map((r) => (
              <a key={r.id} href="#" onClick={(e) => { e.preventDefault(); open(r.id); }} className="flex gap-2" style={{ padding: "4px 0", textDecoration: "none" }}>
                <span style={{ flex: 1 }}>{r.scenario_label} · {r.revision}</span><span className="mono sq-faint">p95 {r.tA_p95_s} s · {r.runs} runs</span></a>))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Results({ id, back, user, open }: { id: string; back: () => void; user: string; open: (id: string) => void }) {
  const [r, setR] = useState<SimResults | null>(null);
  const [rep, setRep] = useState<SimReplay | null>(null);
  const [ai, setAi] = useState<{ text: string; badge: string } | null>(null);
  const [heat, setHeat] = useState(false);
  const [route, setRoute] = useState(false);
  const [cmpId, setCmpId] = useState<string>("");
  const [cmp, setCmp] = useState<{ c: SimCompare; rep: SimReplay } | null>(null);
  const [list, setList] = useState<{ id: string; scenario_label: string; revision: string }[]>([]);
  const [pick, setPick] = useState<{ x: number; y: number; peak: number; over4: number; t: number } | null>(null);
  const [pinned, setPinned] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => {
    setR(null); setRep(null); setAi(null); setCmp(null);
    sim.results(id).then(setR).catch((e) => setErr(String(e)));
    sim.replay(id).then(setRep).catch(() => {});
    sim.explain(id).then(setAi).catch(() => {});
    sim.list().then((l) => setList(l.results.filter((x) => x.id !== id))).catch(() => {});
  }, [id]);
  useEffect(() => {
    if (!cmpId) { setCmp(null); return; }
    Promise.all([sim.compare(id, cmpId), sim.replay(cmpId)]).then(([c, rp]) => setCmp({ c, rep: rp }));
  }, [cmpId, id]);
  const t0 = rep?.t_start_s ?? 0;
  const t1 = Math.max(rep?.frames.at(-1)?.[0] ?? 1, cmp?.rep.frames.at(-1)?.[0] ?? 0);
  const clock = useClock(t0, t1);
  const onPick = (x: number, y: number) => {
    if (!rep) return;
    const d = rep.density, i = Math.floor((x - d.origin[0]) / d.cell_m), j = Math.floor((y - d.origin[1]) / d.cell_m);
    if (i < 0 || j < 0 || i >= d.nx || j >= d.ny) return;
    setPick({ x: +x.toFixed(1), y: +y.toFixed(1), peak: d.peak[j][i], over4: d.over4_s[j][i], t: Math.round(clock.t) });
    setPinned("");
  };
  const worst = useMemo(() => r ? Object.entries(r.landings).sort((a, b) => b[1].queue_max_p95 - a[1].queue_max_p95)[0] : null, [r]);
  if (err) return <div className="sq-banner is-unk">{err}</div>;
  if (!r) return <p className="sq-muted">Loading results…</p>;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2"><button className="sq-btn is-ghost" onClick={back}>← Simulate</button>
        <h1 className="sq-h1" style={{ margin: 0 }}>{r.scenario_label} · {r.revision}</h1></div>
      <Honest label={r.label} />
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(5, minmax(0,1fr))" }}>
        <Kpi k={`Assembly time p${r.percentile}`} v={`${r.tA_p95_s} s`} sub={`p50 ${r.tA_p50_s} s · ${r.runs} runs`} />
        <Kpi k="Deck 5 clear (p95)" v={`${r.deck5_last_p95_s} s`} sub={`${r.people_deck5} people on Deck 5`} />
        <Kpi k="Longest landing queue (p95)" v={worst ? `${worst[1].queue_max_p95}` : "—"} sub={worst ? `landing ${worst[0]} · max ${worst[1].queue_max_max}` : ""} />
        <Kpi k="Peak density (p95)" v={`${r.peak_density_p95} p/m²`} sub={`significant congestion in ${Math.round(r.congestion_significant_share * 100)} % of runs`} />
        <Kpi k="Longest route" v={`${r.longest_route.length_m} m`} sub={`${r.longest_route.space} → Stair ${r.longest_route.stair}`} />
      </div>
      {ai && <div className="sq-card" style={{ padding: 12 }}><span className="sq-ai">{ai.badge}</span><p style={{ margin: "6px 0 0" }}>{ai.text}</p></div>}
      <div className="sq-card" style={{ padding: 12 }}>
        <div className="flex items-center gap-3" style={{ flexWrap: "wrap" }}>
          <div className="sq-label" style={{ flex: 1 }}>Replay · run nearest p{r.percentile} (seed {rep?.seed ?? "…"}, {rep?.tA_s ?? "…"} s)</div>
          <button className="sq-switch" onClick={() => setHeat(!heat)}>{heat ? "☑" : "☐"} Heatmap</button>
          <button className="sq-switch" onClick={() => setRoute(!route)}>{route ? "☑" : "☐"} Longest route</button>
          <span className="sq-faint">Compare with</span>
          <select className="sq-input" value={cmpId} onChange={(e) => setCmpId(e.target.value)}>
            <option value="">—</option>{list.map((x) => <option key={x.id} value={x.id}>{x.scenario_label} · {x.revision}</option>)}</select>
        </div>
        {rep ? (<>
          <div className="grid gap-2" style={{ gridTemplateColumns: cmp ? "1fr 1fr" : "1fr" }}>
            <div>{cmp && <div className="sq-faint">Before · {r.revision}</div>}
              <ReplayView rep={rep} t={clock.t} heat={heat} route={route ? r.longest_route.path : null} onPick={onPick} height={cmp ? 300 : 380} /></div>
            {cmp && <div><div className="sq-faint">After · {cmp.c.after.revision} · {cmp.c.after.label}</div>
              <ReplayView rep={cmp.rep} t={clock.t} heat={heat} height={300} /></div>}
          </div>
          <Controls clock={clock} t0={t0} t1={t1} />
          {rep.smoke_label && <p className="sq-muted">{rep.smoke_label}</p>}
        </>) : <p className="sq-muted">Loading replay…</p>}
        {pick && (
          <div className="sq-card flex flex-col gap-1" style={{ padding: 10, marginTop: 6 }}>
            <div className="sq-label">Hotspot at x {pick.x} m, y {pick.y} m (Fr {Math.round(pick.x / 0.8)})</div>
            <div className="mono">peak {pick.peak} p/m² · {pick.over4} s above 4 p/m² · viewed at t = {pick.t} s</div>
            <div className="flex gap-2"><button className="sq-btn" onClick={async () => {
              try { const p = await sim.pin(id, { t: pick.t, x: pick.x, y: pick.y, finding: "F-07", note: `Replay ${r.scenario_label} ${r.revision}: peak ${pick.peak} p/m² at x ${pick.x}, y ${pick.y}, t ${pick.t} s`, by: user }); setPinned(`Pinned to F-07 review (BCF topic ${p.topic})`); }
              catch (e) { setPinned(String(e)); }
            }}>Pin to review</button>{pinned && <span className="sq-muted">{pinned}</span>}</div>
          </div>)}
      </div>
      <div className="grid gap-3" style={{ gridTemplateColumns: "minmax(0,3fr) minmax(0,2fr)" }}>
        <div className="sq-card" style={{ padding: 12 }}>
          <div className="sq-label">Queue on each landing over time (replay run)</div>
          {rep && <QueueChart rep={rep} t={clock.t} />}
        </div>
        <div className="sq-card" style={{ padding: 12 }}>
          <div className="sq-label">Assembly time over {r.runs} runs</div>
          <Histogram r={r} />
        </div>
      </div>
      <div className="grid gap-3" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <table className="sq-table"><thead><tr><th>Stair</th><th>Capacity p/s</th><th>Deck 5 users (mean)</th><th>From Decks 4, 6, 7</th><th>Clears at p95</th></tr></thead>
          <tbody>{Object.entries(r.stairs).map(([k, s]) => <tr key={k}><td>Stair {k}</td><td className="mono">{s.capacity_p_s}</td><td className="mono">{s.deck5_mean}</td><td className="mono">{s.inflow}</td><td className="mono">{s.last_p95_s} s</td></tr>)}</tbody></table>
        <table className="sq-table"><thead><tr><th>Landing</th><th>Queue p95</th><th>Mean of run max</th><th>Max</th>{cmp && <th>After</th>}</tr></thead>
          <tbody>{Object.entries(r.landings).map(([k, s]) => <tr key={k}><td>{k}</td><td className="mono">{s.queue_max_p95}</td><td className="mono">{s.queue_max_mean}</td><td className="mono">{s.queue_max_max}</td>
            {cmp && <td className="mono">{cmp.c.landings[k]?.after ?? "—"}</td>}</tr>)}</tbody></table>
      </div>
      {cmp && <p className="sq-muted">p95 before {cmp.c.before.tA_p95_s} s, after {cmp.c.after.tA_p95_s} s (difference {cmp.c.delta.tA_p95_s} s). <a href="#" onClick={(e) => { e.preventDefault(); open(cmp.c.after.id); }}>Open after</a></p>}
    </div>
  );
}

function Kpi({ k, v, sub }: { k: string; v: string; sub?: string }) {
  return <div className="sq-card" style={{ padding: 12 }}><div className="sq-label">{k}</div><div style={{ fontSize: 22, fontWeight: 600 }} className="mono">{v}</div>{sub && <div className="sq-faint" style={{ fontSize: 11 }}>{sub}</div>}</div>;
}
