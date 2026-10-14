def test_initial_phrases_copied(as_user, fake):
    r = as_user("alice").get("/phrases")
    assert r.status_code == 200
    assert len(r.json()["phrases"]) == 10


def test_put_validates(as_user, fake):
    c = as_user("alice")
    assert c.put("/phrases", json={"phrases": []}).status_code == 422
    dup = {"phrases": [{"id": "a", "text": "x"}, {"id": "a", "text": "y"}]}
    assert c.put("/phrases", json=dup).status_code == 422
    bad_id = {"phrases": [{"id": "../x", "text": "x"}]}
    assert c.put("/phrases", json=bad_id).status_code == 422
    ok = {"phrases": [{"id": "a", "text": "x"}]}
    assert c.put("/phrases", json=ok).status_code == 200


def test_phrases_are_per_user(as_user, fake):
    as_user("alice").put("/phrases", json={"phrases": [{"id": "a", "text": "秘密"}]})
    assert len(as_user("bob").get("/phrases").json()["phrases"]) == 10
