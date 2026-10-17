"""認識（テスト用の手動操作。仕様 7.2）。録画 → 候補 3 つ → 選択 → 保存（選んだ時だけ録画を残す）。

実使用は常時監視（ステップ3）。この画面は、家族・開発者が精度を確かめるためのもの。
"""
import json
import threading
from pathlib import Path

import numpy as np

from .collect import Pending, StateError
from .ml.infer import Predictor
from .ml.model_store import load_active
from .recording.clip import RecordedClip
from .recording.encoder import encode_webm
from .storage.store import ClipRecord, Store
from .vision.indices import SAVED_INDICES


def clip_to_raw(c: RecordedClip) -> dict:
    return {"t_ms": c.t_ms, "points": c.points, "indices": np.array(SAVED_INDICES), "valid": c.valid,
            "blend": c.blend, "opening": c.opening, "blend_names": np.array(c.blend_names),
            "image_size": np.array([c.width, c.height])}


class SpeakSession:
    def __init__(self, store: Store, settings_fn, models_root: Path):
        self._store, self._settings, self._root = store, settings_fn, models_root
        self._lock = threading.RLock()
        self.predictor: Predictor | None = load_active(models_root)
        self.phase = "idle"                 # idle | recording | result
        self.result: dict | None = None
        self.pending: Pending | None = None
        self.last_choice: dict | None = None

    def reload_model(self) -> None:
        with self._lock:
            self.predictor = load_active(self._root)

    def begin(self) -> dict:
        with self._lock:
            if self.predictor is None:
                raise StateError("まだ学習していません。先にデータ収集と学習（lipvoice train）を行ってください")
            if self.phase != "idle":
                raise StateError("いまは録画を始められません")
            self.phase, self.result, self.pending = "recording", None, None
            return {"kind": "speak"}

    def cancel_recording(self) -> None:
        with self._lock:
            if self.phase == "recording":
                self.phase = "idle"

    def tick(self) -> None:
        pass

    def finish(self, clip: RecordedClip) -> None:
        """録画が終わった（エンジンのスレッドから呼ばれる）。口の動きがなければ候補を出さない。"""
        with self._lock:
            pred = self.predictor
        res: dict = {"stop_reason": clip.stop_reason, "duration_ms": clip.duration_ms, "no_motion": clip.stop_reason == "no_motion",
                     "detected_ratio": round(clip.detected_ratio, 2)}
        if not res["no_motion"] and pred is not None:
            out = pred.predict(clip_to_raw(clip))
            text = {p["id"]: p["text"] for p in self._store.phrases()}
            out["candidates"] = [{**c, "text": text.get(c["phrase_id"], c["phrase_id"])} for c in out["candidates"]]
            res.update(out)
        pending = Pending(clip, clip.to_npz(), encode_webm(clip.crops, clip.t_ms))
        with self._lock:
            self.phase, self.result, self.pending = "result", res, pending

    def choose(self, phrase_id: str | None, negative: bool = False) -> dict:
        """選ばれた正解を保存する。phrase_id なし + negative は「フレーズではない動き」（誤検知）として保存する。"""
        with self._lock:
            if self.phase != "result" or not self.pending or not self.result:
                raise StateError("選べる結果がありません")
            clip, res = self.pending.clip, self.result
            cands = [c["phrase_id"] for c in res.get("candidates", [])]
            if negative:
                rec = ClipRecord(kind="negative", negative_label="実使用の誤検知", source="use", session_id="speak")
                outcome, chosen = "negative", None
            else:
                if not phrase_id or not self._store.phrase_exists(phrase_id):
                    raise StateError("フレーズが正しくありません")
                rec = ClipRecord(kind="phrase", phrase_id=phrase_id, source="use", session_id="speak")
                outcome, chosen = "phrase", phrase_id
            rec.duration_ms, rec.frame_count, rec.fps_measured = clip.duration_ms, clip.frame_count, clip.fps_measured
            rec.detected_ratio, rec.stop_reason, rec.width, rec.height = clip.detected_ratio, clip.stop_reason, clip.width, clip.height
            clip_id = self._store.save_clip(rec, self.pending.npz, self.pending.webm)
            self._store.add_prediction(
                clip_id=clip_id, model_version=res.get("version"), model_kind=res.get("model"),
                top3_json=json.dumps(cands), distance=res.get("distance"), rejected=int(bool(res.get("rejected"))),
                agree=int(bool(res.get("agree"))), chosen=chosen, outcome=outcome, latency_ms=res.get("latency_ms"),
                correct_top1=int(bool(cands) and cands[0] == chosen), correct_top3=int(chosen in cands))
            text = {p["id"]: p["text"] for p in self._store.phrases()}
            self.last_choice = {"phrase_id": chosen, "text": text.get(chosen) if chosen else None, "negative": negative}
            self.phase, self.result, self.pending = "idle", None, None
            return self.last_choice

    def skip(self) -> None:
        with self._lock:
            if self.phase == "result":
                self.phase, self.result, self.pending = "idle", None, None

    def snapshot(self) -> dict:
        with self._lock:
            return {"phase": self.phase, "result": self.result, "has_model": self.predictor is not None,
                    "model_version": self.predictor.version if self.predictor else None,
                    "last_choice": self.last_choice, "phrases": self._store.phrases()}
