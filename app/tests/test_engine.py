"""エンジンの録画の流れ。カメラと顔検出を偽物にして、口が止まって 1 秒で終わることを確かめる。"""
import time

import numpy as np

from lipvoice.capture.base import Frame
from lipvoice.collect import CollectSession
from lipvoice.engine import Engine
from lipvoice.settings import SettingsHolder
from lipvoice.vision.landmarker import Detection

from .test_geometry import fake_face


class FakeSource:
    description = "偽のカメラ"

    def __init__(self):
        self.t0 = time.monotonic()
        self.speak_from = self.speak_to = None     # 口を動かす区間（秒、生成からの相対）

    def read(self):
        time.sleep(0.01)
        return Frame(np.zeros((480, 640, 3), np.uint8), time.monotonic())

    def close(self):
        pass


class FakeDetector:
    def __init__(self, _model, source: FakeSource):
        self.source, self.blend_names = source, [f"b{i}" for i in range(52)]

    def detect(self, frame, ts_ms):
        s = self.source
        t = time.monotonic() - s.t0
        gap = 0.02
        if s.speak_from is not None and s.speak_from <= t < s.speak_to:
            gap = 0.08 + 0.07 * np.sin(t * 12)
        face = fake_face(0.5, 0.5, 1.0, 0.0, 640, 480)
        face[14] = face[13] + np.array([0.0, gap, 0.0])        # 下唇を動かす（口の開き）
        return Detection(face.astype(np.float32), np.zeros(52, np.float32))

    def close(self):
        pass


def make(store, paths, source):
    holder = SettingsHolder(paths.config)
    holder.update({"still_sec": 0.5, "max_sec": 4})
    collect = CollectSession(store, holder.get)
    paths.model_file.write_bytes(b"x")
    eng = Engine(paths.model_file, holder.get, collect, detector_factory=lambda m, **kw: FakeDetector(m, source),
                 source_factory=lambda s: source)
    return eng, collect


def wait(cond, timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_records_until_mouth_stops(store, paths):
    src = FakeSource()
    eng, collect = make(store, paths, src)
    eng.start()
    try:
        assert wait(lambda: eng.snapshot().face_found)
        now = time.monotonic() - src.t0
        src.speak_from, src.speak_to = now + 0.3, now + 1.3         # 1 秒だけ話す
        eng.request_start()
        assert wait(lambda: collect.snapshot()["phase"] == "review", 8)
        p = collect.snapshot()["pending"]
        assert p["stop_reason"] == "still" and 1.5 < p["duration_ms"] / 1000 < 3.4 and p["savable"]
        clip = collect.pending.clip
        assert clip.valid.all() and clip.points.shape[1:] == (110, 3) and len(clip.crops) == clip.frame_count
        collect.save()
        assert store.stats()["total"] == 1
    finally:
        eng.stop()


def test_no_motion_ends_at_max_and_cannot_be_saved(store, paths):
    eng, collect = make(store, paths, FakeSource())
    eng.start()
    try:
        assert wait(lambda: eng.snapshot().face_found)
        eng.request_start()
        assert wait(lambda: collect.snapshot()["phase"] == "review", 8)
        p = collect.snapshot()["pending"]
        assert p["stop_reason"] == "no_motion" and not p["savable"] and 3.8 < p["duration_ms"] / 1000 < 5.2
    finally:
        eng.stop()


def test_camera_error_is_reported_and_start_refused(store, paths):
    holder = SettingsHolder(paths.config)
    collect = CollectSession(store, holder.get)

    def boom(_s):
        raise OSError("カメラを開けません")

    eng = Engine(paths.model_file, holder.get, collect, detector_factory=lambda m, **kw: None, source_factory=boom)
    paths.model_file.write_bytes(b"x")
    eng.start()
    try:
        assert wait(lambda: eng.snapshot().camera == "error")
        import pytest
        from lipvoice.collect import StateError
        with pytest.raises(StateError):
            eng.request_start()
    finally:
        eng.stop()


def test_camera_death_right_after_start_does_not_leave_recording_stuck(store, paths):
    """録画を始めた直後にカメラが止まっても、「録画中」から戻る（患者さんの努力を無駄にしない）。"""
    class DyingSource(FakeSource):
        def __init__(self):
            super().__init__()
            self.alive = True

        def read(self):
            return super().read() if self.alive else None

    src = DyingSource()
    eng, collect = make(store, paths, src)
    eng.start()
    try:
        assert wait(lambda: eng.snapshot().face_found)
        src.alive = False
        eng.request_start()                              # カメラが死んだ直後に開始が押された
        assert wait(lambda: collect.snapshot()["phase"] == "idle", 8)
        assert eng.snapshot().camera == "error"
    finally:
        eng.stop()
