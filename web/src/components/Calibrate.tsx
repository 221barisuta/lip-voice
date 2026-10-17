import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { CalibrationState } from "../types/data";
import { BigButton } from "./BigButton";

const GRADE = {
  ok: ["合格", "#161"],
  conditional: ["条件付き（調整して測り直すと安定します）", "#a60"],
  ng: ["要対応", "#b22"],
  partial: ["静止だけ測定済み（続けて口パクを測ってください）", "#555"],
} as const;

/** 閾値の校正。口を閉じて静止 → フレーズを口パク → 候補を確認して反映（家族が操作する）。 */
export function Calibrate({ disabled }: { disabled: boolean }) {
  const [st, setSt] = useState<CalibrationState | null>(null);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const refresh = () => api.calibration().then(setSt).catch(() => undefined);
  useEffect(() => { refresh(); }, []);
  useEffect(() => {
    if (!st?.running) return;
    const t = setInterval(refresh, 500);
    return () => clearInterval(t);
  }, [st?.running]);

  const run = (phase: "still" | "speech") => () => {
    setError(""); setDone("");
    api.calibrateStart(phase).then(refresh).catch((e) => setError(String(e.message ?? e)));
  };
  const apply = () => api.calibrateApply().then(() => { setDone("反映しました"); refresh(); }).catch((e) => setError(String(e.message ?? e)));
  const r = st?.result;
  const stale = st && st.current.calibrated_still_sec > 0 && st.current.calibrated_still_sec !== st.current.still_sec;

  return (
    <details>
      <summary>校正（閾値の自動提案）</summary>
      <p style={{ margin: "8px 0" }}>
        患者さんの口の動きの大きさに合わせて、録画の終了条件の閾値を決めます。いつもの姿勢・カメラの位置・明るさで測ってください。
        {st && (st.current.calibrated_still_sec > 0
          ? ` 現在の閾値 ${st.current.threshold}（校正済み）`
          : ` 現在の閾値 ${st.current.threshold}（未校正）`)}
      </p>
      {stale && <p style={{ color: "#a60" }}>「止まってから終了するまで」を変えたので、もう一度校正してください。</p>}
      <BigButton onClick={run("still")} disabled={disabled || st?.running}>① 静止を測る（5 秒）</BigButton>
      <BigButton onClick={run("speech")} disabled={disabled || st?.running || !r}>② 口パクを測る（10 秒）</BigButton>
      {st?.running && (
        <p style={{ fontSize: 22 }}>
          {st.phase === "still" ? "口を閉じて、楽にして静止してください" : "フレーズを 3 回、ふだんどおり口パクしてください"}
          （あと {st.remaining_sec ?? "…"} 秒）
        </p>
      )}
      {r && !st?.running && (
        <div style={{ fontSize: 18 }}>
          <p style={{ color: GRADE[r.grade][1], fontWeight: "bold" }}>判定: {GRADE[r.grade][0]}</p>
          {r.noise_p95 !== undefined && <p>静止時の口の動き（ノイズ）: {r.noise_p95}　閾値の候補: <strong>{r.threshold}</strong></p>}
          {r.snr !== undefined && <p>口パク時の動き: {r.speech_level}　SNR（動き ÷ ノイズ）: {r.snr}（3 以上で合格）</p>}
          {st?.face_ratio !== null && st?.face_ratio !== undefined && st.face_ratio < 0.9 &&
            <p style={{ color: "#b22" }}>静止の測定中、顔を検出できた割合は {Math.round(st.face_ratio * 100)}% でした。カメラの位置・明るさを見直してください。</p>}
          {r.warnings.map((w) => <p key={w} style={{ color: "#b22" }}>注意: {w}</p>)}
          {r.threshold !== undefined && <BigButton tone="primary" onClick={apply} disabled={disabled}>この閾値を反映する</BigButton>}
          {done && <span style={{ color: "#161", fontSize: 20 }}> {done}</span>}
        </div>
      )}
      {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
    </details>
  );
}
