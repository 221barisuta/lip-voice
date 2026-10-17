"""口の位置・大きさ・傾き・開きの計算と、特徴点の正規化（仕様 6.3）。

入力の座標は MediaPipe の正規化座標（x, y は 0〜1、z は x と同じ尺度）。
保存した部分集合（SAVED_INDICES）からでも、478 点全部からでも同じ関数で計算できる。
"""
from dataclasses import dataclass

import numpy as np

from .indices import (EYE_OUTER_L, EYE_OUTER_R, LIP_INDICES, LIP_INNER_LOWER, LIP_INNER_UPPER,
                      MOUTH_CORNER_L, MOUTH_CORNER_R)


class Landmarks:
    """点の配列（K, 3）と、各行が Face Mesh の何番の点かを持つ。"""

    def __init__(self, points: np.ndarray, indices: np.ndarray | list[int] | None = None):
        self.points = np.asarray(points, dtype=np.float64)
        idx = np.arange(len(self.points)) if indices is None else np.asarray(indices)
        self._row = {int(i): r for r, i in enumerate(idx)}

    def __getitem__(self, i: int) -> np.ndarray:
        return self.points[self._row[i]]


@dataclass(frozen=True)
class Geometry:
    center: tuple[float, float]   # 口角の中点（画素）
    mouth_width: float            # 口角間の距離（画素）
    eye_distance: float           # 目尻間の距離（画素）
    angle: float                  # 目尻を結ぶ線の傾き（rad）


def _px(lm: Landmarks, i: int, w: int, h: int) -> np.ndarray:
    p = lm[i]
    return np.array([p[0] * w, p[1] * h])


def mouth_geometry(lm: Landmarks, w: int, h: int) -> Geometry:
    a, b = _px(lm, MOUTH_CORNER_L, w, h), _px(lm, MOUTH_CORNER_R, w, h)
    er, el = _px(lm, EYE_OUTER_R, w, h), _px(lm, EYE_OUTER_L, w, h)
    c = (a + b) / 2
    return Geometry((float(c[0]), float(c[1])), float(np.hypot(*(a - b))), float(np.hypot(*(er - el))),
                    float(np.arctan2(el[1] - er[1], el[0] - er[0])))


def mouth_opening(lm: Landmarks, w: int, h: int) -> float:
    """口の開き＝上唇と下唇（内側）の距離 ÷ 目尻間の距離。顔の位置・距離が変わっても同じ尺度。"""
    u, l = _px(lm, LIP_INNER_UPPER, w, h), _px(lm, LIP_INNER_LOWER, w, h)
    eye = mouth_geometry(lm, w, h).eye_distance or 1.0
    return float(np.hypot(*(u - l)) / eye)


def normalize_mouth(lm: Landmarks, w: int, h: int) -> np.ndarray:
    """口の 40 点を正規化する（形は (40, 3)）。
    口角の中点を原点にし、目尻間の距離で大きさを揃え、目尻を結ぶ線が水平になるよう回転する。
    """
    g = mouth_geometry(lm, w, h)
    cos, sin = np.cos(-g.angle), np.sin(-g.angle)
    s = g.eye_distance or 1.0
    out = np.empty((len(LIP_INDICES), 3))
    for r, i in enumerate(LIP_INDICES):
        dx, dy, dz = lm[i][0] * w - g.center[0], lm[i][1] * h - g.center[1], lm[i][2] * w
        out[r] = ((dx * cos - dy * sin) / s, (dx * sin + dy * cos) / s, dz / s)
    return out
