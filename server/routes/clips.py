import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

import store
from auth import current_uid
from schemas import ClipMeta

router = APIRouter()

# 録画は可変長（口が止まるか最大 10〜15 秒で終了）。10 秒 × 30fps の特徴点 JSON は約 1MB
MAX_LANDMARKS_BYTES = 4 * 1024 * 1024
MAX_VIDEO_BYTES = 5 * 1024 * 1024       # 96×96 の webm は 10 秒でも 1MB 未満
MAX_FRAMES = 900                        # 15 秒 × 60fps
MAX_CLIPS_PER_DAY = 500                 # 濫用（コスト）対策。通常運用は 1 日 100 本程度
EBML_MAGIC = b"\x1a\x45\xdf\xa3"        # webm (Matroska) の先頭


async def _read_limited(f: UploadFile, limit: int, label: str) -> bytes:
    data = await f.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"{label} が大きすぎます")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{label} が空です")
    return data


def _validate_landmarks(raw: bytes) -> None:
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "landmarks が JSON ではありません")
    frames = obj.get("frames") if isinstance(obj, dict) else None
    if not isinstance(frames, list) or not (1 <= len(frames) <= MAX_FRAMES):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "landmarks の形式が不正です")


@router.post("/clips", status_code=status.HTTP_201_CREATED)
async def post_clip(
    meta: str = Form(...),
    landmarks: UploadFile = File(...),
    video: UploadFile = File(...),
    uid: str = Depends(current_uid),
):
    try:
        m = ClipMeta.model_validate_json(meta)
    except ValidationError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "meta が不正です")

    landmarks_raw = await _read_limited(landmarks, MAX_LANDMARKS_BYTES, "landmarks")
    video_raw = await _read_limited(video, MAX_VIDEO_BYTES, "video")
    _validate_landmarks(landmarks_raw)
    if not video_raw.startswith(EBML_MAGIC):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "video が webm ではありません")

    # phrase_id は本人のフレーズに存在するものだけ許す
    if not await run_in_threadpool(store.phrase_exists, uid, m.phrase_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "phrase_id が存在しません")

    today = store.today_jst()
    if await run_in_threadpool(store.count_clips_on, uid, today) >= MAX_CLIPS_PER_DAY:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "本日の保存上限に達しました")

    clip_id = uuid.uuid4().hex  # サーバーで採番（クライアント指定のパスは使わない）
    paths = await run_in_threadpool(
        store.save_clip, uid, clip_id, landmarks_raw, video_raw, m.model_dump())
    return {"clip_id": clip_id, **paths}


@router.get("/clips/stats")
async def get_stats(uid: str = Depends(current_uid)):
    return await run_in_threadpool(store.clip_stats, uid)
