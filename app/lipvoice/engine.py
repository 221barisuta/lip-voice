"""カメラ → 顔検出 → 口の開き・切り出し → 録画、を回し続けるスレッド。

映像はこの PC の中だけで処理する。外に出るのは保存した口元の切り出しと特徴点だけ。
"""
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from .capture import open_source
from .collect import CollectSession, StateError
from .recording.controller import RecordingController
from .settings import Settings
from .vision.crop import MouthCropper
from .vision.geometry import Landmarks, mouth_geometry, mouth_opening
from .vision.landmarker import FaceDetector
from .vision.stillness import StillnessConfig, StillnessDetector


@dataclass
class LiveState:
    camera: str = "starting"          # starting | ok | error
    message: str = ""
    source: str = ""
    face_found: bool = False
    fps: float = 0.0
    proc_ms: float = 0.0
    opening: float | None = None
    live_range: float = 0.0           # 直近 still_sec 秒間の口の動き（閾値の調整用）
    remaining_sec: float | None = None
    seq: int = 0                      # フレームが進むたびに増える
    mouth_jpeg: bytes | None = None
    frame_jpeg: bytes | None = None
    delegate: str = "CPU"
    extra: dict = field(default_factory=dict)


class Engine:
    def __init__(self, model_file: Path, settings_fn, collect: CollectSession, detector_factory=FaceDetector,
                 source_factory=open_source):
        self._model_file, self._settings, self._collect = model_file, settings_fn, collect
        self._det_factory, self._src_factory = detector_factory, source_factory
        self._lock = threading.Lock()
        self._live = LiveState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._controller: RecordingController | None = None
        self._want_full_preview = False
        self._start_flag = False
        self._pending_cfg: StillnessConfig | None = None

    # ---- 外からの操作 ----
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="engine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def snapshot(self) -> LiveState:
        with self._lock:
            return LiveState(**{**self._live.__dict__})

    def set_full_preview(self, on: bool) -> None:
        self._want_full_preview = on

    def request_start(self) -> dict:
        with self._lock:
            ok, face = self._live.camera == "ok", self._live.face_found
        if not ok:
            raise StateError("カメラが使えません")
        if not face:
            raise StateError("顔が検出できていません。カメラの正面に顔を向けてください")
        target = self._collect.begin()
        s = self._settings()
        self._controller = None                      # 録画はエンジンのスレッドが次のフレームで始める
        self._pending_cfg = StillnessConfig(s.threshold, s.still_sec, s.max_sec)
        self._start_flag = True
        return target

    # ---- スレッド本体 ----
    def _set(self, **kw) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(self._live, k, v)

    def _run(self) -> None:
        detector = source = None
        cropper = MouthCropper()
        s = self._settings()
        live_cfg = StillnessConfig(float("inf"), s.still_sec, float("inf"))
        live = StillnessDetector(live_cfg)
        fails, ema_dt, ema_proc, last_t, last_range_t = 0, 0.033, 0.0, None, 0.0
        n = 0
        while not self._stop.is_set():
            s = self._settings()
            live_cfg.still_sec = s.still_sec
            try:
                if detector is None:
                    if not self._model_file.exists():
                        raise OSError(f"モデルがありません。lipvoice fetch-models を実行してください（{self._model_file}）")
                    detector = self._det_factory(self._model_file)
                if source is None:
                    source = self._src_factory(s)
                    self._set(camera="ok", message="", source=source.description)
                    fails = 0
            except Exception as e:
                self._set(camera="error", message=str(e), face_found=False)
                self._abort_recording()
                time.sleep(2.0)
                continue

            frame = source.read()
            if frame is None:
                fails += 1
                if fails > 30:                       # 抜かれた・スリープ復帰などで死んだカメラは開き直す
                    source.close()
                    source = None
                    self._set(camera="error", message="カメラから映像が来ません。接続を確認しています", face_found=False)
                    self._abort_recording()
                    time.sleep(1.0)
                time.sleep(0.01)
                continue
            fails = 0
            t_start = time.perf_counter()
            h, w = frame.image.shape[:2]
            det = detector.detect(frame.image, frame.t * 1000)
            geom = opening = None
            if det is not None:
                lm = Landmarks(det.points)
                geom = mouth_geometry(lm, w, h)
                opening = mouth_opening(lm, w, h)
            cropper.update(geom)
            crop = cropper.crop(frame.image)
            live.push(frame.t, opening)

            if self._start_flag:                     # API からの録画開始の要求
                self._start_flag = False
                self._controller = RecordingController(self._pending_cfg, w, h, list(detector.blend_names), t0=frame.t)
            ctl = self._controller
            remaining = None
            if ctl is not None:
                reason = ctl.add(frame.t, det, opening, crop) or ctl.timed_out(frame.t)
                remaining = ctl.remaining(frame.t)
                if reason:
                    self._controller = None
                    clip = ctl.finish(reason)
                    self._collect.finish(clip)
                    remaining = None
            self._collect.tick()

            dt = (frame.t - last_t) if last_t is not None else 0.033
            last_t = frame.t
            ema_dt += 0.1 * (dt - ema_dt)
            ema_proc += 0.1 * ((time.perf_counter() - t_start) * 1000 - ema_proc)
            n += 1
            mouth_jpeg = frame_jpeg = None
            if crop is not None:
                mouth_jpeg = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()
            if self._want_full_preview and n % 3 == 0:
                small = cv2.resize(frame.image, (320, int(320 * h / w)))
                frame_jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])[1].tobytes()
            with self._lock:
                lv = self._live
                lv.face_found, lv.opening, lv.remaining_sec = det is not None, opening, remaining
                lv.fps, lv.proc_ms = round(1 / ema_dt, 1) if ema_dt > 0 else 0.0, round(ema_proc, 1)
                lv.live_range = round(live.range, 4)
                lv.seq += 1
                lv.mouth_jpeg = mouth_jpeg or lv.mouth_jpeg
                if frame_jpeg:
                    lv.frame_jpeg = frame_jpeg
                elif not self._want_full_preview:
                    lv.frame_jpeg = None
        if source:
            source.close()
        if detector:
            detector.close()

    def _abort_recording(self) -> None:
        if self._controller is not None:
            self._controller = None
            self._collect.cancel_recording()
