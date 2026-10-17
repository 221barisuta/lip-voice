"""データ確認（クリップ一覧・口元動画・削除）と、閾値の校正の API。"""
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from ..collect import CollectSession, StateError
from ..engine import Engine
from ..settings import SettingsHolder
from ..storage.store import Store


class CalibrateStart(BaseModel):
    phase: str
    seconds: float | None = None


class CalibrateApply(BaseModel):
    threshold: float | None = None       # 省略すると、測定の候補をそのまま使う


DEFAULT_SECONDS = {"still": 5.0, "speech": 10.0}


def register(app: FastAPI, engine: Engine, store: Store, collect: CollectSession, holder: SettingsHolder) -> None:
    @app.get("/api/clips")
    def clips(date: str | None = None, kind: str | None = None, limit: int = 100, offset: int = 0):
        return store.list_clips(date=date, kind=kind, limit=limit, offset=offset)

    @app.get("/api/clips/{clip_id}/video")
    def clip_video(clip_id: str):
        try:
            path = store.clip_video_path(clip_id)
        except ValueError as e:
            raise HTTPException(404, str(e))
        if not path.exists():
            raise HTTPException(404, "動画ファイルが見つかりません")
        return Response(path.read_bytes(), media_type="video/webm")

    @app.post("/api/clips/{clip_id}/delete")
    def clip_delete(clip_id: str):
        store.delete_clip(clip_id)          # ID の形式・存在の検査は store 側（ValueError は 422）
        collect.forget(clip_id)
        return {"ok": True, "stats": store.stats()}

    # ---- 閾値の校正（静止 → 口パク → 候補 → 反映）----
    def _idle() -> None:
        if collect.snapshot()["phase"] not in ("idle", "ended"):
            raise StateError("録画中・確認中は校正できません")

    @app.post("/api/calibrate/start")
    def calibrate_start(body: CalibrateStart):
        _idle()
        if body.phase not in DEFAULT_SECONDS:
            raise ValueError("phase は still か speech")
        sec = min(30.0, max(3.0, body.seconds or DEFAULT_SECONDS[body.phase]))
        engine.start_calibration(body.phase, sec)
        return engine.calibration_state()

    @app.get("/api/calibrate")
    def calibrate_state():
        s = holder.get()
        return {**engine.calibration_state(), "current": {"threshold": s.threshold, "active_threshold": s.active_threshold,
                "still_sec": s.still_sec, "calibrated_still_sec": s.calibrated_still_sec}}

    @app.post("/api/calibrate/apply")
    def calibrate_apply(body: CalibrateApply):
        res = engine.calibration.result()
        if res is None or "threshold" not in res:
            raise StateError("測定の結果がありません。先に静止を測ってください")
        th = body.threshold if body.threshold is not None else res["threshold"]
        s = holder.update({"threshold": th, "active_threshold": th, "calibrated_still_sec": res["still_sec"]})
        return {"settings": asdict(s)}
