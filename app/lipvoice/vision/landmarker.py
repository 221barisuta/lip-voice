"""MediaPipe Face Landmarker の薄い包み。モデルファイルは初回だけ取得し、以後はオフラインで動く。"""
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Detection:
    points: np.ndarray            # (478, 3) float32。x, y は 0〜1、z は x と同じ尺度
    blend: np.ndarray             # (52,) float32 表情係数
    tilt_deg: float | None = None  # 顔が正面からどれだけ傾いているか（検出器の守備範囲は約 45° 以内）
    roll_deg: float | None = None  # 画像の中で顔が回っている角度


class FaceDetector:
    def __init__(self, model_path: Path, detection: float = 0.5, presence: float = 0.5, tracking: float = 0.5):
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self._mp = mp
        # パスではなくバッファで渡す（Windows で、フォルダ名に日本語が含まれると開けないことがあるため）
        base = mp_python.BaseOptions(model_asset_buffer=Path(model_path).read_bytes(),
                                     delegate=mp_python.BaseOptions.Delegate.CPU)
        opts = vision.FaceLandmarkerOptions(
            base_options=base, running_mode=vision.RunningMode.VIDEO, num_faces=1, output_face_blendshapes=True,
            output_facial_transformation_matrixes=True, min_face_detection_confidence=detection,
            min_face_presence_confidence=presence, min_tracking_confidence=tracking)
        self._lm = vision.FaceLandmarker.create_from_options(opts)
        self.blend_names: list[str] = []
        self._last_ts = -1

    def detect(self, frame_bgr: np.ndarray, ts_ms: float) -> Detection | None:
        ts = max(int(ts_ms), self._last_ts + 1)     # タイムスタンプは単調増加でなければならない
        self._last_ts = ts
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        res = self._lm.detect_for_video(self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb), ts)
        if not res.face_landmarks:
            return None
        pts = np.array([[p.x, p.y, p.z] for p in res.face_landmarks[0]], dtype=np.float32)
        cats = res.face_blendshapes[0] if res.face_blendshapes else []
        if cats and not self.blend_names:
            self.blend_names = [c.category_name for c in cats]
        blend = np.array([c.score for c in cats], dtype=np.float32) if cats else np.zeros(52, np.float32)
        tilt = roll = None
        mats = getattr(res, "facial_transformation_matrixes", None)
        if mats is not None and len(mats):
            r = np.asarray(mats[0])[:3, :3]
            tilt = float(np.degrees(np.arccos(np.clip(abs(r[2, 2]), 0.0, 1.0))))
            roll = float(np.degrees(np.arctan2(r[1, 0], r[0, 0])))
        return Detection(pts, blend, tilt, roll)

    def close(self) -> None:
        self._lm.close()
