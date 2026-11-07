// W2 Inbox (design 12, page 2): discipline tabs with the panel's colours, status chips + Deck/Component filters
// (same as the FreeCAD panel), table with discipline stripe, owner (task board, mock people), age and decision.
// Approve stays one by one in the thread, so each decision is signed.
import { useEffect, useMemo, useState } from "react";
import { api, ORDER, WORD, useIncorrect, type Check, type Run, type RunMeta, type Task } from "../api";
import { Loc, Pill, RuleBadge } from "../components/ui";
import { DISC, PEOPLE } from "./Board";

const TABS: [string, string][] = [["all", "All"], ["fls", "Fire & safety"], ["dnv", "Hull & structure"], ["acc", "Accommodation & interiors"], ["hvac", "HVAC"]];
const COMPONENTS = ["Door", "Stair", "Corridor", "Space", "Wall", "Other"];
export function component(c: Check): string {   // same buckets as the FreeCAD panel
  const cls = c.element?.ifc_class ?? "", name = c.element?.name ?? "";
  if (cls === "IfcDoor") return "Door";
  if (cls.startsWith("IfcStair")) return "Stair";
  if (cls === "IfcSpace") return name.startsWith("COR") ? "Corridor" : "Space";
  if (cls.startsWith("IfcWall")) return "Wall";
  return "Other";
}
export function valueLine(c: Check): string {   // engine values as returned, worded like the panel cards
  const m = c.measured, r = c.required;
  const f = (v: typeof m) => (v && v.value !== null && v.value !== undefined ? (typeof v.value === "number" && v.unit === "mm" ? `${v.value.toLocaleString("en-US")} mm` : `${v.value}${v.unit && !["class", "bool", ""].includes(v.unit) ? " " + v.unit : ""}`) : "?");
  if (c.status === "unk") return `missing ${(c.missing ?? []).join(", ") || "data"} · add it or confirm`;
  if ((c as any).extra?.dead_end && m && r) return `depth ${f(m)} > width ${f(r)}`;
  if (m && r && m.value !== null && r.value !== null) return `${m.unit === "class" ? "fitted" : "measured"} ${f(m)} · required ${f(r)}`;
  return c.summary ?? "";
}
const age = (iso?: string) => {
  if (!iso) return "";
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return min < 60 ? `${min} min` : min < 1440 ? `${Math.round(min / 60)} h` : `${Math.round(min / 1440)} d`;
};

