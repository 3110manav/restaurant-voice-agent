"""A phone call to a kirana or pharmacy whose items are in the shop database: it gets the store agent
(customer memory, medical rules, WhatsApp alerts), not the PhoneOrder read-back flow. The agent itself is a
stand-in here; what is tested is the call's wiring and how it reports its outcome."""
import pytest

from app import db, erp
from app.phone import call as phone_call
from tests.fake_supabase import FakeSupabase


class StubMenu:
    restaurant = {"id": "r1", "slug": "care-plus-medicals", "name": "Care Plus Medicals", "business_type": "pharmacy"}


class StubAgent:
    agent_name = "Sehat"

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.language = "en"
        self.channel = "web"
        self._placed_this_turn = False
        self.said = []

    def set_language(self, language, start=None):
        self.mode = language
        self.language = start or language

    def opening_line(self, store_name=None):
        return f"Namaste from {store_name}"

    def send(self, text):
        self.said.append(text)
        if text == "boom":
            raise RuntimeError("model down")
        self._placed_this_turn = "that's all" in text
        return "Done."


@pytest.fixture
def wired(monkeypatch):
    client = FakeSupabase()
    monkeypatch.setattr(db, "get_client", lambda: client)
    monkeypatch.setattr(phone_call.menu_cache, "get", lambda slug: StubMenu())
    monkeypatch.setattr(phone_call, "LiveMenu", lambda slug: f"live:{slug}")
    monkeypatch.setattr(phone_call, "start_session", lambda *a, **k: {"session_args": a, "session_kwargs": k})
    monkeypatch.setattr(phone_call, "RestaurantOrderingAgent", StubAgent)
    requests = []
    monkeypatch.setattr(erp, "record_request", lambda *a, **k: requests.append((a, k)))
    return requests


def store(business_type="pharmacy", slug="care-plus-medicals", catalog=None):
    return {
        "id": "s1", "slug": "care", "name": "Care Plus Medicals", "business_type": business_type,
        "agent_name": "Sehat", "restaurant_slug": slug, "catalog": catalog,
    }


def test_only_database_kirana_and_pharmacy_stores_use_the_store_agent():
    assert phone_call.is_database_store(store("pharmacy"))
    assert phone_call.is_database_store(store("kirana"))
    assert not phone_call.is_database_store(store("restaurant"))
    assert not phone_call.is_database_store(store("kirana", slug=None, catalog=[{"id": "x"}]))


def test_a_pharmacy_call_runs_the_store_agent_for_a_verified_caller(wired):
    call = phone_call.PhoneCall("call-1", store(), "+919876543210")
    assert call.persona == "store" and call.agent.channel == "voice" and call.agent.language == "hi"
    assert call.agent.kwargs["persona"] == "store" and call.agent.kwargs["live_call"] is True
    assert call.agent.kwargs["menu_store"] == "live:care-plus-medicals"
    assert call.agent.kwargs["customer"]["session_kwargs"] == {"verified": True}  # a real call's caller ID
    assert call.greeting == "Namaste from Care Plus Medicals"


def test_the_outcome_is_ordered_once_an_order_went_through(wired):
    call = phone_call.PhoneCall("call-1", store(), "+919876543210")
    assert call.outcome == "abandoned"
    call.take_turn("two Dolo 650")
    assert call.outcome == "abandoned"
    call.take_turn("that's all")
    assert call.outcome == "ordered"


def test_the_agent_greets_in_hindi_then_follows_the_caller(wired):
    call = phone_call.PhoneCall("call-1", store(), "+919876543210")
    assert call.agent.mode == "auto" and call.agent.language == "hi"  # which language each reply is in is the agent's job


def test_two_failures_in_a_row_leave_a_callback_note_for_the_store(wired):
    call = phone_call.PhoneCall("call-1", store(), "+919876543210")
    call.take_turn("boom")
    assert wired == []
    call.take_turn("boom")
    assert call.outcome == "callback"
    (args, kwargs), = wired
    assert args[2] == "callback" and kwargs["restaurant_id"] == "r1"
