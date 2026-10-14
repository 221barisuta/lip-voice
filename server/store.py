"""Firestore / GCS へのアクセスを 1 か所に集約する。

すべての関数は uid を引数に取り、パスは users/{uid}/ 以下だけに限定する。
"""
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from google.cloud import firestore, storage

import config
from initial_phrases import INITIAL_PHRASES

JST = ZoneInfo("Asia/Tokyo")


@lru_cache
def _db() -> firestore.Client:
    return firestore.Client(project=config.project_id())


@lru_cache
def _bucket() -> storage.Bucket:
    return storage.Client(project=config.project_id()).bucket(config.bucket_name())


def today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def _user(uid: str) -> firestore.DocumentReference:
    return _db().collection("users").document(uid)


# ---- phrases -------------------------------------------------------------

def get_phrases(uid: str) -> list[dict[str, Any]]:
    """フレーズ一覧を返す。初回は users/{uid} を作り初期フレーズをコピーする。"""
    user = _user(uid)
    if not user.get().exists:
        batch = _db().batch()
        batch.set(user, {"created_at": firestore.SERVER_TIMESTAMP})
        for i, p in enumerate(INITIAL_PHRASES):
            batch.set(user.collection("phrases").document(p["id"]),
                      {"text": p["text"], "order": i})
        batch.commit()
    docs = user.collection("phrases").order_by("order").stream()
    return [{"id": d.id, "text": d.get("text")} for d in docs]


def replace_phrases(uid: str, phrases: list[dict[str, str]]) -> None:
    user = _user(uid)
    col = user.collection("phrases")
    keep = {p["id"] for p in phrases}
    batch = _db().batch()
    for d in col.select([]).stream():
        if d.id not in keep:
            batch.delete(d.reference)
    for i, p in enumerate(phrases):
        batch.set(col.document(p["id"]), {"text": p["text"], "order": i})
    batch.commit()


def phrase_exists(uid: str, phrase_id: str) -> bool:
    return _user(uid).collection("phrases").document(phrase_id).get().exists


# ---- clips ---------------------------------------------------------------

def count_clips_on(uid: str, date: str) -> int:
    q = _user(uid).collection("clips").where(
        filter=firestore.FieldFilter("date", "==", date))
    return q.count().get()[0][0].value


def save_clip(uid: str, clip_id: str, landmarks_json: bytes, video_webm: bytes,
              meta: dict[str, Any]) -> dict[str, str]:
    """GCS に 2 ファイルを保存し、Firestore に記録する。"""
    prefix = f"users/{uid}/clips/{clip_id}"
    json_path, webm_path = f"{prefix}.json", f"{prefix}.webm"
    bucket = _bucket()
    bucket.blob(json_path).upload_from_string(landmarks_json, content_type="application/json")
    bucket.blob(webm_path).upload_from_string(video_webm, content_type="video/webm")
    _user(uid).collection("clips").document(clip_id).set({
        **meta,
        "date": today_jst(),
        "created_at": datetime.now(timezone.utc),
        "landmarks_path": json_path,
        "video_path": webm_path,
    })
    return {"landmarks_path": json_path, "video_path": webm_path}


def clip_stats(uid: str) -> dict[str, Any]:
    today = today_jst()
    docs = _user(uid).collection("clips").select(["phrase_id", "date"]).stream()
    per_phrase: dict[str, int] = {}
    today_count = 0
    for d in docs:
        data = d.to_dict()
        per_phrase[data["phrase_id"]] = per_phrase.get(data["phrase_id"], 0) + 1
        if data.get("date") == today:
            today_count += 1
    return {"today": today_count, "per_phrase": per_phrase}
