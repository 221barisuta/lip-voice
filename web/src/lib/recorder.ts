import type { RecordedClip, StopReason } from "../types/clip";
import type { LandmarkFile, LandmarkFrame, Point3 } from "../types/landmarks";
import { LIP_INDICES } from "./mouthRegion";

const MIME_CANDIDATES = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];

/** 口元 canvas を webm に録画し、同じ時間の特徴点を記録する。 */
export class ClipRecorder {
  private mr: MediaRecorder;
  private chunks: Blob[] = [];
  private frames: LandmarkFrame[] = [];
  private names: string[] = [];
  private t0 = performance.now();
  private stopped: Promise<void>;

  constructor(canvas: HTMLCanvasElement) {
    const mimeType = MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m));
    if (!mimeType) throw new Error("このブラウザは webm の録画に対応していません");
    this.mr = new MediaRecorder(canvas.captureStream(30), { mimeType, videoBitsPerSecond: 800_000 });
    this.mr.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    this.stopped = new Promise((resolve) => (this.mr.onstop = () => resolve()));
    this.mr.start();
    this.t0 = performance.now();
  }

  addFrame(points: Point3[] | null, blend: number[] | null, names: string[]): void {
    if (!this.names.length && names.length) this.names = names;
    this.frames.push({ t: Math.round(performance.now() - this.t0), points, blend });
  }

  async stop(stopReason: StopReason): Promise<RecordedClip> {
    const seconds = (performance.now() - this.t0) / 1000;
    this.mr.stop();
    await this.stopped;
    const detected = this.frames.filter((f) => f.points).length;
    const file: LandmarkFile = {
      version: 1,
      lip_indices: LIP_INDICES,
      blendshape_names: this.names,
      frames: this.frames,
    };
    const video = new Blob(this.chunks, { type: "video/webm" });
    return {
      landmarks: new Blob([JSON.stringify(file)], { type: "application/json" }),
      video,
      previewUrl: URL.createObjectURL(video),
      meta: {
        fps_measured: +(this.frames.length / seconds).toFixed(1),
        frame_count: this.frames.length,
        duration_ms: Math.round(seconds * 1000),
        stop_reason: stopReason,
      },
      detectedRatio: this.frames.length ? detected / this.frames.length : 0,
      stopReason,
      durationMs: Math.round(seconds * 1000),
    };
  }
}
