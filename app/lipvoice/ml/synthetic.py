"""合成データ。実データがない段階で、学習 → 評価 → 認識の流れが動くことを確かめるための試験用。

フレーズごとに「口の形の目標が並んだ時間パターン」を持たせ、速さ・大きさ・日ごとのずれ・ノイズ・欠損・
前後の静止・フレームレートの揺れを加えて、実際の録画と同じ形式（npz）の可変長のクリップを作る。
精度の数値は参考値にならない（実データではない）。
"""
import io

import numpy as np

from ..recording.clip import RecordedClip
from ..vision.indices import BLENDSHAPE_NAMES, LIP_INDICES, SAVED_INDICES

PHRASE_LENGTHS = [2, 4, 6, 3, 2, 4, 6, 5, 5, 3]          # フレーズごとの「音節」の数（長い文も混ぜる）
W, H = 640, 480


def base_face(w: int = W, h: int = H) -> np.ndarray:
    """目・口角・唇だけを置いた仮の顔（478 点。残りは 0）。単位は目尻間の距離。"""
    pts = np.zeros((478, 3))
    unit = h

    def put(i, x, y, z=0.0):
        pts[i] = (0.5 + unit * x / w, 0.5 + unit * y / h, z * unit / w)

    put(33, -0.10, -0.1); put(263, 0.10, -0.1); put(61, -0.04, 0.12); put(291, 0.04, 0.12)
    put(13, 0.0, 0.11); put(14, 0.0, 0.13)
    for k, i in enumerate(LIP_INDICES):
        if i not in (61, 291, 13, 14):
            put(i, -0.035 + 0.0017 * k, 0.12 + 0.012 * (k % 3), 0.01)
    return pts


def _templates(n_phrases: int, seed: int = 7) -> list[np.ndarray]:
    """フレーズごとの目標の並び（音節数 × [開き, 幅, 丸め, 下唇のずれ]）。"""
    rng = np.random.default_rng(seed)
    return [rng.uniform(0.0, 1.0, size=(PHRASE_LENGTHS[i % len(PHRASE_LENGTHS)], 4)) for i in range(n_phrases)]


def _trajectory(targets: np.ndarray, speed: float, t: np.ndarray, t0: float) -> np.ndarray:
    """目標を順にたどる滑らかな軌跡 z(t)（4 次元）。録画の前後は口を閉じている（0）。"""
    dur = 0.28 / speed
    knots_t = t0 + np.arange(len(targets)) * dur
    z = np.zeros((len(t), 4))
    for j in range(4):
        z[:, j] = np.interp(t, np.concatenate([[knots_t[0] - dur], knots_t, [knots_t[-1] + dur]]),
                            np.concatenate([[0], targets[:, j], [0]]), left=0, right=0)
    return z


