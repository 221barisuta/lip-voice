import time

import cv2

from .base import Frame


class CameraSource:
    """OpenCV でカメラを開く（Windows は Media Foundation、Mac は AVFoundation）。"""

    def __init__(self, index: int, width: int, height: int, fps: int):
        self.description = f"カメラ {index}"
        self._cap = cv2.VideoCapture(index)
        if not self._cap.isOpened():
            self._cap.release()
            raise OSError(f"カメラ {index} を開けません")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap.set(cv2.CAP_PROP_FPS, fps)

    def read(self) -> Frame | None:
        ok, img = self._cap.read()
        return Frame(img, time.monotonic()) if ok and img is not None else None

    def close(self) -> None:
        self._cap.release()
