import numpy as np

from lipvoice.ml.dtw_baseline import DTWModel, dtw_distances


def naive_dtw(a, b, band):
    n, m = len(a), len(b)
    d = np.full((n + 1, m + 1), np.inf)
    d[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(max(1, i - band), min(m, i + band) + 1):
            c = np.linalg.norm(a[i - 1] - b[j - 1])
            d[i, j] = c + min(d[i - 1, j], d[i, j - 1], d[i - 1, j - 1])
    return d[n, m] / (n + m)


def test_matches_naive_implementation():
    rng = np.random.default_rng(0)
    q = rng.normal(size=(64, 5)).astype(np.float32)
    refs = rng.normal(size=(4, 64, 5)).astype(np.float32)
    got = dtw_distances(q, refs, 12)
    for i in range(4):
        assert abs(got[i] - naive_dtw(q, refs[i], 12)) < 1e-4


def test_identical_is_zero_and_shift_is_tolerated():
    t = np.linspace(0, 6, 64)
    a = np.stack([np.sin(t), np.cos(t)], 1).astype(np.float32)
    shifted = np.roll(a, 3, axis=0)
    assert dtw_distances(a, a[None], 12)[0] < 1e-6
    other = np.stack([np.sin(3 * t), np.cos(5 * t)], 1).astype(np.float32)
    assert dtw_distances(a, shifted[None], 12)[0] < dtw_distances(a, other[None], 12)[0]


def test_classifies_and_roundtrips():
    rng = np.random.default_rng(1)
    t = np.linspace(0, 6, 64)
    protos = {c: np.stack([np.sin((k + 1) * t), np.cos((k + 2) * t)], 1) for k, c in enumerate("abc")}
    xs, ys = [], []
    for c, p in protos.items():
        for _ in range(5):
            xs.append((p + rng.normal(0, 0.1, p.shape)).astype(np.float32)); ys.append(c)
    m = DTWModel.fit(np.stack(xs), ys)
    q = (protos["b"] + rng.normal(0, 0.1, (64, 2))).astype(np.float32)
    out = m.predict(q)
    assert out["ranked"][0] == "b" and abs(sum(out["confidence"]) - 1) < 1e-6
    m2 = DTWModel.from_npz(m.to_npz())
    assert m2.predict(q)["ranked"] == out["ranked"]
    far = (rng.normal(0, 3, (64, 2))).astype(np.float32)
    assert m.predict(far)["distance"] > out["distance"] * 3               # フレーズに似ていない動きは距離が大きい
