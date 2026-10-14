from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import config
from routes import clips, phrases


MAX_REQUEST_BYTES = 8 * 1024 * 1024


def create_app() -> FastAPI:
    # API ドキュメント画面は公開しない
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins(),
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        # 申告サイズが上限超なら本文を読む前に断る（個別の上限は routes/clips.py）
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_REQUEST_BYTES:
            return JSONResponse({"detail": "リクエストが大きすぎます"}, status_code=413)
        return await call_next(request)

    app.include_router(phrases.router)
    app.include_router(clips.router)
    return app


app = create_app()
