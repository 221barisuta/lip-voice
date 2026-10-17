import pytest
from fastapi.testclient import TestClient

from lipvoice.api.app import create_app
from lipvoice.collect import CollectSession

TOKEN = "t0ken"
PORT = 8765


class FakeLive:
    camera, message, source, fps, proc_ms, delegate = "ok", "", "fake", 30.0, 5.0, "CPU"
    face_found, opening, live_range, remaining_sec, seq = True, 0.1, 0.0, None, 0
    mouth_jpeg = frame_jpeg = None


class FakeEngine:
    def snapshot(self):
        return FakeLive()

    def request_start(self):
        raise NotImplementedError

    def set_full_preview(self, on):
        pass


@pytest.fixture
def client(store, settings, paths):
    from lipvoice.settings import SettingsHolder
    holder = SettingsHolder(paths.config)
    app = create_app(FakeEngine(), store, CollectSession(store, holder.get), holder, port=PORT, token=TOKEN)
    return TestClient(app, base_url=f"http://127.0.0.1:{PORT}")


def H(**kw):
    return {"X-LipVoice-Token": TOKEN, **kw}


def test_ok_with_token(client):
    assert client.get("/api/health", headers=H()).status_code == 200


def test_missing_or_wrong_token_is_403(client):
    assert client.get("/api/health").status_code == 403
    assert client.get("/api/health", headers={"X-LipVoice-Token": "x"}).status_code == 403


@pytest.mark.parametrize("host", ["evil.example.com", "127.0.0.1:9999", "localhost", "attacker.test:8765"])
def test_wrong_host_is_rejected_dns_rebinding(client, host):
    r = client.get("/api/health", headers=H(Host=host))
    assert r.status_code == 403


@pytest.mark.parametrize("origin", ["https://evil.example.com", "null", "http://127.0.0.1:1234", "http://localhost:5173"])
def test_foreign_origin_is_rejected(client, origin):
    assert client.get("/api/health", headers=H(Origin=origin)).status_code == 403
    assert client.post("/api/collect/session", headers=H(Origin=origin)).status_code == 403


def test_same_origin_is_allowed(client):
    assert client.get("/api/health", headers=H(Origin=f"http://127.0.0.1:{PORT}")).status_code == 200
    assert client.get("/api/health", headers=H(Origin=f"http://localhost:{PORT}", Host=f"localhost:{PORT}")).status_code == 200


def test_cross_site_fetch_metadata_rejected(client):
    assert client.get("/api/health", headers=H(**{"Sec-Fetch-Site": "cross-site"})).status_code == 403
    assert client.get("/api/health", headers=H(**{"Sec-Fetch-Site": "same-origin"})).status_code == 200


def test_form_post_from_other_site_is_blocked(client):
    # HTML フォームからの POST（preflight なし）も、Origin で止まる
    r = client.post("/api/phrases", headers=H(Origin="https://evil.example.com", **{"Content-Type": "text/plain"}), content="{}")
    assert r.status_code == 403


def test_docs_not_exposed(client):
    for p in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(p, headers=H()).status_code in (403, 404)
