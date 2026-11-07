// W3 Finding thread: evidence card left, review thread right (engine events, designer decision, sign-off).
import { useEffect, useState } from "react";
import { api, fmt, rag, type Check, type Decision, type Sources } from "../api";
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
      <SourceText id={c.id} />
    </div>
  );
}

export function SourceText({ id }: { id: string | null }) {
  const [s, setS] = useState<Sources | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => { if (id) rag.sources(id).then(setS).catch(() => setS(null)); }, [id]);
  if (!s) return null;
  const hits = [...s.reading, ...s.public];
  return (
    <div><div className="flex items-center"><span className="sq-label" style={{ flex: 1 }}>Source text</span>
      <button className="sq-btn is-ghost" onClick={() => setOpen(!open)}>{open ? "Hide" : `Show ${hits.length}`}</button></div>
      {s.note && <p className="sq-faint" style={{ margin: "0 0 4px", fontSize: 12 }}>{s.note}</p>}
      {(open ? hits : hits.slice(0, 1)).map((h) => (
        <div key={h.citation} style={{ borderLeft: "2px solid var(--line-2)", padding: "2px 8px", margin: "4px 0" }}>
          <div className="mono" style={{ fontSize: 12 }}><a href={h.url.startsWith("http") ? h.url : undefined} target="_blank" rel="noreferrer">{h.citation}</a></div>
          <div className="sq-muted" style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{h.text.slice(0, open ? 700 : 260)}{h.text.length > (open ? 700 : 260) ? "…" : ""}</div>
        </div>))}
      {s.links.map((l) => <div key={l.url} className="sq-faint" style={{ fontSize: 12 }}><a href={l.url} target="_blank" rel="noreferrer">{l.title}</a></div>)}
      <div className="sq-faint" style={{ fontSize: 11 }}>Retrieved from public sources ({s.backend}). Retrieval never sets a verdict.</div>
    </div>
  );
}

export default function Thread({ id, units, user, back }: { id: string; units: "mm" | "in"; user: string; back: () => void }) {
  const [c, setC] = useState<Check | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [signed, setSigned] = useState<{ who: string; what: string; time: string; rev: string }[]>([]);
  const [events, setEvents] = useState<{ time: string; text: string; event: string }[]>([]);
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => {
    api.finding(id).then(setC);
    api.history().then((h) => {
      setDecisions(h.decisions.filter((d) => d.finding === id));
      const ev = (h.history as any[]).filter((e) => e.finding === id && (e.event === "pin" || e.event === "review"));
      setEvents(ev.filter((e) => e.event === "pin"));
      setSigned(ev.filter((e) => e.event === "review").map((e) => ({ who: e.text.split(":")[0], what: e.text.split(": ").slice(1).join(": "), time: e.time, rev: "" })));
    });
  }, [id]);
  if (!c) return <p className="sq-muted">Loading…</p>;
  const sign = async (what: string) => {
    if (what !== "Approved" && !reason.trim()) { setErr("A reason is required."); return; }
    setErr("");
    try {
      const r = await rag.review(c.id ?? c.check_key, what, reason, user);
      setSigned([...signed, { who: r.by, what: r.action + (r.reason ? ` · ${r.reason}` : ""), time: r.time, rev: r.revision }]);
      setReason("");
    } catch (e) { setErr(String(e)); }
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
          {events.map((e, i) => (
            <div key={"p" + i} className="sq-sig"><i className="k is-human" /><span>{e.text} <span className="sq-faint">· BCF viewpoint + comment</span></span><span className="rev">{e.time}</span></div>
          ))}
          {signed.map((s, i) => (
            <div key={"s" + i} className="sq-sig"><i className="k is-human" /><span><b>{s.who}</b> {s.what}</span><span className="rev">{s.time}{s.rev ? ` · Rev ${s.rev}` : ""}</span></div>
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
