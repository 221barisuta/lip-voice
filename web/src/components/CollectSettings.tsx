import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { SettingsPayload } from "../types/live";

interface Props {
  /** 直近 still_sec 秒間の口の動き（いまの口の動き） */
  liveRange: number;
  disabled: boolean;
}

type Key = "threshold" | "still_sec" | "max_sec";
const STEP: Record<Key, number> = { threshold: 0.001, still_sec: 0.1, max_sec: 1 };

/** 録画の終了条件。収集と認識で共通の設定で、設定ファイルに保存される。 */
export function CollectSettings({ liveRange, disabled }: Props) {
  const [p, setP] = useState<SettingsPayload | null>(null);
  useEffect(() => { api.settings<SettingsPayload>().then(setP).catch(() => undefined); }, []);
  if (!p) return null;
  const s = p.settings;
  const set = (key: Key, v: number) => {
    setP({ ...p, settings: { ...s, [key]: v } });
    api.putSettings<{ settings: SettingsPayload["settings"] }>({ [key]: v }).then((r) => setP((q) => q && { ...q, settings: r.settings })).catch(() => undefined);
  };
  const slider = (key: Key, label: string, unit: string, digits: number) => (
    <label style={{ display: "block", margin: "4px 0" }}>
      {label}:{" "}
      <input type="range" min={p.limits[key][0]} max={p.limits[key][1]} step={STEP[key]} value={s[key]}
             disabled={disabled} onChange={(e) => set(key, Number(e.target.value))} /> {s[key].toFixed(digits)} {unit}
    </label>
  );
  return (
    <details>
      <summary>録画の終了条件（閾値の調整）</summary>
      <p style={{ margin: "8px 0" }}>
        いまの口の動き: <strong>{liveRange.toFixed(3)}</strong>（{liveRange <= s.threshold ? "止まっている" : "動いている"}と判定）
      </p>
      {slider("threshold", "止まったとみなす閾値（口の開きの変動幅）", "", 3)}
      {slider("still_sec", "止まってから終了するまで", "秒", 1)}
      {slider("max_sec", "最大の録画時間", "秒", 0)}
      <p style={{ fontSize: 12, color: "#555" }}>
        口の開き = 上唇と下唇の距離 ÷ 両目尻の距離。口を閉じて静止した時の値より少し大きい値にします。
      </p>
    </details>
  );
}
