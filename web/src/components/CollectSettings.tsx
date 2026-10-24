import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { SettingsPayload } from "../types/live";

interface Props {
  /** 直近 still_sec 秒間の口の動き（いまの口の動き） */
  liveRange: number;
  disabled: boolean;
}

type Key = "threshold" | "still_sec" | "max_sec" | "session_minutes";
const STEP: Record<Key, number> = { threshold: 0.001, still_sec: 0.1, max_sec: 1, session_minutes: 1 };
type Settings = SettingsPayload["settings"];

/** 録画の終了条件（収集と認識で共通）と、試験用の設定。設定ファイルに保存される。 */
export function CollectSettings({ liveRange, disabled }: Props) {
  const [p, setP] = useState<SettingsPayload | null>(null);
  useEffect(() => { api.settings<SettingsPayload>().then(setP).catch(() => undefined); }, []);
  if (!p) return null;
  const s = p.settings;
  const put = (changes: Record<string, unknown>) => {
    setP({ ...p, settings: { ...s, ...changes } as Settings });
    api.putSettings<{ settings: Settings }>(changes).then((r) => setP((q) => q && { ...q, settings: r.settings })).catch(() => undefined);
  };
  const slider = (key: Key, label: string, unit: string, digits: number) => (
    <label style={{ display: "block", margin: "4px 0" }}>
      {label}:{" "}
      <input type="range" min={p.limits[key][0]} max={p.limits[key][1]} step={STEP[key]} value={s[key]}
             disabled={disabled} onChange={(e) => put({ [key]: Number(e.target.value) })} /> {s[key].toFixed(digits)} {unit}
    </label>
  );
  return (
    <details>
      <summary>設定（録画の終了条件・試験用）</summary>
      <p style={{ margin: "8px 0" }}>
        いまの口の動き: <strong>{liveRange.toFixed(3)}</strong>（{liveRange <= s.threshold ? "止まっている" : "動いている"}と判定）
      </p>
      {slider("threshold", "止まったとみなす閾値（口の動きの変動幅）", "", 3)}
      {slider("still_sec", "止まってから終了するまで", "秒", 1)}
      {slider("max_sec", "最大の録画時間", "秒", 0)}
      {slider("session_minutes", "1 セッションの長さ", "分", 0)}
      <p style={{ fontSize: 12, color: "#555" }}>
        口の動き = 口の開き（上唇と下唇の距離）と口の幅の、どちらか大きい方の変動幅（目尻間の距離を 1 とした値）。
        口を閉じて（楽にして）静止した時の値より少し大きい値にします。
      </p>
      <fieldset style={{ marginTop: 8 }}>
        <legend>自動学習（患者さんの PC では DTW のみ。別プロセス・低い優先度で動く）</legend>
        <label style={{ display: "block" }}>
          学習する時機:{" "}
          <select value={s.auto_train} onChange={(e) => put({ auto_train: e.target.value })}>
            <option value="nightly">毎晩（日付の切り替えの 1 時間後。新しいデータがある時だけ）</option>
            <option value="after_session">収集セッションの終了後</option>
            <option value="on_start">起動の 5 分後</option>
            <option value="off">しない（手動）</option>
          </select>
        </label>
        <label style={{ display: "block", marginTop: 4 }}>
          学習に使うデータ:{" "}
          <select value={s.train_sources} onChange={(e) => put({ train_sources: e.target.value })}>
            <option value="collect">収集したものだけ（おすすめ）</option>
            <option value="collect_use_top1">＋実使用のうち、1 位が合っていたもの</option>
            <option value="collect_use_all">＋実使用のすべて（選び間違いが混ざる）</option>
          </select>
        </label>
        <label style={{ display: "block", marginTop: 4 }}>
          新しいモデルを自動で使い始める最低の上位 3 正解率:{" "}
          <input type="number" min={0} max={100} step={5} value={Math.round(s.auto_activate_min_top3 * 100)}
                 onChange={(e) => put({ auto_activate_min_top3: Number(e.target.value) / 100 })} style={{ width: 60 }} /> %
        </label>
      </fieldset>
      <fieldset style={{ marginTop: 8 }}>
        <legend>試験用（実際の収集では、どちらも空・オフにする）</legend>
        <label style={{ display: "block" }}>
          撮影日の上書き:{" "}
          <input value={s.date_override} placeholder="例: day1" disabled={disabled} style={{ width: 90 }}
                 onChange={(e) => put({ date_override: e.target.value })} />{" "}
          {["day1", "day2", "day3"].map((d) => <button key={d} disabled={disabled} onClick={() => put({ date_override: d })}>{d}</button>)}{" "}
          <button disabled={disabled} onClick={() => put({ date_override: "" })}>実際の日付</button>
        </label>
        <label style={{ display: "block", marginTop: 4 }}>
          <input type="checkbox" checked={s.auto_save} disabled={disabled} onChange={(e) => put({ auto_save: e.target.checked })} />{" "}
          自動保存（保存できる録画は確認なしで保存して次へ進む）
        </label>
        <p style={{ fontSize: 12, color: "#555", margin: "4px 0" }}>
          撮影日の上書きは、1 日でまとめて集めても「1 日目・2 日目…」として記録するための試験用です（学習と評価は撮影日で分けます）。
        </p>
      </fieldset>
    </details>
  );
}
