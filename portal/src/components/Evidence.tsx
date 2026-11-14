// Proof of accuracy in the Studio (spec B2, B4, B5): readiness card, accuracy banner, source chips. Everything shown here
// comes from the engine's JSON; the portal never computes a verdict, a count or a value.
import { useEffect, useState } from "react";
import { apiFetch, type Check, type Provenance, type Readiness } from "../api";

const KIND: Record<string, string> = { model: "model", derived: "derived", public: "public", estimated: "estimated", user: "user-entered", confirmed: "confirmed" };

export function SourceChip({ p, label }: { p?: Provenance | null; label: string }) {
  const [open, setOpen] = useState(false);
  if (!p) return null;
  const word = p.kind === "confirmed" && p.by ? `confirmed by ${p.by}${p.date ? `, ${p.date}` : ""}` : KIND[p.kind] ?? p.kind;
  return (
    <span className="src-wrap">
      <button type="button" className={`src-chip k-${p.kind}`} aria-expanded={open} title="Where this value comes from"
        onClick={(e) => { e.stopPropagation(); setOpen(!open); }}>{label} · {word}</button>
      {open && (
        <span className="src-pop sq-card" role="dialog" onClick={(e) => e.stopPropagation()}>
          <b>{label}: {word}</b>
          <table className="ship-kv"><tbody>
            {Object.entries(p).filter(([k, v]) => k !== "kind" && v != null && v !== "").map(([k, v]) => (
              <tr key={k}><th>{k.replace(/_/g, " ")}</th><td className="mono">{Array.isArray(v) ? `${v.length} inputs: ${v.slice(0, 6).join(", ")}${v.length > 6 ? " …" : ""}` : typeof v === "object" ? JSON.stringify(v) : String(v)}</td></tr>))}
          </tbody></table>
          {p.kind === "public" && p.verified_against_official_text === false && <div className="sq-faint" style={{ fontSize: 11 }}>Not yet checked against the official text.</div>}
        </span>
      )}
    </span>
  );
}

export function SourceChips({ c }: { c: Check }) {
  const m = c.measured?.provenance, r = c.required?.provenance;
  if (!m && !r) return null;
  return <span className="flex gap-1" style={{ flexWrap: "wrap" }}><SourceChip p={m} label="Is" /><SourceChip p={r} label="Must be" /></span>;
}

const STATE: Record<string, [string, string]> = { ready: ["Ready", "s-pass"], partial: ["Partial", "s-warn"], not_possible: ["Not possible", "s-unk"] };

