// 2D vector replay: SVG ship (DeckPlan) + Canvas people (2 Hz samples interpolated at 60 fps, small neutral dots)
// + optional density heatmap (one sequential ramp, p/m²). d3 draws scales, timeline, histogram and queue chart.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import * as d3 from "d3";
import type { SimReplay, SimResults } from "../api";
import DeckPlan, { viewBox } from "./DeckPlan";

// One sequential ramp (accent tint, as design 10), binned like the design legend; p/m².
export const BINS = [0.5, 1, 2, 3.5];
export const BIN_LABELS = ["<0.5", "0.5–1", "1–2", "2–3.5", ">3.5"];
const ALPHA = [0, 0.22, 0.42, 0.65, 0.9];
export function heatColor(v: number, accent: string) {
  let b = 0; while (b < BINS.length && v >= BINS[b]) b++;
  return { a: ALPHA[b], c: accent };
}
export function mmss(s: number | null | undefined) {
  if (s == null || isNaN(s)) return "—";
  const m = Math.floor(s / 60), r = Math.round(s - m * 60);
  return `${String(m).padStart(2, "0")}:${String(r === 60 ? 0 : r).padStart(2, "0")}`;
}

type Frame = SimReplay["frames"][number];
const BY_ID = new WeakMap<object, Map<number, Frame[1][number]>>();

function positionsAt(frames: Frame[], t: number): [number, number, number, number][] {
  if (!frames.length) return [];
  let lo = 0, hi = frames.length - 1;
  if (t <= frames[0][0]) return frames[0][1].map((p) => [p[0], p[1], p[2], 1]);
  if (t >= frames[hi][0]) return frames[hi][1].map((p) => [p[0], p[1], p[2], 0]);
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (frames[m][0] <= t) lo = m; else hi = m; }
  const [ta, a] = frames[lo], [tb, b] = frames[hi];
  const f = (t - ta) / (tb - ta);
  let nb = BY_ID.get(b);
  if (!nb) { nb = new Map(b.map((p) => [p[0], p])); BY_ID.set(b, nb); }   // built once per frame sample, not per paint
  const out: [number, number, number, number][] = [];
  const dt = tb - ta;
  for (const p of a) {
    const q = nb.get(p[0]);
    const v = q ? Math.hypot(q[1] - p[1], q[2] - p[2]) / dt : 0;   // m/s between samples: < 0.15 = waiting
    out.push(q ? [p[0], p[1] + (q[1] - p[1]) * f, p[2] + (q[2] - p[2]) * f, v] : [p[0], p[1], p[2], 0]);
  }
  return out;
}

