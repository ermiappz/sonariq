// Findings at scale (spec B6): grouped by rule, then by status, fails first; counts per rule; filters for rule
// source, SWBS group, deck and status; one virtualised list (never more than a screenful of rows in the DOM).
// The selected finding's full card (with its actions) sits above the list. Counts and verdicts come from the run.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ORDER, WORD, type Check, type Run } from "../api";
import { Pill } from "./ui";

const ROW = 44;
const OVERSCAN = 6;
const SWBS: Record<string, string> = { "1": "1 Hull structure", "2": "2 Propulsion", "3": "3 Electric plant", "4": "4 Command & surveillance",
  "5": "5 Auxiliary systems", "6": "6 Outfit & furnishing", "7": "7 Mission systems" };

type Item = { kind: "head"; rule: string; title: string; ref: string; line: string; open: boolean; worst: string }
  | { kind: "row"; c: Check };

/** a compact pass row (whole-ship runs) as the minimal Check the list, the viewer and the card need */
export function passCheck(run: Run, p: NonNullable<Run["passes"]>[number]): Check {
  const [rule, guid, name, deck, summary, swbs] = p;
  const br = run.by_rule?.[rule];
  return { id: null, check_key: `${rule}|${guid ?? "-"}`, rule, title: br?.title ?? rule, source: br?.source_group ?? "", clause: "", ref: br?.ref ?? "",
    clause_text: "", reading: "", rule_status: "", to_verify: false, pack: "", group: br?.group ?? "", discipline: "", discipline_label: "",
    status: "pass", status_word: "Pass", glyph: "✓", element: guid ? { guid, name: name ?? guid, ifc_class: "" } : null,
    location: { deck, frame: null, side: null, label: deck ? `Deck ${deck}` : "", swbs: swbs ?? undefined }, required: null, measured: null, margin: null,
    summary, formula: null, method: "", missing: [], revision: run.revision } as Check;
}

const n = (v: number) => v.toLocaleString("en-US");
export function countLine(counts: Record<string, number>): string {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const parts = ORDER.filter((s) => counts[s]).map((s) => `${n(counts[s])} ${WORD[s].toLowerCase()}`);
  return `${n(total)} part${total === 1 ? "" : "s"}: ${parts.join(", ")}`;
}

