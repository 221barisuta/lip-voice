import { SETTING_LIMITS, type CollectSettings as Settings } from "../lib/collectSettings";

interface Props {
  value: Settings;
  onChange: (next: Settings) => void;
  /** 直近 stillSec 秒間の口の開きの変動幅（いまの口の動き） */
  liveRange: number;
  disabled: boolean;
}

/** 録画の終了条件。いまの口の動きを見ながら、閾値を調整できる。 */
export function CollectSettings({ value, onChange, liveRange, disabled }: Props) {
  const L = SETTING_LIMITS;
  const still = liveRange <= value.threshold;
  const slider = (key: keyof Settings, label: string, unit: string, digits: number) => (
    <label style={{ display: "block", margin: "4px 0" }}>
      {label}:{" "}
      <input
        type="range"
        min={L[key].min}
        max={L[key].max}
        step={L[key].step}
        value={value[key]}
        disabled={disabled}
        onChange={(e) => onChange({ ...value, [key]: Number(e.target.value) })}
      />{" "}
      {value[key].toFixed(digits)} {unit}
    </label>
  );
  return (
    <details>
      <summary>録画の終了条件（閾値の調整）</summary>
      <p style={{ margin: "8px 0" }}>
        いまの口の動き: <strong>{liveRange.toFixed(3)}</strong>（{still ? "止まっている" : "動いている"}と判定）
      </p>
      {slider("threshold", "止まったとみなす閾値（口の開きの変動幅）", "", 3)}
      {slider("stillSec", "止まってから終了するまで", "秒", 1)}
      {slider("maxSec", "最大の録画時間", "秒", 0)}
      <p style={{ fontSize: 12, color: "#555" }}>
        口の開き = 上唇と下唇の距離 ÷ 両目尻の距離。口を閉じて静止した時の値より少し大きい値にします。
      </p>
    </details>
  );
}