export default function Inbox({ run, hvac, meta, onOpen }: { run: Run | null; hvac: Run | null; meta?: RunMeta | null; onOpen: (c: Check) => void }) {
  const [tab, setTab] = useState("all");
  const [status, setStatus] = useState<string | null>(null);
  const [deck, setDeck] = useState("");
  const [comp, setComp] = useState("");
  const [sel, setSel] = useState<string[]>([]);
  const [pop, setPop] = useState(false);
  const [tasks, setTasks] = useState<Record<string, Task>>({});
  const [incorrect] = useIncorrect();
  useEffect(() => { api.tasks().then((r) => setTasks(r.tasks)).catch(() => {}); }, [run]);
  const all = useMemo(() => [...(run?.findings ?? []), ...(hvac?.findings ?? [])], [run, hvac]);
  if (!run) return <p className="sq-muted">Loading findings from the rule engine…</p>;
  const decks = [...new Set(all.map((c) => c.location.deck).filter(Boolean))] as string[];
  const inTab = all.filter((c) => tab === "all" || c.group === tab);
  const rows = inTab.filter((c) => !status || c.status === status).filter((c) => !deck || c.location.deck === deck)
    .filter((c) => !comp || component(c) === comp)
    .sort((a, b) => Number(!!incorrect[a.check_key]) - Number(!!incorrect[b.check_key]) ||
      ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || (a.id ?? "").localeCompare(b.id ?? ""));
  const assign = async (pid: string) => {
    for (const k of sel) {
      setTasks((m) => ({ ...m, [k]: { ...(m[k] ?? { column: "backlog", assignee: null }), assignee: pid } }));
      try { await api.task(k, { assignee: pid }); } catch { /* shown on the board */ }
    }
    setPop(false); setSel([]);
  };
  const owner = (c: Check) => PEOPLE.find((p) => p.id === tasks[c.check_key]?.assignee);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline gap-3" style={{ flexWrap: "wrap" }}>
        <h1 className="sq-h1">Inbox</h1>
        <span className="sq-muted">Demo ship · Rev {run.revision}{meta ? ` · ${meta.source === "FreeCAD panel" ? "sent from FreeCAD" : "from " + meta.source} ${meta.time.slice(11, 16)} · ` : " · "}<span className="mono">{meta?.file ?? ""}</span> · {run.total_checks} checks</span>
      </div>
      <div className="sq-tabs">
        {TABS.map(([k, label]) => {
          const n = k === "all" ? all.length : all.filter((c) => c.group === k).length;
          const [tag, color] = DISC[k] ?? ["", "var(--accent)"];
          return (
            <button key={k} className={`sq-tab${tab === k ? " is-on" : ""}`} onClick={() => setTab(k)}
                    style={tab === k && k !== "all" ? { boxShadow: `inset 0 -2px 0 ${color}` } : undefined}>
              {tag && <b className="mono" style={{ color, fontSize: 11, marginRight: 6 }}>{tag}</b>}{label} <span className="n">{n}</span>
            </button>
          );
        })}
      </div>
      <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
        {(["fail", "warn", "unk"] as const).map((s) => {
          const n = inTab.filter((c) => c.status === s).length;
          return (
            <button key={s} className={`ib-chip${status === s ? " is-on" : ""}`} onClick={() => setStatus(status === s ? null : s)}>
              <span className={`sq-pill s-${s}`} style={{ border: 0, background: "none", padding: 0 }}><i className="sq-ico" /></span><b>{n}</b> {WORD[s]}
            </button>
          );
        })}
        <span style={{ width: 8 }} />
        <select className="ib-sel" value={deck} onChange={(e) => setDeck(e.target.value)}><option value="">Deck</option>{decks.map((d) => <option key={d} value={d}>Deck {d}</option>)}</select>
        <select className="ib-sel" value={comp} onChange={(e) => setComp(e.target.value)}><option value="">Component</option>{COMPONENTS.map((c) => <option key={c}>{c}</option>)}</select>
        {(status || deck || comp) && <button className="sq-btn is-sm" onClick={() => { setStatus(null); setDeck(""); setComp(""); }}>Clear all</button>}
        <span style={{ flex: 1 }} />
        <span className="sq-faint" style={{ fontSize: 12 }}>Approve and decline are one at a time, so each is signed.</span>
      </div>
      {sel.length > 0 && (
        <div className="sq-card ib-bar">
          <span style={{ flex: 1 }}>{sel.length} selected</span>
          <span style={{ position: "relative" }}>
            <button className="sq-btn is-sm" onClick={() => setPop(!pop)}>Assign…</button>
            {pop && (
              <div className="sq-card board-pop" style={{ right: 0, left: "auto" }}>
                <div className="sq-faint" style={{ fontSize: 11, padding: "4px 8px" }}>Assign to… · mock people</div>
                {PEOPLE.map((p) => (
                  <button key={p.id} className="board-person" onClick={() => assign(p.id)}>
                    <b className="tb-av">{p.initials}</b><span style={{ flex: 1, textAlign: "left" }}>{p.name}<br /><span className="sq-faint" style={{ fontSize: 12 }}>{p.role}</span></span>
                  </button>
                ))}
              </div>
            )}
          </span>
          <button className="sq-btn is-sm" onClick={() => setSel([])}>Clear</button>
        </div>
      )}
      <table className="sq-table ib-table">
        <thead><tr><th style={{ width: 34 }}><input type="checkbox" checked={sel.length > 0 && sel.length === rows.length} onChange={(e) => setSel(e.target.checked ? rows.map((c) => c.check_key) : [])} /></th>
          <th>Status</th><th>Finding</th><th>Location</th><th>Rule</th><th>Owner</th><th>Age</th><th>Decision</th></tr></thead>
        <tbody>
          {rows.map((c) => {
            const [tag, color] = DISC[c.group] ?? ["··", "var(--fg-3)"];
            const inc = incorrect[c.check_key];
            const who = owner(c);
            return (
              <tr key={c.check_key} className={`${inc ? "is-incorrect" : ""}${sel.includes(c.check_key) ? " is-sel" : ""}`} style={{ cursor: "pointer" }} onClick={() => onOpen(c)}>
                <td style={{ boxShadow: `inset 3px 0 0 ${inc ? "var(--line-2)" : color}` }} onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" checked={sel.includes(c.check_key)} onChange={() => setSel((s) => s.includes(c.check_key) ? s.filter((x) => x !== c.check_key) : [...s, c.check_key])} />
                </td>
                <td><Pill s={c.status} /></td>
                <td>
                  <div className="mono" style={{ fontSize: 11 }}><b style={{ color }}>{tag}</b> <span className="sq-faint">{c.id}</span>{c.to_verify && <span style={{ color: "var(--st-warn)", marginLeft: 6 }}>To verify</span>}</div>
                  <div>{c.title}</div>
                  <div className="mono sq-faint" style={{ fontSize: 12 }}>{valueLine(c)}</div>
                  {inc && <div className="inc-why">Marked incorrect · {inc.reason} · not exported</div>}
                </td>
                <td><Loc text={c.location.label} /></td>
                <td><RuleBadge c={c} /></td>
                <td>{who ? <span className="flex items-center gap-2"><b className="tb-av">{who.initials}</b>{who.name}</span> : <span className="sq-faint">—</span>}</td>
                <td className="mono sq-faint">{age(meta?.time)}</td>
                <td>{inc ? <span className="sq-muted">Marked incorrect</span> : c.decision ? <span className="sq-st s-acc">Awaiting your approval</span> :
                  c.status === "unk" ? <span className="sq-muted">Needs data</span> : <span className="sq-muted">Open</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {rows.length === 0 && <p className="sq-muted">No open findings match these filters.</p>}
      <p className="sq-faint">Click a finding to open its thread. Owners come from the task board (mock people). Times are local.</p>
    </div>
  );
}
