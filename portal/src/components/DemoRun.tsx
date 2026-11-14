// Demo run-through (spec B8, Studio reliability step 4): a scripted tour that plays by itself and cannot get stuck.
// Every step has a precondition, a timeout and an error state ("Couldn't …: reason" with Retry and Skip step). Next,
// Pause and Stop always respond: Next and Stop abort the running step (its `signal`), so a step never keeps changing
// the Studio after the tour has moved on.
import { useEffect, useRef, useState } from "react";

export type StepCtx = {
  signal: AbortSignal;
  /** poll until ok() (every 200 ms); throws when the step is aborted or `ms` passes */
  until: (ok: () => boolean, what: string, ms?: number) => Promise<void>;
};
export type DemoStep = {
  title: string; text: string;
  /** what the step does, for the error line: "Couldn't <fail>: <reason>" */ fail: string;
  /** ms before the step counts as failed (20 s; 60 s for loading the model) */ timeout?: number;
  /** null when the step can run, else why not (shown as the error) */ pre?: () => string | null;
  run: (ctx: StepCtx) => Promise<void> | void;
};
const DWELL = 7000;                       // ms a step stays on screen before the next one plays

class Aborted extends Error {}

export default function DemoRun({ steps, onStop }: { steps: DemoStep[]; onStop: () => void }) {
  const [i, setI] = useState(0);
  const [attempt, setAttempt] = useState(0);     // Retry runs the same step again
  const [phase, setPhase] = useState<"running" | "done" | "error">("running");
  const [err, setErr] = useState("");
  const [paused, setPaused] = useState(false);
  const ctl = useRef<AbortController | null>(null);
  const last = i === steps.length - 1;
  // drop focus from the button that started the demo, so Space steps the demo instead of pressing that button again
  useEffect(() => { (document.activeElement as HTMLElement | null)?.blur?.(); return () => ctl.current?.abort(); }, []);
  useEffect(() => {
    const step = steps[i];
    const c = new AbortController();
    ctl.current?.abort();
    ctl.current = c;
    setPhase("running"); setErr("");
    const ms = step.timeout ?? 20000;
    const until = async (ok: () => boolean, what: string, max = ms) => {
      const t0 = Date.now();
      while (!ok()) {
        if (c.signal.aborted) throw new Aborted();
        if (Date.now() - t0 > max) throw new Error(`${what} did not finish within ${Math.round(max / 1000)} s`);
        await new Promise((r) => setTimeout(r, 200));
      }
    };
    let timer = 0;
    const timeout = new Promise<never>((_, no) => { timer = window.setTimeout(() => no(new Error(`no answer within ${Math.round(ms / 1000)} s`)), ms); });
    (async () => {
      const why = step.pre?.();
      if (why) throw new Error(why);
      await Promise.race([Promise.resolve().then(() => step.run({ signal: c.signal, until })), timeout]);
    })().then(() => { if (!c.signal.aborted) setPhase("done"); })
      .catch((e) => { if (c.signal.aborted || e instanceof Aborted) return; c.abort(); setErr(String((e as Error).message ?? e)); setPhase("error"); })
      .finally(() => window.clearTimeout(timer));
  }, [i, attempt]); // eslint-disable-line react-hooks/exhaustive-deps
  // plays by itself: DWELL after a step is done, unless paused, failed or last
  useEffect(() => {
    if (phase !== "done" || paused || last) return;
    const t = window.setTimeout(() => setI((n) => Math.min(n + 1, steps.length - 1)), DWELL);
    return () => window.clearTimeout(t);
  }, [phase, paused, i]); // eslint-disable-line react-hooks/exhaustive-deps
  const next = () => { ctl.current?.abort(); if (last) onStop(); else setI(i + 1); };
  const stop = () => { ctl.current?.abort(); onStop(); };
  const nextRef = useRef(next); nextRef.current = next;
  const stopRef = useRef(stop); stopRef.current = stop;
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest?.("input, textarea, select")) return;
      if (e.key === "Escape") { e.preventDefault(); stopRef.current(); }
      else if (e.key === " " || e.key === "ArrowRight") { e.preventDefault(); nextRef.current(); }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const s = steps[i];
  return (
    <div className="demo-bar sq-card" role="region" aria-label="Demo run-through" aria-live="polite" data-phase={phase}>
      <div className="demo-dots" aria-hidden>{steps.map((_, k) => <i key={k} className={k < i ? "is-done" : k === i ? "is-on" : ""} />)}</div>
      <div className="demo-text">
        <div className="sq-faint mono" style={{ fontSize: 11 }}>Demo · step {i + 1} of {steps.length}{phase === "running" ? " · working…" : phase === "error" ? " · needs you" : paused ? " · paused" : ""}</div>
        <b>{s.title}</b>
        {phase === "error"
          ? <div className="demo-err" role="alert"><span>Couldn't {s.fail}: {err}</span>
              <span className="flex gap-1"><button className="sq-btn is-sm" onClick={() => setAttempt((n) => n + 1)}>Retry</button>
                <button className="sq-btn is-sm" onClick={next}>{last ? "Finish" : "Skip step"}</button></span></div>
          : <div>{s.text}</div>}
      </div>
      <div className="flex gap-1 demo-actions">
        <button className="sq-btn is-sm" onClick={() => setPaused(!paused)} aria-pressed={paused}>{paused ? "Play" : "Pause"}</button>
        <button className="sq-btn is-sm is-primary" onClick={next}>{last ? "Finish" : "Next →"}</button>
        <button className="sq-btn is-sm" onClick={stop} aria-label="Stop demo (Esc)">Stop</button>
      </div>
    </div>
  );
}
