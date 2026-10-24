"""フレーズの追加・編集・削除の規則（録画のあるフレーズを消せない、番号を戻さない、最後の 1 件は消せない）と、続けて録るモード。"""
import pytest
from fastapi.testclient import TestClient

from lipvoice.api.app import create_app
from lipvoice.collect import CollectSession, StateError
from lipvoice.settings import SettingsHolder
from lipvoice.storage.store import Store

from .test_collect_api import H, PORT, TOKEN, FakeEngine, make_clip


@pytest.fixture
def env(paths):
    holder = SettingsHolder(paths.config)
    store = Store(paths, holder.get)
    collect = CollectSession(store, holder.get)
    app = create_app(FakeEngine(collect), store, collect, holder, port=PORT, token=TOKEN, models_root=paths.models)
    yield TestClient(app, base_url=f"http://127.0.0.1:{PORT}"), collect, store, holder
    store.close()


def save_one(c, collect):
    c.post("/api/collect/start", headers=H)
    collect.finish(make_clip())
    c.post("/api/collect/save", headers=H)


def test_add_assigns_new_ids_and_never_reuses_them(env):
    c, _, store, _ = env
    n0 = len(store.phrases())
    a = c.post("/api/phrases", headers=H, json={"text": "水がほしい"}).json()["added"]
    assert a["id"] == f"p{n0 + 1:02d}" and store.phrases()[-1] == a
    c.put("/api/phrases", headers=H, json={"phrases": [p for p in store.phrases() if p["id"] != a["id"]]})   # 0 本なので消せる
    b = c.post("/api/phrases", headers=H, json={"text": "電気をつけて"}).json()["added"]
    assert b["id"] != a["id"] and int(b["id"][1:]) > int(a["id"][1:])


def test_add_rejects_empty_duplicate_and_over_limit(env):
    c, _, store, holder = env
    assert c.post("/api/phrases", headers=H, json={"text": "  "}).status_code == 422
    assert c.post("/api/phrases", headers=H, json={"text": store.phrases()[0]["text"]}).status_code == 422
    holder.update({})
    store._settings = lambda: type("S", (), {"max_phrases": len(store.phrases()), "max_phrase_chars": 200})()
    assert c.post("/api/phrases", headers=H, json={"text": "新しい"}).status_code == 422


def test_phrases_with_clips_cannot_be_removed_by_any_route(env):
    c, collect, store, _ = env
    save_one(c, collect)
    used = c.get("/api/collect/state", headers=H).json()["stats"]["per_phrase"]
    pid = next(iter(used))
    rest = [p for p in store.phrases() if p["id"] != pid]
    r = c.put("/api/phrases", headers=H, json={"phrases": rest})
    assert r.status_code == 422 and "録画のあるフレーズ" in r.json()["detail"]
    assert any(p["id"] == pid for p in store.phrases())
    # テキストの修正と並べ替えはできる
    edited = [{**p, "text": p["text"] + "！"} if p["id"] == pid else p for p in reversed(store.phrases())]
    assert c.put("/api/phrases", headers=H, json={"phrases": edited}).status_code == 200


def test_last_phrase_cannot_be_removed(env):
    c, _, store, _ = env
    assert c.put("/api/phrases", headers=H, json={"phrases": []}).status_code == 422


def test_phrase_info_counts_clips_days_and_model(env):
    c, collect, store, _ = env
    save_one(c, collect)
    info = c.get("/api/phrases/info", headers=H).json()["phrases"]
    assert sum(p["clips"] for p in info) == 1 and max(p["days"] for p in info) == 1 and not any(p["in_model"] for p in info)


def test_focus_mode_repeats_the_phrase_and_clears_when_deleted(env):
    c, collect, store, _ = env
    new = c.post("/api/phrases", headers=H, json={"text": "水がほしい"}).json()["added"]
    st = c.post("/api/collect/focus", headers=H, json={"phrase_id": new["id"]}).json()
    assert st["focus"] == new["id"] and st["phrase"]["id"] == new["id"]
    for _ in range(3):
        save_one(c, collect)
        assert collect.snapshot()["phrase"]["id"] == new["id"]
    c.post("/api/collect/skip", headers=H)
    assert collect.snapshot()["phrase"]["id"] == new["id"]          # 続けて録っている間は、スキップしても変わらない
    assert c.post("/api/collect/focus", headers=H, json={"phrase_id": "nope"}).status_code == 409
    assert c.post("/api/collect/focus", headers=H, json={"phrase_id": None}).json()["focus"] is None


def test_phrase_edits_during_review_are_applied_after_saving(env):
    c, collect, store, _ = env
    c.post("/api/collect/start", headers=H)
    collect.finish(make_clip())                                      # 確認中
    c.post("/api/phrases", headers=H, json={"text": "水がほしい"})
    assert all(p["text"] != "水がほしい" for p in collect.snapshot()["phrases"])      # 確認中は、まだ古い一覧
    c.post("/api/collect/discard", headers=H)
    assert any(p["text"] == "水がほしい" for p in collect.snapshot()["phrases"])       # 待機に戻ったら反映
    with pytest.raises(StateError):
        c.post("/api/collect/start", headers=H); collect.set_focus(None)             # 録画中は変えられない
