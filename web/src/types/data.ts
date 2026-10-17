import type { StopReason } from "./live";

export interface ClipRow {
  id: string;
  kind: "phrase" | "negative";
  source: "collect" | "use";
  date: string;
  created_at: string;
  duration_ms: number;
  detected_ratio: number;
  stop_reason: StopReason;
  label: string;
}

export interface ClipsPayload {
  clips: ClipRow[];
  total: number;
  dates: string[];
}

export interface CalibrationResult {
  grade: "ok" | "conditional" | "ng" | "partial";
  still_sec: number;
  threshold?: number;
  noise_p95?: number;
  speech_level?: number;
  snr?: number;
  warnings: string[];
}

export interface CalibrationState {
  running: boolean;
  phase: "still" | "speech" | null;
  remaining_sec: number | null;
  face_ratio: number | null;
  result?: CalibrationResult;
  current: { threshold: number; active_threshold: number; still_sec: number; calibrated_still_sec: number };
}
