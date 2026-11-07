// W2 Discipline inbox: tabs per discipline, findings table. Approve stays one by one so each is signed.
import { useMemo, useState } from "react";
import { ORDER, type Check, type Run } from "../api";
import { Loc, Pill, RuleBadge } from "../components/ui";

const TABS = [
  ["fire_life_safety", "Fire & life safety"], ["structure", "Structure"], ["architecture", "Architecture"],
  ["hvac", "HVAC"], ["systems", "Systems"], ["accessibility", "Accessibility"],
] as const;
const EMPTY: Record<string, string> = {
  structure: "No open findings. The class pack runs on Deck 5 with To verify rules; OCX stiffeners are not loaded yet.",
  architecture: "No open findings routed to architecture on this revision.",
  systems: "No systems pack on this model yet (pipe penetrations are on the roadmap).",
};

export default function Inbox({ run, hvac, onOpen }: { run: Run | null; hvac: Run | null; onOpen: (c: Check) => void }) {
  const [tab, setTab] = useState<string>("fire_life_safety");
  const [filter, setFilter] = useState<string>("all");
  const all = useMemo(() => [...(run?.findings ?? []), ...(hvac?.findings ?? [])], [run, hvac]);
  const rows = all.filter((c) => c.discipline === tab).filter((c) => filter === "all" || c.status === filter)
    .sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || (a.id ?? "").localeCompare(b.id ?? ""));
  if (!run) return <p className="sq-muted">Loading findings from the rule engine…</p>;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline gap-3">
        <h1 className="sq-h1">Inbox</h1>
        <span className="sq-muted">Demo ship · Rev {run.revision} · {run.total_checks} checks · {run.duration_s.toFixed(2)} s</span>
      </div>
      <div className="sq-tabs">
        {TABS.map(([k, label]) => (
          <button key={k} className={`sq-tab${tab === k ? " is-on" : ""}`} onClick={() => setTab(k)}>
            {label} <span className="n">{all.filter((c) => c.discipline === k).length}</span>
          </button>
        ))}
      </div>
      <div className="flex items-center gap-3">
        <div className="sq-seg">
          {[["all", "All open"], ["fail", "Fail"], ["warn", "Warning"], ["unk", "Cannot verify"]].map(([k, l]) => (
            <button key={k} className={filter === k ? "is-on" : ""} onClick={() => setFilter(k)}>{l}</button>
          ))}
        </div>
        <span className="sq-faint">Approve and decline are one at a time, so each is signed.</span>
      </div>
      <table className="sq-table">
        <thead><tr><th>Status</th><th>Finding</th><th>Location</th><th>Rule</th><th>Owner</th><th>Decision</th></tr></thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.check_key} style={{ cursor: "pointer" }} onClick={() => onOpen(c)}>
              <td><Pill s={c.status} /></td>
              <td><div className="sq-faint mono" style={{ fontSize: 11 }}>{c.id}</div><div>{c.title}</div>
                <div className="sq-faint" style={{ fontSize: 12 }}>{c.summary}</div></td>
              <td><Loc text={c.location.label} /></td>
              <td><RuleBadge c={c} /></td>
              <td className="sq-muted">{c.discipline_label} lead</td>
              <td>{c.decision ? <span className="sq-st s-acc">Awaiting your approval</span> :
                c.status === "unk" ? <span className="sq-muted">Needs data</span> : <span className="sq-muted">Open</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="sq-muted">{EMPTY[tab] ?? "No open findings in this inbox."}</p>}
      <p className="sq-faint">Click a finding to open its thread.</p>
    </div>
  );
}
