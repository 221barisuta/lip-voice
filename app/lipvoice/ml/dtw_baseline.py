"""段階 A: 時系列の距離で比べる方式（DTW + 近傍法）。学習は不要で、お手本（学習データ）を覚えるだけ。"""
import numpy as np


def dtw_distances(q: np.ndarray, refs: np.ndarray, band: int) -> np.ndarray:
    """q（n, D）と、全お手本 refs（M, m, D）との DTW 距離を、まとめて計算する。
    時間のずれは band フレーム以内だけ許す（Sakoe-Chiba の帯）。距離は経路の長さで割る。
    """
    M, m, _ = refs.shape
    n = len(q)
    cross = np.einsum("nd,mjd->mnj", q, refs)
    cost = np.sqrt(np.maximum((q ** 2).sum(1)[None, :, None] + (refs ** 2).sum(2)[:, None, :] - 2 * cross, 0.0))
    d = np.full((M, n + 1, m + 1), np.inf)
    d[:, 0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(max(1, i - band), min(m, i + band) + 1):
            d[:, i, j] = cost[:, i - 1, j - 1] + np.minimum(np.minimum(d[:, i - 1, j], d[:, i, j - 1]), d[:, i - 1, j - 1])
    return d[:, n, m] / (n + m)


class DTWModel:
    def __init__(self, refs: np.ndarray, labels: list[str], band: int = 12, temp: float = 0.1):
        self.refs, self.labels, self.band, self.temp = refs.astype(np.float32), list(labels), band, temp
        self.classes = sorted(set(labels))
        self._cls_idx = [np.flatnonzero(np.array(labels) == c) for c in self.classes]

    @classmethod
    def fit(cls, x: np.ndarray, labels: list[str], band: int = 12) -> "DTWModel":
        model = cls(x, labels, band)
        gaps = []                                                   # 学習データ自身で、1 位と 2 位の距離の差を見て温度を決める
        for i in range(len(x)):
            d = dtw_distances(x[i], np.delete(x, i, 0), band)
            lab = np.delete(np.array(labels), i)
            per = sorted(d[lab == c].min() for c in model.classes if (lab == c).any())
            if len(per) >= 2:
                gaps.append(per[1] - per[0])
        model.temp = float(max(np.median(gaps) / 2, 1e-3)) if gaps else 0.1
        return model

    def class_distances(self, q: np.ndarray) -> dict[str, float]:
        d = dtw_distances(q, self.refs, self.band)
        return {c: float(d[idx].min()) for c, idx in zip(self.classes, self._cls_idx)}

    def predict(self, q: np.ndarray) -> dict:
        """上位の候補と確信度、棄却に使う最小距離（これが大きいほど、どのフレーズにも似ていない）。"""
        dist = self.class_distances(q)
        order = sorted(dist, key=dist.get)
        dmin = dist[order[0]]
        w = np.exp(-(np.array([dist[c] for c in order]) - dmin) / self.temp)
        conf = w / w.sum()
        return {"ranked": order, "confidence": [float(v) for v in conf], "distance": dmin, "class_distances": dist}

    def to_npz(self) -> dict:
        return {"refs": self.refs, "labels": np.array(self.labels, dtype="U40"), "band": np.int32(self.band),
                "temp": np.float32(self.temp)}

    @classmethod
    def from_npz(cls, z) -> "DTWModel":
        return cls(z["refs"], [str(v) for v in z["labels"]], int(z["band"]), float(z["temp"]))
