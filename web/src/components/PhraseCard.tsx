import type { Phase } from "../lib/useCollect";

interface Props { text: string; phase: Phase; remainingSec: number | null }

export function PhraseCard({ text, phase, remainingSec }: Props) {
  const recording = phase === "recording";
  return (
    <div style={{ textAlign: "center", padding: "24px 0" }}>
      <div style={{ fontSize: 72, fontWeight: 700 }}>{text}</div>
      <div style={{ height: 96, color: "#555" }}>
        {recording && (
          <>
            <div style={{ fontSize: 40 }}>
              録画中 <strong>残り {remainingSec ?? ""} 秒</strong>
            </div>
            <div style={{ fontSize: 28 }}>話し終えたら口を閉じてください</div>
          </>
        )}
      </div>
    </div>
  );
}
