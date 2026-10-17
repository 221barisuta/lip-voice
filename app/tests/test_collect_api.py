"""収集の一連の流れ（開始 → 録画終了 → 確認 → 保存/撮り直し）。カメラと顔検出は偽物で置き換える。"""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from lipvoice.api.app import create_app
from lipvoice.collect import CollectSession, StateError
from lipvoice.recording.clip import RecordedClip, load_npz
from lipvoice.settings import SettingsHolder
from lipvoice.storage.store import Store
from lipvoice.vision.indices import SAVED_INDICES

TOKEN, PORT = "tok", 8765
H = {"X-LipVoice-Token": TOKEN}


def make_clip(stop="still", n=60, valid_ratio=1.0) -> RecordedClip:
    valid = np.arange(n) < int(n * valid_ratio)
    return RecordedClip(
        t_ms=(np.arange(n) * 33).astype(np.int32), points=np.random.rand(n, len(SAVED_INDICES), 3).astype(np.float32),
        valid=valid, blend=np.random.rand(n, 52).astype(np.float32), opening=np.random.rand(n).astype(np.float32),
        crops=[(np.random.rand(96, 96) * 255).astype(np.uint8) for _ in range(n)],
        blend_names=[f"b{i}" for i in range(52)], width=640, height=480, stop_reason=stop)


class FakeEngine:
    def __init__(self, collect):
        self.collect, self.face = collect, True

    def snapshot(self):
        from lipvoice.engine import LiveState
        return LiveState(camera="ok", face_found=self.face)

    def request_start(self):
        if not self.face:
            raise StateError("顔が検出できていません")
        return self.collect.begin()

    def set_full_preview(self, on):
        pass

    def cancel(self):
        self.collect.cancel_recording()


@pytest.fixture
def env(paths):
    holder = SettingsHolder(paths.config)
    store = Store(paths, holder.get)          # 本番と同じく、画面・保存・収集が同じ設定を見る
    collect = CollectSession(store, holder.get)
    eng = FakeEngine(collect)
    app = create_app(eng, store, collect, holder, port=PORT, token=TOKEN)
    yield TestClient(app, base_url=f"http://127.0.0.1:{PORT}"), collect, eng, store
    store.close()


def test_record_review_save(env):
    c, collect, _, store = env
    phrase = c.get("/api/collect/state", headers=H).json()["phrase"]
    assert c.post("/api/collect/start", headers=H).json()["phase"] == "recording"
    collect.finish(make_clip())                          # エンジンが録画を終えた
    st = c.get("/api/collect/state", headers=H).json()
    assert st["phase"] == "review" and st["pending"]["savable"]
    assert c.get("/api/collect/pending/video", headers=H).content[:4] == b"\x1a\x45\xdf\xa3"   # webm
    r = c.post("/api/collect/save", headers=H).json()
    assert r["phase"] == "idle" and r["stats"]["today"] == 1 and r["stats"]["per_phrase"] == {phrase["id"]: 1}
    row = store.clip_rows()[0]
    z = load_npz(str(store.clip_path(row["landmarks_path"])))
    assert z["points"].shape == (60, len(SAVED_INDICES), 3) and list(z["indices"]) == SAVED_INDICES
    assert store.clip_path(row["video_path"]).exists()


def test_retake_does_not_save(env):
    c, collect, _, store = env
    c.post("/api/collect/start", headers=H)
    collect.finish(make_clip())
    assert c.post("/api/collect/discard", headers=H).json()["phase"] == "idle"
    assert store.stats()["total"] == 0


def test_no_motion_and_low_detection_cannot_be_saved(env):
    c, collect, _, _ = env
    for clip, msg in ((make_clip("no_motion"), "動き"), (make_clip(valid_ratio=0.5), "顔")):
        c.post("/api/collect/start", headers=H)
        collect.finish(clip)
        assert not c.get("/api/collect/state", headers=H).json()["pending"]["savable"]
        r = c.post("/api/collect/save", headers=H)
        assert r.status_code == 409 and msg in r.json()["detail"]
        c.post("/api/collect/discard", headers=H)


def test_start_requires_face_and_idle(env):
    c, _, eng, _ = env
    eng.face = False
    assert c.post("/api/collect/start", headers=H).status_code == 409
    eng.face = True
    assert c.post("/api/collect/start", headers=H).status_code == 200
    assert c.post("/api/collect/start", headers=H).status_code == 409     # 録画中は二重に始められない


