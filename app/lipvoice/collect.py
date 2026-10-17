"""データ収集の進行（仕様 7.1）。フレーズを順に出し、録画 → 保存/撮り直し → 次へ。1 セッションは最大 5 分（設定可）。"""
import random
import threading
import time
import uuid
from dataclasses import dataclass

from .recording.clip import RecordedClip
from .recording.encoder import encode_webm
from .settings import Settings
from .storage.store import ClipRecord, Store


class StateError(Exception):
    """いまの状態ではできない操作。"""


class PhraseQueue:
    """全フレーズをシャッフルして順に出す。一巡したら再シャッフル（境界で同じ語が続かないようにする）。"""

    def __init__(self, phrases: list[dict]):
        self._phrases, self._queue, self._last = phrases, [], None

    def next(self) -> dict:
        if not self._queue:
            self._queue = random.sample(self._phrases, len(self._phrases))
            if len(self._queue) > 1 and self._queue[0]["id"] == self._last:
                self._queue.append(self._queue.pop(0))
        p = self._queue.pop(0)
        self._last = p["id"]
        return p


@dataclass
class Pending:
    clip: RecordedClip
    npz: bytes
    webm: bytes


def unsavable_reason(clip: RecordedClip, s: Settings) -> str | None:
    if clip.stop_reason == "no_motion":
        return "口の動きが検出できませんでした。撮り直してください"
    if clip.detected_ratio < s.min_detected_ratio:
        return "顔が十分に検出できませんでした。撮り直してください"
    return None


class CollectSession:
    def __init__(self, store: Store, settings_fn, clock=time.monotonic):
        self._store, self._settings, self._clock = store, settings_fn, clock
        self._lock = threading.RLock()
        self.mode = "phrase"                 # phrase | negative
        self.negative_label: str | None = None
        self.phase = "idle"                  # idle | recording | review | ended
        self.target: dict | None = None
        self.pending: Pending | None = None
        self._queue = PhraseQueue(store.phrases())
        self._started_at: float | None = None
        self.session_id = uuid.uuid4().hex
        self._phrase = self._queue.next()
        self._stats = store.stats()

    # ---- 操作 ----
    def new_session(self) -> None:
        with self._lock:
            self.session_id = uuid.uuid4().hex
            self._started_at, self.pending, self.phase = None, None, "idle"
            self._reload_phrases()

    def set_mode(self, mode: str, negative_label: str | None = None) -> None:
        with self._lock:
            if self.phase not in ("idle",):
                raise StateError("録画中・確認中はモードを変えられません")
            if mode not in ("phrase", "negative"):
                raise StateError("モードが不正です")
            if mode == "negative":
                kinds = self._settings().negative_kinds
                self.negative_label = negative_label if negative_label in kinds else kinds[0]
            self.mode = mode

    def begin(self) -> dict:
        with self._lock:
            if self.phase != "idle":
                raise StateError("いまは録画を始められません")
            self._started_at = self._started_at if self._started_at is not None else self._clock()
            self.target = ({"kind": "phrase", "phrase": self._phrase} if self.mode == "phrase"
                           else {"kind": "negative", "label": self.negative_label})
            self.phase = "recording"
            return self.target

    def cancel_recording(self) -> None:
        with self._lock:
            if self.phase == "recording":
                self.phase = "idle"

    def finish(self, clip: RecordedClip) -> None:
        pending = Pending(clip, clip.to_npz(), encode_webm(clip.crops, clip.t_ms))
        with self._lock:
            self.pending, self.phase = pending, "review"

    def discard(self) -> None:
        with self._lock:
            if self.phase != "review":
                raise StateError("撮り直せる録画がありません")
            self.pending, self.phase = None, "idle"

    def save(self) -> str:
        with self._lock:
            if self.phase != "review" or not self.pending:
                raise StateError("保存できる録画がありません")
            clip = self.pending.clip
            reason = unsavable_reason(clip, self._settings())
            if reason:
                raise StateError(reason)
            t = self.target or {}
            rec = ClipRecord(
                kind=t.get("kind", "phrase"), session_id=self.session_id,
                phrase_id=t["phrase"]["id"] if t.get("kind") == "phrase" else None,
                negative_label=t.get("label") if t.get("kind") == "negative" else None,
                duration_ms=clip.duration_ms, frame_count=clip.frame_count, fps_measured=clip.fps_measured,
                detected_ratio=clip.detected_ratio, stop_reason=clip.stop_reason, width=clip.width, height=clip.height)
            clip_id = self._store.save_clip(rec, self.pending.npz, self.pending.webm)
            self._stats = self._store.stats()
            self.pending, self.phase = None, "idle"
            if rec.kind == "phrase":
                self._phrase = self._queue.next()
            return clip_id

    def tick(self) -> None:
        """5 分（設定可）で自動終了。録画中は録画が終わるまで待つ。"""
        with self._lock:
            if self._started_at is None or self.phase in ("recording", "ended"):
                return
            if self._clock() - self._started_at >= self._settings().session_minutes * 60:
                self.pending, self.phase = None, "ended"

    def _reload_phrases(self) -> None:
        self._queue = PhraseQueue(self._store.phrases())
        self._phrase = self._queue.next()

    def phrases_changed(self) -> None:
        with self._lock:
            if self.phase in ("idle", "ended"):
                self._reload_phrases()

    # ---- 表示用 ----
    def snapshot(self) -> dict:
        with self._lock:
            s = self._settings()
            left = None
            if self._started_at is not None:
                left = max(0, int(s.session_minutes * 60 - (self._clock() - self._started_at) + 0.999))
            pend = None
            if self.pending:
                c = self.pending.clip
                reason = unsavable_reason(c, s)
                pend = {"duration_ms": c.duration_ms, "stop_reason": c.stop_reason, "fps": c.fps_measured,
                        "frames": c.frame_count, "detected_ratio": round(c.detected_ratio, 2),
                        "savable": reason is None, "problem": reason}
            return {"phase": self.phase, "mode": self.mode, "negative_label": self.negative_label,
                    "negative_kinds": s.negative_kinds, "phrase": self._phrase,
                    "target": self.target, "pending": pend, "session_remaining_sec": left,
                    "session_total_sec": int(s.session_minutes * 60), "stats": self._stats,
                    "phrases": self._store.phrases()}
