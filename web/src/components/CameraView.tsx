import { useEffect, useRef, type RefObject } from "react";
import type { CameraStatus } from "../lib/useMouthCamera";

interface Props {
  videoRef: RefObject<HTMLVideoElement>;
  cropCanvas: HTMLCanvasElement;
  status: CameraStatus;
  error: string;
  faceFound: boolean;
  recording: boolean;
}

/** カメラ映像（この端末の画面にだけ表示）と、送信される口元の切り出しのプレビュー。 */
export function CameraView({ videoRef, cropCanvas, status, error, faceFound, recording }: Props) {
  const mirror = useRef<HTMLCanvasElement>(null);

  // 切り出しの様子を小さく見せる（送信されるのはこの 96×96 だけ）
  useEffect(() => {
    const ctx = mirror.current?.getContext("2d");
    let raf = 0;
    const tick = () => {
      raf = requestAnimationFrame(tick);
      ctx?.drawImage(cropCanvas, 0, 0);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, [cropCanvas]);

  return (
    <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
      <div style={{ position: "relative" }}>
        <video ref={videoRef} muted playsInline style={{ width: 360, borderRadius: 8, transform: "scaleX(-1)", background: "#000" }} />
        {recording && <span style={{ position: "absolute", top: 8, left: 8, color: "#fff", background: "#d00", padding: "2px 8px", borderRadius: 4 }}>● 録画中</span>}
      </div>
      <div>
        <canvas ref={mirror} width={96} height={96} style={{ width: 96, height: 96, border: "1px solid #888" }} />
        <p style={{ margin: "4px 0", fontSize: 12 }}>送信される口元</p>
        <p style={{ margin: 0, color: faceFound ? "green" : "crimson" }}>
          {status === "starting" && "カメラ準備中…"}
          {status === "error" && `カメラを使えません: ${error}`}
          {status === "ready" && (faceFound ? "顔を検出中" : "顔が見つかりません")}
        </p>
      </div>
    </div>
  );
}
