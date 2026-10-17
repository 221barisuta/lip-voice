"""推論（numpy のみ。torch は読み込まない）と、保存したモデルの読み込み。"""
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .dtw_baseline import DTWModel
from .features import FeatureConfig, Standardizer, extract


def conv1d_same(x: np.ndarray, w: np.ndarray, b: np.ndarray) -> np.ndarray:
    """x: (C, T)、w: (O, C, K)。長さを変えない畳み込み。"""
    k = w.shape[2]
    xp = np.pad(x, ((0, 0), (k // 2, k - 1 - k // 2)))
    return np.einsum("ock,ctk->ot", w, sliding_window_view(xp, k, axis=1)) + b[:, None]


def maxpool2(x: np.ndarray) -> np.ndarray:
    t = x.shape[1] // 2 * 2
    return x[:, :t].reshape(x.shape[0], t // 2, 2).max(-1)


class CNNModel:
    """学習済みの 1D-CNN（BN を畳み込みに畳み込み済み）を numpy で実行する。"""

    def __init__(self, z: dict):
        self.z = {k: np.asarray(v) for k, v in z.items()}
        self.classes = [str(c) for c in self.z["classes"]]
        self.prototypes = self.z["prototypes"]

    def forward(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        z = self.z
        h = x.T.astype(np.float32)
        h = maxpool2(np.maximum(conv1d_same(h, z["c1_w"], z["c1_b"]), 0))
        h = maxpool2(np.maximum(conv1d_same(h, z["c2_w"], z["c2_b"]), 0))
        h = np.maximum(conv1d_same(h, z["c3_w"], z["c3_b"]), 0)
        feat = np.concatenate([h.mean(1), h.max(1)])
        emb = np.maximum(z["fc1_w"] @ feat + z["fc1_b"], 0)
        return z["fc2_w"] @ emb + z["fc2_b"], emb

    def predict(self, x: np.ndarray) -> dict:
        logits, emb = self.forward(x)
        p = np.exp(logits - logits.max())
        p /= p.sum()
        order = np.argsort(-p)
        d = np.linalg.norm(self.prototypes - emb[None, :], axis=1)      # 各フレーズの代表との距離
        return {"ranked": [self.classes[i] for i in order], "confidence": [float(p[i]) for i in order],
                "distance": float(d.min()), "class_distances": {c: float(v) for c, v in zip(self.classes, d)}}


@dataclass
class Meta:
    version: str
    classes: list[str]
    feature: dict
    active: str                      # "A" | "B"
    tau: dict                        # 棄却の閾値 {"A": ..., "B": ...}
    extra: dict


class Predictor:
    def __init__(self, folder: Path):
        m = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        self.meta = Meta(m["version"], m["classes"], m["feature"], m["active"], m["tau"], m.get("extra", {}))
        self.cfg = FeatureConfig(**m["feature"])
        with np.load(folder / "stats.npz", allow_pickle=False) as z:
            self.std = Standardizer(z["mean"], z["std"])
        self.dtw = self.cnn = None
        if (folder / "dtw.npz").exists():
            with np.load(folder / "dtw.npz", allow_pickle=False) as z:
                self.dtw = DTWModel.from_npz(z)
        if (folder / "cnn.npz").exists():
            with np.load(folder / "cnn.npz", allow_pickle=False) as z:
                self.cnn = CNNModel(dict(z))

    @property
    def version(self) -> str:
        return self.meta.version

    def predict_features(self, x_std: np.ndarray) -> dict:
        out: dict = {}
        if self.dtw is not None:
            out["A"] = self.dtw.predict(x_std)
        if self.cnn is not None:
            out["B"] = self.cnn.predict(x_std)
        return out

    def predict(self, raw: dict) -> dict:
        """生の特徴点 → 候補。棄却（フレーズに似ていない動き）と、A と B が一致したかも返す。"""
        t0 = time.perf_counter()
        x, info = extract(raw, self.cfg)
        res = self.predict_features(self.std(x))
        kind = self.meta.active if self.meta.active in res else next(iter(res))
        r = res[kind]
        tau = self.meta.tau.get(kind, float("inf"))
        agree = len({v["ranked"][0] for v in res.values()}) == 1
        return {"candidates": [{"phrase_id": c, "confidence": p} for c, p in zip(r["ranked"][:3], r["confidence"][:3])],
                "distance": r["distance"], "tau": tau, "rejected": bool(r["distance"] > tau), "model": kind,
                "agree": agree, "version": self.meta.version, "segment": info,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}
