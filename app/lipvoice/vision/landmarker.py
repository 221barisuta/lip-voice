"""MediaPipe Face Landmarker の薄い包み。モデルファイルは初回だけ取得し、以後はオフラインで動く。"""
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Detection:
    points: np.ndarray   # (478, 3) float32。x, y は 0〜1、z は x と同じ尺度
    blend: np.ndarray    # (52,) float32 表情係数


class FaceDetector:
    def __init__(self, model_path: Path):
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self._mp = mp
        base = mp_python.BaseOptions(model_asset_path=str(model_path),
                                     delegate=mp_python.BaseOptions.Delegate.CPU)
        opts = vision.FaceLandmarkerOptions(base_options=base, running_mode=vision.RunningMode.VIDEO,
                                            num_faces=1, output_face_blendshapes=True)
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
        return Detection(pts, blend)

    def close(self) -> None:
        self._lm.close()
