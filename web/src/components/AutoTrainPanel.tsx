import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { AutoTrainState } from "../types/report";
import { BigButton } from "./BigButton";

const when = (iso?: string) => (iso ? iso.replace("T", " ").slice(0, 16) : "—");

/** 自動学習の状態。使わなかった新しい版は、理由と「この版を使う」を出す。「今すぐ学習し直す」で手動の実行。 */
export function AutoTrainPanel({ auto, pending, active, onChanged }: {
  auto: AutoTrainState | null; pending: { version: string; reason: string | null } | null; active: string | null; onChanged: () => void;
}) {
  const [error, setError] = useState("");
  useEffect(() => {
    if (!auto?.running) return;
    const t = setInterval(onChanged, 3000);
    return () => clearInterval(t);
  }, [auto?.running, onChanged]);
  if (!auto) return null;
  const run = () => { setError(""); api.autoTrainRun().then(onChanged).catch((e) => setError(String(e.message ?? e))); };
  return (
    <section style={{ border: "1px solid #aaa", borderRadius: 8, padding: "8px 16px", margin: "12px 0" }}>
      <h3 style={{ margin: "4px 0" }}>自動学習</h3>
      <p style={{ margin: "4px 0" }}>
        {auto.running ? "学習中です…（数秒〜数分）" : `最後の実行: ${when(auto.last_run_at)}`}
        {!auto.running && auto.version && <>　新しい版: {auto.version}（{auto.activated ? "使っています" : "使っていません"}）</>}
      </p>
      {auto.reason && <p style={{ margin: "4px 0", color: auto.activated ? "#161" : "#a60" }}>{auto.reason}</p>}
      {auto.error && <p role="alert" style={{ margin: "4px 0", color: "crimson" }}>{auto.error}</p>}
      {pending && pending.version !== active && (
        <p style={{ margin: "4px 0" }}>
          <BigButton style={{ minHeight: 40, fontSize: 16 }} onClick={() => api.activateModel(pending.version).then(onChanged).catch((e) => setError(String(e.message ?? e)))}>
            新しい版（{pending.version}）を使う
          </BigButton>
          <span style={{ fontSize: 14 }}>自動では切り替えていません。評価の数字を確認してから選んでください。</span>
        </p>
      )}
      <BigButton style={{ minHeight: 40, fontSize: 16 }} onClick={run} disabled={auto.running}>今すぐ学習し直す</BigButton>
      {error && <span role="alert" style={{ color: "crimson" }}> {error}</span>}
    </section>
  );
}
