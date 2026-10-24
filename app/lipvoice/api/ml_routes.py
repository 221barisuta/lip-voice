"""認識（テスト用の手動操作）・評価・モデルの版の API。"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from ..collect import StateError
from ..ml.model_store import active_version, set_active, versions
from ..speak import SpeakSession
from ..storage.store import Store


class ChooseBody(BaseModel):
    phrase_id: str | None = None
    negative: bool = False


class ActivateBody(BaseModel):
    version: str


def register(app: FastAPI, engine, store: Store, speak: SpeakSession, models_root: Path, trainer=None) -> None:
    @app.get("/api/speak/state")
    def speak_state():
        return speak.snapshot()

    @app.post("/api/speak/start")
    def speak_start():
        engine.request_start("speak")
        return speak.snapshot()

    @app.post("/api/speak/choose")
    def speak_choose(body: ChooseBody):
        return {"choice": speak.choose(body.phrase_id, body.negative), **speak.snapshot()}

    @app.post("/api/speak/skip")
    def speak_skip():
        speak.skip()
        return speak.snapshot()

    @app.get("/api/report")
    def report():
        """使っているモデルの学習・評価の結果と、実使用の日ごとの正解率、自動学習の状態（使わなかった新しい版は pending）。"""
        act = active_version(models_root)
        latest = None
        for name in ([f"{act}.json"] if act else []) + ["latest.json"]:
            try:
                latest = json.loads((models_root / "reports" / name).read_text(encoding="utf-8"))
                break
            except (OSError, ValueError):
                continue
        auto = trainer.state() if trainer is not None else None
        pending = None
        if auto and auto.get("version") and auto.get("version") != act and auto.get("activated") is False:
            pending = {"version": auto["version"], "reason": auto.get("reason")}
        return {"report": latest, "real_use": store.real_use_by_day(), "auto": auto, "pending": pending,
                "models": {"versions": versions(models_root), "active": act}}

    @app.post("/api/auto_train/run")
    def auto_train_run():
        """家族が「今すぐ学習し直す」を押した時。新しいデータがなくても、手動なら実行する。"""
        if trainer is None:
            raise StateError("自動学習が使えません")
        if not trainer.run_now("manual"):
            raise StateError("学習がすでに実行中です")
        return trainer.state()

    @app.post("/api/models/activate")
    def activate(body: ActivateBody):
        try:
            set_active(models_root, body.version)
        except FileNotFoundError as e:
            raise StateError(str(e))
        speak.reload_model()
        return {"active": body.version}

    @app.post("/api/models/reload")
    def reload_models():
        speak.reload_model()
        return speak.snapshot()
