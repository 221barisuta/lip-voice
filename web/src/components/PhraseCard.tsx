import type { Phase } from "../lib/useCollect";

interface Props { text: string; phase: Phase; count: number }

export function PhraseCard({ text, phase, count }: Props) {
  return (
    <div style={{ textAlign: "center", padding: "24px 0" }}>
      <div style={{ fontSize: 72, fontWeight: 700 }}>{text}</div>
      <div style={{ fontSize: 64, height: 80, color: "#555" }}>
        {phase === "countdown" && count}
        {phase === "recording" && "口パク！"}
      </div>
    </div>
  );
}
