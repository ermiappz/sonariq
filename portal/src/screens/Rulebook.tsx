// W6 Rulebook: packs, rules with clause, plain summary, parameters and status, straight from rules/seed_rules.yaml.
import { useEffect, useState } from "react";
import { api, rag } from "../api";

export default function Rulebook() {
  const [rules, setRules] = useState<Record<string, any>[]>([]);
  useEffect(() => { api.rules().then((r) => setRules(r.rules)); }, []);
  return (
    <div className="flex flex-col gap-4">
      <h1 className="sq-h1">Rules</h1>
      <p className="sq-muted" style={{ margin: 0 }}>{rules.length} rules. Thresholds live in the rulebook, not in code. To verify = paragraph or reading not yet confirmed; verdicts carry the tag.</p>
      <DraftRule />
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

function DraftRule() {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [r, setR] = useState<Awaited<ReturnType<typeof rag.draft>> | null>(null);
  const [saved, setSaved] = useState("");
  const go = async () => { setBusy(true); setSaved(""); try { setR(await rag.draft(q)); } catch (e) { setR({ ok: false, error: String(e) }); } setBusy(false); };
  return (
    <div className="sq-card flex flex-col gap-2" style={{ padding: 12 }}>
      <div className="flex items-center gap-2"><b style={{ flex: 1 }}>Draft rule from clause</b><span className="sq-ai">AI draft · you approve</span></div>
      <div className="flex gap-2"><input className="sq-input" style={{ flex: 1 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. ADA 404.2.3 door clear width, or PVAG V403.5 route width"
        onKeyDown={(e) => e.key === "Enter" && go()} /><button className="sq-btn" onClick={go} disabled={busy || !q.trim()}>{busy ? "Reading…" : "Draft"}</button></div>
      {r?.error && <div className="sq-banner is-unk">{r.error}</div>}
      {r?.source && <div style={{ borderLeft: "2px solid var(--line-2)", padding: "2px 8px" }}><div className="mono" style={{ fontSize: 12 }}>{r.source.citation}</div>
        <div className="sq-muted" style={{ fontSize: 12 }}>{r.source.text.slice(0, 500)}</div></div>}
      {r?.draft && <>
        <pre className="mono" style={{ fontSize: 12, background: "var(--bg-2)", padding: 8, margin: 0, whiteSpace: "pre-wrap" }}>{
          ["id", "title", "source", "clause", "clause_text", "reading", "applies_to", "check", "params", "pack", "status", "drafted_from", "drafted_by"]
            .map((k) => `${k}: ${typeof r.draft![k] === "object" ? JSON.stringify(r.draft![k]) : r.draft![k]}`).join("\n")}</pre>
        {r.numbers_not_in_source && r.numbers_not_in_source.length > 0 &&
          <div className="sq-banner is-unk">Numbers not found in the source text: {r.numbers_not_in_source.join(", ")}. Check before approving.</div>}
        <div className="flex gap-2 items-center"><button className="sq-btn is-primary" onClick={async () => { const a = await rag.approve(r.draft!, "Mikko Saari · Fire & life safety lead"); setSaved(`${a.path} · ${a.note}`); }}>Approve as draft</button>
          <button className="sq-btn is-ghost" onClick={() => setR(null)}>Discard</button>{saved && <span className="sq-muted" style={{ fontSize: 12 }}>Saved {saved}</span>}</div>
      </>}
      <p className="sq-faint" style={{ margin: 0, fontSize: 11 }}>Public sources only (MSC.1/Circ.1533, ADA 2010, PVAG, COLREG). A draft never runs until it is moved into the rulebook.</p>
    </div>
  );
}