export function useClock(t0: number, t1: number, autoplay: boolean | number = false) {
  // autoplay: start playing as soon as the replay is loaded (a truthy value that becomes true once data is in)
  const [t, setT] = useState(t0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(10);
  useEffect(() => { setT(t0); }, [t0]);
  useEffect(() => { if (autoplay) setPlaying(true); }, [autoplay]);
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

export function Controls({ clock, t0, t1, events = [], extra, synced }:
  { clock: ReturnType<typeof useClock>; t0: number; t1: number; events?: { label: string; t_s: number }[]; extra?: ReactNode; synced?: boolean }) {
  const pct = (t: number) => `${(100 * (t - t0)) / Math.max(1, t1 - t0)}%`;
  return (
    <div className="sq-card" style={{ padding: "8px 10px" }}>
      <div className="flex items-center gap-2">
        <button className="sq-btn" onClick={() => { if (clock.t >= t1) clock.setT(t0); clock.setPlaying(!clock.playing); }} aria-label={clock.playing ? "Pause" : "Play"}>
          {clock.playing ? "❚❚" : "▶"}</button>
        {synced && <span className="sq-tag">Synced</span>}
        <span className="mono sq-faint" style={{ fontSize: 12 }}>{mmss(clock.t)} / {mmss(t1)}</span>
        <div style={{ flex: 1, position: "relative", height: 22 }}>
          <input type="range" min={t0} max={t1} step={0.5} value={clock.t} onChange={(e) => clock.setT(+e.target.value)} style={{ width: "100%", position: "absolute", top: 3 }} aria-label="Time" />
          {events.filter((e) => e.t_s >= t0 && e.t_s <= t1).map((e) => <span key={e.label} title={`${e.label} · ${mmss(e.t_s)}`} onClick={() => clock.setT(e.t_s)}
            style={{ position: "absolute", left: pct(e.t_s), top: 0, width: 1, height: 22, borderLeft: "1px dashed var(--fg-3)", cursor: "pointer" }} />)}
        </div>
        <div className="sq-seg">{[1, 10].map((s) => <button key={s} className={clock.speed === s ? "is-on" : ""} onClick={() => clock.setSpeed(s)}>×{s}</button>)}</div>
        {extra}
      </div>
      {events.length > 0 && <div className="flex gap-4 sq-faint" style={{ fontSize: 11, paddingLeft: 40, flexWrap: "wrap" }}>
        {events.map((e) => <a key={e.label} href="#" onClick={(ev) => { ev.preventDefault(); clock.setT(e.t_s); }} style={{ color: "inherit" }}>{e.label} · {mmss(e.t_s)}</a>)}</div>}
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
  // The heatmap and the canvas size change rarely: paint them once into a layer, then each frame only blits it and
  // draws the dots (the replay ticks at 60 fps).
  const layer = useMemo(() => {
    const c = cv.current; if (!c) return null;
    const dpr = window.devicePixelRatio || 1;
    c.width = size.w * dpr; c.height = size.h * dpr;
    const css = getComputedStyle(c);
    const ink = css.getPropertyValue("--fg-1").trim() || "#eee";
    if (!heat) return { dpr, ink, bg: null as HTMLCanvasElement | null };
    const bg = document.createElement("canvas"); bg.width = c.width; bg.height = c.height;
    const ctx = bg.getContext("2d")!; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const d = rep.density, cs = d.cell_m, accent = css.getPropertyValue("--accent").trim() || "#e392c8";
    ctx.fillStyle = accent;
    for (let j = 0; j < d.ny; j++) for (let i = 0; i < d.nx; i++) {
      const v = d.peak[j][i]; const h = heatColor(v, accent); if (!h.a) continue;
      ctx.globalAlpha = h.a * 0.6;
      const x = d.origin[0] + i * cs, y = d.origin[1] + j * cs;
      ctx.fillRect(map.X(x), map.Y(y + cs), cs * map.s + 0.5, cs * map.s + 0.5);
    }
    return { dpr, ink, bg };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rep, heat, size, map, cv.current]);
  useEffect(() => {
    const c = cv.current; if (!c || !layer) return;
    const ctx = c.getContext("2d")!;
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, c.width, c.height);
    if (layer.bg) ctx.drawImage(layer.bg, 0, 0);
    ctx.setTransform(layer.dpr, 0, 0, layer.dpr, 0, 0);
    const r = Math.max(1.6, 0.2 * map.s);
    ctx.fillStyle = layer.ink; ctx.strokeStyle = layer.ink; ctx.lineWidth = 1.2;
    const moving = new Path2D(), waiting = new Path2D();
    for (const p of positionsAt(rep.frames, t)) {
      const x = map.X(p[1]), y = map.Y(p[2]), path = p[3] < 0.15 ? waiting : moving;
      path.moveTo(x + r, y); path.arc(x, y, r, 0, Math.PI * 2);
    }
    ctx.fill(moving); ctx.stroke(waiting);
  }, [rep, t, layer, map]);
  const smokeKey = (smoke ?? []).join(",");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const plan = useMemo(() => <DeckPlan g={rep.geometry} smoke={smoke} route={route} />, [rep.geometry, smokeKey, route]);
  return (
    <div ref={wrap} style={{ position: "relative", height, border: "1px solid var(--line)", borderRadius: "var(--r)", overflow: "hidden" }}>
      {plan}
      <canvas ref={cv} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", cursor: onPick ? "crosshair" : "default", willChange: "transform" }}
              onClick={(e) => { if (!onPick) return; const b = (e.target as HTMLCanvasElement).getBoundingClientRect(); const [x, y] = map.inv(e.clientX - b.left, e.clientY - b.top); onPick(x, y); }} />
      {heat && <HeatLegend />}
    </div>
  );
}

function HeatLegend() {
  return (
    <div style={{ position: "absolute", left: 8, bottom: 8, background: "var(--bg-1)", border: "1px solid var(--line)", padding: "4px 6px", fontSize: 10.5 }}>
      <div className="sq-faint">Peak density · heatmap at 60 %</div>
      <div style={{ display: "flex", gap: 2, marginTop: 3 }}>{BIN_LABELS.map((l, i) => (
        <div key={l} style={{ textAlign: "center" }}><div style={{ width: 34, height: 8, background: "var(--accent)", opacity: Math.max(0.06, ALPHA[i]) }} /><span className="mono">{l}</span></div>))}</div>
      <div className="sq-faint">p/m² · peak over the run</div>
    </div>
  );
}

export function QueueChart({ rep, t, height = 140, only }: { rep: SimReplay; t: number; height?: number; only?: string }) {
  const ref = useRef<SVGSVGElement>(null);
  const keys = Object.keys(rep.queue_series).filter((k) => !only || k.startsWith(only));
  const n = Math.max(...keys.map((k) => rep.queue_series[k].length), 1);
  const w = 360, m = { l: 28, r: 34, t: 8, b: 22 };
  const x = d3.scaleLinear().domain([rep.series_t0_s, rep.series_t0_s + n]).range([m.l, w - m.r]);
  const ymax = Math.max(4, ...keys.flatMap((k) => rep.queue_series[k]));
  const y = d3.scaleLinear().domain([0, ymax]).nice().range([height - m.b, m.t]);
  useEffect(() => {
    const s = d3.select(ref.current!); s.selectAll("*").remove();
    s.append("g").attr("transform", `translate(0,${height - m.b})`).call(d3.axisBottom(x).ticks(4).tickFormat((d) => mmss(+d))).attr("color", "var(--fg-3)");
    s.append("g").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4)).attr("color", "var(--fg-3)");
    const line = d3.line<number>().x((_, i) => x(rep.series_t0_s + i)).y((v) => y(v));
    const dash = ["", "4 2", "1 2", "6 2 1 2", "8 3", "2 4"];
    keys.forEach((k, i) => {
      const ser = rep.queue_series[k];
      s.append("path").datum(ser).attr("d", line).attr("fill", "none").attr("stroke", "var(--fg-1)").attr("stroke-width", 1.4).attr("stroke-dasharray", dash[i % dash.length]);
      s.append("text").attr("x", w - m.r + 4).attr("y", y(ser[Math.floor(ser.length * 0.15)] ?? 0)).attr("fill", "var(--fg-2)").attr("font-size", 10).text(k);
    });
  }, [rep, only]);
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
    s.append("g").attr("transform", `translate(0,${height - m.b})`).call(d3.axisBottom(x).ticks(4).tickFormat((d) => mmss(+d))).attr("color", "var(--fg-3)");
    s.append("g").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(3)).attr("color", "var(--fg-3)");
    s.selectAll("rect").data(c).join("rect").attr("x", (_, i) => x(e[i]) + 0.5).attr("width", (_, i) => Math.max(1, x(e[i + 1]) - x(e[i]) - 1))
      .attr("y", (v) => y(v)).attr("height", (v) => height - m.b - y(v)).attr("fill", "var(--fg-3)");
    s.append("line").attr("x1", x(r.tA_p95_s)).attr("x2", x(r.tA_p95_s)).attr("y1", m.t).attr("y2", height - m.b).attr("stroke", "var(--accent)").attr("stroke-width", 2);
    s.append("text").attr("x", x(r.tA_p95_s) - 4).attr("y", m.t + 10).attr("text-anchor", "end").attr("fill", "var(--fg-2)").attr("font-size", 10).text(`p${r.percentile}`);
  }, [r, height]);
  return <svg ref={ref} viewBox={`0 0 360 ${height}`} style={{ width: "100%", height }} aria-label="Assembly time over all runs" />;
}
