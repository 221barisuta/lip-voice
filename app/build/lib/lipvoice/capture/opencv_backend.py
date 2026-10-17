import time

import cv2

from .base import Frame

_BACKENDS = {"any": cv2.CAP_ANY, "msmf": getattr(cv2, "CAP_MSMF", cv2.CAP_ANY), "dshow": getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY)}


class CameraSource:
    """OpenCV でカメラを開く（Windows は Media Foundation か DirectShow、Mac は AVFoundation）。"""

    def __init__(self, index: int, width: int, height: int, fps: int, backend: str = "any"):
        self._cap = cv2.VideoCapture(index, _BACKENDS.get(backend, cv2.CAP_ANY))
        if not self._cap.isOpened():
            self._cap.release()
            raise OSError(
                f"カメラ {index} を開けません。他のアプリがカメラを使っていないか、Windows の「プライバシーとセキュリティ → "
                "カメラ → デスクトップ アプリにカメラへのアクセスを許可する」がオンか確認してください")
        # 設定の順序: 形式 → 幅 → 高さ → fps（ドライバによっては、この順でないと効かない）
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap.set(cv2.CAP_PROP_FPS, fps)
        for _ in range(10):                      # 開いた直後の黒い・不安定なフレームを捨てる
            self._cap.read()
        w, h = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        note = "" if (w, h) == (width, height) else f"（要求 {width}×{height} とは違う解像度）"
        self.description = f"カメラ {index} {w}×{h} {self._cap.get(cv2.CAP_PROP_FPS):.0f}fps{note}"

    def read(self) -> Frame | None:
        ok, img = self._cap.read()
        return Frame(img, time.perf_counter()) if ok and img is not None else None

    def close(self) -> None:
        self._cap.release()
