"""One codebase, two speech stacks, chosen by SARTHI_SPEECH: what each setting changes, and what it doesn't."""
from types import SimpleNamespace

import pytest

from app.voice import stack, stt, tts


def test_groq_is_the_default_and_a_typo_fails_loudly(monkeypatch):
    monkeypatch.delenv("SARTHI_SPEECH", raising=False)
    assert stack.speech_stack() == "groq" and not stack.uses_sarvam()
    monkeypatch.setenv("SARTHI_SPEECH", " Sarvam ")
    assert stack.speech_stack() == "sarvam" and stack.uses_sarvam()
    monkeypatch.setenv("SARTHI_SPEECH", "sarvm")
    with pytest.raises(ValueError, match="SARTHI_SPEECH"):
        stack.speech_stack()


def test_groq_stack_hears_with_whisper_in_the_conversations_language(monkeypatch):
    monkeypatch.setenv("SARTHI_SPEECH", "groq")
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return " one naan \n"

    monkeypatch.setattr(stt, "_groq", lambda: SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))))
    assert stt.transcribe_bytes(b"x", "clip.webm", language="en") == "one naan"
    assert seen["model"] == "whisper-large-v3-turbo" and seen["language"] == "en"
    seen.clear()
    stt.transcribe_bytes(b"x", "clip.webm")
    assert "language" not in seen  # no language given: Whisper detects it


def test_sarvam_stack_never_touches_groq_to_hear(monkeypatch):
    monkeypatch.setenv("SARTHI_SPEECH", "sarvam")
    monkeypatch.setattr(stt, "_groq", lambda: pytest.fail("the Sarvam stack must not call Groq"))
    monkeypatch.setattr(
        stt, "_sarvam", lambda: SimpleNamespace(speech_to_text=SimpleNamespace(transcribe=lambda **k: SimpleNamespace(transcript="x")))
    )
    assert stt.transcribe_bytes(b"x") == "x"


def test_speaking_english_is_orpheus_on_groq_and_bulbul_on_sarvam(monkeypatch):
    monkeypatch.setattr(tts, "_synthesize_english", lambda text, voice="": b"orpheus")
    monkeypatch.setattr(tts, "synthesize_sarvam", lambda text, persona, rate=None: b"bulbul")
    monkeypatch.setenv("SARTHI_SPEECH", "groq")
    assert tts.synthesize("Sure.", "waiter", "en") == b"orpheus"
    assert tts.synthesize("ठीक है", "waiter", "hi") == b"bulbul"  # Hindi is Bulbul on both
    monkeypatch.setenv("SARTHI_SPEECH", "sarvam")
    assert tts.synthesize("Sure.", "waiter", "en") == b"bulbul"


def test_a_deployment_needs_only_the_key_of_its_own_stack(monkeypatch):
    # Importing the speech modules must not build either client (and so not need either key).
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    import importlib

    importlib.reload(stt)
    importlib.reload(tts)


@pytest.fixture
def livekit_stack(monkeypatch):
    pytest.importorskip("livekit.agents")
    pytest.importorskip("livekit.plugins.sarvam")
    pytest.importorskip("livekit.plugins.groq")
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("SARVAM_API_KEY", "test")
    from app.voice import livekit_stack

    return livekit_stack


def test_realtime_calls_pick_the_ears_by_stack(monkeypatch, livekit_stack):
    from livekit.plugins import groq, sarvam

    monkeypatch.setenv("SARTHI_SPEECH", "groq")
    assert isinstance(livekit_stack.build_stt("hi"), groq.STT)
    assert isinstance(livekit_stack.build_stt(None), groq.STT)  # a phone call: detects the language itself
    monkeypatch.setenv("SARTHI_SPEECH", "sarvam")
    assert isinstance(livekit_stack.build_stt("hi"), sarvam.STT)


def test_realtime_calls_pick_the_voice_by_stack(monkeypatch, livekit_stack):
    monkeypatch.setenv("SARTHI_SPEECH", "groq")
    assert livekit_stack.build_tts("waiter", "en")._wrapped_tts._sarvam_only is False
    monkeypatch.setenv("SARTHI_SPEECH", "sarvam")
    assert livekit_stack.build_tts("waiter", "en")._wrapped_tts._sarvam_only is True


def test_health_says_which_stack_a_deployment_runs(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    from fastapi.testclient import TestClient

    from app import main

    monkeypatch.setenv("SARTHI_SPEECH", "sarvam")
    assert TestClient(main.app).get("/health").json() == {"status": "ok", "speech": "sarvam"}
