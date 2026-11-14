// Printable report of one stored run (spec B7): readiness, accuracy banner, counts per rule, findings with provenance.
// Opened at #print/<run id> in the light theme (design: light for print); the browser's Print turns it into PDF. Everything comes from the engine's JSON.
import { useEffect, useState } from "react";
import { API, WORD, api, apiFetch, type Run, type RunMeta } from "../api";
import { AccuracyBanner, ReadinessCard } from "../components/Evidence";
import { countLine } from "../components/FindingsList";
import { valueLine } from "./Inbox";

export default function PrintReport({ id }: { id: string }) {
  const [d, setD] = useState<(RunMeta & { run: Run }) | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.runGet(id).then(setD).catch((e) => setErr(String(e))); }, [id]);
  if (err) return <div className="sq sq-light"><div className="pr"><p>Report not available: {err}</p></div></div>;
  if (!d) return <div className="sq sq-light"><div className="pr"><p className="sq-muted">Loading the run…</p></div></div>;
  const run = d.run;
  const prov = (v: any) => v?.provenance ? `${v.provenance.kind}${v.provenance.prop ? ": " + v.provenance.prop : v.provenance.source ? ": " + v.provenance.source : ""}` : "";
  return (
    <div className="sq sq-light"><div className="pr">
      <header className="pr-head">
        <div><h1>SonarIQ review report</h1>
          <div className="mono">{d.file} · Rev {d.revision} · {d.time.replace("T", " ")} · {run.total_checks.toLocaleString("en-US")} checks · run {d.id}</div></div>
        <div className="pr-actions no-print">
          <button className="sq-btn" onClick={() => window.print()}>Print / save as PDF</button>
          <a className="sq-btn" href={`${API}/runs/${encodeURIComponent(d.id)}/csv`} onClick={(e) => { e.preventDefault(); apiFetch(`/runs/${encodeURIComponent(d.id)}/csv`).then((r) => r.blob()).then((b) => { const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = `sonariq_${d.revision}_${d.id}.csv`; a.click(); }); }}>CSV</a>
        </div>
      </header>
      <p className="sq-faint">Verdicts and numbers are the rule engine's. SonarIQ supports the engineer's review; each finding is to be checked on the drawing.</p>
      <AccuracyBanner revision={d.revision} verified={run.rules_verified_against_official_text} />
      {run.readiness && <section><h2>Data readiness</h2><ReadinessCard src={null} given={run.readiness} /></section>}
      <section><h2>Checks per rule</h2>
        <table className="pr-table"><thead><tr><th>Rule</th><th>Title</th><th>Source</th><th>Result</th></tr></thead><tbody>
          {Object.entries(run.by_rule ?? {}).sort().map(([k, r]) => <tr key={k}><td className="mono">{k}</td><td>{r.title}</td><td>{r.ref}</td><td className="mono">{countLine(r.counts)}</td></tr>)}
          {(run.not_run ?? []).map((r) => <tr key={r.rule}><td className="mono">{r.rule}</td><td>{r.title}</td><td>{r.ref}</td><td>Cannot verify: {r.reason}</td></tr>)}
        </tbody></table></section>
      <section><h2>Findings ({run.findings.length})</h2>
        <table className="pr-table"><thead><tr><th>ID</th><th>Status</th><th>Finding</th><th>Element · location</th><th>Values</th><th>Sources</th></tr></thead><tbody>
          {run.findings.map((c) => (
            <tr key={c.check_key}><td className="mono">{c.id}</td><td>{WORD[c.status]}</td><td>{c.title}<div className="sq-faint">{c.ref}{c.to_verify ? " · To verify" : ""}</div></td>
              <td>{c.element?.name}<div className="sq-faint mono">{c.location.label}</div></td><td className="mono">{valueLine(c)}</td>
              <td className="mono">{[prov(c.measured) && "Is " + prov(c.measured), prov(c.required) && "Must be " + prov(c.required)].filter(Boolean).join(" · ")}</td></tr>))}
        </tbody></table></section>
    </div></div>
  );
}
