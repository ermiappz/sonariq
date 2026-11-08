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

// The portal is served at / (live) or /next/ (staging); the API sits next to it. The demo key lets the browser reach
// the API without the basic-auth prompt the FreeCAD panel still uses.
export const BASE = import.meta.env.BASE_URL;            // "/" or "/next/"
export const API = BASE + "api";
// hosted builds get the portal key from VITE_SQ_KEY at build time (scripts/deploy_vm.sh); local dev needs none
const KEY = (import.meta.env.VITE_SQ_KEY as string | undefined) ?? "";
export const HDR: Record<string, string> = KEY ? { "X-SonarIQ-Key": KEY } : {};
export const apiFetch = (path: string, init?: RequestInit) =>
  fetch(API + path, { ...init, headers: { ...HDR, ...(init?.headers as Record<string, string> | undefined) } });

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + path, { ...init, headers: { "Content-Type": "application/json", ...HDR } });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}
export const api = {
  resetAll: () => j<{ ok: boolean; archived: string; runs: number }>("/admin/reset", { method: "POST" }),
  model: () => j<{ bounds: number[] | null; revision: string }>("/model"),
  health: () => j<{ ok: boolean; simulate?: boolean; ai: { endpoint: string; online: boolean } }>("/health"),
  analyse: (revision: string, packs?: string[]) =>
    j<Run>("/analyse", { method: "POST", body: JSON.stringify({ revision, scope: "deck:5", packs }) }),
  finding: (id: string) => j<Check>(`/findings/${encodeURIComponent(id)}`),
  accept: (id: string, reason: string, by: string) =>
    j<Decision>(`/findings/${encodeURIComponent(id)}/accept`, { method: "POST", body: JSON.stringify({ reason, by }) }),
  history: () => j<{ history: Record<string, unknown>[]; decisions: Decision[] }>("/history"),
  rules: () => j<{ rules: Record<string, any>[] }>("/rules"),
  mapping: () => j<{ rows: Record<string, string>[] }>("/rcrv/mapping"),
  reports: () => j<{ reports: Report[] }>("/reports"),
  report: (run_id: string) => j<Report & { existing?: boolean }>("/reports", { method: "POST", body: JSON.stringify({ run_id }) }),
  tasks: () => j<{ tasks: Record<string, Task> }>("/tasks"),
  incorrect: () => j<{ incorrect: Record<string, Incorrect> }>("/incorrect"),
  markIncorrect: (body: { check_key: string; finding: string | null; reason: string; by: string; revision?: string; file?: string }) =>
    j<Incorrect>("/incorrect", { method: "POST", body: JSON.stringify(body) }),
  undoIncorrect: (key: string) => j<{ undone: boolean }>(`/incorrect/${encodeURIComponent(key)}`, { method: "DELETE" }),
  task: (key: string, body: Partial<Task>) => j<Task>(`/tasks/${encodeURIComponent(key)}`, { method: "PUT", body: JSON.stringify(body) }),
  runs: () => j<{ runs: RunMeta[] }>("/runs"),
  runGet: (id: string) => j<RunMeta & { run: Run }>(`/runs/${encodeURIComponent(id)}`),
  runDiff: (a: string, b: string) => j<RunDiff>(`/runs/diff?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),
};

export interface Report { id: string; run_id: string; time: string; file: string; revision: string; counts: Record<string, number>;
  total_checks: number; open_findings: number }
export interface Incorrect { finding: string | null; reason: string; by: string; time: string; revision?: string | null; file?: string | null }
export interface Task { column: "backlog" | "doing" | "done"; assignee: string | null }

// ---- Stored runs (every Analyse, from the panel or the portal, is kept; never overwritten)
export interface RunMeta { id: string; seq: number; time: string; file: string; revision: string; scope: string; packs: string[];
  counts: Record<string, number>; total_checks: number; source: string; scope_note?: string | null }
export interface DiffRow { id: string | null; check_key: string; rule: string; title: string; status: string; before: string | null; location: string; element: string | null }
export interface RunDiff { a: RunMeta; b: RunMeta; counts_delta: Record<string, number>; new_findings: DiffRow[]; cleared: DiffRow[];
  changed: DiffRow[]; added_checks: number; removed_checks: number }

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

// ---- Simulate (engine computes; UI only draws what the engine returns)
export interface SimScenario { case: "night" | "day"; route?: "primary" | "secondary"; closed_stair?: string | null; closed_door?: string | null; fire_origin?: string | null }
export interface SimStatus { id: string; state: string; runs_done: number; runs_target: number; elapsed_s?: number; scenario_label?: string;
  revision?: string; label: string; error?: string | null; cached?: boolean; live?: { tA_p95_s: number; tA_p50_s: number } }
export interface SimPreview { preview: { scenario: SimScenario; label: string; revision: string; runs: number; source: string }; confirm_required?: boolean }
export interface Ring { outer: number[][]; holes: number[][][] }
export interface SimGeometry { walkable: Ring | Ring[]; bounds: number[]; spaces: { name: string; category: string; poly: Ring; label_xy: number[] }[];
  walls: { name: string; rating: string | null; poly: Ring }[]; doors: { name: string; self_closing: boolean | null; rating: string | null; width: number; poly: Ring }[];
  stairs: { name: string; width: number; flight: Ring; landings: number[][]; persons_by_deck: Record<string, number> }[] }
export interface SimResults { runs: number; target_runs: number; tA_p50_s: number; tA_p95_s: number; tA_min_s: number; tA_max_s: number; tA_mean_s: number;
  deck5_last_p95_s: number; peak_density_p95: number; congestion_significant_share: number; unfinished_runs: number; people_deck5: number;
  stairs: Record<string, { last_p95_s: number; capacity_p_s: number; deck5_mean: number; inflow: number; inflow_wait_max_p95: number }>;
  landings: Record<string, { queue_max_p95: number; queue_max_mean: number; queue_max_max: number }>;
  histogram: { edges: number[]; counts: number[] }; p95_seed: number; longest_route: { space: string; length_m: number; stair: string; path: number[][] };
  scenario_label: string; revision: string; label: string; percentile: number; elapsed_s: number; replay_run?: { seed: number; tA_s: number } }
export interface SimReplay { id: string; label: string; scenario_label: string; geometry: SimGeometry; seed: number; tA_s: number; t_start_s: number;
  frames: [number, [number, number, number][]][]; queue_series: Record<string, number[]>; inflow_wait_series: Record<string, number[]>; series_t0_s: number;
  density: { cell_m: number; origin: number[]; nx: number; ny: number; peak: number[][]; over4_s: number[][] }; smoke_label: string | null;
  smoke_events?: { t: number; spaces: string[] }[]; smoke?: Record<string, number> }
export interface SimCompare { before: { id: string; label: string; revision: string; tA_p95_s: number }; after: { id: string; label: string; revision: string; tA_p95_s: number };
  delta: { tA_p95_s: number | null }; landings: Record<string, { before: number | null; after: number | null; delta: number | null }>; label: string }
export const sim = {
  preview: (body: { text?: string; scenario?: SimScenario; revision?: string; runs?: number }) =>
    j<SimPreview>("/simulate", { method: "POST", body: JSON.stringify(body) }),
  start: (body: { scenario: SimScenario; revision?: string; runs?: number }) =>
    j<SimStatus & SimPreview>("/simulate", { method: "POST", body: JSON.stringify({ ...body, confirm: true }) }),
  status: (id: string) => j<SimStatus>(`/simulate/${id}`),
  results: (id: string) => j<SimResults>(`/simulate/${id}/results`),
  replay: (id: string) => j<SimReplay>(`/simulate/${id}/replay`),
  compare: (a: string, b: string) => j<SimCompare>(`/simulate/compare?a=${a}&b=${b}`),
  list: () => j<{ results: { id: string; scenario_label: string; revision: string; runs: number; tA_p95_s: number }[] }>("/simulate"),
  explain: (id: string, q?: string) => j<{ text: string; source: string; badge: string }>(`/simulate/${id}/explain${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  hotspot: (id: string, x: number, y: number, t: number) =>
    j<{ text: string; badge: string; source: string; facts: Record<string, any> }>(`/simulate/${id}/hotspot?x=${x}&y=${y}&t=${t}`),
  pin: (id: string, body: { t: number; x: number; y: number; finding?: string; note: string; by: string }) =>
    j<{ ok: boolean; topic: string }>(`/simulate/${id}/pin`, { method: "POST", body: JSON.stringify(body) }),
};

// ---- RAG and review (engine computes; RAG never sets a verdict)
export interface SourceHit { citation: string; text: string; title: string; url: string; source: string; score?: number }
export interface Sources { finding: string; reading: SourceHit[]; public: SourceHit[]; note: string | null; links: { title: string; url: string }[]; backend: string }
export const rag = {
  sources: (id: string) => j<Sources>(`/findings/${encodeURIComponent(id)}/sources`),
  draft: (query: string) => j<{ ok: boolean; draft?: Record<string, any>; source?: SourceHit; numbers_not_in_source?: string[]; error?: string; alternatives?: SourceHit[] }>(
    "/rules/draft", { method: "POST", body: JSON.stringify({ query }) }),
  approve: (draft: Record<string, any>, by: string) => j<{ ok: boolean; path: string; note: string }>("/rules/draft/approve", { method: "POST", body: JSON.stringify({ draft, by }) }),
  review: (id: string, action: string, reason: string, by: string) =>
    j<{ finding: string; action: string; reason: string; by: string; time: string; revision: string }>(`/findings/${encodeURIComponent(id)}/review`, { method: "POST", body: JSON.stringify({ action, reason, by }) }),
};

// Findings marked "Incorrect" (by the FreeCAD panel or the browser), polled so both stay in step.
import { useEffect as _useEffect, useState as _useState } from "react";
export function useIncorrect(): [Record<string, Incorrect>, () => void] {
  const [m, setM] = _useState<Record<string, Incorrect>>({});
  const load = () => { api.incorrect().then((r) => setM(r.incorrect)).catch(() => {}); };
  _useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t); }, []);
  return [m, load];
}
