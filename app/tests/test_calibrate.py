import random

from lipvoice.calibrate import Calibration, Sampler, suggest


def _noise(n, level, seed=0):
    r = random.Random(seed)
    return [abs(r.gauss(level, level / 4)) for _ in range(n)]


def test_clear_separation_is_ok():
    sug = suggest(_noise(100, 0.004), _noise(100, 0.08, 1), 1.5)
    assert sug["grade"] == "ok"
    assert 0.004 < sug["threshold"] < 0.02
    assert sug["snr"] >= 3 and not sug["warnings"]


def test_small_movement_is_not_ok():
    sug = suggest(_noise(100, 0.004), _noise(100, 0.006, 1), 1.5)
    assert sug["grade"] == "ng" and sug["warnings"]


def test_conditional_snr():
    sug = suggest([0.01] * 50, [0.026] * 50, 1.0)     # SNR 2.6
    assert sug["grade"] == "conditional"


def test_noisy_still_warns():
    sug = suggest([0.03] * 50, None, 1.0)
    assert sug["grade"] == "partial" and any("静止" in w for w in sug["warnings"])


def test_too_short_measurement():
    assert suggest([0.01] * 5, None, 1.0)["grade"] == "ng"
    assert suggest([0.01] * 50, [0.1] * 3, 1.0)["grade"] == "ng"


def test_threshold_is_clamped_to_limits():
    assert suggest([0.0] * 50, None, 1.0)["threshold"] == 0.002
    assert suggest([0.5] * 50, None, 1.0)["threshold"] == 0.05


def test_sampler_skips_settling_and_ends():
    sm = Sampler("still", 3.0)
    done = [sm.add(i * 0.1, 0.01) for i in range(40)]
    assert done.index(True) == 30 and len(sm.samples) >= 19      # 最初の 1 秒は除く
    sm2 = Sampler("still", 2.0)
    for i in range(30):
        sm2.add(i * 0.1, None)                                   # 顔が検出できなければ、サンプルは貯まらない
    assert sm2.samples == [] and sm2.faces == 0


def test_calibration_flow_through_phases():
    c = Calibration()
    c.start("still", 3.0, 1.5)
    for i in range(50):
        c.feed(i * 0.1, 0.004)
    assert c.snapshot()["running"] is False and c.snapshot()["result"]["grade"] == "partial"
    c.start("speech", 3.0, 1.5)
    assert c.snapshot()["running"] and c.snapshot()["phase"] == "speech"
    for i in range(60):
        c.feed(i * 0.1, 0.1)
    snap = c.snapshot()
    assert not snap["running"] and snap["result"]["grade"] == "ok" and snap["face_ratio"] == 1.0
    c.start("still", 3.0, 1.5)                                   # 静止からやり直すと、前の結果は消える
    assert "result" not in c.snapshot()


def test_noisy_but_clear_movement_is_ok_without_noise_warning():
    sug = suggest([0.016] * 60, [0.14] * 60, 1.0)          # 実機で見た値（ノイズ 0.016、動き 0.14）
    assert sug["grade"] == "ok" and not sug["warnings"] and sug["threshold"] > 0.02
    bad = suggest([0.03] * 60, [0.05] * 60, 1.0)
    assert bad["grade"] == "ng" and any("静止" in w for w in bad["warnings"])
