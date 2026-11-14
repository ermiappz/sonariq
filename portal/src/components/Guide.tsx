// First-run guide (Studio reliability step 5): five callouts anchored to the real Studio controls, placed by the same
// module as the finding callouts (viewer/callout.ts placeCallout: beside the target, never over it, inside the view).
// A target that is not on screen yet (e.g. findings before Analyse) gets a centred card that says so.
import { useEffect, useRef, useState } from "react";
import { placeCallout, type Placed } from "../viewer/callout";

type GStep = { title: string; text: string; targets: string[]; missing: string };
export const GUIDE: GStep[] = [
  { title: "Pick a model here, or upload your own IFC", text: "Each project keeps its own models; a model opens at its latest revision.",
    targets: ['[aria-label="Models in this project"]'], missing: "Press Open model to see the list." },
  { title: "Press Analyse", text: "The rule engine checks the open revision. Every verdict and number comes from the engine, not from AI.",
    targets: ['[data-guide="analyse"]'], missing: "Open a model first." },
  { title: "Here is your first finding, click it", text: "The callout in the 3D shows what the model has, what it must be, the clause and where each value comes from.",
    targets: [".fl-row", ".studio-card"], missing: "Findings appear here after you press Analyse." },
  { title: "Cut a section here, change the view here", text: "Section at finding cuts through the selected finding; the View tab has display modes, systems and saved views.",
    targets: ['[data-guide="section"]', ".sec-toggle", '[data-guide="view-tab"]'], missing: "Open a model to use the section and view tools." },
  { title: "Save a revision or export", text: "Report, CSV and BCF save this revision exactly as it is now; Clear all asks before closing the model.",
    targets: [".studio-sum", '[data-guide="export"]'], missing: "These appear once the revision is analysed." },
];

export default function Guide({ onDone, onDemo }: { onDone: () => void; onDemo: () => void }) {
  const [i, setI] = useState(0);
  const card = useRef<HTMLDivElement>(null);
  const [geo, setGeo] = useState<{ p: Placed | null; rings: DOMRect[]; anchor: [number, number] | null }>({ p: null, rings: [], anchor: null });
  const s = GUIDE[i];
  // measured on a timer, not on every render: placing the card changes its size, which would re-place it forever
  const measure = useRef<() => void>(() => {});
  measure.current = () => {
    const els = s.targets.map((q) => document.querySelector(q)).filter((e): e is Element => !!e && (e as HTMLElement).offsetParent !== null);
    const rings = els.map((e) => e.getBoundingClientRect());
    const size = { w: card.current?.offsetWidth ?? 320, h: card.current?.offsetHeight ?? 160 };
    const view = { w: window.innerWidth, h: window.innerHeight };
    if (!rings.length) { setGeo((g) => (g.p || g.rings.length ? { p: null, rings: [], anchor: null } : g)); return; }
    const r = rings[0];
    const anchor: [number, number] = [r.left + r.width / 2, r.top + r.height / 2];
    const p = placeCallout(anchor, { x0: r.left, y0: r.top, x1: r.right, y1: r.bottom }, size, view, 18, 12);
    const sig = (q: Placed | null, rs: DOMRect[]) => JSON.stringify([q && [Math.round(q.x), Math.round(q.y)], rs.map((x) => [Math.round(x.left), Math.round(x.top), Math.round(x.width), Math.round(x.height)])]);
    setGeo((g) => (sig(g.p, g.rings) === sig(p, rings) ? g : { p, rings, anchor }));
  };
  useEffect(() => { measure.current(); const t = window.setInterval(() => measure.current(), 300); return () => window.clearInterval(t); }, [i]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onDone(); };
    window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const last = i === GUIDE.length - 1;
  const style = geo.p ? { left: geo.p.x, top: geo.p.y } : { left: "50%", top: "40%", transform: "translate(-50%, -50%)" };
  return (
    <div className="guide" aria-live="polite">
      <svg className="guide-lead" width="100%" height="100%" aria-hidden>
        {geo.p && geo.rings[0] && (() => { const r = geo.rings[0], [lx, ly] = geo.p.lead;   // leader stops at the ring's edge
          return <line x1={lx} y1={ly} x2={Math.min(Math.max(lx, r.left - 4), r.right + 4)} y2={Math.min(Math.max(ly, r.top - 4), r.bottom + 4)} />; })()}
        {geo.rings.map((r, k) => <rect key={k} x={r.left - 4} y={r.top - 4} width={r.width + 8} height={r.height + 8} rx={6} />)}
      </svg>
      <div ref={card} className="co-card sq-card guide-card" role="dialog" aria-label={`Guide step ${i + 1} of ${GUIDE.length}`} style={style}>
        <div className="guide-dots" aria-hidden>{GUIDE.map((_, k) => <i key={k} className={k < i ? "is-done" : k === i ? "is-on" : ""} />)}</div>
        <b className="guide-title">{s.title}</b>
        <div>{s.text}</div>
        {!geo.p && <div className="sq-faint">{s.missing}</div>}
        {i === 0 && <button className="studio-link guide-demo" onClick={onDemo}>Play the demo instead</button>}
        <div className="flex gap-1" style={{ justifyContent: "flex-end", marginTop: 6 }}>
          <button className="sq-btn is-sm" onClick={onDone}>Skip</button>
          <button className="sq-btn is-sm" disabled={i === 0} onClick={() => setI(i - 1)}>Back</button>
          <button className="sq-btn is-sm is-primary" autoFocus onClick={() => (last ? onDone() : setI(i + 1))}>{last ? "Done" : "Next"}</button>
        </div>
      </div>
    </div>
  );
}