def make_clip(rng: np.random.Generator, targets: np.ndarray, day_shift: float, day_speed: float,
              negative: str | None = None) -> RecordedClip:
    """1 本のクリップ。targets が None のとき（negative 指定）は、フレーズではない動き。"""
    fps = rng.uniform(22, 30)
    lead, tail = rng.uniform(0.3, 1.0), rng.uniform(1.0, 1.2)
    if negative is None:
        speed = day_speed * rng.uniform(0.85, 1.2)
        body = len(targets) * 0.28 / speed
    else:
        speed, body = 1.0, rng.uniform(1.0, 3.0)
    dur = lead + body + 0.3 + tail
    t = np.arange(0, dur, 1 / fps) + rng.normal(0, 0.003, int(np.ceil(dur * fps)))[: len(np.arange(0, dur, 1 / fps))]
    t = np.sort(t)
    if negative is None:
        z = _trajectory(targets * rng.uniform(0.85, 1.15), speed, t, lead)
    else:                                                        # 負例: 目標の並びとは関係のない、大きな・ゆっくり or 鋭い動き
        kind = abs(hash(negative)) % 3
        x = np.clip((t - lead) / max(body, 0.1), 0, 1)
        z = np.zeros((len(t), 4))
        if kind == 0:  z[:, 0] = np.sin(np.pi * x) ** 2 * 1.2                                  # あくび: 大きくゆっくり
        elif kind == 1: z[:, 0] = (np.sin(x * 20) > 0.8) * 0.9 * (x < 1)                       # 咳: 鋭い数回
        else:           z[:, 0] = 0.3 * np.abs(np.sin(x * 6)) * (x < 1); z[:, 2] = 0.5 * (x < 1)  # 口を湿らす等
    z = np.clip(z + day_shift * np.array([0.05, 0.05, 0.05, 0.05]), -0.2, 1.3)

    n, K = len(t), len(SAVED_INDICES)
    face = base_face()
    pts = np.zeros((n, K, 3), np.float32)
    row = {int(i): r for r, i in enumerate(SAVED_INDICES)}
    cy = face[13, 1]
    for f in range(n):
        opn, wid, rnd, ls = z[f]
        gap = 0.02 + 0.13 * opn
        wfac = 1 + 0.35 * (wid - rnd)
        for i in LIP_INDICES:
            p = face[i].copy()
            p[0] = 0.5 + (p[0] - 0.5) * wfac
            p[1] += (-gap / 2 if p[1] < cy else gap / 2) + 0.01 * ls
            pts[f, row[i]] = p
        for i in (33, 263):
            pts[f, row[i]] = face[i]
    pts += rng.normal(0, 0.0004, pts.shape).astype(np.float32)               # 検出のノイズ
    blend = np.zeros((n, 52), np.float32)
    idx = {nm: i for i, nm in enumerate(BLENDSHAPE_NAMES)}
    blend[:, idx["jawOpen"]] = z[:, 0]
    blend[:, idx["mouthSmileLeft"]] = blend[:, idx["mouthSmileRight"]] = np.clip(z[:, 1] - z[:, 2], 0, 1)
    blend[:, idx["mouthPucker"]] = z[:, 2]
    blend[:, idx["mouthFunnel"]] = z[:, 2] * 0.8
    blend[:, idx["mouthLowerDownLeft"]] = blend[:, idx["mouthLowerDownRight"]] = z[:, 3]
    blend += rng.normal(0, 0.01, blend.shape).astype(np.float32)
    valid = rng.random(n) > 0.02
    pts[~valid] = 0
    opening = np.hypot(0.0, pts[:, row[14], 1] - pts[:, row[13], 1]) / 0.2 * (H / H)
    opening = np.where(valid, opening, np.nan).astype(np.float32)
    crops = [np.zeros((96, 96), np.uint8)] * n
    return RecordedClip(t_ms=(t * 1000).astype(np.int32), points=pts, valid=valid, blend=blend, opening=opening,
                        crops=crops, blend_names=list(BLENDSHAPE_NAMES), width=W, height=H,
                        stop_reason="still" if negative is None else "still")


def generate_into_store(store, per_day: list[int], phrase_ids: list[str], negatives: dict[str, int] | None = None,
                        seed: int = 0, day_names: list[str] | None = None) -> int:
    """store に、日ごとのクリップを保存する。per_day = 各日のフレーズあたりの本数（例 [10, 10, 5]）。"""
    from ..recording.encoder import encode_webm
    from ..storage.store import ClipRecord

    rng = np.random.default_rng(seed)
    tpl = _templates(len(phrase_ids))
    names = day_names or [f"day{i + 1}" for i in range(len(per_day))]
    total = 0
    blank_webm = encode_webm([np.zeros((96, 96), np.uint8)] * 3, np.array([0, 33, 66]))
    for d, (name, k) in enumerate(zip(names, per_day)):
        shift, speed = rng.normal(0, 1.0), rng.uniform(0.9, 1.1)          # 日ごとの照明・姿勢・話す速さのずれ
        sid = f"synth{d}"
        for pid, targets in zip(phrase_ids, tpl):
            for _ in range(k):
                c = make_clip(rng, targets, shift, speed)
                rec = ClipRecord(kind="phrase", session_id=sid, phrase_id=pid, duration_ms=c.duration_ms,
                                 frame_count=c.frame_count, fps_measured=c.fps_measured,
                                 detected_ratio=c.detected_ratio, stop_reason="still", width=W, height=H)
                store.save_clip(rec, c.to_npz(), blank_webm, day=name)
                total += 1
        for label, n_neg in (negatives or {}).items():
            for _ in range(max(1, round(n_neg * k / max(per_day)))):
                c = make_clip(rng, None, shift, speed, negative=label)
                rec = ClipRecord(kind="negative", session_id=sid, negative_label=label, duration_ms=c.duration_ms,
                                 frame_count=c.frame_count, fps_measured=c.fps_measured,
                                 detected_ratio=c.detected_ratio, stop_reason="still", width=W, height=H)
                store.save_clip(rec, c.to_npz(), blank_webm, day=name)
                total += 1
    return total
