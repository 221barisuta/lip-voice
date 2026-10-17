import time

import numpy as np

from ..vision.geometry import Geometry
from ..vision.indices import SAVED_INDICES
from ..vision.landmarker import Detection
from ..vision.stillness import StillnessConfig, StillnessDetector, StopReason
from .clip import RecordedClip


class RecordingController:
    """録画 1 回ぶん。フレームを受け取り、口が止まる／最大秒数で終わりを知らせる。"""

    def __init__(self, cfg: StillnessConfig, width: int, height: int, blend_names: list[str], t0: float | None = None):
        self.cfg = cfg
        self.t0 = time.monotonic() if t0 is None else t0
        self._det = StillnessDetector(cfg)
        self._w, self._h, self._names = width, height, blend_names
        self._t: list[int] = []
        self._pts: list[np.ndarray] = []
        self._valid: list[bool] = []
        self._blend: list[np.ndarray] = []
        self._open: list[float] = []
        self._crops: list[np.ndarray] = []
        self._blank = np.zeros((len(SAVED_INDICES), 3), np.float32)

    def elapsed(self, now: float) -> float:
        return now - self.t0

    def remaining(self, now: float) -> float:
        return max(0.0, self.cfg.max_sec - self.elapsed(now))

    def add(self, now: float, det: Detection | None, opening: float | None, crop: np.ndarray | None) -> StopReason | None:
        t = self.elapsed(now)
        self._t.append(int(t * 1000))
        self._valid.append(det is not None)
        self._pts.append(det.points[SAVED_INDICES] if det is not None else self._blank)
        self._blend.append(det.blend if det is not None else np.zeros(52, np.float32))
        self._open.append(opening if opening is not None else float("nan"))
        if crop is not None:
            self._crops.append(crop)
        else:   # まだ切り出し位置が決まっていない間は、直前の絵（なければ黒）で埋める
            self._crops.append(self._crops[-1] if self._crops else np.zeros((96, 96), np.uint8))
        return self._det.push(t, opening)

    def timed_out(self, now: float) -> StopReason | None:
        """フレームが来なくなっても、最大秒数で必ず終える。"""
        if self.elapsed(now) >= self.cfg.max_sec + 0.1:
            return "max" if self._det.has_moved else "no_motion"
        return None

    def finish(self, reason: StopReason) -> RecordedClip:
        n = len(self._t)
        return RecordedClip(
            t_ms=np.array(self._t, dtype=np.int32), points=np.array(self._pts, dtype=np.float32).reshape(n, len(SAVED_INDICES), 3),
            valid=np.array(self._valid, dtype=bool), blend=np.array(self._blend, dtype=np.float32).reshape(n, 52),
            opening=np.array(self._open, dtype=np.float32), crops=self._crops, blend_names=self._names,
            width=self._w, height=self._h, stop_reason=reason)


__all__ = ["RecordingController", "Geometry"]
