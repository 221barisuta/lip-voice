import numpy as np

from lipvoice.ml.features import (FeatureConfig, Standardizer, active_segment, extract, feature_dim, normalize_batch)
from lipvoice.ml.split import leave_one_day_out, split_by_date
from lipvoice.ml.synthetic import _templates, make_clip
from lipvoice.recording.clip import load_npz
from lipvoice.vision.geometry import Landmarks, normalize_mouth, mouth_opening
from lipvoice.vision.indices import SAVED_INDICES

from .test_geometry import fake_face


def raw_of(clip):
    return load_npz(clip.to_npz())


def test_batch_matches_scalar_normalization():
    full = np.stack([fake_face(0.5, 0.5, 1.0, 0.0, 640, 480), fake_face(0.42, 0.55, 0.7, 0.2, 640, 480)])
    pts, opening, width = normalize_batch(full[:, SAVED_INDICES], np.array(SAVED_INDICES), 640, 480)
    for f in range(2):
        assert np.allclose(pts[f], normalize_mouth(Landmarks(full[f]), 640, 480), atol=1e-9)
        assert abs(opening[f] - mouth_opening(Landmarks(full[f]), 640, 480)) < 1e-9


def test_extract_shape_and_determinism():
    rng = np.random.default_rng(0)
    clip = make_clip(rng, _templates(10)[2], 0.0, 1.0)
    cfg = FeatureConfig()
    x1, info = extract(raw_of(clip), cfg)
    x2, _ = extract(raw_of(clip), cfg)
    assert x1.shape == (64, feature_dim(cfg)) and np.array_equal(x1, x2) and np.isfinite(x1).all()
    assert 0.5 < info["active_sec"] < info["clip_sec"]


def test_leading_and_trailing_stillness_are_cut():
    """録画の始め方が違っても（前後の静止の長さが違っても）、同じ形の入力になる。"""
    tpl = _templates(10)[4]
    cfg = FeatureConfig()
    xs = []
    for seed in range(6):
        rng = np.random.default_rng(100)                      # 同じ動き
        c = make_clip(rng, tpl, 0.0, 1.0)
        # 前に静止を足す（時刻をずらす）
        pad = seed * 0.25
        raw = raw_of(c)
        raw["t_ms"] = raw["t_ms"] + int(pad * 1000)
        t0 = np.arange(0, pad, 0.033)
        if len(t0):
            for k in ("points", "blend", "opening"):
                head = np.repeat(raw[k][:1], len(t0), axis=0)
                raw[k] = np.concatenate([head, raw[k]])
            raw["valid"] = np.concatenate([np.ones(len(t0), bool), raw["valid"]])
            raw["t_ms"] = np.concatenate([(t0 * 1000).astype(np.int32), raw["t_ms"]])
        xs.append(extract(raw, cfg)[0])
    ref = xs[0]
    assert all(np.abs(x - ref).mean() < 0.05 for x in xs[1:])


def test_duration_feature_is_optional():
    rng = np.random.default_rng(1)
    raw = raw_of(make_clip(rng, _templates(10)[0], 0.0, 1.0))
    a, _ = extract(raw, FeatureConfig(use_duration=False))
    b, _ = extract(raw, FeatureConfig(use_duration=True))
    assert b.shape[1] == a.shape[1] + 1


def test_standardizer():
    x = np.random.default_rng(0).normal(5, 3, (20, 64, 4)).astype(np.float32)
    z = Standardizer.fit(x)(x)
    assert abs(z.mean()) < 1e-3 and abs(z.std() - 1) < 1e-2


class It:
    def __init__(self, d): self.date = d


def test_split_by_date():
    items = [It("d1")] * 3 + [It("d2")] * 2 + [It("d3")] * 1
    tr, ev, info = split_by_date(items)
    assert info["train_dates"] == ["d1", "d2"] and info["eval_dates"] == ["d3"] and (len(tr), len(ev)) == (5, 1)
    assert split_by_date([It("a")] * 2)[2]["eval_dates"] == []             # 1 日分しかなければ評価しない
    import pytest
    with pytest.raises(ValueError):
        split_by_date(items, eval_dates=["d2"], train_dates=["d2", "d1"])  # 重なりは拒否
    with pytest.raises(ValueError):
        split_by_date(items, eval_dates=["nope"])
    assert leave_one_day_out(items) == [(["d2", "d3"], "d1"), (["d1", "d3"], "d2"), (["d1", "d2"], "d3")]
