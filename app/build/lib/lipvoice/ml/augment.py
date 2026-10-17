"""データの水増し（仕様 8.3）。学習のときだけ使う。"""
import numpy as np


def time_stretch(x: np.ndarray, s: float) -> np.ndarray:
    """速さを s 倍にする（s>1 は速く = 短くなる）。長さは元のフレーム数に、端を延ばす／中央を切るで戻す。"""
    n = len(x)
    m = max(8, int(round(n / s)))
    grid = np.linspace(0, n - 1, m)
    y = np.stack([np.interp(grid, np.arange(n), x[:, j]) for j in range(x.shape[1])], axis=1)
    if m >= n:
        a = (m - n) // 2
        return y[a:a + n]
    pad = n - m
    return np.pad(y, ((pad // 2, pad - pad // 2), (0, 0)), mode="edge")


def shift(x: np.ndarray, k: int) -> np.ndarray:
    """開始位置を前後にずらす（端は繰り返しで埋める）。"""
    if k == 0:
        return x
    return np.pad(x[k:], ((0, k), (0, 0)), mode="edge") if k > 0 else np.pad(x[:k], ((-k, 0), (0, 0)), mode="edge")


def augment(x: np.ndarray, rng: np.random.Generator, speed=(0.8, 1.2), max_shift=4, noise=0.03) -> np.ndarray:
    y = time_stretch(x, float(rng.uniform(*speed)))
    y = shift(y, int(rng.integers(-max_shift, max_shift + 1)))
    y = y * rng.uniform(0.95, 1.05, size=(1, y.shape[1])) + rng.normal(0, noise, y.shape)
    return y.astype(np.float32)
