"""ローカル API の防御。認証サービスはないので、次の 3 つで守る。

 1. Host ヘッダの許可リスト … DNS rebinding（他のサイトの名前を 127.0.0.1 に向けて攻撃する手口）を防ぐ
 2. Origin の検査 … 他のサイトのページからの要求（CSRF）を防ぐ。Origin が "null" の要求は拒否する
 3. 起動ごとのトークン … 画面（同じ origin）にだけ埋め込まれる。他のサイトは画面の中身を読めない

同じ PC の同じ利用者権限の他のプログラムは、ファイルを直接読めるため、この仕組みの対象外（脅威モデル外）。
"""
import hmac
import json

TOKEN_HEADER = "x-lipvoice-token"

# 画面は同じ origin のものだけを読み込み、他のページに埋め込まれない（古いブラウザ向けの保険）
SECURITY_HEADERS = [
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"content-security-policy", b"default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
                                 b"style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
                                 b"frame-ancestors 'none'; base-uri 'none'; form-action 'none'"),
]


def allowed_hosts(port: int, extra: list[str] | None = None) -> set[str]:
    base = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
    return base | {h.lower() for h in (extra or [])}


class LocalGuard:
    """ASGI ミドルウェア。HTTP と WebSocket の全要求に Host/Origin の検査をかける。"""

    def __init__(self, app, hosts: set[str], token: str, dev_origins: list[str] | None = None):
        self.app, self.hosts, self.token = app, hosts, token
        self.origins = {f"http://{h}" for h in hosts} | set(dev_origins or [])
        self.dev = bool(dev_origins)

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        problem = self._check(headers, scope.get("path", ""))
        if problem is None:
            async def send_with_headers(message):
                if message["type"] == "http.response.start":
                    have = {k.lower() for k, _ in message.get("headers", [])}
                    message["headers"] = list(message.get("headers", [])) + [h for h in SECURITY_HEADERS if h[0] not in have]
                await send(message)
            return await self.app(scope, receive, send_with_headers if scope["type"] == "http" else send)
        status, msg = problem
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        body = json.dumps({"detail": msg}, ensure_ascii=False).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json; charset=utf-8"),
                                (b"content-length", str(len(body)).encode()), *SECURITY_HEADERS]})
        await send({"type": "http.response.body", "body": body})

    def _check(self, h: dict[str, str], path: str) -> tuple[int, str] | None:
        if h.get("host", "").lower() not in self.hosts:
            return 403, "この Host は許可されていません"
        origin = h.get("origin")
        if origin is not None and origin not in self.origins:    # "null" もここで拒否される
            return 403, "この Origin は許可されていません"
        site = h.get("sec-fetch-site")
        if site is not None and site not in ("same-origin", "none") and not (self.dev and site == "same-site"):
            return 403, "他のサイトからの要求は受け付けません"
        if path.startswith("/api/"):
            sent = h.get(TOKEN_HEADER, "")
            if not hmac.compare_digest(sent.encode(), self.token.encode()):
                return 403, "トークンが正しくありません"
        return None
