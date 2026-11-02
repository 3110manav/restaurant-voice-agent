"""Only kirana (quick_commerce) and the waiter are live; the other agents are refused everywhere."""
import importlib
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent.graph import _PERSONAS, ENABLED_PERSONAS

HIDDEN = sorted(set(_PERSONAS) - set(ENABLED_PERSONAS))


class StubStore:
    def __init__(self, data_path=None, collection_name="restaurant_menu"):
        self.collection_name = collection_name
        self.menu = [{"id": collection_name, "name": collection_name}]


@pytest.fixture
def client(monkeypatch):
    # The real stores open the Chroma index and need an embeddings key.
    from app.rag import menu_store

    monkeypatch.setattr(menu_store, "MenuStore", StubStore)
    monkeypatch.delitem(sys.modules, "app.main", raising=False)
    main = importlib.import_module("app.main")
    yield TestClient(main.app), main
    sys.modules.pop("app.main", None)


def test_only_kirana_and_the_waiter_are_enabled():
    assert set(ENABLED_PERSONAS) == {"quick_commerce", "waiter"}
    assert HIDDEN == ["hotel", "online"]


@pytest.mark.parametrize("persona", HIDDEN)
def test_hidden_agents_are_refused_on_every_route(client, persona):
    http, _ = client
    assert http.post("/chat", json={"session_id": "s", "message": "hi", "persona": persona}).status_code == 404
    assert http.get("/menu", params={"persona": persona}).status_code == 404
    assert http.get("/cart", params={"session_id": "s", "persona": persona}).status_code == 404
    cart = {"session_id": "s", "persona": persona, "item_id": "x"}
    assert http.post("/cart/add", json=cart).status_code == 404
    assert http.post("/cart/remove", json=cart).status_code == 404
    assert http.post("/cart/sync", json={"session_id": "s", "persona": persona, "cart": []}).status_code == 404


@pytest.mark.parametrize("persona", HIDDEN)
def test_a_hidden_agent_cannot_get_a_call_token(client, monkeypatch, persona):
    http, main = client
    monkeypatch.setattr(main.livekit_tokens, "is_configured", lambda: True)
    assert http.post("/livekit/token", json={"session_id": "s", "persona": persona}).status_code == 404


def test_each_enabled_agent_gets_its_own_catalog(client):
    http, _ = client
    assert http.get("/menu", params={"persona": "quick_commerce"}).json()["items"][0]["id"] == "grocery_catalog"
    assert http.get("/menu", params={"persona": "waiter"}).json()["items"][0]["id"] == "restaurant_menu"


def test_enabled_agents_can_still_start_a_session(client, monkeypatch):
    http, main = client
    agent = SimpleNamespace(cart=[], service_log=[], set_language=lambda _: None)
    monkeypatch.setattr(main, "RestaurantOrderingAgent", lambda **_: agent)
    for persona in ENABLED_PERSONAS:
        assert http.get("/cart", params={"session_id": "s", "persona": persona}).status_code == 200


def test_kirana_clis_and_worker_read_the_grocery_catalog(monkeypatch):
    from app.rag import menu_store

    monkeypatch.setattr(menu_store, "MenuStore", StubStore)
    assert menu_store.store_for_persona("quick_commerce").collection_name == "grocery_catalog"
    assert menu_store.store_for_persona("waiter").collection_name == "restaurant_menu"
