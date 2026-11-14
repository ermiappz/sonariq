// Callout card for the active finding in the 3D (spec Phase 5): title + status, Is, Must be (formula with the
// engine's numbers), clause + location, source chips, actions. Placed beside the element's screen box (never over
// it) with a leader line to the anchor; collapses to a pin when other parts hide the anchor.
import { useLayoutEffect, useRef, useState } from "react";
import type { Check } from "../api";
import { calloutContent, placeCallout, type Rect } from "../viewer/callout";
import { SourceChips } from "./Evidence";
import { Pill } from "./ui";

export type CalloutGeo = { anchor: [number, number]; rect: Rect; occluded: boolean } | null;

export default function Callout({ c, geo, view, unlocatable, actions, onClose }: {
  c: Check; geo: CalloutGeo; view: { w: number; h: number }; unlocatable: boolean;
  actions: { label: string; run: () => void; title?: string }[]; onClose: () => void;
}) {
  const card = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 320, h: 190 });
  useLayoutEffect(() => {
    const el = card.current; if (!el) return;
    const w = el.offsetWidth, h = el.offsetHeight;
    if (Math.abs(w - size.w) > 1 || Math.abs(h - size.h) > 1) setSize({ w, h });
  });
  const k = calloutContent(c);
  const free = unlocatable || !geo;           // no anchor: the card sits in the top-left corner, no leader
  if (geo?.occluded && !unlocatable) {
    return <span className="co-pin is-hidden-anchor" style={{ left: geo.anchor[0], top: geo.anchor[1] }} title={`${k.id}: hidden behind other parts. Isolate or cut to see it.`}>{k.id}</span>;
  }
  const p = free ? null : placeCallout(geo!.anchor, geo!.rect, size, view);
  return (
    <>
      {p && (
        <svg className="co-lead" width={view.w} height={view.h} aria-hidden>
          <line x1={geo!.anchor[0]} y1={geo!.anchor[1]} x2={p.lead[0]} y2={p.lead[1]} />
          <circle cx={geo!.anchor[0]} cy={geo!.anchor[1]} r={4} />
        </svg>
      )}
      <div ref={card} className={`co-card sq-card s-${c.status}`} role="dialog" aria-label={`Finding ${k.id}`}
           style={p ? { left: p.x, top: p.y } : { left: 12, top: 52 }} data-side={p?.side ?? "free"}>
        <div className="flex items-center gap-2"><Pill s={c.status} /><b className="mono">{k.id}</b><span style={{ flex: 1 }} />
          <button className="studio-link" onClick={onClose} aria-label="Close callout">×</button></div>
        <div className="co-title">{k.title}</div>
        <dl className="co-kv">
          <dt>Is</dt><dd className="mono">{k.is}</dd>
          <dt>Must be</dt><dd className="mono">{k.mustBe}{k.formula && <><br /><span className="sq-faint">{k.formula}</span></>}</dd>
        </dl>
        <div className="mono sq-faint co-where">{k.where}</div>
        <SourceChips c={c} />
        {unlocatable && <div className="co-note">Not located in the 3D: the model has no element or position for this finding.</div>}
        <div className="flex gap-1 co-actions">{actions.map((a) => <button key={a.label} className="sq-btn is-sm" title={a.title} onClick={a.run}>{a.label}</button>)}</div>
      </div>
    </>
  );
}
