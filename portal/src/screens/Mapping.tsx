// W5 Import mapping review, fed by data/rcrv/mapping_review.csv. Nothing unmapped is guessed.
import { useEffect, useState } from "react";
import { api } from "../api";

export default function Mapping() {
  const [rows, setRows] = useState<Record<string, string>[]>([]);
  useEffect(() => { api.mapping().then((r) => setRows(r.rows)); }, []);
  return (
    <div className="flex flex-col gap-4">
      <h1 className="sq-h1">Import mapping review · RCRV</h1>
      <p className="sq-muted" style={{ margin: 0 }}>Navisworks layer / item → IFC class → deck, frame, side, MVZ, SOLAS category, berths. Showing the first {rows.length} rows that need a person. Unmapped items stay out of the checks and report Cannot verify.</p>
      <table className="sq-table">
        <thead><tr><th>Status</th><th>Source item</th><th>Layer</th><th>File</th><th>IFC class</th><th>Deck</th><th>Side</th><th>Note</th></tr></thead>
        <tbody>{rows.slice(0, 300).map((r) => (
          <tr key={r.source_id}>
            <td><span className={`sq-pill ${r.status === "Unmapped" ? "s-unk" : "s-warn"}`}><i className="sq-ico" />{r.status}</span></td>
            <td>{r.name}</td><td className="sq-muted">{r.layer}</td><td className="sq-faint" style={{ fontSize: 12 }}>{r.source_file}</td>
            <td className="mono">{r.ifc_class || "—"}</td><td>{r.deck}</td><td>{r.side}</td><td className="sq-faint" style={{ fontSize: 12 }}>{r.note}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
