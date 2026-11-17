"""The per-turn log, the cap on history each model call carries, and the false "your order is ready" claim."""
import logging

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent import graph
from app.agent import guardrails as g
from app.voice import turnlog


# ---- the turn log

def test_the_turn_log_is_off_unless_asked_for(monkeypatch, caplog):
    monkeypatch.delenv("SARTHI_LOG_TURNS", raising=False)
    with caplog.at_level(logging.INFO, logger="sarthi.turns"):
        turnlog.log_turn("browser-call", "sarvam", "en", "two Dolo", "Done.", 120, "abcdefghij")
    assert caplog.text == ""


def test_a_logged_turn_says_what_was_heard_what_was_answered_and_on_which_stack(monkeypatch, caplog):
    monkeypatch.setenv("SARTHI_LOG_TURNS", "1")
    with caplog.at_level(logging.INFO, logger="sarthi.turns"):
        turnlog.log_turn("browser-call", "sarvam", "hi", "दो Dolo 650", "हो गया", 850, "abcdefghij-long-session")
    line = caplog.text
    assert "browser-call" in line and "speech=sarvam" in line and "lang=hi" in line and "850 ms" in line
    assert "दो Dolo 650" in line and "हो गया" in line and "session=abcdefgh" in line


def test_phone_numbers_are_masked_and_long_text_is_clipped(monkeypatch, caplog):
    monkeypatch.setenv("SARTHI_LOG_TURNS", "yes")
    with caplog.at_level(logging.INFO, logger="sarthi.turns"):
        turnlog.log_turn("push-to-talk", "groq", "en", "my number is 98765 43210 call me " + "x" * 600, "ok", 5)
    assert "98765" not in caplog.text and "<digits>" in caplog.text
    assert "x" * 400 not in caplog.text


# ---- history

def _turn(i):
    return [HumanMessage(content=f"u{i}"), AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": f"c{i}"}]),
            ToolMessage(content="result", tool_call_id=f"c{i}", name="t"), AIMessage(content=f"a{i}")]


def test_history_keeps_the_last_turns_and_always_starts_on_a_customer_message():
    messages = [m for i in range(10) for m in _turn(i)]
    kept = graph.recent_turns(messages, 3)
    assert isinstance(kept[0], HumanMessage) and kept[0].content == "u7"
    assert [m.content for m in kept if isinstance(m, HumanMessage)] == ["u7", "u8", "u9"]
    assert not isinstance(kept[0], ToolMessage)  # a tool result is never left without the call that asked for it


def test_a_short_conversation_is_sent_whole():
    messages = [m for i in range(3) for m in _turn(i)]
    assert graph.recent_turns(messages, 6) == messages
    assert graph.recent_turns(messages, 0) == messages  # 0 means no cap


def test_the_model_call_carries_only_the_recent_turns(monkeypatch):
    from tests.test_agent_guardrails import ScriptedLLM, Store

    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(graph, "HISTORY_TURNS", 2)
    agent = graph.RestaurantOrderingAgent("s1", Store(), persona="waiter")
    agent.llm_with_tools = ScriptedLLM(*[AIMessage(content=f"reply {i}") for i in range(5)])
    for i in range(5):
        agent.send(f"message number {i}")
    seen = [str(m.content) for m in agent.llm_with_tools.seen[-1]]
    assert "message number 4" in seen and "message number 3" in seen
    assert "message number 0" not in seen and "message number 1" not in seen
    state = agent.graph.get_state({"configurable": {"thread_id": "s1"}})
    assert sum(isinstance(m, HumanMessage) for m in state.values["messages"]) == 5  # the full history is still kept


# ---- a claim the model cannot make

def test_saying_the_order_is_ready_before_checkout_is_caught():
    facts = g.TurnFacts(user_text="and one ORS", tool_calls=[("add_to_cart", "Added ORS")])
    for claim in ("Great, your order is ready.", "Your order is completed.", "Your order is booked."):
        assert "unbacked_order" in [v.kind for v in g.check_reply(claim, facts)], claim
    placed = g.TurnFacts(user_text="that's all", tool_calls=[("checkout", "Order placed: 1x Dolo")])
    assert g.check_reply("Great, your order is ready.", placed) == []  # true once checkout succeeded


def test_the_rate_limit_wait_is_longer_than_it_was():
    assert graph._MAX_RETRY_WAIT >= 5
