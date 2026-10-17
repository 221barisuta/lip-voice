import type { ButtonHTMLAttributes } from "react";

/** 視線・タッチでも押せる大きなボタン。 */
export function BigButton({ tone = "normal", style, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "normal" | "primary" | "danger" }) {
  const bg = tone === "primary" ? "#1a6" : tone === "danger" ? "#c33" : "#ddd";
  return (
    <button
      {...rest}
      style={{ minHeight: 64, minWidth: 140, fontSize: 24, padding: "8px 20px", margin: "6px 8px 6px 0", borderRadius: 10,
               border: "1px solid #888", background: rest.disabled ? "#eee" : bg, color: tone === "normal" || rest.disabled ? "#222" : "#fff",
               cursor: rest.disabled ? "default" : "pointer", ...style }}
    />
  );
}
