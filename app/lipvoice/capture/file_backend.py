import time

import cv2

from .base import Frame


class FileSource:
    """動画ファイルをカメラの代わりに繰り返し流す（開発・試験用）。実時間の速さで進める。"""

    def __init__(self, path: str, width: int = 0, height: int = 0):
        self.description = f"動画 {path}"
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise OSError(f"動画を開けません: {path}")
        fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        self._interval = 1.0 / fps
        self._size = (width, height) if width and height else None
        self._next = time.monotonic()

    def read(self) -> Frame | None:
        ok, img = self._cap.read()
        if not ok:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, img = self._cap.read()
            if not ok:
                return None
        if self._size and (img.shape[1], img.shape[0]) != self._size:
            img = cv2.resize(img, self._size)
        self._next += self._interval
        delay = self._next - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            self._next = time.monotonic()   # 処理が遅れたら、遅れを取り戻そうとしない
        return Frame(img, time.perf_counter())

    def close(self) -> None:
        self._cap.release()
