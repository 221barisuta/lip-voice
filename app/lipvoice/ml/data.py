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


def select_rows(store: Store, sources: tuple[str, ...] = ("collect",), min_detected_ratio: float = 0.7) -> list:
    """学習に使うクリップの記録。既定は収集（collect）のみ。実使用（use）は、選択ミスでラベルが汚れうるので、指定した時だけ入れる。
    use_top1 は、実使用のうち、1 位が合っていて棄却されなかったものだけ。消されたフレーズのクリップは使わない。"""
    existing = {p["id"] for p in store.phrases()}
    good_use = {r[0] for r in store.db.execute(
        "SELECT clip_id FROM predictions WHERE clip_id IS NOT NULL AND correct_top1=1 AND COALESCE(rejected,0)=0")}
    out = []
    for r in store.clip_rows():
        src = r["source"]
        if not (src in sources or (src == "use" and "use_top1" in sources and r["id"] in good_use)):
            continue
        if (r["detected_ratio"] or 0) < min_detected_ratio:
            continue
        if r["kind"] == "phrase" and r["phrase_id"] not in existing:
            continue
        out.append(r)
    return out


def load_items(store: Store, cfg: FeatureConfig, sources: tuple[str, ...] = ("collect",),
               min_detected_ratio: float = 0.7) -> list[ClipItem]:
    out = []
    for r in select_rows(store, sources, min_detected_ratio):
        x, info = extract_file(store.clip_path(r["landmarks_path"]), cfg)
        label = r["phrase_id"] if r["kind"] == "phrase" else (r["negative_label"] or "負例")
        out.append(ClipItem(r["id"], r["kind"], label, r["date"], r["source"], x, info))
    return out


def stack(items: list[ClipItem]) -> np.ndarray:
    return np.stack([it.x for it in items]) if items else np.zeros((0, 0, 0), np.float32)
