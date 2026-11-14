// Demo run-through (spec B8): a scripted tour that plays by itself. Each step does something real in the Studio
// (the caller's `run`), then the caption explains it. Space or → goes to the next step now, Esc stops.
import { useEffect, useRef, useState } from "react";

export type DemoStep = { title: string; text: string; run: () => Promise<void> | void };
const DWELL = 7000;                       // ms a step stays on screen before the next one plays

export default function DemoRun({ steps, onStop }: { steps: DemoStep[]; onStop: () => void }) {
  const [i, setI] = useState(0);
  const [busy, setBusy] = useState(true);
  const [err, setErr] = useState("");
  const [paused, setPaused] = useState(false);
  const live = useRef(true);
  // drop focus from the button that started the demo, so Space steps the demo instead of pressing that button again
  useEffect(() => { live.current = true; (document.activeElement as HTMLElement | null)?.blur?.(); return () => { live.current = false; }; }, []);
  const ran = useRef(-1);                 // StrictMode runs effects twice in dev: each step's action runs once
  // run step i once; when it is done, wait DWELL and advance (unless paused or last)
  useEffect(() => {
    if (ran.current === i) return;
    ran.current = i;
    setBusy(true); setErr("");
    Promise.resolve().then(() => steps[i].run()).catch((e) => setErr(String((e as Error).message ?? e))).finally(() => { if (live.current) setBusy(false); });
  }, [i]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (busy || paused || i >= steps.length - 1) return;
    const t = window.setTimeout(() => setI((n) => Math.min(n + 1, steps.length - 1)), DWELL);
    return () => window.clearTimeout(t);
  }, [i, busy, paused]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest?.("input, textarea, select")) return;
      if (e.key === "Escape") { e.preventDefault(); onStop(); }
      else if (e.key === " " || e.key === "ArrowRight") { e.preventDefault(); if (!busy) { if (i < steps.length - 1) setI(i + 1); else onStop(); } }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [i, busy]); // eslint-disable-line react-hooks/exhaustive-deps
  const s = steps[i], last = i === steps.length - 1;
  return (
    <div className="demo-bar sq-card" role="region" aria-label="Demo run-through" aria-live="polite">
      <div className="demo-dots" aria-hidden>{steps.map((_, k) => <i key={k} className={k < i ? "is-done" : k === i ? "is-on" : ""} />)}</div>
      <div className="demo-text">
        <div className="sq-faint mono" style={{ fontSize: 11 }}>Demo · step {i + 1} of {steps.length}{busy ? " · working…" : paused ? " · paused" : ""}</div>
        <b>{s.title}</b>
        <div>{err ? <span className="studio-warn">This step did not complete: {err}</span> : s.text}</div>
      </div>
      <div className="flex gap-1 demo-actions">
        <button className="sq-btn is-sm" onClick={() => setPaused(!paused)} aria-pressed={paused}>{paused ? "Play" : "Pause"}</button>
        <button className="sq-btn is-sm is-primary" disabled={busy} onClick={() => (last ? onStop() : setI(i + 1))}>{last ? "Finish" : "Next →"}</button>
        <button className="sq-btn is-sm" onClick={onStop} aria-label="Stop demo (Esc)">Stop</button>
      </div>
    </div>
  );
}
