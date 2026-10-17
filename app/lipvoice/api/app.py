import asyncio
import base64
import json
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import __version__
from ..collect import CollectSession, StateError
from ..engine import Engine
from ..settings import LIMITS, SettingsHolder
from ..storage.store import LimitExceeded, Store
from .security import LocalGuard, allowed_hosts


class PhrasesBody(BaseModel):
    phrases: list[dict]


class ModeBody(BaseModel):
    mode: str
    negative_label: str | None = None


class PreviewBody(BaseModel):
    full: bool = False


def create_app(engine: Engine, store: Store, collect: CollectSession, holder: SettingsHolder, *,
               port: int, token: str, static_dir: Path | None = None, dev_origins: list[str] | None = None,
               extra_hosts: list[str] | None = None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(StateError)
    async def _state(_, e: StateError):
        return Response(json.dumps({"detail": str(e)}, ensure_ascii=False), status_code=409,
                        media_type="application/json")

    @app.exception_handler(ValueError)
    async def _value(_, e: ValueError):
        return Response(json.dumps({"detail": str(e)}, ensure_ascii=False), status_code=422,
                        media_type="application/json")

    @app.exception_handler(LimitExceeded)
    async def _limit(_, e: LimitExceeded):
        return Response(json.dumps({"detail": str(e)}, ensure_ascii=False), status_code=429,
                        media_type="application/json")

    # ---- 設定・フレーズ・統計 ----
    @app.get("/api/health")
    def health():
        live = engine.snapshot()
        return {"ok": True, "version": __version__, "camera": live.camera, "message": live.message,
                "source": live.source, "fps": live.fps, "proc_ms": live.proc_ms, "delegate": live.delegate}

    @app.get("/api/settings")
    def get_settings():
        return {"settings": asdict(holder.get()), "limits": {k: list(v) for k, v in LIMITS.items()}}

    @app.put("/api/settings")
    def put_settings(changes: dict):
        return {"settings": asdict(holder.update(changes))}

    @app.get("/api/phrases")
    def get_phrases():
        return {"phrases": store.phrases()}

    @app.put("/api/phrases")
    def put_phrases(body: PhrasesBody):
        out = store.replace_phrases(body.phrases)
        collect.phrases_changed()
        return {"phrases": out}

    @app.get("/api/stats")
    def stats():
        return store.stats()

    # ---- 収集 ----
    @app.get("/api/collect/state")
    def collect_state():
        return collect.snapshot()

    @app.post("/api/collect/mode")
    def collect_mode(body: ModeBody):
        collect.set_mode(body.mode, body.negative_label)
        return collect.snapshot()

    @app.post("/api/collect/start")
    def collect_start():
        engine.request_start()
        return collect.snapshot()

    @app.post("/api/collect/save")
    def collect_save():
        clip_id = collect.save()
        return {"clip_id": clip_id, **collect.snapshot()}

    @app.post("/api/collect/discard")
    def collect_discard():
        collect.discard()
        return collect.snapshot()

    @app.post("/api/collect/session")
    def collect_new_session():
        collect.new_session()
        return collect.snapshot()

    @app.get("/api/collect/pending/video")
    def pending_video():
        p = collect.pending
        if not p:
            raise HTTPException(404, "確認中の録画がありません")
        return Response(p.webm, media_type="video/webm")

    @app.post("/api/preview")
    def preview(body: PreviewBody):
        engine.set_full_preview(body.full)
        return {"full": body.full}

    # ---- 画面への配信（Server-Sent Events）----
    @app.get("/api/events")
    async def events(request: Request):
        async def gen():
            last_seq, last_full, tick = -1, 0.0, 0
            while not await request.is_disconnected():
                live = engine.snapshot()
                payload = {"live": {"camera": live.camera, "message": live.message, "source": live.source,
                                    "face_found": live.face_found, "fps": live.fps, "proc_ms": live.proc_ms,
                                    "opening": live.opening, "live_range": live.live_range,
                                    "remaining_sec": live.remaining_sec},
                           "collect": collect.snapshot()}
                if live.seq != last_seq:
                    last_seq = live.seq
                    if live.mouth_jpeg:
                        payload["mouth"] = base64.b64encode(live.mouth_jpeg).decode()
                    if live.frame_jpeg:
                        payload["frame"] = base64.b64encode(live.frame_jpeg).decode()
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                tick += 1
                await asyncio.sleep(0.1)
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    # ---- 画面（ビルド済みの React）。トークンはここでだけ埋め込む ----
    if static_dir and (static_dir / "index.html").exists():
        if (static_dir / "assets").exists():
            app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
        index = (static_dir / "index.html").read_text(encoding="utf-8")
        page = index.replace("</head>", f'<meta name="lipvoice-token" content="{token}"></head>', 1)

        @app.get("/{path:path}", response_class=HTMLResponse)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            return HTMLResponse(page, headers={"Cache-Control": "no-store"})
    else:
        @app.get("/", response_class=HTMLResponse)
        def no_ui():
            return HTMLResponse("<p>画面がビルドされていません（web/ で npm run build）。API は動いています。</p>")

    return LocalGuard(app, allowed_hosts(port, extra_hosts), token, dev_origins)  # type: ignore[return-value]
