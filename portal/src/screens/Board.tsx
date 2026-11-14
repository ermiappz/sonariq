// Task board: one card per open finding in Backlog / Doing / Done. Column and assignee are stored by the engine
// (data/tasks.json), keyed by check. People and due dates are mock, and say so.
import { useEffect, useState } from "react";
import { api, ORDER, type Check, type Run, type Task } from "../api";
import { Pill } from "../components/ui";

export const PEOPLE = [
  { id: "ms", name: "Mikko Saari", role: "Fire & life safety lead", initials: "MS" },
  { id: "jk", name: "Jussi Koski", role: "HVAC engineer", initials: "JK" },
  { id: "ln", name: "Laura Niemi", role: "Hull & structure engineer", initials: "LN" },
  { id: "al", name: "Aino Laine", role: "Interiors engineer", initials: "AL" },
];
export const DISC: Record<string, [string, string]> = {
  fls: ["FIRE", "#e27dff"], acc: ["INT", "#b98cff"], dnv: ["HULL", "#5c9dff"], hvac: ["HVAC", "#3fd0e6"], sts: ["HULL", "#5c9dff"],
};
const COLS: [Task["column"], string][] = [["backlog", "Backlog"], ["doing", "Doing"], ["done", "Done"]];

export default function Board({ run, hvac, onOpen }: { run: Run; hvac: Run | null; onOpen: (c: Check) => void }) {
  const [tasks, setTasks] = useState<Record<string, Task>>({});
  const [pop, setPop] = useState<string | null>(null);
  const [drag, setDrag] = useState<string | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.tasks().then((r) => setTasks(r.tasks)).catch((e) => setErr(String(e))); }, []);
  const cards = [...run.findings, ...(hvac?.findings ?? [])]
    .sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || (a.id ?? "").localeCompare(b.id ?? ""));
  const t = (c: Check): Task => tasks[c.check_key] ?? { column: "backlog", assignee: null };
  const save = async (key: string, body: Partial<Task>) => {
    setTasks((m) => ({ ...m, [key]: { ...(m[key] ?? { column: "backlog", assignee: null }), ...body } as Task }));
    try { await api.task(key, body); } catch (e) { setErr(String(e)); }
  };
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline gap-3">
        <h1 className="sq-h1">Demo ship · Rev {run.revision} · {cards.length} tasks</h1>
        <span className="sq-chip" style={{ fontSize: 11 }}>people and dates mock</span>
      </div>
      {err && <div className="sq-banner">{err}</div>}
      <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))", alignItems: "start" }}>
        {COLS.map(([col, label]) => {
          const mine = cards.filter((c) => t(c).column === col);
          return (
            <section key={col} className="sq-card board-col" onDragOver={(e) => e.preventDefault()}
                     onDrop={() => { if (drag) save(drag, { column: col }); setDrag(null); }}>
              <header className="flex items-center" style={{ padding: "12px 14px", borderBottom: "1px solid var(--line)" }}>
                <b style={{ flex: 1 }}>{label} <span className="sq-faint mono">{mine.length}</span></b>
              </header>
              <div className="flex flex-col gap-2" style={{ padding: 12, minHeight: 120 }}>
                {mine.length === 0 && <div className="sq-card is-dashed sq-muted" style={{ padding: 16, textAlign: "center", fontSize: 13 }}>
                  {col === "done" ? "Nothing done yet. A task moves here when you finish it; the rule engine re-checks on the next run." : "Drop a card here."}</div>}
                {mine.map((c) => {
                  const [tag, color] = DISC[c.group] ?? ["··", "var(--fg-3)"];
                  const who = PEOPLE.find((p) => p.id === t(c).assignee);
                  return (
                    <div key={c.check_key} className="sq-card board-card" draggable onDragStart={() => setDrag(c.check_key)}
                         style={{ borderLeft: `3px solid ${color}` }}>
                      <div className="flex items-center gap-2">
                        <b className="mono" style={{ color, fontSize: 11 }}>{tag}</b><Pill s={c.status} /><span className="mono sq-faint" style={{ fontSize: 12 }}>{c.id}</span>
                        <span style={{ flex: 1 }} />
                        <select className="board-move" value={col} title="Move to" onChange={(e) => save(c.check_key, { column: e.target.value as Task["column"] })}>
                          {COLS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                        </select>
                      </div>
                      <a href="#" className="board-title" onClick={(e) => { e.preventDefault(); onOpen(c); }}>{c.title}</a>
                      <div className="flex items-center gap-2" style={{ position: "relative" }}>
                        {who ? <button className="board-who" onClick={() => setPop(pop === c.check_key ? null : c.check_key)}><b className="tb-av">{who.initials}</b>{who.name}</button>
                             : <button className="sq-btn is-sm" onClick={() => setPop(pop === c.check_key ? null : c.check_key)}>Assign</button>}
                        <span style={{ flex: 1 }} /><span className="sq-faint mono" style={{ fontSize: 11 }}>{c.location.label}</span>
                        {pop === c.check_key && (
                          <div className="sq-card board-pop">
                            <div className="sq-faint" style={{ fontSize: 11, padding: "4px 8px" }}>Assign to… · mock people</div>
                            {PEOPLE.map((p) => (
                              <button key={p.id} className="board-person" onClick={() => { save(c.check_key, { assignee: p.id }); setPop(null); }}>
                                <b className="tb-av">{p.initials}</b><span style={{ flex: 1, textAlign: "left" }}><span>{p.name}</span><br /><span className="sq-faint" style={{ fontSize: 12 }}>{p.role}</span></span>
                                <span className="sq-chip" style={{ fontSize: 10 }}>mock</span>
                              </button>
                            ))}
                            {who && <button className="board-person sq-muted" onClick={() => { save(c.check_key, { assignee: "" }); setPop(null); }}>Unassign</button>}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
      <p className="sq-faint">Drag a card or use its menu to move it. The verdict still comes from the rule engine: moving a card to Done does not clear a finding.</p>
    </div>
  );
}
