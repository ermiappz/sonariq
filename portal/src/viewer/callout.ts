// Rendered rule callouts (spec Phase 5 / A5), the reusable part: what a callout says (content), where it sits on
// screen (placement) and which numbers it may show (guard). No DOM, no three.js: ShipView projects the anchor and
// draws the card (components/Callout.tsx); e2e and the unit test use these functions directly.
import type { Check, Val } from "../api";

export type CalloutContent = {
  id: string; title: string; status: string;
  is: string; mustBe: string; formula: string | null;
  where: string;                      // clause ref · location
};
export type Rect = { x0: number; y0: number; x1: number; y1: number };
export type Placed = { x: number; y: number; side: "right" | "left" | "above" | "below" | "corner"; lead: [number, number] };

const OP: Record<string, string> = { ">=": "at least", "<=": "at most", ">": "more than", "<": "less than", "=": "" };
const num = (v: number) => v.toLocaleString("en-US");
export function fmtVal(v: Val | null | undefined): string {
  if (!v || v.value === null || v.value === undefined) return "";
  const u = v.unit && !["class", "bool"].includes(v.unit) ? ` ${v.unit}` : "";
  return `${typeof v.value === "number" ? num(v.value) : String(v.value)}${u}`;
}

/** Engine values only: every number on the card is a number of the finding JSON (see numbersOk). */
export function calloutContent(c: Check): CalloutContent {
  const m = c.measured, r = c.required, ms = fmtVal(m), rq = fmtVal(r);
  const name = c.element?.name ?? "";
  let is: string, mustBe: string;
  if (c.status === "unk") is = `not in the model: ${(c.missing ?? []).join(", ") || "data missing"}`;
  else if (c.extra?.dead_end) is = `dead end ${ms} deep`;
  else if (m?.unit === "class") is = `${name} rated ${ms || "without a fire class"}`.trim();
  else if (m?.unit === "mm") is = `clear width ${ms}${name ? ` · ${name}` : ""}`;
  else is = ms ? `${ms}${name ? ` · ${name}` : ""}` : c.summary;
  if (!r || r.value === null || r.value === undefined) mustBe = "no requirement value (see clause)";
  else if (c.extra?.dead_end) mustBe = `at most as deep as it is wide: ${rq}`;
  else if (r.op === "present") mustBe = `${rq} present`;
  else mustBe = `${OP[r.op ?? ""] ?? r.op ?? ""} ${rq}${r.alt ? ` (${num(r.alt.value)} ${r.alt.unit})` : ""}`.trim();
  return {
    id: c.id ?? c.check_key, title: c.title, status: c.status, is, mustBe,
    formula: c.formula?.worked ?? null,
    where: [c.ref || `${c.source} ${c.clause}`, c.location?.label].filter(Boolean).join(" · "),
  };
}

const NUM = /\d[\d,]*(?:\.\d+)?/g;
const nums = (s: string) => (s.match(NUM) ?? []).map((x) => Number(x.replace(/,/g, ""))).filter((x) => !Number.isNaN(x));
/** Numbers on the card that the finding JSON does not contain (empty = the card only repeats engine numbers). */
export function strayNumbers(c: Check, text: string): number[] {
  const known = new Set(nums(JSON.stringify(c)));
  return nums(text).filter((x) => !known.has(x));
}
export const calloutText = (k: CalloutContent) => [k.id, k.title, k.is, k.mustBe, k.formula ?? "", k.where].join("\n");

/** Card position: beside the element's screen box, never over it, inside the view; leader ends on the card edge. */
export function placeCallout(anchor: [number, number], avoid: Rect, size: { w: number; h: number }, view: { w: number; h: number }, gap = 28, pad = 8): Placed {
  const { w, h } = size;
  const cy = Math.min(Math.max(anchor[1] - h / 2, pad), view.h - h - pad), cx = Math.min(Math.max(anchor[0] - w / 2, pad), view.w - w - pad);
  const cand: [Placed["side"], number, number][] = [
    ["right", avoid.x1 + gap, cy], ["left", avoid.x0 - gap - w, cy], ["above", cx, avoid.y0 - gap - h], ["below", cx, avoid.y1 + gap]];
  const fits = (x: number, y: number) => x >= pad && y >= pad && x + w <= view.w - pad && y + h <= view.h - pad;
  const hit = (x: number, y: number) => x < avoid.x1 && x + w > avoid.x0 && y < avoid.y1 && y + h > avoid.y0;
  let best: [Placed["side"], number, number] | undefined = cand.find(([, x, y]) => fits(x, y) && !hit(x, y));
  // element fills the view: the corner farthest from the anchor
  if (!best) best = ["corner", anchor[0] > view.w / 2 ? pad : view.w - w - pad, anchor[1] > view.h / 2 ? pad : view.h - h - pad];
  const [side, x, y] = best;
  const lead: [number, number] = [Math.min(Math.max(anchor[0], x), x + w), Math.min(Math.max(anchor[1], y), y + h)];
  return { x, y, side, lead };
}
