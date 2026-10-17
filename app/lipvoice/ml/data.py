"""保存したクリップを読み、学習・評価に使う形（ClipItem）にする。"""
from dataclasses import dataclass, field

import numpy as np

from ..storage.store import Store
from .features import FeatureConfig, extract_file


@dataclass
class ClipItem:
    id: str
    kind: str                 # phrase | negative
    label: str                # phrase_id、または負例の種類
    date: str
    source: str
    x: np.ndarray             # (frames, 特徴)
    info: dict = field(default_factory=dict)


def load_items(store: Store, cfg: FeatureConfig, sources: tuple[str, ...] = ("collect",),
               min_detected_ratio: float = 0.7) -> list[ClipItem]:
    """既定は収集（collect）のクリップのみ。実使用（use）は、選択ミスでラベルが汚れうるので、指定した時だけ入れる。"""
    out = []
    for r in store.clip_rows():
        if r["source"] not in sources or (r["detected_ratio"] or 0) < min_detected_ratio:
            continue
        x, info = extract_file(store.clip_path(r["landmarks_path"]), cfg)
        label = r["phrase_id"] if r["kind"] == "phrase" else (r["negative_label"] or "負例")
        out.append(ClipItem(r["id"], r["kind"], label, r["date"], r["source"], x, info))
    return out


def stack(items: list[ClipItem]) -> np.ndarray:
    return np.stack([it.x for it in items]) if items else np.zeros((0, 0, 0), np.float32)
