// Revisions: every Analyse kept as a run (newest first). Select two runs to see what changed between them.
import { useEffect, useState } from "react";
import { api, useIncorrect, type DiffRow, type Incorrect, type RunDiff, type RunMeta } from "../api";
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
  const [inc] = useIncorrect();
  const n = (id: string) => "#" + id.split("_")[0].replace(/^0+/, "");
  const changed = d.new_findings.length + d.cleared.length + d.changed.length;
  const bad = (c?: Record<string, number>) => `${c?.fail ?? 0} fail · ${c?.warn ?? 0} warning · ${c?.unk ?? 0} cannot verify`;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline gap-3" style={{ flexWrap: "wrap" }}>
        <h2 className="sq-h1" style={{ fontSize: 22 }}>Rev {d.a.revision} → Rev {d.b.revision}</h2>
        <span className="sq-muted">{n(d.a.id)} <span className="mono">{d.a.file}</span> {d.a.time.slice(11, 16)} → {n(d.b.id)} <span className="mono">{d.b.file}</span> {d.b.time.slice(11, 16)}</span>
      </div>
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
        <Stat label="Verdicts changed" value={changed} sub={`of ${d.b.total_checks} checks`} />
        <Stat label="New or worse" value={d.new_findings.length} sub="findings that appeared" />
        <Stat label="Cleared" value={d.cleared.length} sub="findings that went away" />
        <Stat label="Still open" value={d.still_open.length} sub={d.fallback_matches ? `${d.fallback_matches} to confirm` : "matched by element ID"} />
        <Stat label="Checks" value={`${d.added_checks ? "+" + d.added_checks : 0} / −${d.removed_checks}`} sub="added / removed by the change" />
      </div>
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
        <div className="sq-card" style={{ padding: 12 }}><b>Rev {d.a.revision}</b> <span className="sq-faint">· {d.a.time.slice(11, 16)}</span><div className="mono sq-muted" style={{ marginTop: 6 }}>{bad(d.a.counts)}</div></div>
        <div className="sq-card" style={{ padding: 12 }}><b>Rev {d.b.revision}</b> <span className="sq-faint">· {d.b.time.slice(11, 16)}</span><div className="mono sq-muted" style={{ marginTop: 6 }}>{bad(d.b.counts)}</div></div>
      </div>
      <div className="sq-card" style={{ padding: 0 }}>
        <div className="sq-label" style={{ padding: "12px 14px", borderBottom: "1px solid var(--line)" }}>Verdicts that changed · {changed}</div>
        {!changed && <p className="sq-muted" style={{ padding: 14 }}>No verdict changed between these runs.</p>}
        {[...d.new_findings, ...d.cleared, ...d.changed].map((r) => <Row key={r.check_key + r.status} r={r} inc={inc} />)}
      </div>
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: number | string; sub: string }) {
  return (
    <div className="sq-card" style={{ padding: 12 }}>
      <div className="sq-label">{label}</div>
      <div style={{ fontSize: 26, fontWeight: 600 }}>{value}</div>
      <div className="sq-faint" style={{ fontSize: 12 }}>{sub}</div>
    </div>
  );
}

export function Row({ r, inc }: { r: DiffRow; inc: Record<string, Incorrect> }) {
  const pill = (s: string | null) => (s && ["fail", "warn", "unk", "pass", "dor", "na"].includes(s) ? <Pill s={s as any} /> : <span className="sq-faint">{s ?? "new check"}</span>);
  const i = inc[r.check_key];
  return (
    <div className={`rev-row${i ? " is-incorrect" : ""}`}>
      <span className="mono" style={{ width: 70 }}>{r.id ?? r.rule}</span>
      <span style={{ flex: 1, minWidth: 0 }}>{r.title}<div className="mono sq-faint" style={{ fontSize: 12 }}>{r.location}{r.element ? ` · ${r.element}` : ""}</div>
        {i && <div className="inc-why">Marked incorrect · {i.reason}</div>}
        {r.match === "fallback" && <div className="rev-confirm">Matched by rule + element name, not by element ID · please confirm</div>}</span>
      <span className="flex items-center gap-2">{pill(r.before)} → {pill(r.status)}</span>
    </div>
  );
}
