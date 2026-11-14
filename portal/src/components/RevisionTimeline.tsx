// Revision timeline in the Studio (spec B11): every model's revisions, oldest first. Export saves a revision; a saved
// revision never changes except its label. Open shows a saved revision read-only; tick two to compare (engine diff).
import { useEffect, useState } from "react";
import { api, download, useIncorrect, type RevCompare, type RevModel, type Revision } from "../api";
import { Row, Stat } from "../screens/Revisions";

const when = (s: string) => s.replace("T", " ").slice(0, 16);

/** `pick`: revision ids to tick (the demo run-through compares two revisions this way) */
export default function RevisionTimeline({ current, onOpen, pick }: { current: string | null; onOpen: (r: Revision) => void; pick?: number[] }) {
  const [models, setModels] = useState<RevModel[] | null>(null);
  const [sel, setSel] = useState<number[]>([]);
  const [cmp, setCmp] = useState<RevCompare | null>(null);
  const [edit, setEdit] = useState<{ id: number; text: string } | null>(null);
  const [err, setErr] = useState("");
  const [inc] = useIncorrect();
  const load = () => api.revisions().then((r) => setModels(r.models)).catch((e) => setErr(String(e)));
  useEffect(() => { load(); }, [current]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (pick?.length) setSel(pick.slice(-2)); }, [pick?.join()]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    setCmp(null);
    if (sel.length !== 2) return;
    const [a, b] = [...sel].sort((x, y) => x - y);   // ids grow with time: a = older
    api.revCompare(a, b).then(setCmp).catch((e) => setErr(String(e)));
  }, [sel]);
  const rename = async () => {
    if (!edit) return;
    const text = edit.text.trim();
    setEdit(null);
    if (!text) return;
    try { await api.revLabel(edit.id, text); load(); } catch (e) { setErr(String(e)); }
  };
  const toggle = (id: number) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id].slice(-2)));

  if (models === null) return <p className="sq-muted" style={{ padding: 12 }}>{err || "Loading revisions…"}</p>;
  return (
    <div className="rtl">
      {err && <div className="sq-banner">{err}</div>}
      {!models.length && <p className="sq-muted">No revisions yet. Analyse a model: the run becomes its draft revision, and Export (BCF, report or CSV) saves it as Rev A.</p>}
      {models.map((m) => (
        <section key={m.id} aria-label={`Revisions of ${m.name}`} className="flex flex-col gap-2">
          <div className="sq-label">{m.name} · {m.revisions.filter((r) => r.state === "saved").length} saved</div>
          {m.revisions.map((r) => {
            const c = r.counts ?? {};
            return (
              <div key={r.id} className={`rtl-row${r.run_id === current ? " is-on" : ""}${r.state === "draft" ? " is-draft" : ""}`} data-rev={r.label}>
                <input type="checkbox" aria-label={`Compare ${r.label}`} checked={sel.includes(r.id)} onChange={() => toggle(r.id)} />
                {edit?.id === r.id
                  ? <input className="sq-input" autoFocus maxLength={60} aria-label="Revision label" value={edit.text} onChange={(e) => setEdit({ id: r.id, text: e.target.value })}
                      onBlur={rename} onKeyDown={(e) => { if (e.key === "Enter") rename(); if (e.key === "Escape") setEdit(null); }} />
                  : <button className="rtl-label" title="Rename" onClick={() => setEdit({ id: r.id, text: r.label })}>{r.label}</button>}
                <span className="flex gap-1">
                  {r.state === "saved" && <button className="sq-btn is-sm" onClick={() => onOpen(r)} aria-label={`Open ${r.label} read-only`}>Open</button>}
                  {r.state === "saved" && <button className="sq-btn is-sm" aria-label={`Download ${r.label} bundle`}
                    onClick={() => download(`/revisions/${r.id}/bundle`, `sonariq_${r.label.replace(/[^A-Za-z0-9_-]+/g, "_")}_bundle.zip`).catch((e) => setErr(String(e)))}>Bundle</button>}
                </span>
                <span className="rtl-meta mono sq-faint">
                  {r.state === "saved" ? `Saved ${when(r.saved_at!)}` : "Draft · latest analysis, saved on Export"} · {r.file ?? ""}<br />
                  <span className="rtl-counts">{c.fail ?? 0} fail · {c.pass ?? 0} pass · {c.unk ?? 0} cannot verify</span>
                </span>
              </div>
            );
          })}
        </section>
      ))}
      {sel.length === 1 && <p className="sq-faint" style={{ fontSize: 12 }}>Tick a second revision to compare.</p>}
      {cmp && (
        <section className="flex flex-col gap-2" aria-label="Compare revisions">
          <div className="sq-label">{cmp.a.label} → {cmp.b.label}</div>
          <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
            <Stat label="New" value={cmp.new_findings.length} sub="findings" />
            <Stat label="Resolved" value={cmp.cleared.length} sub="findings" />
            <Stat label="Still open" value={cmp.still_open.length} sub={cmp.fallback_matches ? `${cmp.fallback_matches} please confirm` : "by element ID"} />
          </div>
          <div className="sq-card" style={{ padding: 0 }}>
            {[...cmp.new_findings, ...cmp.cleared, ...cmp.still_open.filter((r) => r.match === "fallback" || r.before !== r.status)].map((r) =>
              <Row key={r.check_key + r.status + r.match} r={r} inc={inc} />)}
            {!cmp.new_findings.length && !cmp.cleared.length && <p className="sq-muted" style={{ padding: 12 }}>No finding appeared or went away.</p>}
          </div>
        </section>
      )}
    </div>
  );
}
