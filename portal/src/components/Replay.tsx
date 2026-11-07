// 2D vector replay: SVG ship (DeckPlan) + Canvas people (2 Hz samples interpolated at 60 fps, small neutral dots)
// + optional density heatmap (one sequential ramp, p/m²). d3 draws scales, timeline, histogram and queue chart.
import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import type { SimReplay, SimResults } from "../api";
import DeckPlan, { viewBox } from "./DeckPlan";

export const HEAT = d3.interpolateCividis; // one sequential ramp
export const HEAT_MAX = 4; // p/m² legend top = Circ.1533 Annex 3 §3.1 congestion level (from params)

type Frame = SimReplay["frames"][number];

function positionsAt(frames: Frame[], t: number): [number, number, number][] {
  if (!frames.length) return [];
  let lo = 0, hi = frames.length - 1;
  if (t <= frames[0][0]) return frames[0][1];
  if (t >= frames[hi][0]) return frames[hi][1];
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (frames[m][0] <= t) lo = m; else hi = m; }
  const [ta, a] = frames[lo], [tb, b] = frames[hi];
  const f = (t - ta) / (tb - ta);
  const nb = new Map(b.map((p) => [p[0], p]));
  const out: [number, number, number][] = [];
  for (const p of a) {
    const q = nb.get(p[0]);
    out.push(q ? [p[0], p[1] + (q[1] - p[1]) * f, p[2] + (q[2] - p[2]) * f] : p);
  }
  return out;
}

export function useClock(t0: number, t1: number) {
  const [t, setT] = useState(t0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(10);
  useEffect(() => { setT(t0); }, [t0]);
  useEffect(() => {
    if (!playing) return;
    let raf = 0, last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000; last = now;
      setT((x) => { const n = x + dt * speed; if (n >= t1) { setPlaying(false); return t1; } return n; });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, t1]);
  return { t, setT, playing, setPlaying, speed, setSpeed };
}

export function Controls({ clock, t0, t1 }: { clock: ReturnType<typeof useClock>; t0: number; t1: number }) {
  return (
    <div className="flex items-center gap-2" style={{ padding: "6px 0" }}>
      <button className="sq-btn" onClick={() => { if (clock.t >= t1) clock.setT(t0); clock.setPlaying(!clock.playing); }} aria-label={clock.playing ? "Pause" : "Play"}>
        {clock.playing ? "❚❚ Pause" : "▶ Play"}</button>
      <div className="sq-seg">{[1, 10].map((s) => <button key={s} className={clock.speed === s ? "is-on" : ""} onClick={() => clock.setSpeed(s)}>×{s}</button>)}</div>
      <input type="range" min={t0} max={t1} step={0.5} value={clock.t} onChange={(e) => clock.setT(+e.target.value)} style={{ flex: 1 }} aria-label="Time" />
      <span className="mono" style={{ minWidth: 72, textAlign: "right" }}>t = {Math.round(clock.t)} s</span>
    </div>
  );
}

export function ReplayView({ rep, t, heat, smoke, route, onPick, height = 360 }:
  { rep: SimReplay; t: number; heat: boolean; smoke?: string[]; route?: number[][] | null; onPick?: (x: number, y: number) => void; height?: number }) {
  const wrap = useRef<HTMLDivElement>(null);
  const cv = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ w: 800, h: height });
  const vb = useMemo(() => viewBox(rep.geometry), [rep]);
  useEffect(() => {
    const el = wrap.current; if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el); return () => ro.disconnect();
  }, []);
  const map = useMemo(() => {
    const s = Math.min(size.w / vb.w, size.h / vb.h);
    const ox = (size.w - vb.w * s) / 2, oy = (size.h - vb.h * s) / 2;
    return { s, X: (x: number) => ox + (x - vb.x) * s, Y: (y: number) => oy + (-y - vb.y) * s,
      inv: (px: number, py: number) => [vb.x + (px - ox) / s, -(vb.y + (py - oy) / s)] };
  }, [size, vb]);
  useEffect(() => {
    const c = cv.current; if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = size.w * dpr; c.height = size.h * dpr;
    const ctx = c.getContext("2d")!; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.w, size.h);
    if (heat) {
      const d = rep.density, cs = d.cell_m;
      for (let j = 0; j < d.ny; j++) for (let i = 0; i < d.nx; i++) {
        const v = d.peak[j][i]; if (v < 0.5) continue;
        ctx.fillStyle = HEAT(Math.min(1, v / HEAT_MAX)); ctx.globalAlpha = 0.8;
        const x = d.origin[0] + i * cs, y = d.origin[1] + j * cs;
        ctx.fillRect(map.X(x), map.Y(y + cs), cs * map.s + 0.5, cs * map.s + 0.5);
      }
      ctx.globalAlpha = 1;
    }
    const r = Math.max(1.6, 0.2 * map.s);
    ctx.fillStyle = getComputedStyle(c).getPropertyValue("--fg-1") || "#eee";
    for (const p of positionsAt(rep.frames, t)) { ctx.beginPath(); ctx.arc(map.X(p[1]), map.Y(p[2]), r, 0, Math.PI * 2); ctx.fill(); }
  }, [rep, t, heat, size, map]);
  return (
    <div ref={wrap} style={{ position: "relative", height, border: "1px solid var(--line)", borderRadius: "var(--r)", overflow: "hidden" }}>
      <DeckPlan g={rep.geometry} smoke={smoke} route={route} />
      <canvas ref={cv} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", cursor: onPick ? "crosshair" : "default" }}
              onClick={(e) => { if (!onPick) return; const b = (e.target as HTMLCanvasElement).getBoundingClientRect(); const [x, y] = map.inv(e.clientX - b.left, e.clientY - b.top); onPick(x, y); }} />
      {heat && <HeatLegend />}
    </div>
  );
}

