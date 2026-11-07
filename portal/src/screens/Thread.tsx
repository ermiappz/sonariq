// W3 Finding thread: evidence card left, review thread right (engine events, designer decision, sign-off).
import { useEffect, useState } from "react";
import { api, fmt, type Check, type Decision } from "../api";
import { Engine, Loc, Pill, RuleBadge } from "../components/ui";

export function Evidence({ c, units }: { c: Check; units: "mm" | "in" }) {
  return (
    <div className="sq-card" style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
      <div className="flex items-center gap-2"><Pill s={c.status} lg /><span className="mono sq-faint">{c.id}</span>
        <span style={{ flex: 1 }} /><Engine /></div>
      <h2 className="sq-h2">{c.title}</h2>
      <div className="flex flex-wrap gap-2">{c.element && <Loc text={c.element.name} />}<Loc text={c.location.label} /></div>
      <div className="flex flex-col gap-1"><RuleBadge c={c} /><p className="sq-muted" style={{ margin: 0 }}>{c.clause_text}</p></div>
      {c.status === "unk" && (
        <div className="sq-banner is-unk"><div><b>Cannot verify.</b> Missing: {c.missing.join(", ")}. {c.rule} needs it;
          SonarIQ does not guess.</div></div>
      )}
      <div className="sq-vs">
        <div><span className="k">Required</span><span className="v">{fmt(c.required, units)}</span></div>
        <div><span className="k">Measured</span><span className="v">{fmt(c.measured, units)}</span></div>
        <div><span className="k">Margin</span><span className="v">{fmt(c.margin, units)}</span></div>
      </div>
      {c.formula && (
        <div><div className="sq-label">Formula · inputs from the model</div>
          <div className="sq-formula">
            <div>{c.formula.text}</div>
            {c.formula.inputs.map((i) => (
              <div key={i.name}><span className="sq-in">{i.name} <small>D{i.deck}</small></span> = {i.weight !== 1 ? `${i.weight} × ` : ""}{i.value}
                <span className="op"> · {i.source === "model" ? "counted from the model" : "persons_by_deck"}</span></div>
            ))}
            <div>= {c.formula.worked}</div>
          </div></div>
      )}
      <div><div className="sq-label">Measurement method</div><p className="sq-muted" style={{ margin: 0 }}>{c.method}</p></div>
    </div>
  );
}

export default function Thread({ id, units, user, back }: { id: string; units: "mm" | "in"; user: string; back: () => void }) {
  const [c, setC] = useState<Check | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [signed, setSigned] = useState<{ who: string; what: string; time: string; rev: string }[]>([]);
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => {
    api.finding(id).then(setC);
    api.history().then((h) => setDecisions(h.decisions.filter((d) => d.finding === id)));
  }, [id]);
  if (!c) return <p className="sq-muted">Loading…</p>;
  const sign = (what: string) => {
    if (what !== "Approved" && !reason.trim()) { setErr("A reason is required."); return; }
    setErr("");
    setSigned([...signed, { who: user, what: what + (reason ? ` · ${reason}` : ""), time: new Date().toLocaleTimeString(), rev: c.revision }]);
    setReason("");
  };
  return (
    <div className="flex flex-col gap-4">
      <button className="sq-btn is-ghost" style={{ alignSelf: "flex-start" }} onClick={back}>← Inbox</button>
      <div className="grid gap-6" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)" }}>
        <Evidence c={c} units={units} />
        <div className="flex flex-col gap-3">
          <div className="sq-label">Thread</div>
          <div className="sq-sig"><i className="k" /><span>Rule engine found {c.id}: {c.summary}</span><span className="rev">Rev {c.revision}</span></div>
          {decisions.map((d, i) => (
            <div key={i} className="sq-sig"><i className="k is-human" /><span><b>{d.by}</b> accepted with reason from FreeCAD: “{d.reason}”. Goes to {d.to}.</span>
              <span className="rev">{d.time} · Rev {d.revision}</span></div>
          ))}
          {signed.map((s, i) => (
            <div key={"s" + i} className="sq-sig"><i className="k is-human" /><span><b>{s.who}</b> {s.what}</span><span className="rev">{s.time} · Rev {s.rev}</span></div>
          ))}
          <div className="sq-field"><label>Comment or reason <span className="req">(required to decline or request a change)</span></label>
            <textarea className="sq-input" style={{ height: 70, paddingTop: 6 }} value={reason} onChange={(e) => setReason(e.target.value)} /></div>
          {err && <span className="sq-st s-fail">{err}</span>}
          <div className="flex gap-2">
            <button className="sq-btn is-primary" onClick={() => sign("Approved")}>Approve</button>
            <button className="sq-btn" onClick={() => sign("Requested a change")}>Request change</button>
            <button className="sq-btn" onClick={() => sign("Declined")}>Decline</button>
          </div>
          <p className="sq-faint">The engine verdict stays {c.status_word}. A signed row records name, role, time and revision.</p>
        </div>
      </div>
    </div>
  );
}
