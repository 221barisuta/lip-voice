export interface Rate {
  k: number;
  n: number;
  rate: number | null;
}

export interface Metrics {
  top1: Rate;
  top3: Rate;
  per_phrase: Record<string, { n: number; top1: number; top3: number; top1_rate: number; top3_rate: number }>;
  confusion: Record<string, Record<string, number>>;
  mistakes: { clip_id: string; date: string; true: string; top3: string[] }[];
}

export interface Judge {
  value: number | null;
  need: number;
  ok: boolean;
}

export interface ModelResult {
  lodo: Metrics;
  last_day: Metrics | null;
  tau: number;
  tau_note: string;
  rejection: { conf: number; auto_rate: Rate; wrong_rate: Rate; neg_accept: Rate }[];
  by_day: Record<string, Metrics | null>;
}

export interface Report {
  created_at: string;
  version: string;
  active: "A" | "B";
  dates: string[];
  classes: string[];
  n_pos: number;
  n_neg: number;
  counts_by_day: Record<string, number>;
  negatives_by_label: Record<string, number>;
  evaluated: boolean;
  note?: string;
  results: Record<string, ModelResult>;
  latency_ms: { mean: number; p95: number };
  judgement?: { lodo: Record<string, Judge>; last_day: Record<string, Judge> | null };
}

export interface ReportPayload {
  report: Report | null;
  real_use: { date: string; n: number; top1: number; top3: number; rejected: number }[];
  models: { versions: string[]; active: string | null };
}
