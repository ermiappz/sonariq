// Traceability matrix (spec B7): parts × rules, one coloured cell per check; click a cell to select that part's check.
// Drawn on a canvas, only the visible window, so a whole ship (tens of thousands of parts) stays light.
import { useEffect, useMemo, useRef, useState } from "react";
import { ORDER, WORD, type Check, type Run } from "../api";
import { passCheck } from "./FindingsList";

const RH = 14, CW = 34, LW = 170, HEAD = 74;

export default function TraceMatrix({ run, onPick, selected }: { run: Run; onPick: (c: Check) => void; selected: string | null }) {
  const cv = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState(0);
  const [size, setSize] = useState({ w: 380, h: 400 });
  const [tip, setTip] = useState<string>("");
  const [css, setCss] = useState<CSSStyleDeclaration>(() => getComputedStyle(document.documentElement));
  useEffect(() => { if (wrap.current) setCss(getComputedStyle(wrap.current)); }, []);   // tokens live on the theme element
  const col = (s: string) => css.getPropertyValue(s === "pass" ? "--st-pass-fill" : s === "fail" ? "--st-fail-fill" : s === "warn" ? "--st-warn-fill" : s === "unk" ? "--st-unk" : "--st-dor").trim() || "#888";

  const { rules, parts } = useMemo(() => {
    const rules = Object.keys(run.by_rule ?? {}).sort();
    const all = [...run.checks, ...(run.compact ? (run.passes ?? []).map((p) => passCheck(run, p)) : [])];
    const by = new Map<string, { name: string; cells: Record<string, Check>; worst: number }>();
    for (const c of all) {
      const g = c.element?.guid ?? c.check_key;
      const p = by.get(g) ?? { name: c.element?.name ?? c.title, cells: {}, worst: 9 };
      p.cells[c.rule] = c; p.worst = Math.min(p.worst, ORDER.indexOf(c.status));
      by.set(g, p);
    }
    const parts = [...by.values()].sort((a, b) => a.worst - b.worst || a.name.localeCompare(b.name));
    return { rules, parts };
  }, [run]);

  useEffect(() => {
    const el = wrap.current; if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight })); ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const c = cv.current; if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = size.w * dpr; c.height = size.h * dpr;
    const g = c.getContext("2d")!; g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, size.w, size.h);
    g.font = "11px 'IBM Plex Mono', monospace"; g.textBaseline = "middle";
    const fg = css.getPropertyValue("--fg-2").trim(), faint = css.getPropertyValue("--fg-3").trim(), line = css.getPropertyValue("--line").trim();
    rules.forEach((r, k) => {                                   // rule ids, rotated
      g.save(); g.translate(LW + k * CW + CW / 2 + 4, HEAD - 6); g.rotate(-Math.PI / 3); g.fillStyle = fg; g.fillText(r, 0, 0); g.restore();
    });
    const first = Math.floor(top / RH), last = Math.min(parts.length, first + Math.ceil((size.h - HEAD) / RH) + 1);
    for (let i = first; i < last; i++) {
      const p = parts[i], y = HEAD + (i * RH - top);
      g.fillStyle = faint; g.fillText(p.name.slice(0, 22), 4, y + RH / 2);
      rules.forEach((r, k) => {
        const c = p.cells[r];
        g.fillStyle = c ? col(c.status) : "transparent";
        if (c) g.fillRect(LW + k * CW + 2, y + 2, CW - 4, RH - 4);
        if (c && c.check_key === selected) { g.strokeStyle = css.getPropertyValue("--accent").trim(); g.lineWidth = 2; g.strokeRect(LW + k * CW + 1, y + 1, CW - 2, RH - 2); }
      });
      g.fillStyle = line; g.fillRect(0, y + RH - 0.5, LW + rules.length * CW, 0.5);
    }
  }, [top, size, parts, rules, selected, css]); // eslint-disable-line react-hooks/exhaustive-deps

  const at = (e: React.MouseEvent) => {
    const r = cv.current!.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    if (y < HEAD || x < LW) return null;
    const p = parts[Math.floor((y - HEAD + top) / RH)], rule = rules[Math.floor((x - LW) / CW)];
    return p && rule ? p.cells[rule] ?? null : null;
  };
  return (
    <div className="tm">
      <div className="sq-faint tm-legend">{parts.length.toLocaleString("en-US")} parts × {rules.length} rules · {ORDER.filter((s) => s !== "dor").map((s) => (
        <span key={s}><i style={{ background: col(s) }} />{WORD[s]}</span>))}</div>
      <div className="tm-wrap" ref={wrap} onScroll={(e) => setTop(e.currentTarget.scrollTop)}>
        <canvas ref={cv} className="tm-cv" style={{ width: size.w, height: size.h }} aria-label="Traceability matrix: parts by rules"
          onMouseMove={(e) => { const c = at(e); setTip(c ? `${c.element?.name ?? ""} · ${c.rule} · ${WORD[c.status]}${c.summary ? " · " + c.summary : ""}` : ""); }}
          onMouseLeave={() => setTip("")} onClick={(e) => { const c = at(e); if (c) onPick(c); }} />
        <div style={{ height: Math.max(0, HEAD + parts.length * RH - size.h) }} />
      </div>
      <div className="tm-tip mono">{tip || "Click a cell to select that part"}</div>
    </div>
  );
}
