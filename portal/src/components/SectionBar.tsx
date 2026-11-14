// Section blade (spec A3): position, then cut. Cross section by frame, longitudinal by offset from CL, deck plan by
// height or deck. Drag the blade, wheel over it, arrow keys (one frame or 0.1 m; Shift = 10), slider or number field.
// Nothing is clipped until Cut; then the near side goes, the camera eases to face the cut and the cut faces are capped.
// Up to 3 cuts; each chip re-opens its cut for nudge + re-cut, flip, or clear.
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../api";
import type { ShipViewer } from "../viewer/ShipViewer";
import { KIND_LABEL, PLAN_HEIGHT, chip, clampTo, deckBelow, frameAt, nearSideFlip, range, readout, snap, step, xOfFrame,
  type Box, type Cut, type CutKind, type DeckLevel, type Grid } from "../viewer/section";

const KINDS: CutKind[] = ["cross", "long", "deck"];

export default function SectionBar({ v, modelId, decks, onClose }: { v: ShipViewer; modelId: string | null; decks: DeckLevel[]; onClose: () => void }) {
  const box = v.index.box as Box;
  const [grid, setGrid] = useState<Grid>(v.grid);
  const [cuts, setCuts] = useState<Cut[]>(v.cuts);
  const [active, setActive] = useState<number | null>(v.cuts.length ? v.cuts.length - 1 : null);
  const first = v.cuts[v.cuts.length - 1];
  const [kind, setKind] = useState<CutKind>(first?.kind ?? "cross");
  const [pos, setPos] = useState<number>(first?.pos ?? defaultPos("cross", v.grid, decks, box));
  const [gridEdit, setGridEdit] = useState<{ f0: string; sp: string } | null>(null);
  const live = useRef({ kind, pos, grid });
  live.current = { kind, pos, grid };

  // the viewer is the source of truth for applied cuts (named views and "Section at finding" set them too)
  useEffect(() => {
    const sync = () => {
      setCuts([...v.cuts]);
      setActive((a) => (v.cuts.length ? (a !== null && a < v.cuts.length ? a : v.cuts.length - 1) : null));
    };
    const prev = v.onView;
    v.onView = () => { prev?.(); sync(); };
    v.onBladeDrag = (p) => setPos(clampTo(live.current.kind, snap(live.current.kind, p, live.current.grid), box));
    v.onBladeWheel = (dir, big) => setPos((p) => step(live.current.kind, p, dir, live.current.grid, box, big));
    return () => { v.onView = prev; v.onBladeDrag = null; v.onBladeWheel = null; v.setBlade(null); };
  }, [v]); // eslint-disable-line react-hooks/exhaustive-deps
  // a cut set from outside (Section at finding, a named view) becomes the one being edited
  const ckey = cuts.map((c) => `${c.kind}${c.pos}${c.flip}`).join("|");
  useEffect(() => { if (active !== null && cuts[active]) { setKind(cuts[active].kind); setPos(cuts[active].pos); } }, [ckey, active]); // eslint-disable-line react-hooks/exhaustive-deps

  const applied = active !== null ? cuts[active] : null;
  const moved = !applied || applied.kind !== kind || Math.abs(applied.pos - pos) > 1e-6;
  // the blade shows while positioning; on an applied, unmoved cut it would only tint the cap
  useEffect(() => { v.setBlade(moved ? { kind, pos, flip: applied?.flip ?? false } : null); }, [kind, pos, moved]); // eslint-disable-line react-hooks/exhaustive-deps

  const ro = readout(kind, pos, grid, decks, box);
  const [lo, hi] = range(kind, box);
  const nudge = (dir: 1 | -1, big: boolean) => setPos((p) => step(kind, p, dir, grid, box, big));
  const apply = (next: Cut[], face: Cut | null) => { v.setCuts(next); setCuts([...v.cuts]); if (face) v.faceCut(face); };

  const doCut = () => {
    if (applied) {                                   // nudge and re-cut: same side kept, camera stays
      const c = { ...applied, kind, pos, flip: applied.kind === kind ? applied.flip : nearSideFlip(kind, pos, v.camera.position.toArray()) };
      apply(cuts.map((x, i) => (i === active ? c : x)), applied.kind === kind ? null : c);
      return;
    }
    if (cuts.length >= 3) return;
    const c: Cut = { kind, pos, flip: nearSideFlip(kind, pos, v.camera.position.toArray()) };
    apply([...cuts, c], c);
    setActive(cuts.length);
  };
  const flip = () => { if (!applied) return; const c = { ...applied, flip: !applied.flip }; apply(cuts.map((x, i) => (i === active ? c : x)), c); };
  const sectionView = () => { if (!applied) return; v.setProjection("orthographic"); v.faceCut(applied); };
  const clear = (i: number) => { const next = cuts.filter((_, k) => k !== i); apply(next, null); setActive(next.length ? next.length - 1 : null); };
  const add = () => { if (cuts.length < 3) setActive(null); };
  const setKindTo = (k: CutKind) => { setKind(k); setPos(applied?.kind === k ? applied.pos : defaultPos(k, grid, decks, box)); };

  const onKey = (e: React.KeyboardEvent) => {
    const t = e.target as HTMLElement;
    if (t.tagName === "INPUT" && (t as HTMLInputElement).type !== "range") return;   // number fields step themselves
    if (t.tagName === "SELECT") return;
    if (["ArrowRight", "ArrowUp"].includes(e.key)) { e.preventDefault(); nudge(1, e.shiftKey); }
    else if (["ArrowLeft", "ArrowDown"].includes(e.key)) { e.preventDefault(); nudge(-1, e.shiftKey); }
    else if (e.key === "Enter" && t.tagName !== "BUTTON") { e.preventDefault(); doCut(); }
  };
  const field = kind === "cross" ? Math.round(frameAt(pos, grid)) : Math.round(pos * 100) / 100;
  const setField = (x: number) => { if (!Number.isFinite(x)) return; setPos(clampTo(kind, kind === "cross" ? xOfFrame(Math.round(x), grid) : snap(kind, x, grid), box)); };
  const saveGrid = async () => {
    if (!gridEdit || !modelId) return;
    const r = await apiFetch(`/models/${modelId}/grid`, { method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame0_x: Number(gridEdit.f0), spacing_m: Number(gridEdit.sp) }) });
    if (!r.ok) return;
    const g = await r.json();
    v.grid = g; setGrid(g); setGridEdit(null);
    if (kind === "cross") setPos((p) => snap("cross", p, g));
  };

  return (
    <div className="sec-bar sq-card" role="group" aria-label="Section blade" onKeyDown={onKey}
         onWheel={(e) => { if ((e.target as HTMLElement).tagName !== "SELECT") nudge(e.deltaY < 0 ? 1 : -1, e.shiftKey); }}>
      <div className="sec-row">
        <div className="sq-seg" role="radiogroup" aria-label="Cut type">
          {KINDS.map((k) => <button key={k} role="radio" aria-checked={kind === k} className={kind === k ? "is-on" : ""} onClick={() => setKindTo(k)}>{KIND_LABEL[k]}</button>)}
        </div>
        {kind === "deck" && decks.length > 0 && (
          <select className="sq-input sec-deck" aria-label="Deck" value={deckBelow(pos, decks)?.deck ?? ""}
                  onChange={(e) => { const d = decks.find((x) => x.deck === Number(e.target.value)); if (d) setPos(clampTo("deck", snap("deck", d.z + PLAN_HEIGHT, grid), box)); }}>
            {deckBelow(pos, decks) === null && <option value="">below deck {decks[0].deck}</option>}
            {decks.map((d) => <option key={d.deck} value={d.deck}>Deck {d.deck} + {PLAN_HEIGHT} m</option>)}
          </select>)}
        <span className="sec-readout" aria-live="polite"><b className="mono">{ro.main}</b> <span className="mono sq-faint">{ro.sub}</span></span>
        <span style={{ flex: 1 }} />
        {cuts.map((c, i) => (
          <span key={i} className={`sec-chip${i === active ? " is-on" : ""}`}>
            <button className="studio-link" onClick={() => setActive(i)} title={`Edit cut ${i + 1}`}>{i + 1} · {chip(c, grid, decks, box)}</button>
            <button className="studio-link" onClick={() => clear(i)} aria-label={`Clear cut ${i + 1}`}>×</button>
          </span>))}
        <button className="studio-link" onClick={onClose} aria-label="Close section blade">×</button>
      </div>
      <div className="sec-row">
        <input type="range" className="sec-slider" aria-label="Section position" aria-valuetext={ro.main}
               min={lo} max={hi} step="any" value={pos} onChange={(e) => setPos(clampTo(kind, snap(kind, Number(e.target.value), grid), box))} />
        <label className="sec-field">{kind === "cross" ? "Fr" : kind === "long" ? "y (+PS) m" : "z m"}
          <input type="number" className="sq-input mono" aria-label={kind === "cross" ? "Frame number" : "Position in metres"}
                 step={kind === "cross" ? 1 : 0.1} value={field} onChange={(e) => setField(Number(e.target.value))} /></label>
        <button className="sq-btn is-sm is-primary" onClick={doCut} disabled={(!applied && cuts.length >= 3) || (!!applied && !moved)}
                title={applied ? "Move the cut here" : "Remove the near side and cap the cut faces"}>{applied ? "Re-cut" : "Cut"}</button>
        <button className="sq-btn is-sm" onClick={flip} disabled={!applied} title="Keep the other side">Flip</button>
        <button className="sq-btn is-sm" onClick={sectionView} disabled={!applied} title="Orthographic, facing the cut">Section view</button>
        <button className="sq-btn is-sm" onClick={() => active !== null && clear(active)} disabled={!applied}>Clear cut</button>
        <button className="sq-btn is-sm" onClick={add} disabled={!applied || cuts.length >= 3} title="Up to three cuts">Add cut</button>
      </div>
      <div className="sec-note sq-faint">
        Caps on structure and architecture; other disciplines show section outlines (their meshes are not closed solids).{" "}
        {gridEdit === null
          ? <button className="studio-link" onClick={() => setGridEdit({ f0: String(grid.frame0_x), sp: String(grid.spacing_m) })}
                    title={grid.source ?? ""}>Frames: Fr 0 at x {grid.frame0_x.toFixed(2)} m, {grid.spacing_m} m spacing ({grid.source?.startsWith("user") ? "set by you" : grid.source?.split(":")[0] ?? "default"})</button>
          : <span className="sec-grid">Fr 0 at x <input className="sq-input mono" aria-label="Frame zero x" value={gridEdit.f0} onChange={(e) => setGridEdit({ ...gridEdit, f0: e.target.value })} /> m,
              spacing <input className="sq-input mono" aria-label="Frame spacing" value={gridEdit.sp} onChange={(e) => setGridEdit({ ...gridEdit, sp: e.target.value })} /> m
              <button className="sq-btn is-sm" onClick={saveGrid}>Save</button><button className="studio-link" onClick={() => setGridEdit(null)}>Cancel</button></span>}
      </div>
    </div>
  );
}

function defaultPos(k: CutKind, g: Grid, decks: DeckLevel[], box: Box): number {
  if (k === "deck" && decks.length) { const d = decks[Math.floor((decks.length - 1) / 2)]; return clampTo("deck", snap("deck", d.z + PLAN_HEIGHT, g), box); }
  if (k === "long") return 0;
  const [lo, hi] = range(k, box);
  return clampTo(k, snap(k, (lo + hi) / 2, g), box);
}
