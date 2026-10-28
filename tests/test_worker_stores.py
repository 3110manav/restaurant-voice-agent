"""The worker loads the old four-persona menu index only on demand, so the hosted worker image can leave Chroma out."""
import sys


def test_legacy_menu_index_is_optional(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("SARVAM_API_KEY", "test")
    from app.voice import livekit_worker as worker

    # A missing Chroma install shows up as an ImportError; the worker then declines the call instead of crashing.
    monkeypatch.setitem(sys.modules, "app.rag.menu_store", None)
    assert worker._menu_store_for.__wrapped__("online") is None
    assert worker._menu_store_for.__wrapped__("quick_commerce") is None


def test_the_agent_name_can_be_overridden_for_local_testing(monkeypatch):
    import importlib

    from app.voice import livekit_tokens

    monkeypatch.setenv("LIVEKIT_AGENT_NAME", "sarthi-voice-dev")
    assert importlib.reload(livekit_tokens).AGENT_NAME == "sarthi-voice-dev"
    monkeypatch.delenv("LIVEKIT_AGENT_NAME")
    assert importlib.reload(livekit_tokens).AGENT_NAME == "sarthi-voice"
