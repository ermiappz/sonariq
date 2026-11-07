// W6 Rulebook: packs, rules with clause, plain summary, parameters and status, straight from rules/seed_rules.yaml.
import { useEffect, useState } from "react";
import { api } from "../api";

export default function Rulebook() {
  const [rules, setRules] = useState<Record<string, any>[]>([]);
  useEffect(() => { api.rules().then((r) => setRules(r.rules)); }, []);
  return (
    <div className="flex flex-col gap-4">
      <h1 className="sq-h1">Rules</h1>
      <p className="sq-muted" style={{ margin: 0 }}>{rules.length} rules. Thresholds live in the rulebook, not in code. To verify = paragraph or reading not yet confirmed; verdicts carry the tag.</p>
      <table className="sq-table">
        <thead><tr><th>ID</th><th>Clause</th><th>What it checks</th><th>Applies to</th><th>Parameters</th><th>Status</th></tr></thead>
        <tbody>{rules.map((r) => (
          <tr key={r.id}>
            <td className="mono">{r.id}</td>
            <td><span className="sq-rule"><b>{r.source.startsWith("SOLAS") ? "SOLAS" : r.source}</b><span>{r.clause}</span></span></td>
            <td><div>{r.title}</div><div className="sq-faint" style={{ fontSize: 12 }}>{r.reading}</div></td>
            <td className="sq-muted" style={{ fontSize: 12 }}>{r.applies_to}{r.applicability?.passengers_gt ? ` · ships > ${r.applicability.passengers_gt} passengers` : ""}</td>
            <td className="mono" style={{ fontSize: 12 }}>{Object.entries(r.params ?? {}).map(([k, v]) => `${k} ${JSON.stringify(v)}`).join(" · ") || "—"}</td>
            <td>{r.status === "verified" ? <span className="sq-st s-pass">Verified</span> : <span className="sq-tag">To verify</span>}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
