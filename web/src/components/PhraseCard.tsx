import type { CollectState } from "../types/live";

interface Props { state: CollectState; remainingSec: number | null }

export function PhraseCard({ state, remainingSec }: Props) {
  const negative = state.mode === "negative";
  const recording = state.phase === "recording";
  return (
    <div style={{ textAlign: "center", padding: "24px 0" }}>
      {negative ? (
        <div style={{ fontSize: 56, fontWeight: 700 }}>
          <span style={{ fontSize: 24, display: "block", color: "#a60" }}>フレーズではない動き（負例）</span>
          {state.negative_label}
        </div>
      ) : (
        <div style={{ fontSize: 72, fontWeight: 700 }}>{state.phrase.text}</div>
      )}
      <div style={{ height: 96, color: "#555" }}>
        {recording && (
          <>
            <div style={{ fontSize: 40 }}>録画中 <strong>残り {remainingSec ?? ""} 秒</strong></div>
            <div style={{ fontSize: 28 }}>話し終えたら口を閉じてください</div>
          </>
        )}
      </div>
    </div>
  );
}
