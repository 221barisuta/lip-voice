"""カメラ映像から口元を 96×96 グレースケールに切り出す。顔全体は結果に含まれない。"""
import math

import cv2
import numpy as np

from .geometry import Geometry

CROP_SIZE = 96


class MouthCropper:
    def __init__(self) -> None:
        self._s: tuple[float, float, float, float] | None = None   # cx, cy, side, angle

    def update(self, g: Geometry | None) -> None:
        """切り出し位置を更新する（なめらかに追従）。None なら直前の位置のまま。"""
        if g is None:
            return
        side = max(g.mouth_width * 2.0, g.eye_distance * 0.7)
        if self._s is None:
            self._s = (g.center[0], g.center[1], side, g.angle)
            return
        a = 0.5   # 追従の強さ（小さいほど滑らか）
        cx, cy, sd, ang = self._s
        self._s = (cx + a * (g.center[0] - cx), cy + a * (g.center[1] - cy),
                   sd + a * (side - sd), ang + a * (g.angle - ang))

    def crop(self, frame_bgr: np.ndarray) -> np.ndarray | None:
        if self._s is None:
            return None
        cx, cy, side, angle = self._s
        k = CROP_SIZE / side
        c, s = math.cos(angle), math.sin(angle)   # 目尻の線が水平になるよう傾きを補正
        m = np.array([[k * c, k * s, CROP_SIZE / 2 - k * (c * cx + s * cy)],
                      [-k * s, k * c, CROP_SIZE / 2 - k * (-s * cx + c * cy)]], dtype=np.float64)
        warped = cv2.warpAffine(frame_bgr, m, (CROP_SIZE, CROP_SIZE), flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
        return cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    def reset(self) -> None:
        self._s = None
