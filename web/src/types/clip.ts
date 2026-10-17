/** still: 口が止まって終了 / max: 最大秒数で終了 / no_motion: 口の動きが検出されないまま最大秒数に達した */
export type StopReason = "still" | "max" | "no_motion";

export interface ClipMeta {
  phrase_id: string;
  session_id: string;
  source: "collect" | "use";
  fps_measured: number;
  frame_count: number;
  duration_ms: number;
  stop_reason: StopReason;
}

export interface RecordedClip {
  landmarks: Blob;
  video: Blob;
  /** 口元動画の再生確認用 URL（ローカルのみ。送信しない） */
  previewUrl: string;
  meta: Omit<ClipMeta, "phrase_id" | "session_id" | "source">;
  /** 顔が検出できたフレームの割合 0〜1 */
  detectedRatio: number;
  stopReason: StopReason;
  durationMs: number;
}

export interface ClipStats {
  today: number;
  per_phrase: Record<string, number>;
}
