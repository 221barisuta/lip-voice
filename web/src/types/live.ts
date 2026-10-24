import type { Phrase } from "./phrase";

export interface LiveInfo {
  camera: "starting" | "ok" | "error";
  message: string;
  source: string;
  face_found: boolean;
  fps: number;
  proc_ms: number;
  opening: number | null;
  /** 直近 still_sec 秒間の口の動き（閾値の調整用） */
  live_range: number;
  tilt_deg: number | null;
  roll_deg: number | null;
  remaining_sec: number | null;
}

export interface Stats {
  today: number;
  total: number;
  per_phrase: Record<string, number>;
  negatives: Record<string, number>;
}

export type StopReason = "still" | "max" | "no_motion";

export interface Pending {
  duration_ms: number;
  stop_reason: StopReason;
  fps: number;
  frames: number;
  detected_ratio: number;
  savable: boolean;
  problem: string | null;
}

export interface CollectState {
  phase: "idle" | "recording" | "review" | "ended";
  mode: "phrase" | "negative";
  negative_label: string | null;
  negative_kinds: string[];
  phrase: Phrase;
  target: { kind: "phrase"; phrase: Phrase } | { kind: "negative"; label: string } | null;
  pending: Pending | null;
  session_remaining_sec: number | null;
  session_total_sec: number;
  stats: Stats;
  phrases: Phrase[];
  last_saved: { label: string; seconds: number; n: number } | null;
  date: string;
  auto_save: boolean;
  /** 続けて録るフレーズの id（指定がなければ null） */
  focus: string | null;
}

export interface Candidate {
  phrase_id: string;
  text: string;
  confidence: number;
}

export interface SpeakResult {
  no_motion?: boolean;
  stop_reason: StopReason;
  duration_ms: number;
  candidates?: Candidate[];
  rejected?: boolean;
  agree?: boolean;
  model?: "A" | "B";
  version?: string;
  distance?: number;
  latency_ms?: number;
}

export interface SpeakState {
  phase: "idle" | "recording" | "result";
  result: SpeakResult | null;
  has_model: boolean;
  model_version: string | null;
  last_choice: { phrase_id: string | null; text: string | null; negative: boolean } | null;
  phrases: Phrase[];
}

export interface Snapshot {
  live: LiveInfo;
  collect: CollectState;
  speak?: SpeakState;
  /** 口元の切り出し（96×96 JPEG の base64）。送信されるのはこれだけ */
  mouth?: string;
  /** カメラ位置の確認用の縮小映像（この PC の画面にだけ出る。既定はオフ） */
  frame?: string;
}

export interface SettingsPayload {
  settings: {
    threshold: number;
    still_sec: number;
    max_sec: number;
    session_minutes: number;
    min_detected_ratio: number;
    negative_kinds: string[];
    camera_source: string;
    date_override: string;
    auto_save: boolean;
  };
  limits: Record<string, [number, number]>;
}
