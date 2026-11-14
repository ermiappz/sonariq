// View pane (spec A4, DECISIONS M8): display mode, disciplines (show / hide / solo) and colour by. It only changes how
// the model is drawn; the findings and their numbers stay the engine's.
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../api";
import type { DisplayMode, ShipViewer } from "../viewer/ShipViewer";

const MODES: [DisplayMode, string, string][] = [
  ["shaded", "Shaded", "Flat-lit faces"], ["edges", "Shaded + edges", "Faces with element outlines (default)"],
  ["realistic", "Realistic", "Softer light from above"], ["xray", "X-ray", "Everything see-through with outlines"],
  ["lines", "Lines", "Outlines only, hidden lines removed"], ["wireframe", "Wireframe", "Every triangle edge"]];
export const DISC_LABEL: Record<string, string> = { structure: "Structure", architecture: "Architecture / outfitting", hvac: "HVAC", piping: "Piping",
  electrical: "Electrical", fire: "Fire safety", equipment: "Equipment", other: "Other" };
type ColourBy = "discipline" | "model" | "fire" | "status" | "deck" | "swbs";
const COLOUR: [ColourBy, string][] = [["discipline", "Discipline"], ["model", "Model colours"], ["fire", "Fire class of boundaries"],
  ["status", "Finding status"], ["deck", "Deck"], ["swbs", "SWBS group"]];
const FIRE: [RegExp, [number, number, number], string][] = [[/^A-?60/i, [213, 94, 0], "A-60"], [/^A-?(30|15)/i, [230, 159, 0], "A-30 / A-15"],
  [/^A-?0/i, [240, 228, 66], "A-0"], [/^B/i, [86, 180, 233], "B-class"], [/^C/i, [0, 158, 115], "C-class"]];
const SERIES: [number, number, number][] = [[86, 180, 233], [230, 159, 0], [0, 158, 115], [240, 228, 66], [0, 114, 178], [213, 94, 0], [204, 121, 167], [160, 160, 160]];
const NEUTRAL: [number, number, number] = [120, 124, 132];

export default function ViewPane({ v, modelId }: { v: ShipViewer | null; modelId: string | null }) {
  const [mode, setMode] = useState<DisplayMode>(v?.mode ?? "edges");
  const [off, setOff] = useState<Set<number>>(new Set(v?.discOff ?? []));
  const [solo, setSolo] = useState<number | null>(v?.solo ?? null);
  const [by, setBy] = useState<ColourBy>("discipline");
  const [legend, setLegend] = useState<[string, [number, number, number]][]>([]);
  const counts = useMemo(() => {
    const c: Record<number, number> = {};
    if (v) for (let i = 0; i < v.disc.length; i++) if (v.base[i * 4 + 3] > 0) c[v.disc[i]] = (c[v.disc[i]] ?? 0) + 1;
    return c;
  }, [v]);
  const groups = (v?.index?.groups ?? []).map((g, k) => [g, k] as const).filter(([g, k]) => g !== "spaces" && counts[k]);

  useEffect(() => { if (v) v.setMode(mode); }, [v, mode]);
  useEffect(() => { if (!v) return; v.discOff = new Set(off); v.solo = solo; v.compose(); }, [v, off, solo]);
  useEffect(() => {
    if (!v) return;
    let live = true;
    const col = async (f: string) => modelId ? (await apiFetch(`/models/${modelId}/column/${f}`)).json() as Promise<(string | null)[]> : [];
    (async () => {
      if (by === "discipline") { v.setColourBy({ kind: "discipline" }); setLegend(groups.map(([g, k]) => [DISC_LABEL[g] ?? g, v.discRgb[k]])); return; }
      if (by === "model") { v.setColourBy({ kind: "model" }); setLegend([]); return; }
      if (by === "status") { v.setColourBy({ kind: "values", rgb: () => NEUTRAL }); setLegend([["Fail", [213, 94, 0]], ["Warning", [230, 159, 0]], ["Cannot verify", [201, 205, 212]], ["No finding", NEUTRAL]]); return; }
      if (by === "deck") {
        const decks = [...new Set(Array.from(v.deckOf))].sort((a, b) => a - b);
        const c = (d: number) => SERIES[decks.indexOf(d) % SERIES.length];
        v.setColourBy({ kind: "values", rgb: (i) => c(v.deckOf[i]) }); setLegend(decks.map((d) => [`Deck ${d}`, c(d)])); return;
      }
      const vals = await col(by === "fire" ? "fire_rating" : "swbs");
      if (!live) return;
      if (by === "fire") {
        const rgb = vals.map((x) => (x ? FIRE.find(([re]) => re.test(x))?.[1] ?? NEUTRAL : NEUTRAL));
        v.setColourBy({ kind: "values", rgb: (i) => rgb[i] }); setLegend([...FIRE.map(([, c, l]) => [l, c] as [string, [number, number, number]]), ["No fire rating", NEUTRAL]]);
      } else {
        const g = [...new Set(vals.map((x) => x?.[0]).filter(Boolean) as string[])].sort();
        const rgb = vals.map((x) => (x ? SERIES[g.indexOf(x[0]) % SERIES.length] : NEUTRAL));
        v.setColourBy({ kind: "values", rgb: (i) => rgb[i] }); setLegend([...g.map((d) => [`SWBS ${d}xx`, SERIES[g.indexOf(d) % SERIES.length]] as [string, [number, number, number]]), ["No SWBS", NEUTRAL]]);
      }
    })();
    return () => { live = false; };
  }, [v, by, modelId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!v) return <p className="sq-muted" style={{ padding: 12 }}>Open a model to change how it is drawn.</p>;
  const rgb = (c: [number, number, number]) => `rgb(${c.join(",")})`;
  return (
    <div className="vp">
      <section><div className="sq-label">Display</div>
        <div className="vp-modes" role="radiogroup" aria-label="Display mode">
          {MODES.map(([k, l, d]) => <button key={k} role="radio" aria-checked={mode === k} className={`vp-mode${mode === k ? " is-on" : ""}`} title={d} onClick={() => setMode(k)}>{l}</button>)}
        </div></section>
      <section><div className="sq-label">Disciplines</div>
        {groups.map(([g, k]) => (
          <div key={g} className={`vp-disc${solo === k ? " is-solo" : ""}`}>
            <label><input type="checkbox" checked={!off.has(k)} onChange={(e) => setOff((s) => { const n = new Set(s); if (e.target.checked) n.delete(k); else n.add(k); return n; })} />
              <i style={{ background: rgb(v.discRgb[k] ?? NEUTRAL) }} />{DISC_LABEL[g] ?? g}</label>
            <span className="mono sq-faint">{(counts[k] ?? 0).toLocaleString("en-US")}</span>
            <button className="sq-btn is-sm" aria-pressed={solo === k} onClick={() => setSolo(solo === k ? null : k)}>{solo === k ? "Unsolo" : "Solo"}</button>
          </div>))}
        <div className="sq-faint" style={{ fontSize: 11 }}>Solo draws that discipline solid and the rest as x-ray.</div>
      </section>
      <section><div className="sq-label">Colour by</div>
        <select className="sq-input" aria-label="Colour by" value={by} onChange={(e) => setBy(e.target.value as ColourBy)}>
          {COLOUR.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        {legend.length > 0 && <div className="vp-legend">{legend.map(([l, c]) => <span key={l}><i style={{ background: rgb(c) }} />{l}</span>)}</div>}
      </section>
    </div>
  );
}
