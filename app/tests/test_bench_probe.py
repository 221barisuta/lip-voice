"""顔が見つからない時の、映像の向きの調べ方（bench）。実機で検出率 0% だった事例への対応。"""
from types import SimpleNamespace

import numpy as np

from lipvoice.bench import probe_rotation
from lipvoice.settings import Settings
from lipvoice.vision.rotate import rotate_image


class Src:
    """上下逆に付いたカメラ: 右下だけ明るい横長の画像を返す。"""
    def __init__(self, marker="bottom_right"):
        self.t, self.marker = 0.0, marker

    def read(self):
        img = np.zeros((20, 40, 3), np.uint8)
        if self.marker == "bottom_right":
            img[-1, -1] = 255
        elif self.marker == "none":
            pass
        self.t += 0.3
        return SimpleNamespace(t=self.t, image=img)


class Det:
    """横長で、左上が明るい画像（正しい向き）だけ、顔を検出できる。"""
    def __init__(self, *a):
        pass

    def detect(self, img, ts):
        if img.shape[1] > img.shape[0] and img[0, 0, 0] == 255:
            return SimpleNamespace(roll_deg=1.0)
        if img.shape[0] > img.shape[1]:                       # 横に倒れた顔も、検出器は見つけることがある（実機・実測）
            return SimpleNamespace(roll_deg=90.0)
        return None

    def close(self):
        pass


def test_rotate_image_matches_opencv_directions():
    img = np.arange(6, dtype=np.uint8).reshape(2, 3)
    assert rotate_image(img, 0) is img
    assert rotate_image(img, 180)[0, 0] == img[-1, -1]
    assert rotate_image(img, 90).shape == (3, 2) and rotate_image(img, 270).shape == (3, 2)


def test_probe_finds_upside_down_camera():
    r = probe_rotation(Src(), "model", Settings(), make_detector=Det)
    assert r["frames"] == 12 and r["best"] == 180
    assert r["counts"][180] == 12 and r["counts"][0] == 0
    assert r["counts"][90] == 12 and r["rolls"][90] == 90.0 and r["rolls"][180] == 1.0   # 倒れた向きでは見つかるが、「立って」見えるのは 180°


def test_probe_reports_none_when_no_face_in_any_orientation():
    r = probe_rotation(Src("none"), "model", Settings(), make_detector=Det)
    assert r["best"] is None                                  # 倒れた顔（回転 90°）しか見つからない向きは、正しい向きとは言わない
    assert r["counts"][0] == 0 and r["counts"][180] == 0