def test_negative_mode(env):
    c, collect, _, store = env
    assert c.post("/api/collect/mode", headers=H, json={"mode": "negative", "negative_label": "咳"}).status_code == 200
    c.post("/api/collect/start", headers=H)
    collect.finish(make_clip())
    c.post("/api/collect/save", headers=H)
    assert store.stats()["negatives"] == {"咳": 1} and store.stats()["per_phrase"] == {}


def test_phrases_and_settings_roundtrip(env):
    c, *_ = env
    assert len(c.get("/api/phrases", headers=H).json()["phrases"]) == 10
    long = {"id": "x1", "text": "お水を一口ください、それから体の向きを少し変えてください"}
    assert c.put("/api/phrases", headers=H, json={"phrases": [long]}).status_code == 200
    assert c.put("/api/phrases", headers=H, json={"phrases": [{"id": "../a", "text": "x"}]}).status_code == 422
    s = c.put("/api/settings", headers=H, json={"threshold": 0.02, "max_sec": 12}).json()["settings"]
    assert s["threshold"] == 0.02 and s["max_sec"] == 12.0
    assert c.put("/api/settings", headers=H, json={"threshold": 99}).json()["settings"]["threshold"] == 0.05


def test_session_times_out(store, paths):
    holder = SettingsHolder(paths.config)
    t = [0.0]
    collect = CollectSession(store, holder.get, clock=lambda: t[0])
    collect.begin()
    collect.cancel_recording()
    t[0] = 301
    collect.tick()
    assert collect.snapshot()["phase"] == "ended"
    collect.new_session()
    assert collect.snapshot()["phase"] == "idle"


def test_test_day_override_and_auto_save(env, paths):
    c, collect, _, store = env
    c.put("/api/settings", headers=H, json={"date_override": "day2", "auto_save": True})
    c.post("/api/collect/start", headers=H)
    collect.finish(make_clip())                          # 自動保存されて、確認なしで idle に戻る
    st = c.get("/api/collect/state", headers=H).json()
    assert st["phase"] == "idle" and st["last_saved"]["n"] == 1 and st["date"] == "day2"
    assert store.clip_rows()[0]["date"] == "day2"
    c.put("/api/settings", headers=H, json={"date_override": "bad value!"})
    assert c.get("/api/settings", headers=H).json()["settings"]["date_override"] == ""


def test_review_is_not_discarded_by_session_timeout(store, paths):
    """確認中（保存前）の録画は、セッションの時間切れで消えない。"""
    holder = SettingsHolder(paths.config)
    t = [0.0]
    collect = CollectSession(store, holder.get, clock=lambda: t[0])
    collect.begin()
    collect.finish(make_clip())
    t[0] = 10_000
    collect.tick()
    assert collect.snapshot()["phase"] == "review" and collect.pending is not None


def test_undo_skip_cancel(env):
    c, collect, _, store = env
    first = c.get("/api/collect/state", headers=H).json()["phrase"]
    c.post("/api/collect/start", headers=H)
    collect.finish(make_clip())
    c.post("/api/collect/save", headers=H)
    assert store.stats()["total"] == 1
    r = c.post("/api/collect/undo", headers=H).json()                # 取り消し: 消えて、同じフレーズがもう一度出る
    assert store.stats()["total"] == 0 and r["phrase"]["id"] == first["id"]
    assert not [p for p in store.paths.clips.rglob("*") if p.is_file()]
    assert c.post("/api/collect/undo", headers=H).status_code == 409
    nxt = c.post("/api/collect/skip", headers=H).json()["phrase"]
    assert nxt["id"] != first["id"]
    c.post("/api/collect/start", headers=H)
    assert c.post("/api/collect/cancel", headers=H).status_code == 200


def test_camera_settings_cannot_be_changed_from_the_page(env):
    c, *_ = env
    c.put("/api/settings", headers=H, json={"camera_source": "/etc/passwd", "threshold": 0.02})
    s = c.get("/api/settings", headers=H).json()["settings"]
    assert s["camera_source"] == "0" and s["threshold"] == 0.02


def test_security_headers_are_sent(env):
    c, *_ = env
    r = c.get("/api/health", headers=H)
    assert r.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert c.get("/api/health").headers["x-content-type-options"] == "nosniff"      # 403 の応答にも付く
