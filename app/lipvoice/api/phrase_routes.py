"""フレーズの追加・一覧（本数・日数・モデルに入っているか）と、「このフレーズを続けて録る」の API。
並べ替え・テキストの編集・削除は、既存の PUT /api/phrases（全件置換。録画のあるフレーズを消せない検査つき）を使う。"""
import json
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from ..collect import CollectSession
from ..ml.model_store import active_version
from ..storage.store import Store


class AddBody(BaseModel):
    text: str


class FocusBody(BaseModel):
    phrase_id: str | None = None


def _model_classes(models_root: Path | None) -> set[str]:
    if models_root is None:
        return set()
    try:
        v = active_version(models_root)
        return set(json.loads((models_root / v / "meta.json").read_text(encoding="utf-8")).get("classes", [])) if v else set()
    except (OSError, ValueError):
        return set()


def register(app: FastAPI, store: Store, collect: CollectSession, models_root: Path | None) -> None:
    @app.post("/api/phrases")
    def add_phrase(body: AddBody):
        added = store.add_phrase(body.text)
        collect.phrases_changed()
        return {"added": added, "phrases": store.phrases()}

    @app.get("/api/phrases/info")
    def phrase_info():
        stats, in_model = store.phrase_stats(), _model_classes(models_root)
        return {"phrases": [{**p, "clips": stats.get(p["id"], {}).get("clips", 0), "days": stats.get(p["id"], {}).get("days", 0),
                             "in_model": p["id"] in in_model} for p in store.phrases()]}

    @app.post("/api/collect/focus")
    def collect_focus(body: FocusBody):
        collect.set_focus(body.phrase_id)
        return collect.snapshot()
