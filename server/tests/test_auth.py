from fastapi.testclient import TestClient


def test_no_token_is_401(app, fake):
    c = TestClient(app)
    assert c.get("/phrases").status_code == 401
    assert c.put("/phrases", json={"phrases": []}).status_code == 401
    assert c.post("/clips").status_code in (401, 422)  # 検証前に認証で弾く
    assert c.get("/clips/stats").status_code == 401


def test_garbage_token_is_401(app, fake):
    c = TestClient(app)
    r = c.get("/phrases", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


def test_docs_not_exposed(app):
    c = TestClient(app)
    for p in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(p).status_code == 404


import pytest
from fastapi import HTTPException

from auth import authorize

GOOD = {"uid": "abc123", "email": "dev@example.com", "email_verified": True,
        "firebase": {"sign_in_provider": "google.com"}}


def test_authorize_ok():
    assert authorize(GOOD) == "abc123"


@pytest.mark.parametrize("patch,code", [
    ({"email": "other@example.com"}, 403),
    ({"email_verified": False}, 403),
    ({"firebase": {"sign_in_provider": "anonymous"}}, 401),
    ({"uid": "../x"}, 401),
    ({"uid": ""}, 401),
])
def test_authorize_rejects(patch, code):
    with pytest.raises(HTTPException) as e:
        authorize({**GOOD, **patch})
    assert e.value.status_code == code


def test_body_limit(app, fake):
    c = TestClient(app)
    r = c.post("/clips", content=b"x", headers={"content-length": str(9 * 1024 * 1024)})
    assert r.status_code == 413
