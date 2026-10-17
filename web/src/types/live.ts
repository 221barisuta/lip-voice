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
}

export interface Snapshot {
  live: LiveInfo;
  collect: CollectState;
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
  };
  limits: Record<string, [number, number]>;
}
