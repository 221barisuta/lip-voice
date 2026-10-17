import type { StillnessConfig } from "./stillness";

/** 録画の終了条件の設定。収集（/collect）と認識（/speak）で共通。収集画面から変更でき、/settings ができたらそちらへ移す。 */
export type RecordingSettings = StillnessConfig;

export const DEFAULT_SETTINGS: RecordingSettings = { threshold: 0.01, stillSec: 1.0, maxSec: 10 };

export const SETTING_LIMITS = {
  threshold: { min: 0.002, max: 0.05, step: 0.001 },
  stillSec: { min: 0.5, max: 3, step: 0.1 },
  maxSec: { min: 3, max: 15, step: 1 },
} as const;

const KEY = "lipvoice.recordingSettings";

const clamp = (v: unknown, min: number, max: number, fallback: number) =>
  typeof v === "number" && Number.isFinite(v) ? Math.min(max, Math.max(min, v)) : fallback;

export function sanitize(raw: Partial<Record<keyof RecordingSettings, unknown>>): RecordingSettings {
  const L = SETTING_LIMITS;
  return {
    threshold: clamp(raw.threshold, L.threshold.min, L.threshold.max, DEFAULT_SETTINGS.threshold),
    stillSec: clamp(raw.stillSec, L.stillSec.min, L.stillSec.max, DEFAULT_SETTINGS.stillSec),
    maxSec: clamp(raw.maxSec, L.maxSec.min, L.maxSec.max, DEFAULT_SETTINGS.maxSec),
  };
}

export function loadSettings(): RecordingSettings {
  try {
    const raw = localStorage.getItem(KEY);
    return sanitize(raw ? JSON.parse(raw) : {});
  } catch {
    return DEFAULT_SETTINGS; // ブラウザの保存が使えない時も動く
  }
}

export function saveSettings(s: RecordingSettings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* 保存できなくても、その場の設定は有効 */
  }
}
