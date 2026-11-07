// Revisions: every Analyse kept as a run (newest first). Select two runs to see what changed between them.
import { useEffect, useState } from "react";
import { api, type DiffRow, type RunDiff, type RunMeta } from "../api";
import { Pill } from "../components/ui";

const KEYS = ["fail", "warn", "unk", "pass", "dor"] as const;

export default function Revisions({ runs }: { runs: RunMeta[] | null }) {
  const [sel, setSel] = useState<string[]>([]);
  const [diff, setDiff] = useState<RunDiff | null>(null);
  const [err, setErr] = useState("");
  // keep the two newest selected by default once there are two runs, until the user picks
  const [touched, setTouched] = useState(false);
  useEffect(() => {
    if (!touched && runs && runs.length >= 2) setSel([runs[1].id, runs[0].id]);
  }, [runs, touched]);
  useEffect(() => {
    setDiff(null); setErr("");
    if (sel.length !== 2 || !runs) return;
    const order = runs.map((r) => r.id);
    const [a, b] = [...sel].sort((x, y) => order.indexOf(y) - order.indexOf(x)); // a = older, b = newer
    api.runDiff(a, b).then(setDiff).catch((e) => setErr(String(e)));
  }, [sel, runs]);

  if (runs === null) return <p className="sq-muted">Connecting to the rule engine…</p>;
  const toggle = (id: string) => {
    setTouched(true);
    setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id].slice(-2)));
  };
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline gap-3">
        <h1 className="sq-h1">Revisions</h1>
        <span className="sq-muted">{runs.length} run{runs.length === 1 ? "" : "s"} · every Analyse is kept · select two to compare</span>
      </div>
      {runs.length === 0 ? (
        <div className="sq-card is-dashed" style={{ padding: 24, maxWidth: 640 }}>
          <h2 className="sq-h2">No runs yet</h2>
          <p className="sq-muted">No runs yet — open a model in FreeCAD and press Analyse.</p>
        </div>
      ) : (
        <table className="sq-table">
          <thead><tr><th></th><th>Run</th><th>Time</th><th>File</th><th>Revision</th><th>Scope</th><th>Packs</th><th>Source</th><th>Fail · Warn · Unk · Pass · Dormant</th></tr></thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} className={sel.includes(r.id) ? "is-sel" : ""} style={{ cursor: "pointer" }} onClick={() => toggle(r.id)}>
                <td><input type="checkbox" readOnly checked={sel.includes(r.id)} /></td>
                <td className="mono">#{r.seq}</td>
                <td className="mono">{r.time.replace("T", " ")}</td>
                <td className="mono">{r.file}</td>
                <td>Rev {r.revision}</td>
                <td className="mono" title={r.scope_note ?? ""}>{r.scope}</td>
                <td className="mono">{(r.packs ?? []).join(", ")}</td>
                <td className="sq-muted">{r.source}</td>
                <td className="mono">{KEYS.map((k) => r.counts?.[k] ?? 0).join(" · ")} <span className="sq-faint">({r.total_checks})</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {err && <div className="sq-banner">{err}</div>}
      {diff && <Diff d={diff} />}
    </div>
  );
}

function Diff({ d }: { d: RunDiff }) {
  const delta = KEYS.map((k) => `${d.counts_delta[k] > 0 ? "+" : ""}${d.counts_delta[k]}`).join(" · ");
  return (
    <div className="sq-card" style={{ padding: 16 }}>
      <h2 className="sq-h2">#{d.a.id.split("_")[0].replace(/^0+/, "")} {d.a.file} → #{d.b.id.split("_")[0].replace(/^0+/, "")} {d.b.file}</h2>
      <p className="mono sq-muted">counts {KEYS.map((k) => d.a.counts?.[k] ?? 0).join(" · ")} → {KEYS.map((k) => d.b.counts?.[k] ?? 0).join(" · ")} (Δ {delta})
        {d.added_checks || d.removed_checks ? ` · checks +${d.added_checks} / −${d.removed_checks}` : ""}</p>
      <Rows title="New or worse findings" rows={d.new_findings} />
      <Rows title="Cleared" rows={d.cleared} />
      <Rows title="Other status changes" rows={d.changed} />
      {!d.new_findings.length && !d.cleared.length && !d.changed.length && <p className="sq-muted">No verdict changed between these runs.</p>}
    </div>
  );
}

function Rows({ title, rows }: { title: string; rows: DiffRow[] }) {
  if (!rows.length) return null;
  const pill = (s: string | null) => (s && ["fail", "warn", "unk", "pass", "dor", "na"].includes(s) ? <Pill s={s as any} /> : <span className="sq-faint">{s ?? "new check"}</span>);
  return (
    <div style={{ marginTop: 12 }}>
      <div className="sq-label">{title} · {rows.length}</div>
      <table className="sq-table">
        <tbody>
          {rows.map((r) => (
            <tr key={r.check_key + title}>
              <td className="mono">{r.id ?? r.rule}</td>
              <td>{r.title}</td>
              <td className="mono sq-muted">{r.location}</td>
              <td>{pill(r.before)} → {pill(r.status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
