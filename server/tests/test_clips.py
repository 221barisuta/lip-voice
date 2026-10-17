import json

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64
LM = json.dumps({"frames": [{"t": 0, "points": []}]}).encode()


def post(c, meta=None, lm=LM, video=WEBM):
    meta = meta or {"phrase_id": "p01", "session_id": "s1"}
    return c.post("/clips", data={"meta": json.dumps(meta)},
                  files={"landmarks": ("l.json", lm, "application/json"),
                         "video": ("v.webm", video, "video/webm")})


def test_save_clip(as_user, fake):
    r = post(as_user("alice"))
    assert r.status_code == 201
    body = r.json()
    assert body["video_path"].startswith("users/alice/clips/")
    assert body["landmarks_path"] in fake.blobs and body["video_path"] in fake.blobs


def test_body_uid_is_ignored(as_user, fake):
    # 本文に uid を入れても保存先はトークンの uid
    r = post(as_user("alice"), meta={"phrase_id": "p01", "session_id": "s1", "uid": "bob"})
    assert r.status_code == 201
    assert "bob" not in r.json()["video_path"]
    assert "bob" not in fake.clips


def test_unknown_phrase_rejected(as_user, fake):
    assert post(as_user("alice"), meta={"phrase_id": "zzz", "session_id": "s1"}).status_code == 422


def test_other_users_phrase_rejected(as_user, fake):
    as_user("bob").put("/phrases", json={"phrases": [{"id": "only_bob", "text": "x"}]})
    r = post(as_user("alice"), meta={"phrase_id": "only_bob", "session_id": "s1"})
    assert r.status_code == 422


def test_path_traversal_ids_rejected(as_user, fake):
    for bad in ("../x", "a/b", "a b", ""):
        assert post(as_user("alice"), meta={"phrase_id": bad, "session_id": "s1"}).status_code == 422
        assert post(as_user("alice"), meta={"phrase_id": "p01", "session_id": bad}).status_code == 422


def test_bad_files_rejected(as_user, fake):
    c = as_user("alice")
    assert post(c, video=b"not webm").status_code == 422
    assert post(c, lm=b"not json").status_code == 422
    assert post(c, lm=b'{"frames": []}').status_code == 422
    assert post(c, lm=b'[1,2]').status_code == 422


def test_oversize_rejected(as_user, fake):
    assert post(as_user("alice"), video=WEBM + b"\0" * (5 * 1024 * 1024)).status_code == 413


def test_daily_cap(as_user, fake, monkeypatch):
    import routes.clips as clips
    monkeypatch.setattr(clips, "MAX_CLIPS_PER_DAY", 2)
    c = as_user("alice")
    assert post(c).status_code == 201
    assert post(c).status_code == 201
    assert post(c).status_code == 429


def test_stats_per_user(as_user, fake):
    post(as_user("alice"))
    assert as_user("alice").get("/clips/stats").json()["per_phrase"] == {"p01": 1}
    assert as_user("bob").get("/clips/stats").json()["per_phrase"] == {}


def frames(n):
    return json.dumps({"frames": [{"t": i * 33, "points": None, "blend": None} for i in range(n)]}).encode()


def test_variable_length_clip_with_duration_meta(as_user, fake):
    # 10 秒 × 30fps = 300 フレームの可変長録画
    meta = {"phrase_id": "p01", "session_id": "s1", "frame_count": 300,
            "duration_ms": 10000, "stop_reason": "max"}
    assert post(as_user("alice"), meta=meta, lm=frames(300)).status_code == 201


def test_too_many_frames_rejected(as_user, fake):
    assert post(as_user("alice"), lm=frames(901)).status_code == 422


def test_bad_stop_reason_rejected(as_user, fake):
    meta = {"phrase_id": "p01", "session_id": "s1", "stop_reason": "whatever"}
    assert post(as_user("alice"), meta=meta).status_code == 422
