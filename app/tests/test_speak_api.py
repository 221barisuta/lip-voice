"""認識（テスト用の手動操作）→ 候補 → 選択 → 保存、評価画面の API。"""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from lipvoice.api.app import create_app
from lipvoice.collect import CollectSession, StateError
from lipvoice.ml.features import FeatureConfig
from lipvoice.ml.synthetic import _templates, generate_into_store, make_clip
from lipvoice.ml.train import run_training
from lipvoice.settings import SettingsHolder
from lipvoice.speak import SpeakSession
from lipvoice.storage.store import Store

TOKEN, PORT = "tok", 8765
H = {"X-LipVoice-Token": TOKEN}
PHRASES = ["p01", "p02", "p03", "p04"]


class FakeEngine:
    def __init__(self, collect, speak):
        self.collect, self.speak = collect, speak

    def snapshot(self):
        from lipvoice.engine import LiveState
        return LiveState(camera="ok", face_found=True)

    def request_start(self, which="collect"):
        return (self.speak if which == "speak" else self.collect).begin()

    def set_full_preview(self, on):
        pass


@pytest.fixture
def env(paths):
    holder = SettingsHolder(paths.config)
    store = Store(paths, holder.get)
    generate_into_store(store, [4, 4, 3], PHRASES, {"あくび": 5, "咳": 5}, seed=1)
    run_training(store, paths, FeatureConfig(), use_cnn=False, log=lambda *_: None)
    collect = CollectSession(store, holder.get)
    speak = SpeakSession(store, holder.get, paths.models)
    app = create_app(FakeEngine(collect, speak), store, collect, holder, port=PORT, token=TOKEN, speak=speak,
                     models_root=paths.models)
    yield TestClient(app, base_url=f"http://127.0.0.1:{PORT}"), speak, store, paths
    store.close()


def real_clip(label_index=0, seed=5):
    return make_clip(np.random.default_rng(seed), _templates(len(PHRASES))[label_index], 0.0, 1.0)


def test_candidates_choose_and_save(env):
    c, speak, store, _ = env
    n0 = store.stats()["total"]
    assert c.post("/api/speak/start", headers=H).json()["phase"] == "recording"
    speak.finish(real_clip(2))                                     # エンジンが録画を終えた
    st = c.get("/api/speak/state", headers=H).json()
    cands = st["result"]["candidates"]
    assert st["phase"] == "result" and len(cands) == 3 and {"text", "confidence", "phrase_id"} <= set(cands[0])
    assert cands[0]["phrase_id"] == "p03"                          # 合成データは、同じフレーズ 3 番目の動き
    r = c.post("/api/speak/choose", headers=H, json={"phrase_id": cands[0]["phrase_id"]}).json()
    assert r["phase"] == "idle" and r["choice"]["phrase_id"] == "p03" and r["choice"]["text"]
    assert store.stats()["total"] == n0 + 1
    row = [x for x in store.clip_rows() if x["source"] == "use"][0]
    assert row["phrase_id"] == "p03"
    ru = c.get("/api/report", headers=H).json()["real_use"]
    assert ru[0]["n"] == 1 and ru[0]["top1"] == 1 and ru[0]["top3"] == 1


def test_wrong_candidate_is_recorded_as_miss(env):
    c, speak, _, _ = env
    c.post("/api/speak/start", headers=H)
    speak.finish(real_clip(0))
    c.post("/api/speak/choose", headers=H, json={"phrase_id": "p04"})        # 「どれも違う」→ 正しいフレーズを選ぶ
    ru = c.get("/api/report", headers=H).json()["real_use"][0]
    assert ru["n"] == 1 and ru["top1"] == 0


def test_not_a_phrase_is_saved_as_negative_and_skip_saves_nothing(env):
    c, speak, store, _ = env
    c.post("/api/speak/start", headers=H); speak.finish(real_clip(1))
    c.post("/api/speak/choose", headers=H, json={"negative": True})
    assert store.stats()["negatives"].get("実使用の誤検知") == 1
    n = store.stats()["total"]
    c.post("/api/speak/start", headers=H); speak.finish(real_clip(1))
    c.post("/api/speak/skip", headers=H)
    assert store.stats()["total"] == n


def test_no_motion_gives_no_candidates(env):
    c, speak, _, _ = env
    c.post("/api/speak/start", headers=H)
    clip = real_clip(0); clip.stop_reason = "no_motion"
    speak.finish(clip)
    st = c.get("/api/speak/state", headers=H).json()
    assert st["result"]["no_motion"] and "candidates" not in st["result"]


def test_no_model_says_to_train_first(paths):
    holder = SettingsHolder(paths.config)
    store = Store(paths, holder.get)
    speak = SpeakSession(store, holder.get, paths.models)
    with pytest.raises(StateError, match="学習"):
        speak.begin()
    store.close()


def test_report_and_rollback(env):
    c, speak, _, paths = env
    r = c.get("/api/report", headers=H).json()
    assert r["report"]["evaluated"] and r["models"]["active"] == r["report"]["version"]
    assert c.post("/api/models/activate", headers=H, json={"version": "nope"}).status_code == 409
    assert c.post("/api/models/activate", headers=H, json={"version": r["models"]["active"]}).status_code == 200
