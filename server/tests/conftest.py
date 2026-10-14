import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("GCS_BUCKET", "test-bucket")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")
os.environ.setdefault("ALLOWED_EMAILS", "Dev@example.com")

import pytest
from fastapi.testclient import TestClient

import store
from auth import current_uid
from initial_phrases import INITIAL_PHRASES
from main import create_app


class FakeStore:
    """store.py の代わりに使うメモリ実装（Firestore / GCS には触れない）。"""

    def __init__(self):
        self.phrases: dict[str, list[dict]] = {}
        self.clips: dict[str, dict[str, dict]] = {}
        self.blobs: dict[str, bytes] = {}

    def get_phrases(self, uid):
        return self.phrases.setdefault(uid, [dict(p) for p in INITIAL_PHRASES])

    def replace_phrases(self, uid, phrases):
        self.phrases[uid] = phrases

    def phrase_exists(self, uid, phrase_id):
        return any(p["id"] == phrase_id for p in self.get_phrases(uid))

    def count_clips_on(self, uid, date):
        return sum(1 for c in self.clips.get(uid, {}).values() if c["date"] == date)

    def save_clip(self, uid, clip_id, landmarks_json, video_webm, meta):
        prefix = f"users/{uid}/clips/{clip_id}"
        self.blobs[prefix + ".json"] = landmarks_json
        self.blobs[prefix + ".webm"] = video_webm
        self.clips.setdefault(uid, {})[clip_id] = {**meta, "date": store.today_jst()}
        return {"landmarks_path": prefix + ".json", "video_path": prefix + ".webm"}

    def clip_stats(self, uid):
        clips = self.clips.get(uid, {}).values()
        per: dict[str, int] = {}
        for c in clips:
            per[c["phrase_id"]] = per.get(c["phrase_id"], 0) + 1
        return {"today": len(list(clips)), "per_phrase": per}


@pytest.fixture
def fake(monkeypatch):
    f = FakeStore()
    for name in ("get_phrases", "replace_phrases", "phrase_exists",
                 "count_clips_on", "save_clip", "clip_stats"):
        monkeypatch.setattr(store, name, getattr(f, name))
    return f


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def as_user(app):
    """as_user("alice") で、そのユーザーとして認証済みの TestClient を返す。"""
    def make(uid: str) -> TestClient:
        app.dependency_overrides[current_uid] = lambda: uid
        return TestClient(app)
    return make
