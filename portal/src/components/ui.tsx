import type { Check, Status } from "../api";
import { WORD } from "../api";

export function Pill({ s, lg }: { s: Status; lg?: boolean }) {
  return <span className={`sq-pill s-${s}${lg ? " is-lg" : ""}`}><i className="sq-ico" />{WORD[s]}</span>;
}
export function Loc({ text }: { text: string }) {
  return <span className="sq-chip loc">{text}</span>;
}
export function RuleBadge({ c }: { c: Pick<Check, "source" | "clause" | "to_verify"> }) {
  const src = c.source.startsWith("SOLAS") ? "SOLAS" : c.source;
  return (
    <span className={`sq-rule${c.source === "PVAG" ? " is-draft" : ""}`}>
      <b>{src}</b><span>{c.clause}{c.to_verify ? " · to verify" : ""}</span>
    </span>
  );
}
export function Engine() {
  return <span className="sq-engine">Rule engine</span>;
}
