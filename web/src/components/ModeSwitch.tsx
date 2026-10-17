import { api } from "../lib/api";
import type { CollectState } from "../types/live";

/** フレーズの収集と、フレーズではない動き（負例）の収集を切り替える。 */
export function ModeSwitch({ state, disabled, onError }: { state: CollectState; disabled: boolean; onError: (m: string) => void }) {
  const go = (mode: "phrase" | "negative", label?: string) => api.setMode(mode, label).catch((e) => onError(String(e.message)));
  return (
    <div style={{ margin: "8px 0" }}>
      <button disabled={disabled || state.mode === "phrase"} onClick={() => go("phrase")}>フレーズ</button>{" "}
      <button disabled={disabled || state.mode === "negative"} onClick={() => go("negative", state.negative_kinds[0])}>
        フレーズではない動き（負例）
      </button>{" "}
      {state.mode === "negative" && (
        <select value={state.negative_label ?? ""} disabled={disabled} onChange={(e) => go("negative", e.target.value)}>
          {state.negative_kinds.map((k) => <option key={k}>{k}</option>)}
        </select>
      )}
    </div>
  );
}
