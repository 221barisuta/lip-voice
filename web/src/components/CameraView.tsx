import { api } from "../lib/api";
import type { LiveInfo } from "../types/live";

interface Props {
  live: LiveInfo;
  mouth?: string;
  frame?: string;
  recording: boolean;
  fullPreview: boolean;
  onFullPreview: (on: boolean) => void;
}

/** 送信（保存）される口元の切り出しと、カメラの状態。カメラ位置の確認用の映像は、この画面にだけ出る。 */
export function CameraView({ live, mouth, frame, recording, fullPreview, onFullPreview }: Props) {
  const status =
    live.camera === "error" ? `カメラを使えません: ${live.message}`
    : live.camera === "starting" ? "カメラ準備中…"
    : live.face_found ? "顔を検出中" : "顔が見つかりません";
  const color = live.camera === "ok" && live.face_found ? "green" : "crimson";
  const toggle = (on: boolean) => { onFullPreview(on); void api.preview(on); };
  return (
    <div style={{ display: "flex", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
      <div style={{ position: "relative" }}>
        {mouth
          ? <img alt="送信される口元" src={`data:image/jpeg;base64,${mouth}`} width={192} height={192}
                 style={{ border: "1px solid #888", imageRendering: "pixelated", opacity: live.face_found ? 1 : 0.3 }} />
          : <div style={{ width: 192, height: 192, background: "#eee" }} />}
        {recording && <span style={{ position: "absolute", top: 6, left: 6, color: "#fff", background: "#d00", padding: "2px 8px", borderRadius: 4 }}>● 録画中</span>}
      </div>
      <div>
        <p style={{ margin: "0 0 4px", color }}>{status}</p>
        <p style={{ margin: 0, fontSize: 12, color: "#555" }}>
          {live.source} ／ {live.fps} fps ／ 処理 {live.proc_ms} ms
          {live.tilt_deg != null && ` ／ 顔の傾き ${live.tilt_deg.toFixed(0)}°`}
        </p>
        <label style={{ display: "block", marginTop: 8 }}>
          <input type="checkbox" checked={fullPreview} onChange={(e) => toggle(e.target.checked)} /> カメラ位置の確認（この画面にだけ表示）
        </label>
        {fullPreview && frame && <img alt="カメラ" src={`data:image/jpeg;base64,${frame}`} width={320} style={{ marginTop: 8, borderRadius: 6 }} />}
      </div>
    </div>
  );
}
