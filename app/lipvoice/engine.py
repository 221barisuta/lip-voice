"""カメラ → 顔検出 → 口の動き・切り出し → 録画、を回し続けるスレッド。

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
from .vision.crop import MouthCropper
from .vision.geometry import Landmarks, mouth_geometry, mouth_opening, mouth_width_ratio
from .vision.landmarker import FaceDetector
from .vision.stillness import StillnessConfig, StillnessDetector

_ROTATE = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


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
    tilt_deg: float | None = None     # 顔の正面からの傾き（約 45° を超えると検出が不安定になる）
    roll_deg: float | None = None
    remaining_sec: float | None = None
    seq: int = 0                      # フレームが進むたびに増える
    mouth_jpeg: bytes | None = None
    frame_jpeg: bytes | None = None
    delegate: str = "CPU"
    extra: dict = field(default_factory=dict)


class Engine:
    def __init__(self, model_file: Path, settings_fn, collect: CollectSession, detector_factory=FaceDetector,
                 source_factory=open_source, speak=None):
        self._model_file, self._settings, self._collect = model_file, settings_fn, collect
        self._speak = speak
        self._active = collect                       # いま録画を受け取るセッション（収集 or 認識）
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

    def stop(self) -> bool:
        """止める。取得の処理が終わらない（カメラの許可待ちなど）時は False を返す。"""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        return not (self._thread and self._thread.is_alive())

    def snapshot(self) -> LiveState:
        with self._lock:
            return LiveState(**{**self._live.__dict__})

    def set_full_preview(self, on: bool) -> None:
        self._want_full_preview = on

    def request_start(self, which: str = "collect") -> dict:
        session = self._speak if which == "speak" else self._collect
        if session is None:
            raise StateError("この機能は使えません")
        other = self._collect if which == "speak" else self._speak
        if other is not None and other.phase not in ("idle", "ended"):
            raise StateError("ほかの操作の途中です")
        with self._lock:
            ok, face = self._live.camera == "ok", self._live.face_found
        if not ok:
            raise StateError("カメラが使えません")
        if not face:
            raise StateError("顔が検出できていません。カメラの正面に顔を向けてください")
        target = session.begin()
        self._active = session
        s = self._settings()
        self._controller = None                      # 録画はエンジンのスレッドが次のフレームで始める
        self._pending_cfg = StillnessConfig(s.threshold, s.still_sec, s.max_sec)
        self._start_flag = True
        return target

    def cancel(self) -> None:
        """録画の途中でやめる（保存しない）。"""
        self._abort_recording()

    # ---- スレッド本体 ----
    def _set(self, **kw) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(self._live, k, v)

    def _open(self, s, detector):
        if detector is None:
            if not self._model_file.exists():
                raise OSError(f"モデルがありません。lipvoice fetch-models を実行してください（{self._model_file}）")
            detector = self._det_factory(self._model_file, detection=s.face_detection_confidence,
                                         presence=s.face_presence_confidence, tracking=s.tracking_confidence)
        source = self._src_factory(s)
        self._set(camera="ok", message="", source=source.description)
        return detector, source

    def _run(self) -> None:
        detector = source = None
        cropper = MouthCropper()
        s = self._settings()
        live_cfg = StillnessConfig(float("inf"), s.still_sec, float("inf"))
        live = StillnessDetector(live_cfg)
        fails, ema_dt, ema_proc, last_t, last_done = 0, 0.033, 0.0, None, 0.0
        n = 0
        while not self._stop.is_set():
            s = self._settings()
            live_cfg.still_sec = s.still_sec
            if source is None:
                try:
                    detector, source = self._open(s, detector)
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
            recording = self._controller is not None or self._start_flag
            if not recording and s.idle_fps and last_done and frame.t - last_done < 1.0 / s.idle_fps:
                continue                             # 待機中は検出を間引いて、PC の負荷を下げる
            last_done = frame.t
            t_start = time.perf_counter()
            image = cv2.rotate(frame.image, _ROTATE[s.camera_rotate]) if s.camera_rotate in _ROTATE else frame.image
            h, w = image.shape[:2]
            det = detector.detect(image, frame.t * 1000)
            geom = opening = None
            indicators = None
            if det is not None:
                lm = Landmarks(det.points)
                geom = mouth_geometry(lm, w, h)
                opening = mouth_opening(lm, w, h)
                indicators = (opening, mouth_width_ratio(lm, w, h))   # 口の開きと口の幅（横に広がる動きも見る）
            cropper.update(geom)
            crop = cropper.crop(image)
            live.push(frame.t, indicators)

            if self._start_flag:                     # API からの録画開始の要求
                self._start_flag = False
                self._controller = RecordingController(self._pending_cfg, w, h, list(detector.blend_names), t0=frame.t)
            ctl = self._controller
            remaining = None
            if ctl is not None:
                reason = ctl.add(frame.t, det, indicators, opening, crop) or ctl.timed_out(frame.t)
                remaining = ctl.remaining(frame.t)
                if reason:
                    self._controller = None
                    clip = ctl.finish(reason)
                    self._active.finish(clip)
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
                small = cv2.resize(image, (320, int(320 * h / w)))
                frame_jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])[1].tobytes()
            with self._lock:
                lv = self._live
                lv.face_found, lv.opening, lv.remaining_sec = det is not None, opening, remaining
                lv.tilt_deg, lv.roll_deg = (det.tilt_deg, det.roll_deg) if det is not None else (None, None)
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
        """録画の途中でカメラが止まった時などに、必ず「録画中」から戻す。"""
        self._controller = None
        self._start_flag = False
        self._active.cancel_recording()
