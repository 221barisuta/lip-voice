import { useCallback, useEffect, useRef, useState } from "react";
import type { RecordedClip } from "../types/clip";
import { getLandmarker } from "./landmarker";
import { MouthCropper } from "./mouthCrop";
import { mouthGeometry } from "./mouthRegion";
import { normalizeMouth } from "./normalize";
import { ClipRecorder } from "./recorder";

export type CameraStatus = "starting" | "ready" | "error";

/**
 * カメラ映像を読み、顔検出 → 特徴点の正規化 → 口元の切り出しを毎フレーム行う。
 * 映像はこのブラウザの中だけで処理し、送信するのは record() の結果（口元動画と特徴点）だけ。
 */
export function useMouthCamera(enabled: boolean) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const cropper = useRef<MouthCropper>();
  const recorder = useRef<ClipRecorder | null>(null);
  const [status, setStatus] = useState<CameraStatus>("starting");
  const [error, setError] = useState("");
  const [faceFound, setFaceFound] = useState(false);
  cropper.current ??= new MouthCropper();

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let stream: MediaStream | null = null;
    let raf = 0;
    let lastTime = -1;
    let lastFound = false;

    (async () => {
      try {
        const [landmarker, s] = await Promise.all([
          getLandmarker(),
          navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
            audio: false, // 声は扱わない
          }),
        ]);
        stream = s;
        const video = videoRef.current!;
        video.srcObject = s;
        await video.play();
        if (!alive) return;
        setStatus("ready");

        const loop = () => {
          raf = requestAnimationFrame(loop);
          if (video.readyState < 2 || video.currentTime === lastTime) return;
          lastTime = video.currentTime;
          const w = video.videoWidth, h = video.videoHeight;
          const res = landmarker.detectForVideo(video, performance.now());
          const lm = res.faceLandmarks[0];
          const cats = res.faceBlendshapes?.[0]?.categories ?? [];
          cropper.current!.draw(video, lm ? mouthGeometry(lm, w, h) : null);
          recorder.current?.addFrame(
            lm ? normalizeMouth(lm, w, h) : null,
            lm ? cats.map((c) => c.score) : null,
            cats.map((c) => c.categoryName),
          );
          if (!!lm !== lastFound) setFaceFound((lastFound = !!lm));
        };
        loop();
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
        setStatus("error");
      }
    })();

    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((t) => t.stop());
      cropper.current!.reset();
    };
  }, [enabled]);

  /** durationMs の間録画して、口元動画と特徴点を返す。 */
  const record = useCallback(async (durationMs: number): Promise<RecordedClip> => {
    const r = new ClipRecorder(cropper.current!.canvas);
    recorder.current = r;
    await new Promise((resolve) => setTimeout(resolve, durationMs));
    recorder.current = null;
    return r.stop();
  }, []);

  return { videoRef, cropCanvas: cropper.current.canvas, status, error, faceFound, record };
}
