// Thin client for the SonarIQ engine (vite proxies /api -> http://127.0.0.1:8765). The UI never computes a verdict.
export type Status = "fail" | "warn" | "unk" | "pass" | "dor" | "na" | "acc";
export interface Val { value: number | string | boolean | null; unit: string; op?: string; alt?: { value: number; unit: string } }
export interface Check {
  id: string | null; check_key: string; rule: string; title: string; source: string; clause: string; ref: string;
  clause_text: string; reading: string; rule_status: string; to_verify: boolean; pack: string; group: string;
  discipline: string; discipline_label: string; status: Status; status_word: string; glyph: string;
  element: { guid: string; name: string; ifc_class: string } | null;
  location: { deck: string | null; frame: string | null; side: string | null; label: string };
  required: Val | null; measured: Val | null; margin: Val | null; summary: string;
  formula: { text: string; worked: string; inputs: { name: string; deck: string; value: number; weight: number; source: string }[] } | null;
  method: string; missing: string[]; revision: string; decision?: Decision;
  evidence?: { guids: string[]; bbox: number[] | null; z: number | null };
}
export interface Decision { finding: string; kind: string; reason: string; by: string; to: string; time: string; revision: string; approved: boolean }
export interface Run {
  revision: string; total_checks: number; duration_s: number; counts: Record<string, number>;
  by_group: Record<string, { label: string; checks: number; counts: Record<string, number>; pack_status: string; short: string }>;
  findings: Check[]; checks: Check[]; not_applicable: { rule: string; title: string; ref: string; reason: string }[];
}

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch("/api" + path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}
export const api = {
  model: () => j<{ bounds: number[] | null; revision: string }>("/model"),
  health: () => j<{ ok: boolean; ai: { endpoint: string; online: boolean } }>("/health"),
  analyse: (revision: string, packs?: string[]) =>
    j<Run>("/analyse", { method: "POST", body: JSON.stringify({ revision, scope: "deck:5", packs }) }),
  finding: (id: string) => j<Check>(`/findings/${encodeURIComponent(id)}`),
  accept: (id: string, reason: string, by: string) =>
    j<Decision>(`/findings/${encodeURIComponent(id)}/accept`, { method: "POST", body: JSON.stringify({ reason, by }) }),
  history: () => j<{ history: Record<string, unknown>[]; decisions: Decision[] }>("/history"),
  rules: () => j<{ rules: Record<string, any>[] }>("/rules"),
  mapping: () => j<{ rows: Record<string, string>[] }>("/rcrv/mapping"),
  ifcUrl: (rev: string) => `/api/model/ifc/${rev}`,
};

export const WORD: Record<Status, string> = { fail: "Fail", warn: "Warning", unk: "Cannot verify", pass: "Pass", dor: "Dormant", na: "Not applicable", acc: "Accepted with reason" };
export const ORDER: Status[] = ["fail", "warn", "unk", "pass", "dor"];

export function fmt(v: Val | null | undefined, units: "mm" | "in" = "mm"): string {
  if (!v || v.value === null || v.value === undefined) return "—";
  const x = v.value;
  if (typeof x === "number" && v.unit === "mm") return units === "in" ? `${(x / 25.4).toFixed(1)} in` : `${x.toLocaleString("en-US")} mm`;
  if (typeof x === "number" && v.unit === "in") return units === "mm" && v.alt ? `${v.alt.value.toLocaleString("en-US")} mm` : `${x} in`;
  if (typeof x === "boolean") return x ? "yes" : "no";
  return `${x}${v.unit && !["class", "bool", ""].includes(v.unit) ? " " + v.unit : ""}`;
}
