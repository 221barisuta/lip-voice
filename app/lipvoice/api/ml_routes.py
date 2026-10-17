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


def register(app: FastAPI, engine, store: Store, speak: SpeakSession, models_root: Path) -> None:
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
        """学習・評価の結果（lipvoice train が書く）と、実使用の日ごとの正解率。"""
        latest = None
        try:
            latest = json.loads((models_root / "reports" / "latest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        return {"report": latest, "real_use": store.real_use_by_day(),
                "models": {"versions": versions(models_root), "active": active_version(models_root)}}

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
