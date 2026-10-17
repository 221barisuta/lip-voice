import math

from lipvoice.vision.stillness import StillnessConfig, StillnessDetector

CFG = StillnessConfig(threshold=0.01, still_sec=1.0, max_sec=10)


def run(open_fn, fps=30, cfg=CFG):
    d = StillnessDetector(cfg)
    for i in range(20 * fps):
        t = i / fps
        r = d.push(t, open_fn(t))
        if r:
            return t, r
    return math.inf, None


def speak_then_still(end):
    return lambda t: 0.08 + 0.07 * math.sin(t * 12) if t < end else 0.02


def test_no_motion_until_max():
    t, r = run(lambda t: 0.02)
    assert r == "no_motion" and abs(t - 10) < 0.5


def test_stops_one_second_after_speaking():
    t, r = run(speak_then_still(2.0))
    assert r == "still" and 2.9 < t < 3.2


def test_low_fps_same_criterion():
    t, r = run(speak_then_still(2.0), fps=10)
    assert r == "still" and 2.8 <= t < 3.3


def test_continuous_speech_reaches_max():
    t, r = run(lambda t: 0.08 + 0.07 * math.sin(t * 12))
    assert r == "max" and abs(t - 10) < 0.5


def test_short_pause_does_not_end():
    t, r = run(lambda t: 0.08 + 0.07 * math.sin(t * 12) if (t < 1 or 1.6 <= t < 6) else 0.02)
    assert r == "still" and t > 6.9


def test_small_noise_is_still():
    t, r = run(lambda t: 0.1 * abs(math.sin(t * 9)) if t < 1.5 else 0.02 + 0.002 * math.sin(t * 50))
    assert r == "still"


def test_threshold_changes_behavior():
    small = lambda t: 0.02 + 0.01 * math.sin(t * 12)    # 変動幅 0.02
    assert run(small, cfg=StillnessConfig(0.01, 1.0, 10))[1] == "max"
    assert run(small, cfg=StillnessConfig(0.05, 1.0, 10))[1] == "no_motion"


def test_lost_face_frames_are_ignored_but_time_advances():
    t, r = run(lambda t: 0.08 + 0.07 * math.sin(t * 12) if t < 2 else (None if t < 2.5 else 0.02))
    assert r == "still"


def test_configurable_still_and_max():
    t, _ = run(speak_then_still(2.0), cfg=StillnessConfig(0.01, 2.0, 10))
    assert t > 3.9
    t, _ = run(lambda t: 0.08, cfg=StillnessConfig(0.01, 1.0, 4))
    assert abs(t - 4) < 0.5