export default function FindingsList({ run, status, selected, onPick, renderCard, incorrect }: {
  run: Run; status: string | null; selected: string | null; onPick: (c: Check) => void;
  renderCard: (c: Check) => ReactNode; incorrect: Record<string, unknown>;
}) {
  const [src, setSrc] = useState(""); const [deck, setDeck] = useState(""); const [swbs, setSwbs] = useState("");
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const [top, setTop] = useState(0);
  const [h, setH] = useState(400);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current; if (!el) return;
    const ro = new ResizeObserver(() => setH(el.clientHeight)); ro.observe(el); setH(el.clientHeight);
    return () => ro.disconnect();
  }, []);

  // every check of the run, passes from compact rows when the run is a whole ship
  const all = useMemo(() => {
    const full = run.checks;
    return run.compact && status === "pass" ? (run.passes ?? []).map((p) => passCheck(run, p)) : full;
  }, [run, status]);
  const sources = useMemo(() => [...new Set(Object.values(run.by_rule ?? {}).map((r) => r.source_group))].sort(), [run]);
  const decks = useMemo(() => [...new Set(all.map((c) => c.location?.deck).filter(Boolean) as string[])].sort((a, b) => Number(a) - Number(b) || a.localeCompare(b)), [all]);
  const swbsGroups = useMemo(() => [...new Set(all.map((c) => c.location?.swbs?.[0]).filter(Boolean) as string[])].sort(), [all]);

  const rows = useMemo(() => all.filter((c) =>
    (status ? c.status === status : ["fail", "warn", "unk"].includes(c.status))
    && (!src || (run.by_rule?.[c.rule]?.source_group ?? c.source_group) === src)
    && (!deck || c.location?.deck === deck)
    && (!swbs || c.location?.swbs?.[0] === swbs)), [all, status, src, deck, swbs, run]);

  const items = useMemo(() => {
    const by = new Map<string, Check[]>();
    for (const c of rows) { const a = by.get(c.rule) ?? []; a.push(c); by.set(c.rule, a); }
    const rank = (cs: Check[]) => Math.min(...cs.map((c) => ORDER.indexOf(c.status)));
    const groups = [...by.entries()].sort((a, b) => rank(a[1]) - rank(b[1]) || a[0].localeCompare(b[0]));
    const out: Item[] = [];
    for (const [rule, cs] of groups) {
      const br = run.by_rule?.[rule];
      const open = !(closed[rule] ?? (groups.length > 1 && cs.length > 200));     // big groups start closed
      out.push({ kind: "head", rule, title: br?.title ?? cs[0].title, ref: br?.ref ?? cs[0].ref, line: br ? countLine(br.counts) : `${n(cs.length)} shown`,
        open, worst: ORDER[rank(cs)] });
      if (open) {
        cs.sort((a, b) => Number(!!incorrect[a.check_key]) - Number(!!incorrect[b.check_key]) || ORDER.indexOf(a.status) - ORDER.indexOf(b.status)
          || (a.id ?? "").localeCompare(b.id ?? "") || (a.element?.name ?? "").localeCompare(b.element?.name ?? ""));
        for (const c of cs) out.push({ kind: "row", c });
      }
    }
    return out;
  }, [rows, closed, run, incorrect]);

  const sel = useMemo(() => all.find((c) => c.check_key === selected) ?? null, [all, selected]);
  const first = Math.max(0, Math.floor(top / ROW) - OVERSCAN);
  const last = Math.min(items.length, Math.ceil((top + h) / ROW) + OVERSCAN);
  const keyNav = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const flat = items.filter((i): i is Extract<Item, { kind: "row" }> => i.kind === "row").map((i) => i.c);
    const k = flat.findIndex((c) => c.check_key === selected);
    const next = flat[Math.max(0, Math.min(flat.length - 1, k + (e.key === "ArrowDown" ? 1 : -1)))];
    if (next) { e.preventDefault(); onPick(next); const idx = items.findIndex((i) => i.kind === "row" && i.c === next);
      const el = box.current; if (el && (idx * ROW < el.scrollTop || (idx + 1) * ROW > el.scrollTop + el.clientHeight)) el.scrollTop = idx * ROW - el.clientHeight / 2; }
  };

  return (
    <div className="fl">
      <div className="fl-filters">
        <select className="sq-input" aria-label="Rule source" value={src} onChange={(e) => setSrc(e.target.value)}>
          <option value="">All sources</option>{sources.map((s) => <option key={s} value={s}>{s}</option>)}</select>
        {swbsGroups.length > 0 && <select className="sq-input" aria-label="SWBS group" value={swbs} onChange={(e) => setSwbs(e.target.value)}>
          <option value="">All SWBS</option>{swbsGroups.map((s) => <option key={s} value={s}>{SWBS[s] ?? s}</option>)}</select>}
        {decks.length > 1 && <select className="sq-input" aria-label="Deck" value={deck} onChange={(e) => setDeck(e.target.value)}>
          <option value="">All decks</option>{decks.map((d) => <option key={d} value={d}>Deck {d}</option>)}</select>}
        <span className="sq-faint fl-count">{n(rows.length)} shown</span>
      </div>
      {sel && <div className="fl-detail">{renderCard(sel)}</div>}
      <div className="fl-list" ref={box} tabIndex={0} role="listbox" aria-label="Findings" onKeyDown={keyNav} onScroll={(e) => setTop(e.currentTarget.scrollTop)}>
        <div style={{ height: items.length * ROW, position: "relative" }}>
          {items.slice(first, last).map((it, k) => {
            const y = (first + k) * ROW;
            if (it.kind === "head") return (
              <button key={"h" + it.rule} className={`fl-head s-${it.worst}`} style={{ top: y }} aria-expanded={it.open}
                onClick={() => setClosed((c) => ({ ...c, [it.rule]: it.open }))}>
                <span className="fl-caret" aria-hidden>{it.open ? "▾" : "▸"}</span>
                <span className="fl-head-t"><b>{it.title}</b> <span className="mono sq-faint">{it.rule}</span><br />
                  <span className="sq-faint mono">{it.line}</span></span>
              </button>);
            const c = it.c, on = c.check_key === selected;
            return (
              <div key={c.check_key} role="option" aria-selected={on} className={`fl-row${on ? " is-on" : ""}${incorrect[c.check_key] ? " is-incorrect" : ""}`}
                style={{ top: y }} onClick={() => onPick(c)}>
                <Pill s={c.status} />
                <span className="mono fl-id">{c.id ?? ""}</span>
                <span className="fl-main"><span className="fl-name">{c.element?.name ?? c.title}</span>
                  <span className="mono sq-faint fl-sub">{[c.location?.label, c.summary].filter(Boolean).join(" · ")}</span></span>
              </div>);
          })}
        </div>
        {items.length === 0 && <p className="sq-muted" style={{ padding: 12 }}>No findings with these filters.</p>}
      </div>
    </div>
  );
}
