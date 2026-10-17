"""保存した生の特徴点から、学習・認識に使う入力（64 フレーム × 特徴）を作る（仕様 8.2）。

収集と認識で必ずこの 1 か所の関数を使う。正規化・動き区間の切り出し・64 フレームへの再サンプルを行う。
"""
from dataclasses import dataclass

import numpy as np

from ..recording.clip import load_npz
from ..vision.indices import (EYE_OUTER_L, EYE_OUTER_R, LIP_INDICES, MOUTH_CORNER_L, MOUTH_CORNER_R)

BLEND_PREFIXES = ("jaw", "mouth")      # 表情係数のうち、口・あご関連だけを使う


@dataclass
class FeatureConfig:
    frames: int = 64
    margin_sec: float = 0.2             # 動き区間の前後に付ける余白
    window_sec: float = 0.3             # 動きの検出に使う窓
    active_threshold: float = 0.01      # 窓の中の口の開き（または口の幅）の変動幅がこれ以上なら「動いている」
    use_duration: bool = False          # 録画の長さを特徴に加える（ALS は疲労で速さが変わるため既定は OFF）

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def blend_columns(names: list[str]) -> list[int]:
    return [i for i, n in enumerate(names) if str(n).startswith(BLEND_PREFIXES)]


def feature_dim(cfg: FeatureConfig, n_blend: int = 27) -> int:
    return len(LIP_INDICES) * 2 + n_blend + (1 if cfg.use_duration else 0)


def _rows(indices: np.ndarray, wanted: list[int]) -> list[int]:
    pos = {int(v): r for r, v in enumerate(indices)}
    return [pos[i] for i in wanted]


def normalize_batch(points: np.ndarray, indices: np.ndarray, w: int, h: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """geometry.normalize_mouth を全フレームまとめて計算する。
    戻り値: 口の 40 点（T, 40, 3）、口の開き（T）、口の幅（T）。いずれも目尻間の距離を 1 とした値。
    """
    r_lip = _rows(indices, LIP_INDICES)
    rc = _rows(indices, [MOUTH_CORNER_L, MOUTH_CORNER_R, EYE_OUTER_R, EYE_OUTER_L, 13, 14])
    p = points.astype(np.float64)
    px = p[..., 0] * w
    py = p[..., 1] * h
    pz = p[..., 2] * w
    ml, mr, er, el = rc[0], rc[1], rc[2], rc[3]
    cx, cy = (px[:, ml] + px[:, mr]) / 2, (py[:, ml] + py[:, mr]) / 2
    eye = np.hypot(px[:, er] - px[:, el], py[:, er] - py[:, el])
    eye = np.where(eye > 0, eye, 1.0)
    ang = np.arctan2(py[:, el] - py[:, er], px[:, el] - px[:, er])
    c, s = np.cos(-ang)[:, None], np.sin(-ang)[:, None]
    dx, dy = px[:, r_lip] - cx[:, None], py[:, r_lip] - cy[:, None]
    out = np.stack([(dx * c - dy * s) / eye[:, None], (dx * s + dy * c) / eye[:, None], pz[:, r_lip] / eye[:, None]], axis=-1)
    opening = np.hypot(px[:, rc[4]] - px[:, rc[5]], py[:, rc[4]] - py[:, rc[5]]) / eye
    width = np.hypot(px[:, ml] - px[:, mr], py[:, ml] - py[:, mr]) / eye
    return out, opening, width


def _interp_missing(x: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """検出できなかったフレームを、前後の検出できたフレームから線形補間する（列ごと）。"""
    if valid.all() or not valid.any():
        return x
    idx = np.arange(len(x))
    flat = x.reshape(len(x), -1)
    out = np.empty_like(flat)
    for j in range(flat.shape[1]):
        out[:, j] = np.interp(idx, idx[valid], flat[valid, j])
    return out.reshape(x.shape)


def active_segment(t: np.ndarray, opening: np.ndarray, width: np.ndarray, cfg: FeatureConfig) -> tuple[float, float]:
    """口が動いている区間（秒）。動きがなければ録画全体。
    窓（window_sec）の中の変動幅が閾値以上のフレームを「動いている」とみなす。
    最初にそうなった時刻が動き始め、最後にそうなった時刻から窓の長さを引いた時刻が動き終わり。
    """
    ts = t / 1000.0
    act = np.zeros(len(ts), dtype=bool)
    for i in range(len(ts)):
        lo = np.searchsorted(ts, ts[i] - cfg.window_sec, side="right")
        a = max(np.ptp(opening[lo:i + 1]), np.ptp(width[lo:i + 1]))
        act[i] = a >= cfg.active_threshold
    if not act.any():
        return float(ts[0]), float(ts[-1])
    first, last = np.flatnonzero(act)[[0, -1]]
    start = ts[first] - cfg.margin_sec
    end = ts[last] - cfg.window_sec + cfg.margin_sec
    start, end = max(start, ts[0]), min(max(end, start + 0.2), ts[-1])
    return float(start), float(end)


def extract(raw: dict[str, np.ndarray], cfg: FeatureConfig | None = None) -> tuple[np.ndarray, dict]:
    """生の特徴点 → (frames, 特徴) と、切り出しの情報。"""
    cfg = cfg or FeatureConfig()
    t = raw["t_ms"].astype(np.float64)
    valid = raw["valid"].astype(bool)
    w, h = (int(v) for v in raw["image_size"])
    names = [str(n) for n in raw["blend_names"]]
    cols = blend_columns(names)
    pts, opening, width = normalize_batch(raw["points"], raw["indices"], w, h)
    xy = _interp_missing(pts[..., :2].reshape(len(t), -1), valid)
    blend = _interp_missing(raw["blend"][:, cols].astype(np.float64), valid)
    opening, width = _interp_missing(opening, valid), _interp_missing(width, valid)
    s0, s1 = active_segment(t, opening, width, cfg)
    grid = np.linspace(s0 * 1000, s1 * 1000, cfg.frames)
    feats = np.concatenate([xy, blend], axis=1)
    out = np.stack([np.interp(grid, t, feats[:, j]) for j in range(feats.shape[1])], axis=1)
    if cfg.use_duration:
        out = np.concatenate([out, np.full((cfg.frames, 1), np.log(max(s1 - s0, 0.1)))], axis=1)
    info = {"start_sec": s0, "end_sec": s1, "active_sec": s1 - s0, "clip_sec": float(t[-1] / 1000)}
    return out.astype(np.float32), info


def extract_file(path, cfg: FeatureConfig | None = None) -> tuple[np.ndarray, dict]:
    return extract(load_npz(str(path)), cfg)


class Standardizer:
    """特徴ごとの平均と標準偏差で標準化する（値は学習データだけから決める）。"""

    def __init__(self, mean: np.ndarray, std: np.ndarray):
        self.mean, self.std = mean.astype(np.float32), std.astype(np.float32)

    @classmethod
    def fit(cls, x: np.ndarray) -> "Standardizer":
        flat = x.reshape(-1, x.shape[-1])
        return cls(flat.mean(0), np.maximum(flat.std(0), 1e-4))

    def __call__(self, x: np.ndarray) -> np.ndarray:
        return ((x - self.mean) / self.std).astype(np.float32)
