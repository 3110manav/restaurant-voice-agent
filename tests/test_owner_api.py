"""The owner API's gatekeeping: no token, a bad token, a stranger's restaurant, and
the roles that may edit — all with Supabase faked out."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import owner_api
from app.menu import repository, service

ROW = {"id": "r1", "slug": "demo", "name": "Demo"}


class FakeAuth:
    def __init__(self):
        self.calls = 0

    def get_user(self, token):
        self.calls += 1
        if token == "good-owner":
            return SimpleNamespace(user=SimpleNamespace(id="u-owner"))
        if token == "good-staff":
            return SimpleNamespace(user=SimpleNamespace(id="u-staff"))
        if token == "good-stranger":
            return SimpleNamespace(user=SimpleNamespace(id="u-stranger"))
        raise Exception("invalid JWT")


@pytest.fixture
def client(monkeypatch):
    auth = FakeAuth()
    monkeypatch.setattr(owner_api.db, "get_client", lambda: SimpleNamespace(auth=auth))
    owner_api._tokens.clear()
    roles = {("u-owner", "r1"): "owner", ("u-staff", "r1"): "staff"}
    monkeypatch.setattr(repository, "user_role", lambda uid, rid: roles.get((uid, rid)))
    monkeypatch.setattr(repository, "get_restaurant", lambda rid: ROW if rid == "r1" else None)
    monkeypatch.setattr(service, "menu_for_owner", lambda rid: {"categories": ["Starters"], "dishes": []})
    app = FastAPI()
    app.include_router(owner_api.router)
    c = TestClient(app)
    c.fake_auth = auth
    return c


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_no_token_is_401(client):
    assert client.get("/owner/restaurants/r1/menu").status_code == 401


def test_invalid_token_is_401(client):
    assert client.get("/owner/restaurants/r1/menu", headers=bearer("garbage")).status_code == 401


def test_member_can_read_the_menu(client):
    r = client.get("/owner/restaurants/r1/menu", headers=bearer("good-owner"))
    assert r.status_code == 200 and r.json()["restaurant"]["slug"] == "demo"


def test_stranger_gets_404_not_403(client):
    assert client.get("/owner/restaurants/r1/menu", headers=bearer("good-stranger")).status_code == 404


def test_unknown_restaurant_is_404(client):
    assert client.get("/owner/restaurants/nope/menu", headers=bearer("good-owner")).status_code == 404


def test_staff_can_read_but_not_edit(client):
    assert client.get("/owner/restaurants/r1/menu", headers=bearer("good-staff")).status_code == 200
    r = client.post("/owner/restaurants/r1/dishes", json={"name": "X", "price": 1}, headers=bearer("good-staff"))
    assert r.status_code == 404
    assert client.delete("/owner/restaurants/r1/dishes/d1", headers=bearer("good-staff")).status_code == 404


def test_owner_edit_goes_through_the_service(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(service, "save_dish", lambda rest, did, payload: seen.update(did=did, payload=payload) or {"ok": 1})
    r = client.patch("/owner/restaurants/r1/dishes/d9", json={"price": 99}, headers=bearer("good-owner"))
    assert r.status_code == 200 and seen == {"did": "d9", "payload": {"price": 99.0}}  # only fields that were sent


def test_validation_errors_become_422(client, monkeypatch):
    def reject(*_):
        raise service.MenuValidationError("a dish needs a name")

    monkeypatch.setattr(service, "save_dish", reject)
    r = client.post("/owner/restaurants/r1/dishes", json={"price": 1}, headers=bearer("good-owner"))
    assert r.status_code == 422 and "needs a name" in r.json()["detail"]


def test_validated_tokens_are_cached(client):
    for _ in range(3):
        client.get("/owner/restaurants/r1/menu", headers=bearer("good-owner"))
    assert client.fake_auth.calls == 1


def test_resolving_a_request_is_scoped_to_the_restaurant(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(repository, "resolve_request", lambda rid, qid: seen.update(rid=rid, qid=qid) or {"id": qid})
    assert client.post("/owner/restaurants/r1/requests/q1/resolve", headers=bearer("good-staff")).status_code == 200
    assert seen == {"rid": "r1", "qid": "q1"}
    monkeypatch.setattr(repository, "resolve_request", lambda rid, qid: None)
    assert client.post("/owner/restaurants/r1/requests/zz/resolve", headers=bearer("good-owner")).status_code == 404


def test_slugify():
    assert owner_api._slugify("Sarson Da Khet!") == "sarson-da-khet"
    assert owner_api._slugify("   ") == "restaurant"
