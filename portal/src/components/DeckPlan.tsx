// DeckPlan (handoff.md): shared plan view. Port at top, bow to the right. Fire-division line styles:
// A-60 4 px solid, A-0 2 px solid, B-15 dashed, B-0 dotted. Ink is neutral. Geometry comes from the engine.
import type { ReactNode } from "react";
import type { Ring, SimGeometry } from "../api";

export const FR = 0.8; // frame spacing, m (model pset frame_spacing_m)

export function ringPath(r: Ring | Ring[]): string {
  const rings = Array.isArray(r) ? r : [r];
  const one = (pts: number[][]) => "M" + pts.map((p) => `${p[0]},${-p[1]}`).join("L") + "Z";
  return rings.map((g) => one(g.outer) + g.holes.map(one).join("")).join("");
}

function centerline(r: Ring): [number, number, number, number] {
  const xs = r.outer.map((p) => p[0]), ys = r.outer.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  return x1 - x0 >= y1 - y0 ? [x0, (y0 + y1) / 2, x1, (y0 + y1) / 2] : [(x0 + x1) / 2, y0, (x0 + x1) / 2, y1];
}

const STYLE: Record<string, { w: string; dash: string }> = {
  "A-60": { w: "var(--fd-a60-w)", dash: "var(--fd-a60-dash)" }, "A-0": { w: "var(--fd-a0-w)", dash: "var(--fd-a0-dash)" },
  "B-15": { w: "var(--fd-b15-w)", dash: "var(--fd-b15-dash)" }, "B-0": { w: "var(--fd-b0-w)", dash: "var(--fd-b0-dash)" },
};

export function viewBox(g: SimGeometry, pad = 2) {
  const [x0, y0, x1, y1] = g.bounds;
  return { x: x0 - pad, y: -y1 - pad - 1.6, w: x1 - x0 + 2 * pad, h: y1 - y0 + 2 * pad + 1.6 };
}

export default function DeckPlan({ g, children, smoke = [], route, legend = true }:
  { g: SimGeometry; children?: ReactNode; smoke?: string[]; route?: number[][] | null; legend?: boolean }) {
  const vb = viewBox(g);
  const [x0, , x1, y1] = g.bounds;
  const f0 = Math.ceil(x0 / FR), f1 = Math.floor(x1 / FR);
  const ticks = [];
  for (let f = f0; f <= f1; f++) ticks.push(f);
  return (
    <svg viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`} style={{ width: "100%", height: "100%", display: "block", background: "var(--plan-bg)" }}
         preserveAspectRatio="xMidYMid meet" aria-label="Deck 5 plan">
      <defs>
        <pattern id="smokehatch" width="0.6" height="0.6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="0.6" stroke="var(--fg-3)" strokeWidth="0.12" />
        </pattern>
      </defs>
      <path d={ringPath(g.walkable)} fill="var(--plan-space)" />
      {g.spaces.filter((s) => s.category === "stair").map((s) => <path key={s.name} d={ringPath(s.poly)} fill="var(--bg-3)" opacity={0.5} />)}
      {g.spaces.filter((s) => smoke.includes(s.name)).map((s) => <path key={"sm" + s.name} d={ringPath(s.poly)} fill="url(#smokehatch)" />)}
      {g.stairs.map((s) => <path key={s.name} d={ringPath(s.flight)} fill="none" stroke="var(--fd-ink)" strokeWidth={1} vectorEffect="non-scaling-stroke" strokeDasharray="2 2" />)}
      {g.walls.map((w) => {
        const [a, b, c, d] = centerline(w.poly);
        const st = STYLE[w.rating ?? ""] ?? { w: "1px", dash: "none" };
        return <line key={w.name} x1={a} y1={-b} x2={c} y2={-d} stroke="var(--fd-ink)" style={{ strokeWidth: st.w, strokeDasharray: st.dash }}
                     vectorEffect="non-scaling-stroke"><title>{w.name} · {w.rating ?? "no rating"}</title></line>;
      })}
      {g.doors.map((d) => {
        const [a, b, c, e] = centerline(d.poly);
        const horiz = Math.abs(c - a) > Math.abs(e - b);
        const half = d.width / 2, cx = (a + c) / 2, cy = (b + e) / 2;
        return <line key={d.name} x1={horiz ? cx - half : cx} y1={-(horiz ? cy : cy - half)} x2={horiz ? cx + half : cx} y2={-(horiz ? cy : cy + half)}
                     stroke="var(--plan-bg)" strokeWidth={3} vectorEffect="non-scaling-stroke"><title>{d.name}{d.self_closing ? " · self-closing" : ""}</title></line>;
      })}
      {route && route.length > 1 && <polyline points={route.map((p) => `${p[0]},${-p[1]}`).join(" ")} fill="none" stroke="var(--fg-2)"
                                              strokeWidth={1.5} strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />}
      {g.stairs.map((s) => {
        const xs = s.flight.outer.map((p) => p[0]);
        return <text key={"t" + s.name} x={(Math.min(...xs) + Math.max(...xs)) / 2} y={0.35} fontSize={0.9} textAnchor="middle" fill="var(--fg-2)">Stair {s.name}</text>;
      })}
      {/* frame ruler: tick every frame, label every 5 */}
      <g>
        {ticks.map((f) => <line key={f} x1={f * FR} x2={f * FR} y1={-y1 - 1.6} y2={-y1 - 1.6 + (f % 5 ? 0.35 : 0.7)} stroke="var(--fg-3)" strokeWidth={0.5} vectorEffect="non-scaling-stroke" />)}
        {ticks.filter((f) => f % 5 === 0).map((f) => <text key={"l" + f} x={f * FR} y={-y1 - 0.4} fontSize={0.7} textAnchor="middle" fill="var(--fg-3)">{f}</text>)}
      </g>
      {children}
      {legend && <g transform={`translate(${vb.x + 0.6},${vb.y + vb.h - 0.6})`} fontSize={0.65} fill="var(--fg-2)">
        {(["A-60", "A-0", "B-15", "B-0"] as const).map((k, i) => (
          <g key={k} transform={`translate(${i * 6},0)`}>
            <line x1={0} x2={2} y1={-0.25} y2={-0.25} stroke="var(--fd-ink)" style={{ strokeWidth: STYLE[k].w, strokeDasharray: STYLE[k].dash }} vectorEffect="non-scaling-stroke" />
            <text x={2.4} y={0}>{k}</text>
          </g>))}
      </g>}
    </svg>
  );
}
