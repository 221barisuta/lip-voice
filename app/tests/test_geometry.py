import numpy as np

from lipvoice.vision.geometry import Landmarks, mouth_opening, normalize_mouth
from lipvoice.vision.indices import LIP_INDICES, SAVED_INDICES


def fake_face(cx, cy, scale, rot, w, h):
    """仮顔。画素空間で (cx, cy) に置き、scale 倍し、rot だけ傾けてから 0〜1 に正規化する。"""
    pts = np.zeros((478, 3))

    def put(i, x, y, z=0.0):
        c, s = np.cos(rot), np.sin(rot)
        px = cx * w + scale * h * (x * c - y * s)
        py = cy * h + scale * h * (x * s + y * c)
        pts[i] = (px / w, py / h, z * scale * h / w)

    put(33, -0.10, -0.1); put(263, 0.10, -0.1)    # 目尻
    put(61, -0.04, 0.12); put(291, 0.04, 0.12)    # 口角
    put(13, 0.0, 0.11); put(14, 0.0, 0.13)        # 内側の上唇・下唇
    for k, i in enumerate(LIP_INDICES):
        if i not in (61, 291, 13, 14):
            put(i, -0.03 + 0.0015 * k, 0.12 + 0.01 * (k % 3), 0.01)
    return pts


def test_invariant_to_position_scale_rotation():
    w, h = 640, 480
    a = normalize_mouth(Landmarks(fake_face(0.5, 0.5, 1, 0, w, h)), w, h)
    b = normalize_mouth(Landmarks(fake_face(0.4, 0.55, 0.6, 0.3, w, h)), w, h)
    assert np.allclose(a, b, atol=0.05)


def test_mouth_center_is_origin():
    p = normalize_mouth(Landmarks(fake_face(0.5, 0.5, 1, 0, 640, 480)), 640, 480)
    l, r = p[LIP_INDICES.index(61)], p[LIP_INDICES.index(291)]
    assert abs((l[0] + r[0]) / 2) < 1e-9 and abs((l[1] + r[1]) / 2) < 1e-9


def test_opening_is_scale_invariant():
    a = mouth_opening(Landmarks(fake_face(0.5, 0.5, 1.0, 0.0, 640, 480)), 640, 480)
    b = mouth_opening(Landmarks(fake_face(0.4, 0.6, 0.5, 0.2, 640, 480)), 640, 480)
    assert abs(a - b) < 1e-6 and abs(a - 0.02 / 0.2) < 1e-6


def test_same_result_from_saved_subset():
    """保存した約 110 点だけからでも、478 点全部と同じ結果になる。"""
    full = fake_face(0.45, 0.5, 0.8, 0.1, 640, 480)
    sub = Landmarks(full[SAVED_INDICES], SAVED_INDICES)
    assert np.allclose(normalize_mouth(Landmarks(full), 640, 480), normalize_mouth(sub, 640, 480))
