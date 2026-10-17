"""データ確認（一覧・動画・削除）と、閾値の校正の API。"""
import pytest
from fastapi.testclient import TestClient

from lipvoice.api.app import create_app
from lipvoice.calibrate import Calibration
from lipvoice.collect import CollectSession
from lipvoice.settings import SettingsHolder
from lipvoice.storage.store import Store

from .test_collect_api import H, PORT, TOKEN, FakeEngine, make_clip


class CalibEngine(FakeEngine):
    def __init__(self, collect, holder):
        super().__init__(collect)
        self.calibration, self._holder = Calibration(), holder

    def start_calibration(self, phase, seconds):
        self.calibration.start(phase, seconds, self._holder.get().still_sec)

    def calibration_state(self):
        return self.calibration.snapshot()


@pytest.fixture
def env(paths):
    holder = SettingsHolder(paths.config)
    store = Store(paths, holder.get)
    collect = CollectSession(store, holder.get)
    eng = CalibEngine(collect, holder)
    app = create_app(eng, store, collect, holder, port=PORT, token=TOKEN)
    yield TestClient(app, base_url=f"http://127.0.0.1:{PORT}"), collect, eng, store, holder
    store.close()


def save_one(c, collect):
    c.post("/api/collect/start", headers=H)
    collect.finish(make_clip())
    c.post("/api/collect/save", headers=H)


def test_list_video_and_delete(env):
    c, collect, _, store, _ = env
    for _ in range(3):
        save_one(c, collect)
    r = c.get("/api/clips", headers=H).json()
    assert r["total"] == 3 and len(r["clips"]) == 3 and r["dates"] == [store.today()]
    assert {"id", "label", "date", "duration_ms", "detected_ratio", "stop_reason"} <= set(r["clips"][0])
    assert "landmarks_path" not in r["clips"][0] and "video_path" not in r["clips"][0]
    cid = r["clips"][0]["id"]
    assert c.get(f"/api/clips/{cid}/video", headers=H).content[:4] == b"\x1a\x45\xdf\xa3"
    assert c.get("/api/clips?date=1999-01-01", headers=H).json()["total"] == 0
    d = c.post(f"/api/clips/{cid}/delete", headers=H).json()
    assert d["stats"]["total"] == 2 and not store.clip_rows()[0]["id"] == cid
    assert c.get(f"/api/clips/{cid}/video", headers=H).status_code == 404


def test_delete_rejects_bad_ids_and_unknown(env):
    c, *_ = env
    assert c.post("/api/clips/..%2F..%2Fetc/delete", headers=H).status_code in (404, 422)
    assert c.post("/api/clips/" + "0" * 32 + "/delete", headers=H).status_code == 422
    assert c.get("/api/clips/not-an-id/video", headers=H).status_code == 404


def test_undo_after_delete_does_not_fail(env):
    c, collect, _, store, _ = env
    save_one(c, collect)
    cid = c.get("/api/clips", headers=H).json()["clips"][0]["id"]
    c.post(f"/api/clips/{cid}/delete", headers=H)
    assert c.post("/api/collect/undo", headers=H).status_code == 409      # 取り消す対象がない（エラーにならず、状態のエラー）


def test_clips_require_token(env):
    c, *_ = env
    assert c.get("/api/clips").status_code in (401, 403)


def test_calibration_flow_and_apply(env):
    c, _, eng, _, holder = env
    assert c.post("/api/calibrate/start", headers=H, json={"phase": "still", "seconds": 3}).json()["running"]
    for i in range(50):
        eng.calibration.feed(i * 0.1, 0.004)
    st = c.get("/api/calibrate", headers=H).json()
    assert not st["running"] and st["result"]["grade"] == "partial"
    c.post("/api/calibrate/start", headers=H, json={"phase": "speech", "seconds": 3})
    for i in range(60):
        eng.calibration.feed(i * 0.1, 0.1)
    st = c.get("/api/calibrate", headers=H).json()
    assert st["result"]["grade"] == "ok"
    s = c.post("/api/calibrate/apply", headers=H, json={}).json()["settings"]
    assert s["threshold"] == s["active_threshold"] == st["result"]["threshold"]
    assert s["calibrated_still_sec"] == holder.get().still_sec
    assert c.post("/api/calibrate/start", headers=H, json={"phase": "nope"}).status_code == 422


def test_calibration_apply_without_result_is_409(env):
    c, *_ = env
    assert c.post("/api/calibrate/apply", headers=H, json={}).status_code == 409


def test_calibration_refused_while_recording(env):
    c, *_ = env
    c.post("/api/collect/start", headers=H)
    assert c.post("/api/calibrate/start", headers=H, json={"phase": "still"}).status_code == 409