export function ReadinessCard({ src, given }: { src: { revision?: string; path?: string } | null; given?: Readiness | null }) {
  const [rd, setRd] = useState<Readiness | null>(given ?? null);
  const [err, setErr] = useState("");
  const key = JSON.stringify(src);
  useEffect(() => {
    if (given) { setRd(given); return; }
    if (!src) { setRd(null); return; }
    let live = true; setRd(null); setErr("");
    const q = src.revision ? `revision=${encodeURIComponent(src.revision)}` : `path=${encodeURIComponent(src.path ?? "")}`;
    apiFetch(`/readiness?${q}`).then(async (r) => { const j = await r.json(); if (!live) return; if (r.ok) setRd(j); else setErr(j.detail ?? r.statusText); });
    return () => { live = false; };
  }, [key, given]); // eslint-disable-line react-hooks/exhaustive-deps
  if (err) return <div className="sq-faint" style={{ fontSize: 12 }}>Readiness not available: {err}</div>;
  if (!rd) return <div className="sq-faint" style={{ fontSize: 12 }}>Reading what the model contains…</div>;
  const i = rd.inventory;
  const n = (v: number) => v.toLocaleString("en-US");
  const rows: [string, string][] = [
    ["Spaces", `${n(i.spaces)}${i.spaces ? ` · ${n(i.corridors)} corridors` : ""}`],
    ["Doors", `${n(i.doors)} · ${n(i.doors_with_fire_rating)} with fire rating`],
    ["Stairs", n(i.stairs)],
    ["Plates", `${n(i.plates)} · ${n(i.plates_with_thickness)} with thickness · ${n(i.plates_with_material)} with material`],
    ["Stiffeners", n(i.stiffeners)],
    ["Pipes", `${n(i.pipes)} · ${n(i.pipes_with_system)} with system · ${n(i.pipes_with_material)} with material`],
    ["SWBS", `${Math.round(i.swbs_coverage * 100)} % of parts`],
    ["Units", i.units],
  ];
  const packs = Object.entries(rd.packs).filter(([k]) => k !== "structure");
  return (
    <div className="sq-card ready-card" aria-label="Data readiness">
      <div className="sq-label">What this model can support</div>
      <table className="ship-kv"><tbody>{rows.map(([k, v]) => <tr key={k}><th>{k}</th><td className="mono">{v}</td></tr>)}</tbody></table>
      <div className="ready-packs">
        {packs.map(([k, p]) => (
          <div key={k} className="ready-row">
            <span className={`sq-pill ${STATE[p.state][1]}`}><i className="sq-ico" />{STATE[p.state][0]}{p.state === "partial" && p.n ? ` (${n(p.n)})` : ""}</span>
            <span><b>{PACK_LABEL[k] ?? k}</b> <span className="sq-faint">{p.reason}</span></span>
          </div>))}
      </div>
    </div>
  );
}
const PACK_LABEL: Record<string, string> = { fire: "Fire", escape: "Escape", accessibility: "Accessibility", hvac: "HVAC", class_dnv: "Class · DNV",
  structure_systems: "Structure & systems", data_quality: "Data quality" };

type Acc = { found: number; expected: number; false_alarms: unknown[]; passes_ok: number; passes_expected: number; scan_rules: string[]; scan_match: boolean; counts_match: boolean; ok: boolean };

export function AccuracyBanner({ revision, verified }: { revision: string; verified?: { verified: number; total: number } }) {
  const [a, setA] = useState<Acc | null | "none">(null);
  useEffect(() => {
    let live = true; setA(null);
    apiFetch(`/accuracy?revision=${encodeURIComponent(revision)}`).then(async (r) => { if (live) setA(r.ok ? await r.json() : "none"); }).catch(() => live && setA("none"));
    return () => { live = false; };
  }, [revision]);
  if (a === "none") return null;
  if (a === null) return <div className="acc-banner sq-faint" role="status">Checking against the hand-checked findings…</div>;
  const parts = [
    `${a.found}/${a.expected} hand-checked findings found`,
    `${a.false_alarms.length} false alarm${a.false_alarms.length === 1 ? "" : "s"}`,
    `${a.passes_ok}/${a.passes_expected} expected passes`,
    a.scan_match && a.counts_match ? `counts match independent scan (${a.scan_rules.length} rule${a.scan_rules.length === 1 ? "" : "s"})` : "counts differ from the independent scan",
  ];
  return (
    <div className={`acc-banner${a.ok ? " is-ok" : " is-off"}`} role="status">
      <span aria-hidden>{a.ok ? "✓" : "!"}</span> {parts.join(" · ")}
      {verified && <span className="sq-faint"> · {verified.verified} of {verified.total} rule values verified against official text</span>}
    </div>
  );
}

export function NotRun({ rows }: { rows: { rule: string; title: string; ref: string; reason: string; kind: string }[] }) {
  if (!rows?.length) return null;
  return (
    <details className="not-run">
      <summary><span className="sq-pill s-unk"><i className="sq-ico" />Cannot verify</span> {rows.length} rule{rows.length === 1 ? "" : "s"} not run on this model</summary>
      {rows.map((r) => <div key={r.rule} className="not-run-row"><b className="mono">{r.rule}</b> {r.title} <span className="sq-faint">· {r.ref}</span><div className="sq-faint">{r.reason}</div></div>)}
    </details>
  );
}
