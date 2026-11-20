"""A guest's change to a dish ("Jain", "no onion", "with podi") rides on that dish to the kitchen, instead of being
dropped or turned into a loose request."""
import pytest

import app.erp as erp
from app.agent.graph import RestaurantOrderingAgent
from app.agent import replies
from app.whatsapp import notify
from tests.test_agent_guardrails import ScriptedLLM, Store, tool_call


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    saved = []
    monkeypatch.setattr(erp, "record_order", lambda session, persona, items, *a, **k: saved.append(items) or {"id": "o1"})
    requests = []
    monkeypatch.setattr(erp, "record_request", lambda *a, **k: requests.append((a, k)))
    a = RestaurantOrderingAgent("s1", Store(), persona="waiter", restaurant={"id": "r1", "name": "Test", "cuisine": "Indian"}, table_no="4")
    a.saved, a.requests = saved, requests
    return a


def test_a_note_given_with_the_dish_is_kept_on_its_line_and_said_back(agent):
    agent.llm_with_tools = ScriptedLLM(tool_call("add_to_cart", {"items": [{"name": "Paneer Tikka", "note": "Jain, no onion"}]}))
    reply = agent.send("one paneer tikka, Jain please")
    assert agent.cart[0]["note"] == "Jain, no onion"
    assert reply.startswith("Done, Paneer Tikka. Noted for the kitchen: Jain, no onion.")


def test_a_note_can_be_added_to_a_dish_already_in_the_cart(agent):
    agent.llm_with_tools = ScriptedLLM(tool_call("add_to_cart", {"items": [{"name": "Paneer Tikka"}]}))
    agent.send("one paneer tikka")
    agent.llm_with_tools = ScriptedLLM(tool_call("add_note", {"name": "Paneer Tikka", "note": "extra spicy"}))
    reply = agent.send("make it extra spicy")
    assert agent.cart[0]["note"] == "extra spicy" and agent.cart[0]["quantity"] == 1  # the count did not change
    assert reply.startswith("Noted for the kitchen, on the Paneer Tikka: extra spicy.")


def test_a_second_note_is_added_to_the_first_not_lost(agent):
    agent.llm_with_tools = ScriptedLLM(tool_call("add_to_cart", {"items": [{"name": "Paneer Tikka", "note": "Jain"}]}))
    agent.send("paneer tikka, Jain")
    agent.llm_with_tools = ScriptedLLM(tool_call("add_note", {"name": "Paneer Tikka", "note": "with podi"}))
    agent.send("and podi on it")
    assert agent.cart[0]["note"] == "Jain; with podi"


def test_a_note_for_a_dish_that_is_not_in_the_cart_is_not_silently_invented(agent):
    agent.llm_with_tools = ScriptedLLM(tool_call("add_note", {"name": "Paneer Tikka", "note": "Jain"}), __import__("langchain_core.messages", fromlist=["AIMessage"]).AIMessage(content="Which dish should I note that on?"))
    agent.send("make it Jain")
    assert agent.cart == []


def test_the_note_travels_with_the_order_to_the_kitchen(agent):
    agent.llm_with_tools = ScriptedLLM(tool_call("add_to_cart", {"items": [{"name": "Paneer Tikka", "note": "no onion"}]}))
    agent.send("paneer tikka no onion")
    agent.llm_with_tools = ScriptedLLM(tool_call("checkout", {}))
    agent.send("that's all, place it")
    assert agent.saved and agent.saved[0][0]["note"] == "no onion"


def test_a_note_on_a_dish_the_kitchen_already_has_tells_the_staff_instead(agent):
    agent.llm_with_tools = ScriptedLLM(tool_call("add_to_cart", {"items": [{"name": "Paneer Tikka"}]}))
    agent.send("paneer tikka")
    agent.mark_order_placed()  # the round went to the kitchen
    agent.llm_with_tools = ScriptedLLM(tool_call("add_note", {"name": "Paneer Tikka", "note": "no onion"}))
    agent.send("actually no onion on it")
    (args, kwargs), = agent.requests
    assert args[2] == "call_staff" and "already sent" in args[3] and "no onion" in args[3]
    assert "note" not in agent.cart[0]  # the cart line would never have reached the kitchen


def test_the_owners_whatsapp_alert_and_the_replies_show_the_note():
    lines = [{"name": "Masala Dosa", "quantity": 1, "note": "Jain"}, {"name": "Plain Dosa", "quantity": 2}]
    assert notify.items_summary(lines) == "1 x Masala Dosa (Jain), 2 x Plain Dosa"
    added = {"type": "added", "lines": [{"name": "Masala Dosa", "variant": None, "quantity": 1, "note": "Jain"}]}
    assert replies.compose([added], "en") == "Done, Masala Dosa. Noted for the kitchen: Jain. Anything else?"
    assert "Jain" in replies.compose([added], "hi")
