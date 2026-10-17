import { useCallback, useEffect, useRef, useState } from "react";
import type { RecordedClip, StopReason } from "../types/clip";
import { getLandmarker } from "./landmarker";
import { MouthCropper } from "./mouthCrop";
import { mouthGeometry, mouthOpening } from "./mouthRegion";
import { normalizeMouth } from "./normalize";
import { ClipRecorder } from "./recorder";
import { StillnessDetector, type StillnessConfig } from "./stillness";

export type CameraStatus = "starting" | "ready" | "error";

interface ActiveRecording {
  rec: ClipRecorder;
  det: StillnessDetector;
  cfg: StillnessConfig;
  t0: number;
  finish: (reason: StopReason) => void;
}

/**
 * カメラ映像を読み、顔検出 → 特徴点の正規化 → 口元の切り出しを毎フレーム行う。
 * 映像はこのブラウザの中だけで処理し、送信するのは record() の結果（口元動画と特徴点）だけ。
 * stillSec は、録画前でも「いまの口の動き」を表示するための窓（秒）。
 */
export function useMouthCamera(enabled: boolean, stillSec: number) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const cropper = useRef<MouthCropper>();
  const active = useRef<ActiveRecording | null>(null);
  const liveCfg = useRef<StillnessConfig>({ threshold: Infinity, stillSec, maxSec: Infinity });
  const live = useRef<StillnessDetector>();
  const [status, setStatus] = useState<CameraStatus>("starting");
  const [error, setError] = useState("");
  const [faceFound, setFaceFound] = useState(false);
  const [remainingSec, setRemainingSec] = useState<number | null>(null);
  const [liveRange, setLiveRange] = useState(0);
  cropper.current ??= new MouthCropper();
  liveCfg.current.stillSec = stillSec;
  live.current ??= new StillnessDetector(liveCfg.current);

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let stream: MediaStream | null = null;
    let raf = 0;
    let lastTime = -1;
    let lastFound = false;
    let lastShown = 0;

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
          const now = performance.now();
          const w = video.videoWidth, h = video.videoHeight;
          const res = landmarker.detectForVideo(video, now);
          const lm = res.faceLandmarks[0];
          const cats = res.faceBlendshapes?.[0]?.categories ?? [];
          cropper.current!.draw(video, lm ? mouthGeometry(lm, w, h) : null);
          const opening = lm ? mouthOpening(lm, w, h) : null;

          // 録画していない間も「いまの口の動き」を測る（閾値の調整用の表示）
          live.current!.push(now / 1000, opening);
          if (now - lastShown > 200) {
            lastShown = now;
            setLiveRange(live.current!.range);
          }

          const a = active.current;
          if (a) {
            const t = (now - a.t0) / 1000;
            a.rec.addFrame(
              lm ? normalizeMouth(lm, w, h) : null,
              lm ? cats.map((c) => c.score) : null,
              cats.map((c) => c.categoryName),
            );
            setRemainingSec(Math.max(0, Math.ceil(a.cfg.maxSec - t)));
            const reason = a.det.push(t, opening);
            if (reason) a.finish(reason);
          }
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

  /**
   * 録画を始め、口が止まって cfg.stillSec 秒経つか cfg.maxSec 秒で終えて、
   * 口元動画と特徴点（可変長）を返す。
   */
  const record = useCallback(
    (cfg: StillnessConfig) =>
      new Promise<RecordedClip>((resolve, reject) => {
        let rec: ClipRecorder;
        try {
          rec = new ClipRecorder(cropper.current!.canvas);
        } catch (e) {
          reject(e);
          return;
        }
        const det = new StillnessDetector(cfg);
        let done = false;
        const finish = (reason: StopReason) => {
          if (done) return;
          done = true;
          clearTimeout(timer);
          active.current = null;
          setRemainingSec(null);
          rec.stop(reason).then(resolve, reject);
        };
        // フレームが来なくなっても（顔を見失う・タブが裏に回る）最大秒数で必ず終える
        const timer = setTimeout(() => finish(det.hasMoved ? "max" : "no_motion"), cfg.maxSec * 1000 + 100);
        active.current = { rec, det, cfg, t0: performance.now(), finish };
        setRemainingSec(Math.ceil(cfg.maxSec));
      }),
    [],
  );

  return { videoRef, cropCanvas: cropper.current.canvas, status, error, faceFound, remainingSec, liveRange, record };
}
