import pytest

from lipvoice.settings import sanitize, Settings
from lipvoice.storage import integrity
from lipvoice.storage.store import ClipRecord, LimitExceeded, Store


def rec(**kw):
    return ClipRecord(kind="phrase", session_id="s1", phrase_id="p01", duration_ms=3000, frame_count=90, **kw)


def test_initial_phrases_seeded(store):
    assert len(store.phrases()) == 10


def test_save_clip_writes_files_and_row(store, paths):
    cid = store.save_clip(rec(), b"NPZ", b"WEBM")
    rows = store.clip_rows()
    assert [r["id"] for r in rows] == [cid]
    assert (paths.clips / rows[0]["landmarks_path"]).read_bytes() == b"NPZ"
    assert (paths.clips / rows[0]["video_path"]).read_bytes() == b"WEBM"
    assert not list(paths.tmp.iterdir())                      # 一時ファイルは残らない
    assert integrity.check(store).ok


def test_unknown_phrase_rejected(store):
    with pytest.raises(ValueError):
        store.save_clip(ClipRecord(kind="phrase", session_id="s", phrase_id="nope"), b"a", b"b")


def test_negative_clip(store):
    store.save_clip(ClipRecord(kind="negative", session_id="s", negative_label="あくび"), b"a", b"b")
    st = store.stats()
    assert st["negatives"] == {"あくび": 1} and st["per_phrase"] == {} and st["today"] == 1


def test_failed_insert_leaves_no_files(store, paths, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("disk")
    monkeypatch.setattr(store, "count_on", lambda d: 0)
    store.db.execute("DROP TABLE clips")                       # INSERT を失敗させる
    with pytest.raises(Exception):
        store.save_clip(rec(), b"a", b"b")
    assert not [p for p in paths.clips.rglob("*") if p.is_file()]
    assert not list(paths.tmp.iterdir())


def test_daily_limit_is_configurable(paths):
    s = Settings(max_clips_per_day=2)
    st = Store(paths, lambda: s)
    st.save_clip(rec(), b"a", b"b")
    st.save_clip(rec(), b"a", b"b")
    with pytest.raises(LimitExceeded):
        st.save_clip(rec(), b"a", b"b")
    s.max_clips_per_day = 0                                    # 0 は無制限
    st.save_clip(rec(), b"a", b"b")
    st.close()


def test_integrity_finds_and_repairs(store, paths):
    cid = store.save_clip(rec(), b"a", b"b")
    row = store.clip_rows()[0]
    (paths.clips / row["video_path"]).unlink()                 # 欠損
    (paths.clips / "2026-01-01").mkdir()
    (paths.clips / "2026-01-01" / "orphan.npz").write_bytes(b"x")   # 孤児
    (paths.tmp / "z.npz.part").write_bytes(b"x")               # 書き込み途中
    r = integrity.check(store)
    assert r.missing_files == [cid] and len(r.orphan_files) >= 1 and r.stale_tmp == ["z.npz.part"]
    r2 = integrity.check(store, repair=True)
    assert r2.moved >= 1 and (paths.orphans / "2026-01-01" / "orphan.npz").exists()


def test_phrases_validation_and_limits(store):
    with pytest.raises(ValueError):
        store.replace_phrases([])
    with pytest.raises(ValueError):
        store.replace_phrases([{"id": "../x", "text": "a"}])
    with pytest.raises(ValueError):
        store.replace_phrases([{"id": "a", "text": "x"}, {"id": "a", "text": "y"}])
    long = {"id": "a", "text": "あ" * 150}                      # 長い文も既定で通る
    assert store.replace_phrases([long])[0]["id"] == "a"


def test_settings_sanitize():
    s = sanitize({"threshold": 5, "still_sec": 0, "max_sec": "x", "max_phrases": -3, "negative_kinds": ["a", " ", "b"]})
    assert s.threshold == 0.05 and s.still_sec == 0.5 and s.max_sec == 10.0
    assert s.max_phrases == 0 and s.negative_kinds == ["a", "b"]
