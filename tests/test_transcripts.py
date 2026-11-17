"""Conversation transcripts: each turn is recorded from the one place every channel passes through, grouped into
conversations, and readable only by owners and managers."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app import db, owner_api, transcripts
from app.agent.graph import RestaurantOrderingAgent
from app.menu import repository, service
from tests.fake_supabase import FakeSupabase
from tests.test_agent_guardrails import ScriptedLLM, Store
from tests.test_owner_api import FakeAuth, bearer


_InPlace = SimpleNamespace(Thread=lambda target, args=(), daemon=None: SimpleNamespace(start=lambda: target(*args)))


@pytest.fixture
def fake(monkeypatch):
    client = FakeSupabase()
    monkeypatch.setattr(db, "get_client", lambda: client)
    # Recording happens on a thread; run it in place so a test can look at the result at once.
    monkeypatch.setattr(transcripts, "threading", _InPlace)
    return client


def test_a_calls_and_the_pages_chat_are_one_conversation():
    assert transcripts.conversation_key("livekit:saffron-table:8c1f-uuid") == "8c1f-uuid"
    assert transcripts.conversation_key("saffron-table:8c1f-uuid:waiter") == "8c1f-uuid"
    assert transcripts.conversation_key("plain") == "plain"


def test_a_turn_is_saved_with_who_where_and_how(fake):
    transcripts.record_turn("r1", "slug:abc:waiter", "browser-call", " two dosa ", " Done. ", language="en", speech="sarvam", latency_ms=812.4, table_no="9")
    (row,) = fake.tables["conversation_turns"]
    assert (row["session_id"], row["channel"], row["speech"], row["customer_text"], row["agent_text"]) == ("abc", "browser-call", "sarvam", "two dosa", "Done.")
    assert row["latency_ms"] == 812 and row["table_no"] == "9" and row["restaurant_id"] == "r1"


def test_nothing_is_saved_for_silence_no_restaurant_or_when_switched_off(fake, monkeypatch):
    transcripts.record_turn("r1", "s", "chat", "um", "", language="en")  # the agent said nothing
    transcripts.record_turn(None, "s", "chat", "hi", "hello")  # no restaurant
    monkeypatch.setenv("SARTHI_STORE_TRANSCRIPTS", "0")
    transcripts.record_turn("r1", "s", "chat", "hi", "hello")
    assert fake.tables.get("conversation_turns", []) == []


def test_a_database_failure_never_reaches_the_conversation(monkeypatch):
    class Broken:
        def table(self, *_):
            raise RuntimeError("down")

    monkeypatch.setattr(db, "get_client", lambda: Broken())
    monkeypatch.setattr(transcripts, "threading", _InPlace)
    monkeypatch.setattr(transcripts, "_warned", False)
    transcripts.record_turn("r1", "s", "chat", "hi", "hello")  # must not raise


def test_every_agent_turn_is_recorded_whatever_the_channel(fake, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    agent = RestaurantOrderingAgent("saffron:abc123:waiter", Store(), persona="waiter", restaurant={"id": "r1", "name": "T", "cuisine": "Indian"}, table_no="9")
    agent.llm_with_tools = ScriptedLLM(AIMessage(content="Hello there."), AIMessage(content="Sure."))
    agent.send("hi")
    agent.channel, agent.speech_label = "voice", "groq"
    agent.send("what do you recommend")
    first, second = fake.tables["conversation_turns"]
    assert (first["channel"], first["session_id"], first["table_no"]) == ("chat", "abc123", "9")
    assert (second["channel"], second["speech"], second["customer_text"]) == ("browser-call", "groq", "what do you recommend")


def test_noise_that_got_no_answer_is_not_recorded(fake, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    agent = RestaurantOrderingAgent("s:abc:waiter", Store(), persona="waiter", restaurant={"id": "r1", "name": "T", "cuisine": "Indian"})
    agent.llm_with_tools = ScriptedLLM()
    assert agent.send("Um.") == ""
    assert fake.tables.get("conversation_turns", []) == []


def test_conversations_are_grouped_and_read_back_in_order(fake):
    for i, (sid, who, said) in enumerate([("a", "c", "hello"), ("a", "w", "hi!"), ("b", "c", "bill please")]):
        fake.tables.setdefault("conversation_turns", []).append({
            "id": str(i), "restaurant_id": "r1", "session_id": sid, "channel": "chat" if sid == "a" else "browser-call",
            "customer_text": said, "agent_text": f"re: {said}", "created_at": f"2026-11-18T10:0{i}:00+00:00", "table_no": None, "caller_phone": None,
        })
    listed = transcripts.list_conversations("r1")
    assert [c["session_id"] for c in listed] == ["b", "a"]  # newest first
    assert listed[1]["turns"] == 2 and listed[1]["preview"] == "hello" and listed[0]["channels"] == ["browser-call"]
    assert [t["customer_text"] for t in transcripts.conversation_turns("r1", "a")] == ["hello", "hi!"]
    assert transcripts.conversation_turns("r2", "a") == []  # another restaurant's turns are not visible


@pytest.fixture
def api(monkeypatch, fake):
    auth = FakeAuth()
    monkeypatch.setattr(owner_api.db, "get_client", lambda: SimpleNamespace(auth=auth, table=fake.table))
    owner_api._tokens.clear()
    roles = {("u-owner", "r1"): "owner", ("u-staff", "r1"): "staff"}
    monkeypatch.setattr(repository, "user_role", lambda uid, rid: roles.get((uid, rid)))
    monkeypatch.setattr(repository, "get_restaurant", lambda rid: {"id": rid, "slug": "demo", "name": "Demo"} if rid == "r1" else None)
    monkeypatch.setattr(service, "menu_for_owner", lambda rid: {"categories": [], "dishes": []})
    fake.tables["conversation_turns"] = [{
        "id": "1", "restaurant_id": "r1", "session_id": "abc", "channel": "chat", "customer_text": "hi", "agent_text": "hello",
        "created_at": "2026-11-18T10:00:00+00:00", "table_no": None, "caller_phone": None,
    }]
    app = FastAPI()
    app.include_router(owner_api.router)
    return TestClient(app)


def test_an_owner_can_list_and_read_conversations(api):
    assert [c["session_id"] for c in api.get("/owner/restaurants/r1/conversations", headers=bearer("good-owner")).json()["conversations"]] == ["abc"]
    turns = api.get("/owner/restaurants/r1/conversations/abc", headers=bearer("good-owner")).json()["turns"]
    assert turns[0]["customer_text"] == "hi" and turns[0]["agent_text"] == "hello"
    assert api.get("/owner/restaurants/r1/conversations/nope", headers=bearer("good-owner")).status_code == 404


def test_staff_strangers_and_logged_out_visitors_cannot_read_what_customers_said(api):
    # Both get 404, as everywhere in this API: it does not reveal which restaurants exist or what a role may see.
    for token, code in (("good-staff", 404), ("good-stranger", 404)):
        assert api.get("/owner/restaurants/r1/conversations", headers=bearer(token)).status_code == code
        assert api.get("/owner/restaurants/r1/conversations/abc", headers=bearer(token)).status_code == code
    assert api.get("/owner/restaurants/r1/conversations").status_code == 401