function HeatLegend() {
  const stops = d3.range(0, 1.01, 0.1);
  return (
    <div style={{ position: "absolute", right: 8, top: 8, background: "var(--bg-1)", border: "1px solid var(--line)", padding: "4px 6px", fontSize: 11 }}>
      <div className="sq-faint">Peak density, p/m²</div>
      <div style={{ display: "flex", height: 8, width: 120, marginTop: 3 }}>{stops.map((s) => <div key={s} style={{ flex: 1, background: HEAT(s) }} />)}</div>
      <div className="flex mono" style={{ justifyContent: "space-between" }}><span>0</span><span>{HEAT_MAX / 2}</span><span>≥{HEAT_MAX}</span></div>
    </div>
  );
}

export function QueueChart({ rep, t, height = 140 }: { rep: SimReplay; t: number; height?: number }) {
  const ref = useRef<SVGSVGElement>(null);
  const keys = Object.keys(rep.queue_series);
  const n = Math.max(...keys.map((k) => rep.queue_series[k].length), 1);
  const w = 560, m = { l: 34, r: 60, t: 8, b: 22 };
  const x = d3.scaleLinear().domain([rep.series_t0_s, rep.series_t0_s + n]).range([m.l, w - m.r]);
  const ymax = Math.max(4, ...keys.flatMap((k) => rep.queue_series[k]));
  const y = d3.scaleLinear().domain([0, ymax]).nice().range([height - m.b, m.t]);
  useEffect(() => {
    const s = d3.select(ref.current!); s.selectAll("*").remove();
    s.append("g").attr("transform", `translate(0,${height - m.b})`).call(d3.axisBottom(x).ticks(6).tickFormat((d) => `${d} s`)).attr("color", "var(--fg-3)");
    s.append("g").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4)).attr("color", "var(--fg-3)");
    const line = d3.line<number>().x((_, i) => x(rep.series_t0_s + i)).y((v) => y(v));
    const dash = ["", "4 2", "1 2", "6 2 1 2", "8 3", "2 4"];
    keys.forEach((k, i) => {
      const ser = rep.queue_series[k];
      s.append("path").datum(ser).attr("d", line).attr("fill", "none").attr("stroke", "var(--fg-1)").attr("stroke-width", 1.4).attr("stroke-dasharray", dash[i % dash.length]);
      s.append("text").attr("x", w - m.r + 4).attr("y", y(ser[Math.floor(ser.length * 0.15)] ?? 0)).attr("fill", "var(--fg-2)").attr("font-size", 10).text(k);
    });
  }, [rep]);
  return (
    <svg ref={ref} viewBox={`0 0 ${w} ${height}`} style={{ width: "100%", height }} aria-label="Queue length per landing">
      <line x1={x(t)} x2={x(t)} y1={m.t} y2={height - m.b} stroke="var(--accent)" />
    </svg>
  );
}

export function Histogram({ r, height = 120 }: { r: SimResults; height?: number }) {
  const ref = useRef<SVGSVGElement>(null);
  useEffect(() => {
    const w = 360, m = { l: 30, r: 8, t: 8, b: 22 };
    const s = d3.select(ref.current!); s.selectAll("*").remove();
    const e = r.histogram.edges, c = r.histogram.counts;
    if (!e.length) return;
    const x = d3.scaleLinear().domain([e[0], e[e.length - 1]]).range([m.l, w - m.r]);
    const y = d3.scaleLinear().domain([0, d3.max(c) ?? 1]).nice().range([height - m.b, m.t]);
    s.append("g").attr("transform", `translate(0,${height - m.b})`).call(d3.axisBottom(x).ticks(5).tickFormat((d) => `${d} s`)).attr("color", "var(--fg-3)");
    s.append("g").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(3)).attr("color", "var(--fg-3)");
    s.selectAll("rect").data(c).join("rect").attr("x", (_, i) => x(e[i]) + 0.5).attr("width", (_, i) => Math.max(1, x(e[i + 1]) - x(e[i]) - 1))
      .attr("y", (v) => y(v)).attr("height", (v) => height - m.b - y(v)).attr("fill", "var(--fg-3)");
    s.append("line").attr("x1", x(r.tA_p95_s)).attr("x2", x(r.tA_p95_s)).attr("y1", m.t).attr("y2", height - m.b).attr("stroke", "var(--accent)").attr("stroke-width", 2);
    s.append("text").attr("x", x(r.tA_p95_s) - 4).attr("y", m.t + 10).attr("text-anchor", "end").attr("fill", "var(--fg-2)").attr("font-size", 10).text(`p${r.percentile}`);
  }, [r, height]);
  return <svg ref={ref} viewBox={`0 0 360 ${height}`} style={{ width: "100%", height }} aria-label="Assembly time over all runs" />;
}
